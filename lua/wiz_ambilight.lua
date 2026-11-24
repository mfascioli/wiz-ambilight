--[[
    wiz_ambilight.lua - Ambilight-style color extraction for mpv.

    This script never talks to the lights itself. It grabs the current video
    frame with mpv's "screenshot-raw" command, computes a handful of zone
    colors (edges, thirds and the whole frame) and writes them as a tiny JSON
    file. mpv_ambilight.py (or any other tool) reads that file and sends the
    colors to the WiZ bulbs over UDP.

    The script does nothing at all until it is activated, either by setting
    the WIZ_AMBILIGHT_CONFIG environment variable to a JSON object (this is
    what mpv_ambilight.py does):

        WIZ_AMBILIGHT_CONFIG='{"path":"/run/user/1000/wiz-ambilight/state.json","fps":10}' mpv movie.mkv --script=lua/wiz_ambilight.lua

    or with --script-opts:

        --script-opts=wiz_ambilight-autostart=yes,wiz_ambilight-output=/path/state.json

    or, for an already running mpv (script installed in ~/.config/mpv/scripts),
    by creating "$XDG_RUNTIME_DIR/wiz-ambilight/control.json". This makes it
    safe to install globally.

    Options (--script-opts):
        wiz_ambilight-autostart=yes     start capturing right away
        wiz_ambilight-output=PATH       where to write the JSON state
        wiz_ambilight-fps=10            captures per second (1-30)
        wiz_ambilight-edge=0.14         edge band size, fraction of the frame
        wiz_ambilight-bar-luma=16       luma below which letterbox bars are cropped
        wiz_ambilight-sampling=auto     auto, lean, balanced, quality or manual
        wiz_ambilight-grid=80           sample columns (24-240; 0 = auto)
        wiz_ambilight-sample=1          average an NxN block per cell (1-4; 0 = auto)
        wiz_ambilight-capture=scaled    scaled (window size) or video (source)
        wiz_ambilight-react=color       color, equalize, cut, motion, duotone,
                                        beat or vu (audio modes add a dynamic
                                        EQ-band analyser only while active)

    JSON written on every capture:
        {"active":true,"t":12.345,"paused":false,"eof":false,
         "w":1920,"h":1080,"rect":[x0,y0,x1,y1],
         "zones":{"all":[r,g,b],"left":[...],"right":[...],"top":[...],
                  "bottom":[...],"thirds":[ [...], [...], [...] ]}}

    In beat and vu the snapshot also carries the analyser levels:
        "audio":{"rms":-24.1,"peak":-18.0,"crest":6.1,"zcr":0.12,
                 "l":-24.1,"r":-25.0}
]]

local utils = require("mp.utils")
local msg = require("mp.msg")

local CONTROL_PATH = (os.getenv("XDG_RUNTIME_DIR") or "/tmp")
    .. "/wiz-ambilight/control.json"
local ENV_CONFIG = "WIZ_AMBILIGHT_CONFIG"
local ENV_CONFIG_LEGACY = "WIZ_AMIBLIGHT_CONFIG" -- typo kept for old installs

local S = {
    active = false,
    from_control = false,
    path = nil,
    fps = 10,
    edge = 0.14,
    bar_luma = 16.0,
    grid_x = 80,
    sample = 1,
    capture = "video",
    sampling = "manual",
    react = "color",
    bands = nil,
    eq = nil,
    audio_warned = false,
    fps_now = 10,
    next_due = 0,
    capture_w = 0,
    capture_h = 0,
    capture_fallback = false,
    last_warned_fallback = false,
    timer = nil,
    control_timer = nil,
    last_write = 0,
    last_result = nil,
    failures = 0,
    cooldown_until = 0,
    paused = false,
    ready_at = 0,
}

local function write_json(path, text)
    if not path then
        return false
    end
    local tmp = path .. ".tmp"
    local f = io.open(tmp, "w")
    if not f then
        return false
    end
    local ok = f:write(text)
    f:close()
    if not ok then
        os.remove(tmp)
        return false
    end
    if not os.rename(tmp, path) then
        os.remove(tmp)
        return false
    end
    return true
end

local function ensure_parent_dir(path)
    local dir = path:match("^(.*)/[^/]+$")
    if dir and dir ~= "" and not utils.file_info(dir) then
        utils.subprocess({
            args = { "mkdir", "-p", dir },
            playback_only = false,
            capture_stdout = true,
            capture_stderr = true,
        })
    end
end

local function round(x)
    return math.floor(x + 0.5)
end

local function color_json(c)
    return string.format("[%d,%d,%d]", round(c[1]), round(c[2]), round(c[3]))
end

local function is_audio_react(name)
    return name == "beat" or name == "vu"
end

-- Audio changes faster than video. The state file therefore beats at 30 Hz
-- while an audio reaction is selected; analyze() still obeys the sampling
-- profile, so these extra ticks only re-read the analyser metadata and reuse
-- the cached zones.
local AUDIO_FPS = 30.0

-- The analyser is a chain of labelled libavfilter filters. astats injects the
-- RMS/peak metadata, the band graph filters a copy of the mix into the
-- configured EQ bands for the meter, and anull keeps the chain valid while the
-- labels are removed one by one. The shaped graph merges the untouched mix back
-- and selects it, so the audio is transparent; the acrossover fallback
-- recombines its slices and adds a small all-pass phase shift.
local FILTER_STATS = "@wizstats:lavfi=[astats=metadata=1:reset=1]"
local FILTER_TAIL = "@wiztail:lavfi=[anull]"
-- The band graph only needs per-channel RMS and peak. Measuring every astats
-- parameter on 2N+2 channels is what made a 16-band EQ cost more than half a
-- core; the two fields below cut that by an order of magnitude. The overall
-- level still comes from wizstats, and the shaped graph also exposes the
-- untouched pair for builds where wizstats is empty.
local ASTATS_BANDS = "astats=metadata=1:reset=1"
    .. ":measure_perchannel=Peak_level+RMS_level:measure_overall=none"
-- Older ffmpeg builds do not know measure_perchannel; retry with the plain
-- filter if the lean graph is rejected.
local ASTATS_BANDS_LEGACY = "astats=metadata=1:reset=1"
-- Without an explicit band plan, keep the classic five bands. The panel and
-- CLI always send their own band plan.
local DEFAULT_SPLITS = { 60, 250, 800, 2500 }

local function sanitize_bands(value)
    if type(value) ~= "table" then
        return nil
    end
    local out = {}
    for _, item in ipairs(value) do
        local hz = tonumber(item)
        if hz and hz > 10 and hz < 22050 then
            out[#out + 1] = hz
        end
    end
    if #out < 1 then
        return nil
    end
    table.sort(out)
    return out
end

local function bands_equal(first, second)
    if first == nil or second == nil then
        return first == second
    end
    if #first ~= #second then
        return false
    end
    for index = 1, #first do
        if math.abs(first[index] - second[index]) > 0.01 then
            return false
        end
    end
    return true
end

local function band_splits()
    return sanitize_bands(S.bands) or DEFAULT_SPLITS
end

-- The panel and CLI send the full band plan. Each band carries the shape that
-- isolates it from the rest of the mix; the Lua side only needs the fields
-- that change the filter graph, because gain, lamp and solo are applied by the
-- Python layer. Older configs without `eq` keep the crossover fallback.
local EQ_TYPES = {
    bell = true,
    bandpass = true,
    lowpass = true,
    highpass = true,
    notch = true,
    flat = true,
}

local function sanitize_eq(value)
    if type(value) ~= "table" then
        return nil
    end
    local out = {}
    for _, item in ipairs(value) do
        if type(item) == "table" then
            local freq = tonumber(item.freq)
            if freq and freq > 10 and freq < 22050 then
                local kind = tostring(item.type or "bell"):lower():gsub("[%s%-]", "")
                if not EQ_TYPES[kind] then
                    kind = "bell"
                end
                local q = tonumber(item.q) or 1.4
                local slope = tonumber(item.slope) or 24
                if slope >= 36 then
                    slope = 48
                elseif slope >= 18 then
                    slope = 24
                else
                    slope = 12
                end
                out[#out + 1] = {
                    freq = freq,
                    type = kind,
                    q = math.max(0.1, math.min(18.0, q)),
                    slope = slope,
                }
            end
        end
    end
    if #out < 1 then
        return nil
    end
    table.sort(out, function(first, second)
        return first.freq < second.freq
    end)
    return out
end

local function eq_equal(first, second)
    if first == nil or second == nil then
        return first == second
    end
    if #first ~= #second then
        return false
    end
    for index = 1, #first do
        local a, b = first[index], second[index]
        if a.type ~= b.type
            or math.abs(a.freq - b.freq) > 0.01
            or math.abs(a.q - b.q) > 0.01
            or a.slope ~= b.slope
        then
            return false
        end
    end
    return true
end

local function cut_chain(kind, freq, slope)
    local stages = slope >= 48 and 4 or (slope >= 24 and 2 or 1)
    local parts = {}
    for _ = 1, stages do
        parts[#parts + 1] = kind .. "=f=" .. freq .. ":poles=2"
    end
    return table.concat(parts, ",")
end

local function band_chain(band)
    local freq = string.format("%.2f", band.freq)
    local q = string.format("%.2f", band.q)
    if band.type == "lowpass" then
        return cut_chain("lowpass", freq, band.slope)
    elseif band.type == "highpass" then
        return cut_chain("highpass", freq, band.slope)
    elseif band.type == "notch" then
        return "bandreject=f=" .. freq .. ":width_type=q:w=" .. q
    elseif band.type == "flat" then
        return "anull"
    elseif band.type == "bandpass" then
        -- A steeper band than the bell: Q sets the edges, slope sets how hard
        -- the mix falls away outside them.
        local edge = 2.0 ^ (0.5 / math.max(0.4, band.q))
        local low = string.format("%.2f", band.freq / edge)
        local high = string.format("%.2f", band.freq * edge)
        return cut_chain("highpass", low, band.slope)
            .. "," .. cut_chain("lowpass", high, band.slope)
    end
    return "bandpass=f=" .. freq .. ":width_type=q:w=" .. q
end

local function eq_filter(eq, astats)
    local count = #eq
    -- The analysis filters run on a copy of the mix. The original is merged
    -- back as the last two channels and the pan selects only those, so the
    -- audible signal is untouched while `astats` sees every shaped band.
    local parts = { "aformat=channel_layouts=stereo,asplit=2[main][mon]" }
    local labels = {}
    for index = 0, count - 1 do
        labels[#labels + 1] = "[m" .. index .. "]"
    end
    parts[#parts + 1] = "[mon]asplit=" .. count .. table.concat(labels)
    local outs = {}
    for index = 0, count - 1 do
        outs[#outs + 1] = "[f" .. index .. "]"
        parts[#parts + 1] = "[m" .. index .. "]" .. band_chain(eq[index + 1])
            .. "[f" .. index .. "]"
    end
    parts[#parts + 1] = table.concat(outs)
        .. "amerge=inputs=" .. count .. "[filtered]"
    parts[#parts + 1] = "[filtered][main]amerge=inputs=2[all]"
    parts[#parts + 1] = "[all]" .. astats .. "[stats]"
    parts[#parts + 1] = "[stats]pan=stereo|c0=c" .. (count * 2)
        .. "|c1=c" .. (count * 2 + 1)
    return "@wizbands:lavfi=[" .. table.concat(parts, ";") .. "]"
end

local function crossover_filter(astats)
    local splits = band_splits()
    local count = #splits + 1
    local frequencies = {}
    for _, hz in ipairs(splits) do
        frequencies[#frequencies + 1] = string.format("%.2f", hz)
    end
    local labels = {}
    local left = {}
    local right = {}
    for index = 0, count - 1 do
        labels[#labels + 1] = "[b" .. index .. "]"
        left[#left + 1] = "c" .. (index * 2)
        right[#right + 1] = "c" .. (index * 2 + 1)
    end
    return "@wizbands:lavfi=[aformat=channel_layouts=stereo,"
        .. "acrossover=split=" .. table.concat(frequencies, " ")
        .. table.concat(labels) .. ";"
        .. table.concat(labels) .. "amerge=inputs=" .. count .. ","
        .. astats .. ","
        .. "pan=stereo|c0=" .. table.concat(left, "+")
        .. "|c1=" .. table.concat(right, "+") .. "]"
end

local function band_filter(astats)
    if S.eq and #S.eq > 0 then
        return eq_filter(S.eq, astats)
    end
    return crossover_filter(astats)
end

local function audio_stats_off()
    for _, name in ipairs({ "@wizbands", "@wizstats", "@wiztail" }) do
        local af = mp.get_property("af") or ""
        if af:find(name, 1, true) then
            mp.commandv("af", "remove", name)
        end
    end
end

local function audio_stats_on()
    local af = mp.get_property("af") or ""
    if af:find("@wizstats", 1, true) and af:find("@wizbands", 1, true) then
        return true
    end
    if af:find("@wizstats", 1, true) or af:find("@wizbands", 1, true)
        or af:find("@wiztail", 1, true)
    then
        audio_stats_off()
    end
    local added = mp.commandv(
        "af",
        "add",
        FILTER_STATS .. "," .. band_filter(ASTATS_BANDS) .. "," .. FILTER_TAIL
    )
    if added ~= false then
        return added
    end
    -- The build rejected measure_perchannel; fall back to the full filter.
    return mp.commandv(
        "af",
        "add",
        FILTER_STATS
            .. ","
            .. band_filter(ASTATS_BANDS_LEGACY)
            .. ","
            .. FILTER_TAIL
    )
end

local function sync_audio_filter()
    if S.active and is_audio_react(S.react) then
        if not audio_stats_on() and not S.audio_warned then
            S.audio_warned = true
            msg.warn("audio analyser unavailable; beat and VU will hold steady")
        end
    else
        audio_stats_off()
    end
end

-- Format a dBFS number as JSON. astats reports -inf for digital silence and
-- Lua cannot serialise NaN/inf, so those become null and the panel treats
-- them as silence.
local function json_number(value)
    local n = tonumber(value)
    if not n or n ~= n or n == math.huge or n == -math.huge then
        return "null"
    end
    return string.format("%.2f", n)
end

local function audio_json()
    if not is_audio_react(S.react) then
        return nil
    end
    local meta = mp.get_property_native("af-metadata/wizstats")
    if type(meta) ~= "table" then
        meta = {}
    end
    local function meta_field(source, name, fallback)
        local value = tonumber(source[name])
        if value then
            return value
        end
        return fallback
    end
    local function field(name, fallback)
        return meta_field(meta, name, fallback)
    end
    local rms = field("lavfi.astats.Overall.RMS_level")
    local peak = field(
        "lavfi.astats.Overall.Peak_level",
        field("lavfi.astats.1.Peak_level")
    )
    local zcr = field(
        "lavfi.astats.Overall.Zero_crossings_rate",
        field("lavfi.astats.1.Zero_crossings_rate")
    )
    local left = field("lavfi.astats.1.RMS_level", rms)
    local right = field("lavfi.astats.2.RMS_level", left)
    -- The band graph exposes two channels per band. Take the louder channel
    -- per band so a one-sided mix still shows. Peak travels beside RMS: the
    -- meter uses both so attacks are not averaged away, and the beat detector
    -- can see a transient in its band.
    local band_meta = mp.get_property_native("af-metadata/wizbands")
    local band_count = S.eq and #S.eq or (#band_splits() + 1)
    local band_rms = {}
    local band_peaks = {}
    if type(band_meta) == "table" then
        local function band_stat(index, suffix)
            local band_left = tonumber(
                band_meta["lavfi.astats." .. (index * 2 + 1) .. "." .. suffix]
            )
            local band_right = tonumber(
                band_meta["lavfi.astats." .. (index * 2 + 2) .. "." .. suffix]
            )
            local value = band_left
            if band_right ~= nil and (value == nil or band_right > value) then
                value = band_right
            end
            return value
        end
        for index = 0, band_count - 1 do
            band_rms[#band_rms + 1] = band_stat(index, "RMS_level")
            band_peaks[#band_peaks + 1] = band_stat(index, "Peak_level")
        end
    end

    -- `af-metadata` only exposes the last astats instance on some mpv builds,
    -- so wizstats can be empty even while the bands are live. The shaped graph
    -- merges the untouched mix back as its last two channels, so read those for
    -- an exact overall level. The crossover fallback has no such pair, and its
    -- slices are the same signal, so their powers add back up instead.
    local function sum_db(values)
        local power, found = 0.0, false
        for _, db in ipairs(values) do
            if db ~= nil then
                found = true
                power = power + 10.0 ^ (db / 10.0)
            end
        end
        if not found then
            return nil
        end
        return 10.0 * math.log(power, 10)
    end
    local function main_stat(suffix)
        if not S.eq or type(band_meta) ~= "table" then
            return nil
        end
        local main_left = tonumber(
            band_meta["lavfi.astats." .. (band_count * 2 + 1) .. "." .. suffix]
        )
        local main_right = tonumber(
            band_meta["lavfi.astats." .. (band_count * 2 + 2) .. "." .. suffix]
        )
        if main_left == nil then
            return main_right
        end
        if main_right == nil then
            return main_left
        end
        return math.max(main_left, main_right)
    end
    local overall_rms = rms
        or left
        or main_stat("RMS_level")
        or sum_db(band_rms)
    local overall_peak = peak
        or main_stat("Peak_level")
        or sum_db(band_peaks)
    if overall_rms == nil and overall_peak == nil then
        return nil
    end

    local function db_array(values)
        local parts = {}
        for index = 1, band_count do
            parts[#parts + 1] = json_number(values[index])
        end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    local bands_json = ',"bands":' .. db_array(band_rms)
        .. ',"band_peaks":' .. db_array(band_peaks)

    -- Derive the crest factor from the two dBFS levels. astats also publishes
    -- a Crest_factor field, but it is scaled oddly across ffmpeg builds, while
    -- peak minus RMS is the same number in dB and always comparable.
    local crest = nil
    if overall_peak ~= nil and overall_rms ~= nil then
        crest = overall_peak - overall_rms
    end
    return ',"audio":{"rms":' .. json_number(overall_rms)
        .. ',"peak":' .. json_number(overall_peak)
        .. ',"crest":' .. json_number(crest)
        .. ',"zcr":' .. json_number(zcr)
        .. ',"l":' .. json_number(left or overall_rms)
        .. ',"r":' .. json_number(right or left or overall_rms)
        .. bands_json
        .. "}"
end

-- Write a state snapshot. `result` holds geometry and zone colors, it may be
-- nil for pauses before the first frame was captured.
local function emit(paused, eof, result, err)
    if not S.active or not S.path then
        return
    end
    local now = mp.get_time()
    S.last_write = now

    -- The capture size is the window (scaled) or the decoded frame (source),
    -- so it can stay the same across files. The video size is the property
    -- people read as "resolution" and does change when a new file loads.
    local video = mp.get_property_native("video-params") or {}
    local vw = tonumber(video.w) or 0
    local vh = tonumber(video.h) or 0

    local parts = {
        string.format(
            '{"active":true,"t":%.3f,"paused":%s,"eof":%s,"w":%d,"h":%d,"vw":%d,"vh":%d',
            now,
            tostring(paused),
            tostring(eof),
            result and result.w or 0,
            result and result.h or 0,
            vw,
            vh
        ),
    }
    -- The panel samples mpv's CPU and RSS by pid. Attach mode has no parent
    -- relationship to follow, so the pid travels in the state file itself.
    local pid = mp.get_property_native("pid")
    if type(pid) == "number" and pid > 0 then
        parts[#parts + 1] = string.format(',"pid":%d', pid)
    end
    if result and result.rect then
        parts[#parts + 1] = string.format(
            ',"rect":[%d,%d,%d,%d]',
            result.rect[1],
            result.rect[2],
            result.rect[3],
            result.rect[4]
        )
    end
    if result and result.zones then
        local z = result.zones
        parts[#parts + 1] = ',"zones":{'
            .. '"all":' .. color_json(z.all)
            .. ',"left":' .. color_json(z.left)
            .. ',"right":' .. color_json(z.right)
            .. ',"top":' .. color_json(z.top)
            .. ',"bottom":' .. color_json(z.bottom)
            .. ',"thirds":[' .. color_json(z.thirds[1])
            .. ',' .. color_json(z.thirds[2])
            .. ',' .. color_json(z.thirds[3]) .. "]"
            .. "}"
        parts[#parts + 1] = string.format(
            ',"capture":%q,"grid":%d,"fps":%.2f',
            result.capture or "video",
            result.grid or 0,
            S.fps_now or S.fps
        )
    end
    local audio = audio_json()
    if audio then
        parts[#parts + 1] = audio
    end
    if err then
        parts[#parts + 1] = ',"error":' .. string.format("%q", err)
    end
    parts[#parts + 1] = "}"

    if not write_json(S.path, table.concat(parts)) then
        msg.verbose("failed to write " .. tostring(S.path))
    end
end

-- Pick a grid, block size and fps cap from the size of the frame we actually
-- captured. A 1080p window keeps the original 80x1 grid and the style's own
-- rate, so `raw` stays at 24 fps; a 4K fullscreen capture uses more columns
-- but far fewer frames, which is what keeps the copy cost flat on a 32" TV.
local function auto_sampling(w, h)
    if h <= 1200 then
        return 80, 1, 30.0
    elseif h <= 1600 then
        return 96, 2, 12.0
    end
    return 112, 2, 8.0
end

-- `scaled` is the window size and can be 2-4x smaller than a 4K source. Older
-- mpv builds or VO drivers may reject the flag, so fall back to the source
-- frame once instead of failing every capture.
local function grab()
    local flag = S.capture
    local res, err = mp.command_native({ "screenshot-raw", flag })
    if (type(res) ~= "table" or type(res.data) ~= "string") and flag ~= "video" then
        if not S.capture_fallback then
            S.capture_fallback = true
            msg.warn("scaled capture is unavailable; using the source frame instead")
        end
        S.capture = "video"
        res, err = mp.command_native({ "screenshot-raw", "video" })
    end
    return res, err
end

-- Grab the current video frame and compute zone averages.
-- Returns a table {w=,h=,rect=,zones=} or nil, error message.
local function analyze()
    local res, err = grab()
    if type(res) ~= "table" then
        return nil, err or "screenshot-raw failed"
    end
    local data = res.data
    if type(data) ~= "string" then
        return nil, "screenshot-raw returned no pixel data (unsupported vo?)"
    end

    local w = res.w or 0
    local h = res.h or 0
    if w < 4 or h < 4 then
        return nil, "video frame too small"
    end

    -- mpv hands us packed 8 bit BGRA/RGBA ("bgr0"/"rgb0") or BGR/RGB 24.
    local fmt = res.format or "bgr0"
    local bpp = 4
    if fmt == "bgr24" or fmt == "rgb24" then
        bpp = 3
    end
    local stride = res.stride
    if not stride or stride < w * bpp then
        stride = w * bpp
    end
    local is_rgb = (fmt == "rgb0" or fmt == "rgb24")

    local grid, block
    if S.sampling == "auto" or S.grid_x <= 0 then
        local auto_grid, auto_block, auto_fps = auto_sampling(w, h)
        grid = S.grid_x > 0 and S.grid_x or auto_grid
        block = S.sample > 0 and S.sample or auto_block
        S.fps_now = math.min(S.fps, auto_fps)
    else
        grid = S.grid_x
        block = S.sample
        S.fps_now = S.fps
    end
    block = math.max(1, math.min(4, block))
    S.capture_w, S.capture_h = w, h

    -- Sample a fixed size grid so cost does not depend on the video resolution.
    local gx = math.min(grid, w)
    local gy = math.min(math.max(2, math.floor(grid * h / w + 0.5)), h)
    local stepx = math.max(1, math.floor(w / gx))
    local stepy = math.max(1, math.floor(h / gy))
    local nx = math.floor((w - 1) / stepx) + 1
    local ny = math.floor((h - 1) / stepy) + 1

    local R, G, B = {}, {}, {}
    local row_luma, col_luma = {}, {}
    local idx = 1
    local half = math.floor((block - 1) / 2)

    for yy = 0, ny - 1 do
        local y = math.min(h - 1, yy * stepy + math.floor(stepy / 2))
        local y0b = math.max(0, y - half)
        local y1b = math.min(h - 1, y0b + block - 1)
        if y1b - y0b + 1 < block then
            y0b = math.max(0, y1b - block + 1)
        end
        local sum = 0
        for xx = 0, nx - 1 do
            local x = math.min(w - 1, xx * stepx + math.floor(stepx / 2))
            local r0, g0, b0
            if block == 1 then
                local off = y * stride + x * bpp
                local c1, c2, c3 = data:byte(off + 1, off + 3)
                if is_rgb then
                    r0, g0, b0 = c1, c2, c3
                else
                    b0, g0, r0 = c1, c2, c3
                end
            else
                local x0b = math.max(0, x - half)
                local x1b = math.min(w - 1, x0b + block - 1)
                if x1b - x0b + 1 < block then
                    x0b = math.max(0, x1b - block + 1)
                end
                local sr, sg, sb, n = 0, 0, 0, 0
                for sy = y0b, y1b do
                    local base = sy * stride
                    for sx = x0b, x1b do
                        local off = base + sx * bpp
                        local c1, c2, c3 = data:byte(off + 1, off + 3)
                        if is_rgb then
                            sr, sg, sb = sr + c1, sg + c2, sb + c3
                        else
                            sr, sg, sb = sr + c3, sg + c2, sb + c1
                        end
                        n = n + 1
                    end
                end
                r0, g0, b0 = sr / n, sg / n, sb / n
            end
            R[idx], G[idx], B[idx] = r0, g0, b0
            local l = 0.2126 * r0 + 0.7152 * g0 + 0.0722 * b0
            sum = sum + l
            col_luma[xx] = (col_luma[xx] or 0) + l
            idx = idx + 1
        end
        row_luma[yy] = sum / nx
    end
    for xx = 0, nx - 1 do
        col_luma[xx] = col_luma[xx] / ny
    end

    -- Crop letterbox / pillarbox bars from the border. We only trim from the
    -- outside in, and never more than 30% per side, so dark scenes are safe.
    local max_trim_y = math.max(1, math.floor(ny * 0.30))
    local max_trim_x = math.max(1, math.floor(nx * 0.30))
    local thr = S.bar_luma
    local y0, y1, x0, x1 = 0, ny - 1, 0, nx - 1
    if thr > 0 then
        while y0 < max_trim_y and row_luma[y0] < thr do
            y0 = y0 + 1
        end
        while y1 > ny - 1 - max_trim_y and row_luma[y1] < thr do
            y1 = y1 - 1
        end
        while x0 < max_trim_x and col_luma[x0] < thr do
            x0 = x0 + 1
        end
        while x1 > nx - 1 - max_trim_x and col_luma[x1] < thr do
            x1 = x1 - 1
        end
    end
    if y1 <= y0 then
        y0, y1 = 0, ny - 1
    end
    if x1 <= x0 then
        x0, x1 = 0, nx - 1
    end

    local function zone(xa, ya, xb, yb)
        if xb < xa then xb = xa end
        if yb < ya then yb = ya end
        local sr, sg, sb, n = 0, 0, 0, 0
        for yy = ya, yb do
            local base = yy * nx + 1
            for xx = xa, xb do
                local i = base + xx
                sr = sr + R[i]
                sg = sg + G[i]
                sb = sb + B[i]
                n = n + 1
            end
        end
        if n == 0 then
            return { 0, 0, 0 }
        end
        return { sr / n, sg / n, sb / n }
    end

    local cw = x1 - x0 + 1
    local ch = y1 - y0 + 1
    local ec = math.max(1, math.floor(cw * S.edge))
    local er = math.max(1, math.floor(ch * S.edge))
    local third = math.max(1, math.floor(cw / 3))

    local zones = {
        all = zone(x0, y0, x1, y1),
        left = zone(x0, y0, x0 + ec - 1, y1),
        right = zone(x1 - ec + 1, y0, x1, y1),
        top = zone(x0, y0, x1, y0 + er - 1),
        bottom = zone(x0, y1 - er + 1, x1, y1),
        thirds = {
            zone(x0, y0, x0 + third - 1, y1),
            zone(x0 + third, y0, x1 - third, y1),
            zone(x1 - third + 1, y0, x1, y1),
        },
    }

    return {
        w = w,
        h = h,
        rect = { x0 * stepx, y0 * stepy, math.min(w, (x1 + 1) * stepx), math.min(h, (y1 + 1) * stepy) },
        zones = zones,
        capture = S.capture == "video" and "source" or "scaled",
        grid = nx,
    }
end

local function tick()
    if not S.active or not S.path then
        return
    end
    local now = mp.get_time()

    local paused = mp.get_property_native("pause") or false
    local eof = mp.get_property_native("eof-reached") or false
    local idle = mp.get_property_native("idle-active") or false
    local has_video = mp.get_property_native("current-tracks/video") ~= nil
    local has_audio = mp.get_property_native("current-tracks/audio") ~= nil
    local vo_ready = mp.get_property_native("vo-configured") or false

    S.paused = paused

    if paused or eof or idle or not has_video or not vo_ready or now < S.ready_at then
        -- Audio modes still need fresh levels while music plays without a
        -- video track, so their heartbeat follows the capture rate instead of
        -- the slow liveness beat used for a paused or closed player.
        local audio_tick = S.active and is_audio_react(S.react) and has_audio
            and not paused and not eof and not idle
        local every = audio_tick and (1.0 / AUDIO_FPS) or 0.5
        if now - S.last_write >= every then
            emit(paused, eof or (not has_video and not has_audio), S.last_result)
        end
        return
    end

    if now < S.cooldown_until then
        return
    end

    -- A video frame is only sampled when due, but the audio meter and beat
    -- need every analyser update. Emit the cached zones at the faster audio
    -- rate and leave the picture untouched. When a frame is due, analyze()
    -- below already writes fresh audio with it, so only one write happens.
    local video_due = S.next_due <= 0 or now >= S.next_due
    if not video_due then
        local audio_tick = is_audio_react(S.react) and has_audio
        if audio_tick and S.last_result
            and now - S.last_write >= 1.0 / AUDIO_FPS
        then
            emit(false, false, S.last_result)
        end
        return
    end

    local result, err = analyze()
    if not result then
        S.failures = S.failures + 1
        if S.failures == 1 then
            msg.warn(err or "frame grab failed")
        end
        -- Back off instead of hammering a broken video output.
        S.cooldown_until = now + math.min(2.0, 0.1 * S.failures)
        if now - S.last_write >= 0.5 then
            emit(false, false, S.last_result, err)
        end
        return
    end

    S.failures = 0
    S.cooldown_until = 0
    S.next_due = now + 1.0 / math.max(1.0, S.fps_now or S.fps)
    S.last_result = result
    emit(false, false, result)
end

local function stop()
    if S.timer then
        S.timer:kill()
        S.timer = nil
    end
    if S.active and S.path then
        write_json(S.path, '{"active":false,"stopped":true}')
    end
    S.active = false
    S.last_result = nil
    S.from_control = false
    audio_stats_off()
end

local function apply_sampling(cfg, reset)
    if cfg.sampling ~= nil then
        S.sampling = tostring(cfg.sampling)
    end
    if cfg.grid_x ~= nil then
        S.grid_x = math.max(0, math.min(240, math.floor(tonumber(cfg.grid_x) or S.grid_x)))
    end
    if cfg.sample ~= nil then
        S.sample = math.max(0, math.min(4, math.floor(tonumber(cfg.sample) or S.sample)))
    end
    if cfg.capture == "scaled" or cfg.capture == "video" then
        if S.capture ~= cfg.capture then
            S.capture_fallback = false
        end
        S.capture = cfg.capture
    end
    if reset then
        S.fps_now = S.fps
        S.next_due = 0
    end
end

local function start(cfg, from_control)
    cfg = cfg or {}
    local path = cfg.path
    if not path or path == "" then
        path = mp.command_native({ "expand-path", "~~cache/wiz-ambilight/state.json" })
    end
    if type(path) ~= "string" or path == "" then
        msg.error("no output path for wiz-ambilight")
        return
    end
    ensure_parent_dir(path)

    if S.active and S.path == path then
        -- Already running with this destination, just refresh the knobs.
        S.fps = math.max(1, math.min(30, tonumber(cfg.fps) or S.fps))
        S.edge = math.max(0.02, math.min(0.45, tonumber(cfg.edge) or S.edge))
        S.bar_luma = tonumber(cfg.bar_luma) or S.bar_luma
        apply_sampling(cfg, false)
        if cfg.react ~= nil then
            S.react = tostring(cfg.react)
        end
        local next_bands = sanitize_bands(cfg.bands)
        if next_bands ~= nil and not bands_equal(S.bands, next_bands) then
            S.bands = next_bands
            audio_stats_off()
        end
        local next_eq = sanitize_eq(cfg.eq)
        if next_eq ~= nil and not eq_equal(S.eq, next_eq) then
            S.eq = next_eq
            audio_stats_off()
        end
        sync_audio_filter()
        return
    end

    stop()

    S.path = path
    S.fps = math.max(1, math.min(30, tonumber(cfg.fps) or 10))
    S.edge = math.max(0.02, math.min(0.45, tonumber(cfg.edge) or 0.14))
    S.bar_luma = tonumber(cfg.bar_luma) or 16
    if cfg.react ~= nil then
        S.react = tostring(cfg.react)
    end
    S.bands = sanitize_bands(cfg.bands)
    S.eq = sanitize_eq(cfg.eq)
    apply_sampling(cfg, true)
    S.from_control = from_control or false
    S.active = true
    S.failures = 0
    S.cooldown_until = 0
    S.last_write = 0
    S.last_result = nil
    S.timer = mp.add_periodic_timer(1.0 / math.max(S.fps, AUDIO_FPS), tick)
    sync_audio_filter()
    msg.info(string.format(
        "active: %.1f fps, %s capture, %s sampling, %s reaction -> %s",
        S.fps,
        S.capture,
        S.sampling,
        S.react,
        path
    ))
end

-- Activation from the command line -----------------------------------------

local function opt(name)
    return mp.get_opt(name)
end

-- mpv_ambilight.py passes its configuration through the environment, which
-- avoids quoting/escaping problems and does not clobber the user's own
-- --script-opts (uosc et al.).
local env_raw = os.getenv(ENV_CONFIG) or os.getenv(ENV_CONFIG_LEGACY)
local env_started = false
local launcher_instance = false
local my_name = mp.get_script_name()
if env_raw and env_raw ~= "" then
    local cfg = utils.parse_json(env_raw)
    if type(cfg) == "table" then
        -- mpv_ambilight.py loads a uniquely named copy of this script. If the
        -- script is also installed globally, only that one instance should
        -- react, or both would capture frames and fight over the state file.
        if not cfg.script or cfg.script == my_name then
            start(cfg, false)
            env_started = true
            launcher_instance = true
        end
    else
        msg.error("could not parse " .. ENV_CONFIG)
    end
end

if not env_started then
    local autostart = opt("autostart")
    if autostart == "yes" or autostart == "true" or autostart == "1" then
        start({
            path = opt("output"),
            fps = opt("fps"),
            edge = opt("edge"),
            bar_luma = opt("bar-luma"),
            sampling = opt("sampling"),
            grid_x = opt("grid"),
            sample = opt("sample"),
            capture = opt("capture"),
            react = opt("react"),
        }, false)
    end
end

-- Activation while mpv is already running ----------------------------------

if not launcher_instance then
    S.control_timer = mp.add_periodic_timer(1.0, function()
        local info = utils.file_info(CONTROL_PATH)
        if not info or math.abs(os.time() - info.mtime) > 6 then
            if S.active and S.from_control then
                msg.info("control file gone, stopping")
                stop()
            end
            return
        end
        local f = io.open(CONTROL_PATH, "r")
        if not f then
            return
        end
        local text = f:read("*a")
        f:close()
        local cfg = utils.parse_json(text or "")
        local target = type(cfg) == "table" and cfg.script or nil
        if type(cfg) == "table" and cfg.enabled and cfg.path
            and (not target or target == my_name) then
            -- Refresh every second while attached: the panel rewrites this
            -- file when the sampling profile or style changes, and mpv stays
            -- open across those restarts.
            if not S.active or S.path ~= cfg.path or S.from_control then
                start(cfg, true)
            end
        elseif S.active and S.from_control then
            stop()
        end
    end)
end

mp.register_event("file-loaded", function()
    S.last_result = nil
    S.ready_at = mp.get_time() + 0.25
    -- The filter list survives a file change on most builds, but reloading it
    -- here covers a track switch and costs nothing when it is already present.
    sync_audio_filter()
end)

mp.register_event("shutdown", function()
    stop()
end)
