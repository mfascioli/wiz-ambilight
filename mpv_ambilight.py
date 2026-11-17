#!/usr/bin/env python3
"""
mpv_ambilight.py - sync WiZ lights with whatever mpv is playing.

It works like a tiny DIY Ambilight: mpv hands us the current video frame
(through a small Lua script), we compute the dominant colors of the edges and
send them to the bulbs over UDP. No extra Python packages are needed.

Quick start:

    ./mpv_ambilight.py movie.mkv

That launches mpv with the right script, auto-discovers your WiZ lights and
maps the first bulb to the left edge of the picture, the second one to the
right edge, and so on.

Other examples:

    # pick the lights yourself
    ./mpv_ambilight.py --lights 192.168.1.5,192.168.1.7 movie.mkv

    # both bulbs follow the whole picture
    ./mpv_ambilight.py --layout all movie.mkv

    # a calmer, dimmer look for a dark room
    ./mpv_ambilight.py --style cinema movie.mkv

    # pass anything through to mpv after a bare "--"
    ./mpv_ambilight.py --lights 192.168.1.5 movie.mkv -- --fullscreen --sub-file=es.srt

    # sync a running mpv: install the Lua script once, then leave this running
    ./mpv_ambilight.py --install-script
    ./mpv_ambilight.py --attach

    # list the bulbs on the network (model, firmware, state)
    ./mpv_ambilight.py --discover
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.3.0"
DEFAULT_PORT = 38899
ZONE_NAMES = {"all", "left", "right", "top", "bottom", "t1", "t2", "t3"}

# Common WiZ scene ids. Firmware varies, so unknown ids are still accepted by
# the CLI and the panel.
WIZ_SCENES = {
    1: "Ocean",
    2: "Romance",
    3: "Sunset",
    4: "Party",
    5: "Fireplace",
    6: "Cozy",
    7: "Forest",
    8: "Pastel colors",
    9: "Wake up",
    10: "Bedtime",
    11: "Warm white",
    12: "Daylight",
    13: "Cool white",
    14: "Night light",
    15: "Focus",
    16: "Relax",
    17: "True colors",
    18: "TV time",
    19: "Plant growth",
    20: "Spring",
    21: "Summer",
    22: "Fall",
    23: "Winter",
    24: "Diwali",
    25: "Ramadan",
    26: "Halloween",
    27: "Christmas",
    28: "New Year",
    29: "Easter",
    30: "Birthday",
    31: "Golden white",
    32: "Pulse",
}


def rgb_to_hex(rgb) -> str:
    channels = [max(0, min(255, int(round(v)))) for v in rgb]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def hex_to_rgb(value):
    text = str(value).strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise ValueError("expected a hex color like #ff8800")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


HERE = Path(__file__).resolve().parent
LUA_SCRIPT = HERE / "lua" / "wiz_ambilight.lua"
SCRIPT_NAME = "wiz_ambilight"


# --------------------------------------------------------------------------- #
# WiZ light I/O
# --------------------------------------------------------------------------- #


class WizSender:
    """Fire-and-forget UDP sender for WiZ bulbs.

    Steady-state color updates should not wait for a reply: the bulbs are
    perfectly happy with one-way datagrams and waiting for each ACK would cap
    us at ~10 updates per second with extra latency.
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        dry_run: bool = False,
        refresh: float = 2.0,
    ):
        self.port = port
        self.dry_run = dry_run
        self.refresh = max(0.0, refresh)
        self._seq = 0
        self._last = {}
        self._last_time = {}
        self._warned = set()
        self._sock = None
        if not dry_run:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except OSError:
                pass

    def _send(self, ip: str, method: str, params: dict) -> bool:
        self._seq = (self._seq + 1) & 0xFFFF
        payload = json.dumps(
            {"id": self._seq, "method": method, "params": params},
            separators=(",", ":"),
        ).encode()
        if self.dry_run:
            print(f"{ip} {method} {params}", flush=True)
            return True
        try:
            self._sock.sendto(payload, (ip, self.port))
            self._warned.discard(ip)
            return True
        except OSError as exc:
            if ip not in self._warned:
                print(f"warning: cannot send to {ip}: {exc}", file=sys.stderr)
                self._warned.add(ip)
            return False

    def set_color(self, ip: str, rgb, dimming: int) -> None:
        r, g, b = rgb
        key = (int(r), int(g), int(b), int(dimming))
        now = time.monotonic()
        # UDP is lossy: refresh an unchanged color every couple of seconds so a
        # dropped packet can never leave a bulb stuck on an old frame.
        if (
            self._last.get(ip) == key
            and now - self._last_time.get(ip, 0.0) < self.refresh
        ):
            return
        self._last_time[ip] = now
        sent = self._send(
            ip,
            "setPilot",
            {
                "r": int(r),
                "g": int(g),
                "b": int(b),
                "dimming": int(dimming),
                "state": True,
            },
        )
        if sent:
            self._last[ip] = key

    def set_power(self, ip: str, on: bool) -> None:
        self._last.pop(ip, None)
        self._send(ip, "setState", {"state": bool(on)})

    def set_pilot(self, ip: str, params: dict) -> bool:
        """Send direct controls (color, white, scene, brightness) to a bulb."""
        self._last.pop(ip, None)
        payload = dict(params)
        payload.setdefault("state", True)
        return self._send(ip, "setPilot", payload)

    def set_scene(self, ip: str, scene_id: int, speed=None) -> bool:
        params = {"sceneId": int(scene_id)}
        if speed is not None:
            params["speed"] = int(speed)
        return self.set_pilot(ip, params)

    def set_temp(self, ip: str, temp: int, dimming: int = 100) -> None:
        """White temperature, used to flash a bulb when identifying it."""
        self._last.pop(ip, None)
        self._send(
            ip,
            "setPilot",
            {"temp": int(temp), "dimming": int(dimming), "state": True},
        )

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None


def discover_lights(timeout: float = 1.5) -> dict:
    """Broadcast getPilot and collect the bulbs that answer."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    found = {}
    deadline = time.monotonic() + timeout
    quiet_deadline = None
    try:
        sock.sendto(
            json.dumps({"id": 1, "method": "getPilot", "params": {}}).encode(),
            ("255.255.255.255", DEFAULT_PORT),
        )
        while True:
            now = time.monotonic()
            wait_until = deadline if quiet_deadline is None else min(deadline, quiet_deadline)
            if now >= wait_until:
                break
            sock.settimeout(max(0.05, wait_until - now))
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                message = json.loads(data)
            except ValueError:
                continue
            if message.get("method") == "getPilot" and "result" in message:
                found[addr[0]] = message["result"]
                # Most bulbs answer within milliseconds; stop soon after the
                # last reply instead of always burning the full timeout.
                quiet_deadline = time.monotonic() + 0.35
    finally:
        sock.close()
    return found


def query_lights(ips, method: str = "getSystemConfig", timeout: float = 0.7) -> dict:
    """Send one request to each IP and collect the results that come back."""
    if not ips:
        return {}
    results = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        payload = json.dumps(
            {"id": 1, "method": method, "params": {}}, separators=(",", ":")
        ).encode()
        for ip in ips:
            try:
                sock.sendto(payload, (ip, DEFAULT_PORT))
            except OSError:
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sock.settimeout(max(0.02, deadline - time.monotonic()))
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
            try:
                message = json.loads(data)
            except ValueError:
                continue
            if message.get("method") == method and "result" in message:
                results[addr[0]] = message["result"]
    finally:
        sock.close()
    return results


# --------------------------------------------------------------------------- #
# Color pipeline
# --------------------------------------------------------------------------- #


def clamp8(value: float) -> int:
    return max(0, min(255, int(round(value))))


def adjust_color(rgb, saturation: float, gamma: float):
    """Boost saturation a little (averages are dull) and apply optional gamma."""
    r, g, b = (max(0.0, min(1.0, channel / 255.0)) for channel in rgb)
    if saturation != 1.0:
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        r, g, b = colorsys.hsv_to_rgb(h, min(1.0, s * saturation), v)
    if gamma and gamma != 1.0:
        exponent = 1.0 / gamma
        r, g, b = r**exponent, g**exponent, b**exponent
    return (clamp8(r * 255), clamp8(g * 255), clamp8(b * 255))


class Smoother:
    """Exponential fade with a wall-clock time constant.

    Small changes fade smoothly, but a big jump (a hard cut in the movie) is
    applied on the next frame. That is what keeps cuts instant without making
    gentle camera moves flicker.
    """

    def __init__(self, tau_seconds: float, cut_delta: float = 128.0):
        self.tau = max(0.0, tau_seconds)
        self.cut_delta = max(0.0, cut_delta)
        self._values = {}

    def step(self, key: str, target, dt: float):
        """Move `key` toward `target`; return (channels, settled)."""
        target = [float(v) for v in target]
        if self.tau <= 0.0 or key not in self._values:
            self._values[key] = target
            return target, True
        current = self._values[key]
        if self.cut_delta and max(abs(target[i] - current[i]) for i in range(3)) >= self.cut_delta:
            current[:] = target
            return current, True
        alpha = 1.0 - math.exp(-max(0.001, dt) / self.tau)
        for i in range(3):
            current[i] += (target[i] - current[i]) * alpha
        if max(abs(target[i] - current[i]) for i in range(3)) < 0.5:
            # Close enough: snap to avoid an endless asymptotic crawl.
            current[:] = target
            return current, True
        return current, False

    def apply(self, key: str, rgb, dt: float):
        current, _ = self.step(key, rgb, dt)
        return tuple(int(round(v)) for v in current)

    def reset(self) -> None:
        self._values.clear()


LAYOUTS = {
    "all": ["all"],
    "left-right": ["left", "right"],
    "top-bottom": ["top", "bottom"],
    "thirds": ["t1", "t2", "t3"],
    "cycle": ["left", "right", "top", "bottom"],
}

# A style is just a coherent starting point. Any individual flag still wins,
# so `--style cinema --brightness 100` does what you expect.
STYLES = {
    "hue": {
        "fps": 15.0,
        "edge": 0.16,
        "smooth": 90.0,
        "saturation": 1.35,
        "gamma": 1.0,
        "brightness": 100,
        "send_hz": 18.0,
    },
    "cinema": {
        "fps": 12.0,
        "edge": 0.20,
        "smooth": 220.0,
        "saturation": 1.15,
        "gamma": 1.0,
        "brightness": 80,
        "send_hz": 15.0,
    },
    "fast": {
        "fps": 20.0,
        "edge": 0.12,
        "smooth": 45.0,
        "saturation": 1.45,
        "gamma": 1.0,
        "brightness": 100,
        "send_hz": 24.0,
    },
    "reactive": {
        "fps": 20.0,
        "edge": 0.13,
        "smooth": 55.0,
        "saturation": 1.4,
        "gamma": 1.0,
        "brightness": 100,
        "send_hz": 26.0,
    },
    "raw": {
        "fps": 24.0,
        "edge": 0.12,
        "smooth": 0.0,
        "saturation": 1.3,
        "gamma": 1.0,
        "brightness": 100,
        "send_hz": 30.0,
    },
}

DEFAULT_STYLE = {
    "fps": 15.0,
    "edge": 0.16,
    "smooth": 90.0,
    "saturation": 1.35,
    "gamma": 1.0,
    "brightness": 100,
    "send_hz": 18.0,
}


def zones_for_layout(layout: str, count: int):
    if layout == "auto":
        if count <= 1:
            layout = "all"
        elif count == 2:
            layout = "left-right"
        elif count == 3:
            layout = "thirds"
        else:
            layout = "cycle"
    if layout == "thirds" and count == 2:
        return ["t1", "t3"]
    base = LAYOUTS[layout]
    return [base[i % len(base)] for i in range(count)]


def zone_color(zones: dict, name: str):
    if name.startswith("t") and name[1:].isdigit():
        index = int(name[1:]) - 1
        thirds = zones.get("thirds") or []
        if 0 <= index < len(thirds):
            return thirds[index]
        return zones.get("all") or (0, 0, 0)
    return zones.get(name) or zones.get("all") or (0, 0, 0)


# --------------------------------------------------------------------------- #
# Runtime paths / state files
# --------------------------------------------------------------------------- #


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = Path(base) / "wiz-ambilight"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def read_state(path: Path):
    try:
        with open(path, "rb") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def clear_state(path: Path) -> None:
    """Drop a state file left behind by a previous (possibly killed) session."""
    try:
        path.unlink()
    except OSError:
        pass


def installed_script_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "mpv" / "scripts" / f"{SCRIPT_NAME}.lua"


# --------------------------------------------------------------------------- #
# The sync loop
# --------------------------------------------------------------------------- #


def run_sync(args, lights, zone_names, state_path: Path, stop_check=None):
    """Follow `state_path` and drive the bulbs with a continuous fade.

    Capture and display run at different rates on purpose: mpv produces a new
    frame a handful of times per second, but the bulbs are updated ~18-30 times
    per second and interpolated every few milliseconds in between. That is what
    turns stepping colors into the smooth glow people expect from Ambilight.
    """
    sender = WizSender(dry_run=args.dry_run)
    smoother = Smoother(args.smooth / 1000.0)
    dimming = max(10, min(100, args.brightness))
    send_interval = 1.0 / max(1.0, args.send_hz)

    print(
        "lights: "
        + ", ".join(f"{ip} ({zone})" for ip, zone in zip(lights, zone_names)),
        file=sys.stderr,
    )
    print(
        f"style: {args.style} | capture: {args.fps:g} fps | edge {args.edge:.0%} | "
        f"smooth {args.smooth:g} ms | saturation {args.saturation:g}x | "
        f"dimming {dimming} | send {args.send_hz:g} Hz",
        file=sys.stderr,
    )
    print(f"state: {state_path}", file=sys.stderr)

    targets = {}
    current = {}
    last_key = None
    last_tick = time.monotonic()
    last_send = 0.0
    last_error = None

    try:
        while True:
            if stop_check is not None and stop_check():
                break

            now = time.monotonic()
            dt = min(0.25, max(0.0, now - last_tick))
            last_tick = now

            # Pick up new frames. The state file is tiny and only rewritten
            # when mpv has something new, so checking its mtime is cheap.
            try:
                stat = state_path.stat()
                key = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                key = None

            if key is not None and key != last_key:
                last_key = key
                state = read_state(state_path)
                if isinstance(state, dict) and state.get("active"):
                    error = state.get("error")
                    if error:
                        if error != last_error:
                            print(
                                f"warning: mpv could not grab frames: {error}",
                                file=sys.stderr,
                            )
                            print(
                                "         try a GPU video output (remove --vo=null / "
                                "--no-video), or add '-- --screenshot-sw=yes'",
                                file=sys.stderr,
                            )
                            last_error = error
                    elif state.get("paused") or state.get("eof"):
                        # Hold the last color: a paused movie should not blink.
                        last_error = None
                    else:
                        zones = state.get("zones")
                        if isinstance(zones, dict):
                            last_error = None
                            for ip, zone in zip(lights, zone_names):
                                rgb = zone_color(zones, zone)
                                targets[ip] = adjust_color(
                                    rgb, args.saturation, args.gamma
                                )

            # Advance every bulb toward its target using wall-clock time, not
            # the media clock (the latter jumps when you seek).
            moving = False
            for ip in lights:
                target = targets.get(ip)
                if target is None:
                    continue
                current[ip], settled = smoother.step(ip, target, dt)
                if not settled:
                    moving = True

            if now - last_send >= send_interval:
                last_send = now
                for ip in lights:
                    cur = current.get(ip)
                    if cur is None:
                        continue
                    sender.set_color(
                        ip,
                        (clamp8(cur[0]), clamp8(cur[1]), clamp8(cur[2])),
                        dimming,
                    )

            # Fast polling while a fade is in progress; idle polling otherwise.
            time.sleep(0.003 if moving else 0.006)
    finally:
        if args.on_exit == "off":
            for ip in lights:
                sender.set_power(ip, False)
        sender.close()


# --------------------------------------------------------------------------- #
# Launcher mode
# --------------------------------------------------------------------------- #


def build_mpv_command(args, media, lua_link: Path, mpv_extra):
    command = [args.mpv or "mpv"]
    command.append(f"--script={lua_link}")
    command.extend(media)
    command.extend(mpv_extra)
    return command


def run_launcher(args, lights, zone_names, mpv_extra):
    pid = os.getpid()
    runtime = runtime_dir()
    state_path = Path(args.state) if args.state else runtime / f"state-{pid}.json"
    link = runtime / f"{SCRIPT_NAME}_run_{pid}.lua"

    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(LUA_SCRIPT)

        config = {
            "path": str(state_path),
            "fps": args.fps,
            "edge": args.edge,
            "bar_luma": 0 if args.no_bars else 16,
            # Only the instance we launch should autostart. If the Lua script
            # is also installed globally, that copy stays asleep.
            "script": link.stem,
        }
        env = os.environ.copy()
        env["WIZ_AMBILIGHT_CONFIG"] = json.dumps(config, separators=(",", ":"))

        clear_state(state_path)
        command = build_mpv_command(args, args.media, link, mpv_extra)
        if args.verbose:
            print("running:", " ".join(command), file=sys.stderr)

        try:
            proc = subprocess.Popen(command, env=env)
        except FileNotFoundError:
            print(
                f"error: could not find '{command[0]}'. Install mpv or pass --mpv PATH.",
                file=sys.stderr,
            )
            return 1

        stop_state = {"requested": False}

        def stop_check():
            return stop_state["requested"] or proc.poll() is not None

        # A background shell may start us with SIGINT ignored, and we still
        # want Ctrl+C / SIGTERM / closing the terminal to take mpv down too.
        # SIGTERM works even when SIGINT is ignored by inherited disposition.
        previous_handlers = {}

        def handle_signal(_signum, _frame):
            stop_state["requested"] = True
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass

        for signum in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)):
            if signum is None:
                continue
            try:
                previous_handlers[signum] = signal.signal(signum, handle_signal)
            except (ValueError, OSError):
                pass

        try:
            run_sync(args, lights, zone_names, state_path, stop_check)
        except KeyboardInterrupt:
            pass
        finally:
            for signum, handler in previous_handlers.items():
                try:
                    signal.signal(signum, handler)
                except (ValueError, OSError):
                    pass
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                except KeyboardInterrupt:
                    proc.kill()
        code = proc.returncode
        return 0 if code is None or code < 0 else code
    finally:
        paths = [link]
        if not args.state:
            paths.append(state_path)
        for path in paths:
            try:
                path.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Attach mode
# --------------------------------------------------------------------------- #


def run_attach(args, lights, zone_names):
    runtime = runtime_dir()
    state_path = Path(args.state) if args.state else runtime / "state.json"
    control_path = runtime / "control.json"

    if not installed_script_path().exists():
        print(
            "warning: the Lua script is not installed in your mpv scripts folder.",
            file=sys.stderr,
        )
        print(
            f"         run '{Path(sys.argv[0]).name} --install-script' first, "
            "then restart mpv.",
            file=sys.stderr,
        )
    else:
        try:
            stale = installed_script_path().read_bytes() != LUA_SCRIPT.read_bytes()
        except OSError:
            stale = False
        if stale:
            print(
                "warning: the installed Lua script differs from this checkout.",
                file=sys.stderr,
            )
            print(
                f"         run '{Path(sys.argv[0]).name} --install-script --force' "
                "and restart mpv.",
                file=sys.stderr,
            )

    config = {
        "enabled": True,
        "path": str(state_path),
        "fps": args.fps,
        "edge": args.edge,
        "bar_luma": 0 if args.no_bars else 16,
        "script": SCRIPT_NAME,
    }

    print("waiting for mpv... (Ctrl+C to stop)", file=sys.stderr)

    clear_state(state_path)

    def touch_control():
        write_json_atomic(control_path, config)

    touch_control()
    last_touch = time.monotonic()
    stop_state = {"requested": False}

    def handle_signal(_signum, _frame):
        stop_state["requested"] = True

    previous_handlers = {}
    for signum in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if signum is None:
            continue
        try:
            previous_handlers[signum] = signal.signal(signum, handle_signal)
        except (ValueError, OSError):
            pass

    try:
        # Keep the control file fresh and process state updates as they appear.
        def stop_check():
            nonlocal last_touch
            if stop_state["requested"]:
                return True
            now = time.monotonic()
            if now - last_touch >= 1.5:
                touch_control()
                last_touch = now
            return False

        run_sync(args, lights, zone_names, state_path, stop_check)
    except KeyboardInterrupt:
        pass
    finally:
        for signum, handler in previous_handlers.items():
            try:
                signal.signal(signum, handler)
            except (ValueError, OSError):
                pass
        try:
            write_json_atomic(control_path, {"enabled": False})
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Direct control (no mpv)
# --------------------------------------------------------------------------- #


def is_ipv4(value: str) -> bool:
    if value.count(".") != 3:
        return False
    try:
        socket.inet_aton(value)
    except OSError:
        return False
    return True


def run_set(args) -> int:
    """Apply one set of controls to one or more bulbs, then exit."""
    ips = parse_lights(args.lights) if args.lights else parse_lights(
        os.environ.get("WIZ_LIGHTS", "") or os.environ.get("WIZ_LIGHT_IPS", "")
    )
    invalid = [ip for ip in ips if not is_ipv4(ip)]
    if invalid:
        print(f"error: invalid light address(es): {', '.join(invalid)}", file=sys.stderr)
        return 2

    params = {}
    try:
        if args.hex is not None:
            r, g, b = hex_to_rgb(args.hex)
            params.update({"r": r, "g": g, "b": b})
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.temp is not None:
        if not 2200 <= args.temp <= 6500:
            print("error: --temp must be between 2200 and 6500 K", file=sys.stderr)
            return 2
        params["temp"] = int(args.temp)
    if args.hex is not None and args.temp is not None:
        print("error: choose --hex or --temp, not both", file=sys.stderr)
        return 2
    if args.brightness is not None:
        params["dimming"] = max(10, min(100, int(args.brightness)))
    if args.scene is not None:
        if not 1 <= args.scene <= 999:
            print("error: --scene must be between 1 and 999", file=sys.stderr)
            return 2
        params["sceneId"] = int(args.scene)
    if args.speed is not None:
        if args.scene is None:
            print("error: --speed needs --scene", file=sys.stderr)
            return 2
        params["speed"] = max(20, min(200, int(args.speed)))
    if args.power == "off" and params:
        print("error: --power off cannot be combined with color or brightness", file=sys.stderr)
        return 2
    if not params and not args.power:
        print(
            "error: nothing to set (use --hex, --temp, --brightness, --scene or --power)",
            file=sys.stderr,
        )
        return 2

    if not ips:
        print("discovering WiZ lights...", file=sys.stderr)
        ips = sorted(discover_lights())
    if not ips:
        print("error: no WiZ lights found. Use --lights or set WIZ_LIGHTS.", file=sys.stderr)
        return 1

    sender = WizSender(dry_run=args.dry_run)
    try:
        if args.power == "off":
            for ip in ips:
                sender.set_power(ip, False)
                if not args.dry_run:
                    print(f"{ip}: off", file=sys.stderr)
            return 0

        states = query_lights(ips) if args.power == "toggle" and not args.dry_run else {}
        for ip in ips:
            current = states.get(ip) or {}
            if args.power == "toggle" and current.get("state"):
                sender.set_power(ip, False)
                if not args.dry_run:
                    print(f"{ip}: off", file=sys.stderr)
                continue
            if params:
                sender.set_pilot(ip, params)
            else:
                sender.set_power(ip, True)
            if not args.dry_run:
                print(f"{ip}: on {params}", file=sys.stderr)
    finally:
        sender.close()
    return 0


# --------------------------------------------------------------------------- #
# Misc commands
# --------------------------------------------------------------------------- #


def install_lua_script(force: bool) -> int:
    if not LUA_SCRIPT.exists():
        print(f"error: missing {LUA_SCRIPT}", file=sys.stderr)
        return 1
    destination = installed_script_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        try:
            same = destination.read_bytes() == LUA_SCRIPT.read_bytes()
        except OSError:
            same = False
        if same:
            print(f"already installed: {destination}")
            return 0
        if not force:
            print(
                f"error: {destination} already exists (use --force to replace it)",
                file=sys.stderr,
            )
            return 1
        destination.unlink()
    # Copy instead of symlinking: the mpv scripts folder should keep working
    # even if this checkout is moved or deleted later.
    shutil.copyfile(LUA_SCRIPT, destination)
    print(f"installed: {destination} (copy of {LUA_SCRIPT})")
    print("restart mpv for it to load the script.")
    return 0


def split_list(value: str):
    """Split a comma or space separated list, keeping duplicates and order."""
    return [item for item in value.replace(" ", ",").split(",") if item]


def parse_lights(value: str):
    seen = set()
    result = []
    for item in split_list(value):
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Everything after a bare "--" goes straight to mpv, so mpv options that
    # collide with ours (--fps is one) can still be used.
    if "--" in argv:
        split = argv.index("--")
        our_argv, mpv_extra = argv[:split], argv[split + 1 :]
    else:
        our_argv, mpv_extra = argv, []

    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name or "mpv_ambilight.py",
        description="Sync WiZ lights with mpv (DIY Ambilight).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  ./mpv_ambilight.py movie.mkv\n"
            "  ./mpv_ambilight.py --lights 192.168.1.5,192.168.1.7 --layout left-right movie.mkv\n"
            "  ./mpv_ambilight.py --style cinema movie.mkv\n"
            "  ./mpv_ambilight.py --layout all movie.mkv\n"
            "  ./mpv_ambilight.py --discover\n"
            "  ./mpv_ambilight.py --gui\n"
            "  ./mpv_ambilight.py --install-script && ./mpv_ambilight.py --attach\n"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}"
    )
    parser.add_argument("media", nargs="*", help="files/URLs to play (mpv arguments are ok too)")
    parser.add_argument(
        "--lights",
        help="comma separated bulb IPs (default: $WIZ_LIGHTS or auto-discovery)",
    )
    parser.add_argument(
        "--layout",
        default="auto",
        choices=["auto", *LAYOUTS],
        help="how to spread the zones over the bulbs (default: auto)",
    )
    parser.add_argument(
        "--zones",
        help="explicit zone list per bulb: all,left,right,top,bottom,t1,t2,t3",
    )
    parser.add_argument(
        "--style",
        default="hue",
        choices=[*STYLES, "custom"],
        help="starting point for the tuning knobs (default: hue)",
    )
    parser.add_argument(
        "--fps", type=float, default=None, help="captures per second (1-30)"
    )
    parser.add_argument(
        "--edge", type=float, default=None, help="edge band size, 0.02-0.45"
    )
    parser.add_argument(
        "--smooth", type=float, default=None, help="color fade in ms (0 = off)"
    )
    parser.add_argument(
        "--saturation", type=float, default=None, help="saturation boost"
    )
    parser.add_argument(
        "--gamma", type=float, default=None, help="output gamma (>1 brightens midtones)"
    )
    parser.add_argument(
        "--brightness", type=int, default=None, help="bulb dimming, 10-100"
    )
    parser.add_argument(
        "--send-hz", type=float, default=None, help="max color updates per second"
    )
    parser.add_argument(
        "--on-exit", choices=["leave", "off"], default="leave", help="what to do when mpv quits"
    )
    parser.add_argument("--state", help="state file to read/write (debugging)")
    parser.add_argument("--no-bars", action="store_true", help="disable letterbox auto-crop")
    parser.add_argument(
        "--attach", action="store_true", help="follow a running mpv (Lua script must be installed)"
    )
    parser.add_argument(
        "--gui", action="store_true", help="open the local web control panel"
    )
    parser.add_argument(
        "--gui-port", type=int, default=8765, help="panel port (default: 8765)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser for --gui"
    )
    parser.add_argument(
        "--demo", action="store_true", help="with --gui: fake lights, never send UDP"
    )
    parser.add_argument("--discover", action="store_true", help="list WiZ lights and exit")
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output for --discover"
    )
    parser.add_argument(
        "--install-script", action="store_true", help="install the Lua script for --attach"
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing script")
    parser.add_argument(
        "--set",
        action="store_true",
        help="apply direct light controls and exit (no mpv needed)",
    )
    parser.add_argument("--hex", help="with --set: color as #rrggbb")
    parser.add_argument(
        "--temp", type=int, help="with --set: white temperature in kelvin (2200-6500)"
    )
    parser.add_argument("--scene", type=int, help="with --set: WiZ scene id")
    parser.add_argument(
        "--speed", type=int, help="with --set: scene speed (20-200, needs --scene)"
    )
    parser.add_argument(
        "--power", choices=["on", "off", "toggle"], help="with --set: power state"
    )
    parser.add_argument(
        "--mpv", default="mpv", help="mpv binary to launch (default: mpv)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print colors instead of sending them"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="show the mpv command line"
    )

    args, unknown = parser.parse_known_args(our_argv)
    mpv_extra = unknown + mpv_extra

    if args.install_script:
        return install_lua_script(args.force)

    if args.discover:
        found = discover_lights()
        if not found:
            print("no lights found")
            return 1
        models = query_lights(sorted(found))
        if args.json:
            payload = {}
            for ip in sorted(found):
                info = dict(found[ip])
                system = models.get(ip) or {}
                info["model"] = system.get("moduleName")
                info["firmware"] = system.get("fwVersion")
                info["homeId"] = system.get("homeId")
                info["roomId"] = system.get("roomId")
                payload[ip] = info
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        for ip in sorted(found):
            info = found[ip]
            system = models.get(ip) or {}
            state = "on" if info.get("state") else "off"
            print(
                f"{ip:16} {system.get('moduleName') or '?':18} "
                f"fw={system.get('fwVersion') or '?':8} "
                f"mac={info.get('mac', '?'):12} state={state:3} "
                f"dimming={info.get('dimming', '?')} rssi={info.get('rssi', '?')}"
            )
        return 0

    if args.gui:
        try:
            from webui import run as run_gui
        except ImportError as exc:
            print(f"error: cannot load the GUI: {exc}", file=sys.stderr)
            return 1
        return run_gui(
            sys.modules[__name__],
            port=args.gui_port,
            demo=args.demo,
            open_browser=not args.no_browser,
        )

    if args.set:
        return run_set(args)

    if args.attach and args.media:
        parser.error("--attach does not take files; it follows the mpv that is already running")

    if not LUA_SCRIPT.exists():
        print(f"error: missing {LUA_SCRIPT}", file=sys.stderr)
        return 1

    if not args.attach and not args.media:
        parser.error("no video file given (or use --attach / --discover)")

    lights = parse_lights(args.lights) if args.lights else parse_lights(
        os.environ.get("WIZ_LIGHTS", "") or os.environ.get("WIZ_LIGHT_IPS", "")
    )
    if not lights:
        print("discovering WiZ lights...", file=sys.stderr)
        found = discover_lights()
        lights = sorted(found)
        if not lights:
            print(
                "error: no WiZ lights found. Use --lights or set WIZ_LIGHTS.",
                file=sys.stderr,
            )
            return 1
        for ip in lights:
            print(f"  found {ip}", file=sys.stderr)

    if args.zones:
        requested = split_list(args.zones)
        invalid = [zone for zone in requested if zone not in ZONE_NAMES]
        if invalid:
            parser.error(f"unknown zone(s): {', '.join(invalid)}")
        zone_names = [requested[i % len(requested)] for i in range(len(lights))]
    else:
        zone_names = zones_for_layout(args.layout, len(lights))

    # Fill every knob the user did not set explicitly from the chosen style.
    preset = DEFAULT_STYLE if args.style == "custom" else STYLES[args.style]
    for name, value in preset.items():
        if getattr(args, name) is None:
            setattr(args, name, value)

    args.fps = max(1.0, min(30.0, args.fps))
    args.edge = max(0.02, min(0.45, args.edge))
    args.send_hz = max(1.0, min(30.0, args.send_hz))
    args.saturation = max(0.0, min(4.0, args.saturation))
    args.gamma = max(0.2, min(3.0, args.gamma))
    args.smooth = max(0.0, min(2000.0, args.smooth))
    args.brightness = max(10, min(100, args.brightness))

    if args.attach:
        run_attach(args, lights, zone_names)
        return 0

    return run_launcher(args, lights, zone_names, mpv_extra)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
