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
                                        beat or vu (audio modes add a pass-through
                                        analyser only while active)

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

-- The analyser is a pair of labelled libavfilter filters. astats injects the
-- RMS/peak metadata, anull keeps the chain valid when astats is removed first.
-- Both are pass-through: the samples reaching the audio output are untouched.
local FILTER_STATS = "@wizstats:lavfi=[astats=metadata=1:reset=1]"
local FILTER_TAIL = "@wiztail:lavfi=[anull]"

local function audio_stats_on()
    local af = mp.get_property("af") or ""
    if af:find("@wizstats", 1, true) then
        return true
    end
    return mp.commandv("af", "add", FILTER_STATS .. "," .. FILTER_TAIL)
end

local function audio_stats_off()
    local af = mp.get_property("af") or ""
    if af:find("@wizstats", 1, true) then
        mp.commandv("af", "remove", "@wizstats")
    end
    af = mp.get_property("af") or ""
    if af:find("@wiztail", 1, true) then
        mp.commandv("af", "remove", "@wiztail")
    end
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
        return nil
    end
    local function field(name, fallback)
        local value = tonumber(meta[name])
        if value then
            return value
        end
        return fallback
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
    if rms == nil and left == nil then
        return nil
    end
    -- Derive the crest factor from the two dBFS levels. astats also publishes
    -- a Crest_factor field, but it is scaled oddly across ffmpeg builds, while
    -- peak minus RMS is the same number in dB and always comparable.
    local crest = nil
    if peak ~= nil then
        crest = peak - (rms or left)
    end
    return ',"audio":{"rms":' .. json_number(rms or left)
        .. ',"peak":' .. json_number(peak)
        .. ',"crest":' .. json_number(crest)
        .. ',"zcr":' .. json_number(zcr)
        .. ',"l":' .. json_number(left)
        .. ',"r":' .. json_number(right)
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
        local every = audio_tick
            and (1.0 / math.max(1.0, S.fps_now or S.fps))
            or 0.5
        if now - S.last_write >= every then
            emit(paused, eof or (not has_video and not has_audio), S.last_result)
        end
        return
    end

    if now < S.cooldown_until then
        return
    end

    -- The timer runs at the style's fps so a profile change takes effect
    -- without recreating it; this gate enforces the resolution-aware cap.
    if S.next_due > 0 and now < S.next_due then
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
    apply_sampling(cfg, true)
    S.from_control = from_control or false
    S.active = true
    S.failures = 0
    S.cooldown_until = 0
    S.last_write = 0
    S.last_result = nil
    S.timer = mp.add_periodic_timer(1.0 / S.fps, tick)
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
