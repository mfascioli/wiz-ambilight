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

    JSON written on every capture:
        {"active":true,"t":12.345,"paused":false,"eof":false,
         "w":1920,"h":1080,"rect":[x0,y0,x1,y1],
         "zones":{"all":[r,g,b],"left":[...],"right":[...],"top":[...],
                  "bottom":[...],"thirds":[ [...], [...], [...] ]}}
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

-- Write a state snapshot. `result` holds geometry and zone colors, it may be
-- nil for pauses before the first frame was captured.
local function emit(paused, eof, result, err)
    if not S.active or not S.path then
        return
    end
    local now = mp.get_time()
    S.last_write = now

    local parts = {
        string.format(
            '{"active":true,"t":%.3f,"paused":%s,"eof":%s,"w":%d,"h":%d',
            now,
            tostring(paused),
            tostring(eof),
            result and result.w or 0,
            result and result.h or 0
        ),
    }
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
    end
    if err then
        parts[#parts + 1] = ',"error":' .. string.format("%q", err)
    end
    parts[#parts + 1] = "}"

    if not write_json(S.path, table.concat(parts)) then
        msg.verbose("failed to write " .. tostring(S.path))
    end
end

-- Grab the current video frame and compute zone averages.
-- Returns a table {w=,h=,rect=,zones=} or nil, error message.
local function analyze()
    local res, err = mp.command_native({ "screenshot-raw", "video" })
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

    -- Sample a fixed size grid so cost does not depend on the video resolution.
    local gx = math.min(S.grid_x, w)
    local gy = math.min(math.max(2, math.floor(S.grid_x * h / w + 0.5)), h)
    local stepx = math.max(1, math.floor(w / gx))
    local stepy = math.max(1, math.floor(h / gy))
    local nx = math.floor((w - 1) / stepx) + 1
    local ny = math.floor((h - 1) / stepy) + 1

    local R, G, B = {}, {}, {}
    local row_luma, col_luma = {}, {}
    local idx = 1

    for yy = 0, ny - 1 do
        local y = math.min(h - 1, yy * stepy + math.floor(stepy / 2))
        local row_off = y * stride
        local sum = 0
        for xx = 0, nx - 1 do
            local x = math.min(w - 1, xx * stepx + math.floor(stepx / 2))
            local off = row_off + x * bpp
            local c1, c2, c3 = data:byte(off + 1, off + 3)
            local r0, g0, b0
            if is_rgb then
                r0, g0, b0 = c1, c2, c3
            else
                b0, g0, r0 = c1, c2, c3
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
    local vo_ready = mp.get_property_native("vo-configured") or false

    S.paused = paused

    if paused or eof or idle or not has_video or not vo_ready or now < S.ready_at then
        -- Keep a slow heartbeat so the daemon knows mpv is alive but idle.
        if now - S.last_write >= 0.5 then
            emit(paused, eof or not has_video, S.last_result)
        end
        return
    end

    if now < S.cooldown_until then
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
        return
    end

    stop()

    S.path = path
    S.fps = math.max(1, math.min(30, tonumber(cfg.fps) or 10))
    S.edge = math.max(0.02, math.min(0.45, tonumber(cfg.edge) or 0.14))
    S.bar_luma = tonumber(cfg.bar_luma) or 16
    S.from_control = from_control or false
    S.active = true
    S.failures = 0
    S.cooldown_until = 0
    S.last_write = 0
    S.last_result = nil
    S.timer = mp.add_periodic_timer(1.0 / S.fps, tick)
    msg.info(string.format("active: %.1f fps -> %s", S.fps, path))
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
            if not S.active or S.path ~= cfg.path then
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
end)

mp.register_event("shutdown", function()
    stop()
end)
