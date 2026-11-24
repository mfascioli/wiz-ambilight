"""Local web panel for WiZ Ambilight.

No third-party dependencies: a small ThreadingHTTPServer serves the static
files in ``web/`` and a JSON API, and the panel owns at most one sync process
(``mpv_ambilight.py --attach`` or a media launch). The panel binds to
127.0.0.1 and only accepts JSON POSTs from its own origin.
"""

import colorsys
import json
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
SCRIPT = HERE / "mpv_ambilight.py"
DEFAULT_PORT = 8765
APP_NAME = "wiz-ambilight"

# Crazy mode streams a rainbow straight to the bulbs for a short burst. WiZ
# firmware starts dropping datagrams when you go much faster than this, so 20
# updates/s is the practical ceiling, not an arbitrary limit.
CRAZY_HZ = 20.0
CRAZY_MAX_HZ = 20.0
CRAZY_SECONDS = 5.0

CONFIG_KEYS = (
    "layout",
    "style",
    "react",
    "react_amount",
    "react_target",
    "auto_lux",
    "lux_target",
    "react_profile",
    "react_bands",
    "react_eq_bands",
    "react_eq",
    "react_auto",
    "react_active_bands",
    "react_color_mode",
    "react_color_a",
    "react_color_b",
    "react_threshold",
    "react_attack",
    "react_release",
    "react_punch",
    "vibrance",
    "brightness",
    "white_leds",
    "mode",
    "media",
    "dry_run",
    "sampling",
    "sampling_fps",
    "sampling_grid",
    "sampling_block",
    "sampling_capture",
    "groups",
    "colors",
)
DEFAULT_CONFIG = {
    "layout": "auto",
    "style": "hue",
    "react": "color",
    "react_amount": 0.8,
    "react_target": 0.45,
    "auto_lux": False,
    "lux_target": 50.0,
    "react_profile": "balanced",
    "react_bands": [],
    "react_eq_bands": 8,
    "react_eq": [],
    "react_auto": "off",
    "react_active_bands": False,
    "react_color_mode": "bands",
    "react_color_a": "#fcbe11",
    "react_color_b": "#38bdf8",
    "react_threshold": -18.0,
    "react_attack": 1.0,
    "react_release": 55.0,
    "react_punch": 3.0,
    "vibrance": 1.0,
    "brightness": 100,
    "white_leds": False,
    "mode": "attach",
    "media": "",
    "dry_run": False,
    "sampling": "auto",
    "sampling_fps": 15,
    "sampling_grid": 80,
    "sampling_block": 1,
    "sampling_capture": "auto",
    "groups": {},
    "colors": [],
    "lights": {},
}

# Power metering is optional per device: newer firmware puts `pc` in the
# getPilot answer, older metering devices answer getPower, and most bulbs do
# neither. Ask at most every POWER_REFRESH seconds, keep a reading for
# POWER_STALE, and stop asking a device after POWER_ATTEMPTS silent tries.
POWER_REFRESH = 30.0
POWER_STALE = 90.0
POWER_ATTEMPTS = 3

# RFC 5737 TEST-NET-1: documentation addresses, never routed on a LAN.
DEMO_LIGHTS = {
    "192.0.2.11": {
        "model": "ESP24_SHRGBC_01",
        "mac": "d8a01154f818",
        "name": "Left wall",
        "state": True,
        "dimming": 62,
        "temp": 3012,
        "r": 255,
        "g": 190,
        "b": 120,
        "pc": 4200,
    },
    "192.0.2.12": {
        "model": "ESP24_SHRGBC_01",
        "mac": "d8a01154fba8",
        "name": "Middle wall",
        "state": True,
        "dimming": 48,
        "temp": 3012,
        "r": 120,
        "g": 200,
        "b": 255,
        "pc": 3800,
    },
    "192.0.2.13": {
        "model": "ESP15_SHTW_01",
        "mac": "d8a01154a1c2",
        "name": "Right shelf",
        "state": False,
        "dimming": 100,
        "temp": 2700,
        "r": 255,
        "g": 255,
        "b": 255,
    },
}


# --------------------------------------------------------------------------- #
# Paths / config
# --------------------------------------------------------------------------- #


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def config_path() -> Path:
    override = os.environ.get("WIZ_AMBILIGHT_GUI_CONFIG")
    return Path(override) if override else config_dir() / "lights.json"


def scenes_path() -> Path:
    override = os.environ.get("WIZ_AMBILIGHT_SCENES_CONFIG")
    return Path(override) if override else config_dir() / "scenes.json"


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = Path(base) / APP_NAME
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def display_path(path: Path) -> str:
    """Shorten a path inside the home directory to ``~/…`` for display."""
    try:
        relative = path.expanduser().relative_to(Path.home())
    except ValueError:
        return str(path)
    return "~/" + str(relative)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def normalize_config(raw, core) -> dict:
    """Return a config that always has the expected shape and sane values."""
    raw = raw if isinstance(raw, dict) else {}
    config = dict(DEFAULT_CONFIG)
    for key in CONFIG_KEYS:
        if key in raw:
            config[key] = raw[key]

    if config["layout"] not in ("auto", *core.LAYOUTS):
        config["layout"] = "auto"
    if config["style"] not in core.STYLES:
        config["style"] = "hue"
    if config["react"] not in core.REACTIONS:
        config["react"] = "color"
    try:
        config["react_amount"] = max(0.0, min(1.0, float(config["react_amount"])))
    except (TypeError, ValueError):
        config["react_amount"] = 0.8
    try:
        config["react_target"] = max(0.05, min(0.95, float(config["react_target"])))
    except (TypeError, ValueError):
        config["react_target"] = 0.45
    try:
        config["lux_target"] = max(
            1.0, min(core.LUX_TARGET_MAX, float(config["lux_target"]))
        )
    except (TypeError, ValueError):
        config["lux_target"] = core.LUX_TARGET
    if config["react_profile"] not in core.PROFILE_LABELS:
        config["react_profile"] = "balanced"
    try:
        eq_bands = int(config["react_eq_bands"])
    except (TypeError, ValueError):
        eq_bands = core.DEFAULT_EQ_BANDS
    eq_bands = max(core.MIN_BANDS, min(core.MAX_BANDS, eq_bands))
    config["react_eq_bands"] = eq_bands
    config["react_eq"] = core.normalize_eq_bands(
        config.get("react_eq"), eq_bands
    )
    config["react_bands"] = [
        core.rgb_to_hex(color)
        for color in core.normalize_band_colors(
            config.get("react_bands"), eq_bands
        )
    ]
    if config["react_auto"] not in core.AUTO_MODES:
        config["react_auto"] = "off"
    config["react_active_bands"] = bool(config.get("react_active_bands"))
    if config["react_color_mode"] not in core.AUDIO_COLOR_MODES:
        config["react_color_mode"] = "bands"
    for key, fallback in (
        ("react_color_a", core.DEFAULT_AUDIO_COLOR_A),
        ("react_color_b", core.DEFAULT_AUDIO_COLOR_B),
    ):
        config[key] = core.rgb_to_hex(
            core.normalize_audio_color(config.get(key), fallback)
        )
    try:
        config["react_threshold"] = max(
            -60.0, min(0.0, float(config["react_threshold"]))
        )
    except (TypeError, ValueError):
        config["react_threshold"] = -18.0
    try:
        config["react_attack"] = max(0.0, min(200.0, float(config["react_attack"])))
    except (TypeError, ValueError):
        config["react_attack"] = 1.0
    try:
        config["react_release"] = max(
            20.0, min(1000.0, float(config["react_release"]))
        )
    except (TypeError, ValueError):
        config["react_release"] = 55.0
    try:
        config["react_punch"] = max(1.0, min(4.0, float(config["react_punch"])))
    except (TypeError, ValueError):
        config["react_punch"] = 3.0
    try:
        config["vibrance"] = max(0.0, min(2.0, float(config["vibrance"])))
    except (TypeError, ValueError):
        config["vibrance"] = 1.0
    try:
        config["brightness"] = max(10, min(100, int(config["brightness"])))
    except (TypeError, ValueError):
        config["brightness"] = 100
    if config["mode"] not in ("attach", "launch"):
        config["mode"] = "attach"
    config["media"] = str(config["media"] or "")[:4096]
    config["dry_run"] = bool(config["dry_run"])
    config["auto_lux"] = bool(config["auto_lux"])
    config["white_leds"] = bool(config["white_leds"])

    sampling_choices = ("auto", "manual", *getattr(core, "SAMPLING_PROFILES", {}))
    if config["sampling"] not in sampling_choices:
        config["sampling"] = "auto"
    try:
        config["sampling_fps"] = max(1, min(30, int(config["sampling_fps"])))
    except (TypeError, ValueError):
        config["sampling_fps"] = 15
    try:
        config["sampling_grid"] = max(24, min(240, int(config["sampling_grid"])))
    except (TypeError, ValueError):
        config["sampling_grid"] = 80
    try:
        config["sampling_block"] = max(1, min(4, int(config["sampling_block"])))
    except (TypeError, ValueError):
        config["sampling_block"] = 1
    if config["sampling_capture"] not in ("auto", "scaled", "source"):
        config["sampling_capture"] = "auto"

    lights = {}
    raw_lights = raw.get("lights") if isinstance(raw.get("lights"), dict) else {}
    for ip, entry in raw_lights.items():
        ip = str(ip).strip()
        if not _IP_RE.match(ip):
            continue
        entry = entry if isinstance(entry, dict) else {}
        zone = entry.get("zone") or ""
        if zone not in core.ZONE_NAMES:
            zone = ""
        lights[ip] = {
            "name": "".join(ch for ch in str(entry.get("name") or "") if ch.isprintable())[:40],
            "enabled": bool(entry.get("enabled", True)),
            "zone": zone,
            "model": str(entry.get("model") or "")[:40],
            "mac": re.sub(r"[^0-9a-f]", "", str(entry.get("mac") or "").lower())[:12],
            "firmware": str(entry.get("firmware") or "")[:20],
        }
    config["lights"] = lights

    # Rooms are named sets of known bulbs. They only drive direct control, so
    # they never feed the sync command and can change while it runs.
    groups = {}
    raw_groups = raw.get("groups") if isinstance(raw.get("groups"), dict) else {}
    for name, members in raw_groups.items():
        name = "".join(ch for ch in str(name) if ch.isprintable()).strip()[:40]
        if not name or not isinstance(members, (list, tuple)):
            continue
        ips = []
        for ip in members:
            ip = str(ip).strip()
            if ip in lights and ip not in ips:
                ips.append(ip)
        if ips:
            groups[name] = ips
    config["groups"] = groups

    colors = []
    raw_colors = raw.get("colors") if isinstance(raw.get("colors"), list) else []
    for value in raw_colors:
        if isinstance(value, dict):
            hex_value = str(value.get("hex") or "").strip().lower()
            brightness = value.get("brightness", 100)
        else:
            # Older configs stored bare hex strings.
            hex_value = str(value or "").strip().lower()
            brightness = 100
        if not re.fullmatch(r"#[0-9a-f]{6}", hex_value):
            continue
        try:
            brightness = max(10, min(100, int(brightness)))
        except (TypeError, ValueError):
            brightness = 100
        existing = next((color for color in colors if color["hex"] == hex_value), None)
        if existing is None:
            colors.append({"hex": hex_value, "brightness": brightness})
        else:
            existing["brightness"] = brightness
        if len(colors) >= 12:
            break
    config["colors"] = colors
    return config


def load_config(core) -> dict:
    return normalize_config(read_json(config_path(), {}), core)


def save_config(config: dict, core) -> dict:
    clean = normalize_config(config, core)
    write_json(config_path(), clean)
    return clean


def _clean_scene_params(entry) -> dict:
    if not isinstance(entry, dict):
        return {}
    params = {}
    if isinstance(entry.get("state"), bool):
        params["state"] = entry["state"]
    for key, low, high in (
        ("dimming", 10, 100),
        ("temp", 2200, 6500),
        ("r", 0, 255),
        ("g", 0, 255),
        ("b", 0, 255),
        ("sceneId", 1, 999),
        ("speed", 20, 200),
    ):
        if key not in entry:
            continue
        try:
            params[key] = max(low, min(high, int(entry[key])))
        except (TypeError, ValueError):
            continue
    if "sceneId" in params:
        for key in ("r", "g", "b", "temp"):
            params.pop(key, None)
    elif all(key in params for key in ("r", "g", "b")):
        params.pop("temp", None)
    else:
        for key in ("r", "g", "b"):
            params.pop(key, None)
    return params


def normalize_scenes(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    scenes = {}
    for name, entries in raw.items():
        name = "".join(ch for ch in str(name) if ch.isprintable()).strip()[:40]
        if not name or not isinstance(entries, dict):
            continue
        clean = {}
        for ip, entry in entries.items():
            if _IP_RE.match(str(ip)):
                params = _clean_scene_params(entry)
                if params:
                    clean[str(ip)] = params
        if clean:
            scenes[name] = clean
    return scenes


def load_scenes() -> dict:
    return normalize_scenes(read_json(scenes_path(), {}))


def save_scenes(scenes: dict) -> dict:
    clean = normalize_scenes(scenes)
    write_json(scenes_path(), clean)
    return clean


def merge_discovered(config: dict, found: dict) -> dict:
    """Add new bulbs to the config, migrating entries when an IP changed."""
    by_mac = {}
    for ip, entry in config["lights"].items():
        if entry.get("mac"):
            by_mac[entry["mac"]] = ip

    for ip, info in found.items():
        mac = re.sub(r"[^0-9a-f]", "", str(info.get("mac") or "").lower())[:12]
        old_ip = by_mac.get(mac) if mac else None
        if old_ip and old_ip != ip and old_ip in config["lights"]:
            # DHCP moved the bulb: keep the name/zone, follow the new address.
            config["lights"][ip] = config["lights"].pop(old_ip)
            by_mac[mac] = ip
        entry = config["lights"].setdefault(
            ip,
            {
                "name": "",
                "enabled": True,
                "zone": "",
                "model": "",
                "mac": "",
                "firmware": "",
            },
        )
        entry["model"] = str(info.get("model") or entry.get("model") or "")[:40]
        entry["firmware"] = str(info.get("firmware") or entry.get("firmware") or "")[:20]
        if mac:
            entry["mac"] = mac
    return config


# --------------------------------------------------------------------------- #
# Effective light plan / commands
# --------------------------------------------------------------------------- #


def enabled_lights(config: dict):
    return [
        (ip, entry)
        for ip, entry in config["lights"].items()
        if entry.get("enabled", True)
    ]


def effective_zones(config: dict, core):
    """Zones in the same order as the enabled bulbs."""
    pairs = enabled_lights(config)
    defaults = core.zones_for_layout(config["layout"], len(pairs))
    zones = []
    for index, (_ip, entry) in enumerate(pairs):
        zones.append(entry.get("zone") or defaults[index])
    return zones


def build_command(config: dict, core, demo: bool = False):
    """Return (argv, ips, zones) for the sync process."""
    pairs = enabled_lights(config)
    if not pairs:
        raise ValueError("select at least one light")
    if config["mode"] == "launch" and not config["media"].strip():
        raise ValueError("choose a video file or switch to attach mode")

    ips = [ip for ip, _ in pairs]
    zones = effective_zones(config, core)
    sampling = config.get("sampling", "auto")
    eq_count = config.get("react_eq_bands", core.DEFAULT_EQ_BANDS)
    eq_bands = core.normalize_eq_bands(config.get("react_eq"), eq_count)
    eq_colors = [
        core.rgb_to_hex(color)
        for color in core.normalize_band_colors(
            config.get("react_bands"), len(eq_bands)
        )
    ]
    argv = [
        sys.executable,
        str(SCRIPT),
        "--lights",
        ",".join(ips),
        "--zones",
        ",".join(zones),
        "--style",
        config["style"],
        "--react",
        config.get("react", "color"),
        "--react-amount",
        f"{config.get('react_amount', 0.8):g}",
        "--react-target",
        f"{config.get('react_target', 0.45):g}",
        *(["--auto-lux"] if config.get("auto_lux") else []),
        "--lux-target",
        f"{config.get('lux_target', core.LUX_TARGET):g}",
        "--react-profile",
        config.get("react_profile", "balanced"),
        "--react-bands",
        ",".join(eq_colors),
        "--react-eq-bands",
        str(eq_count),
        "--react-eq",
        json.dumps(
            eq_bands,
            separators=(",", ":"),
        ),
        "--react-auto",
        config.get("react_auto", "off"),
        *(["--react-active-bands"] if config.get("react_active_bands") else []),
        "--react-color-mode",
        config.get("react_color_mode", "bands"),
        "--react-color-a",
        config.get("react_color_a") or core.DEFAULT_AUDIO_COLOR_A,
        "--react-color-b",
        config.get("react_color_b") or core.DEFAULT_AUDIO_COLOR_B,
        "--react-threshold",
        f"{config.get('react_threshold', -18.0):g}",
        "--react-attack",
        f"{config.get('react_attack', 1.0):g}",
        "--react-release",
        f"{config.get('react_release', 55.0):g}",
        "--react-punch",
        f"{config.get('react_punch', 3.0):g}",
        "--vibrance",
        f"{config.get('vibrance', 1.0):g}",
        *(["--white-leds"] if config.get("white_leds") else []),
        "--brightness",
        str(config["brightness"]),
        "--sampling",
        sampling,
    ]
    if sampling == "manual":
        argv.extend(
            [
                "--fps",
                str(config.get("sampling_fps", 15)),
                "--sample-grid",
                str(config.get("sampling_grid", 80)),
                "--sample-block",
                str(config.get("sampling_block", 1)),
                "--capture",
                config.get("sampling_capture", "auto"),
            ]
        )
    if demo or config["dry_run"]:
        argv.append("--dry-run")
    if config["mode"] == "attach":
        argv.append("--attach")
    else:
        media = config["media"].strip()
        if not media:
            raise ValueError("choose a video file or switch to attach mode")
        # argv is already shell-free. Refuse values that mpv would parse as
        # options (for example --script=evil.lua) so the file field can never
        # turn into an mpv command.
        if media.startswith("-"):
            raise ValueError("media paths cannot start with '-'")
        if any(ord(ch) < 32 for ch in media):
            raise ValueError("invalid media path")
        argv.append(media)
    return argv, ips, zones


# --------------------------------------------------------------------------- #
# Session (the child sync process)
# --------------------------------------------------------------------------- #


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_cmdline(pid: int) -> str:
    """Best effort command line for pid, without trusting the PID file.

    Linux exposes ``/proc/<pid>/cmdline``. macOS and the BSDs do not, so fall
    back to ``ps`` with an argument list (never a shell). On Windows there is
    no ``ps``; the empty result means the process is not adopted.
    """
    proc = Path(f"/proc/{pid}/cmdline")
    if Path("/proc").exists():
        try:
            return proc.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _looks_like_ours(pid: int) -> bool:
    if pid == os.getpid():
        return False
    cmdline = _read_cmdline(pid)
    return str(SCRIPT) in cmdline and "mpv_ambilight" in cmdline


def _stop_process_tree(process, timeout: float) -> None:
    """Stop the child and its group; portable when os.killpg is missing."""
    killpg = getattr(os, "killpg", None)
    try:
        if killpg is not None:
            killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    hard = getattr(signal, "SIGKILL", signal.SIGTERM)
    try:
        if killpg is not None:
            killpg(process.pid, hard)
        else:
            process.kill()
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


class Session:
    def __init__(self, panel):
        self.panel = panel
        self.lock = threading.Lock()
        self.process = None
        self.pid = None
        self.started = None
        self.mode = None
        self.adopted = False
        self.log = deque(maxlen=250)

    @property
    def pid_path(self) -> Path:
        return runtime_dir() / "gui-daemon.json"

    def running(self) -> bool:
        with self.lock:
            if self.process is not None:
                return self.process.poll() is None
            if self.pid and _pid_alive(self.pid):
                return True
            return False

    def write_log(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        with self.lock:
            self.log.append(line[:600])

    def snapshot(self) -> dict:
        running = self.running()
        with self.lock:
            return {
                "running": running,
                "pid": self.pid if running else None,
                "mode": self.mode,
                "adopted": self.adopted and running,
                "started": self.started if running else None,
                "log": list(self.log)[-80:],
            }

    def adopt(self) -> None:
        info = read_json(self.pid_path, None)
        if not isinstance(info, dict):
            return
        pid = info.get("pid")
        if isinstance(pid, int) and _pid_alive(pid) and _looks_like_ours(pid):
            self.pid = pid
            self.started = info.get("started")
            self.mode = info.get("mode")
            self.adopted = True
            self.write_log(f"adopted running process {pid}")

    def start(self, argv) -> None:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError("already running")
            if self.pid and _pid_alive(self.pid):
                raise ValueError("another sync process is already running")
            self.log.clear()
            self.adopted = False
            self.process = subprocess.Popen(
                argv,
                cwd=str(HERE),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            self.pid = self.process.pid
            self.started = time.time()
            self.mode = "launch" if "--attach" not in argv else "attach"
            threading.Thread(target=self._pump, daemon=True).start()
            write_json(
                self.pid_path,
                {"pid": self.pid, "started": self.started, "mode": self.mode},
            )

    def _pump(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                self.write_log(line)
        finally:
            code = process.wait()
            self.write_log(f"process exited with code {code}")
            with self.lock:
                if self.process is process:
                    self.process = None
                    self.pid = None
                    self.started = None
                    self.adopted = False
            try:
                self.pid_path.unlink()
            except OSError:
                pass

    def stop(self, timeout: float = 4.0) -> None:
        with self.lock:
            process = self.process
            pid = self.pid
        if process is not None and process.poll() is None:
            _stop_process_tree(process, timeout)
        elif pid and _pid_alive(pid) and _looks_like_ours(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and _pid_alive(pid):
                time.sleep(0.05)
            if _pid_alive(pid):
                try:
                    os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                except OSError:
                    pass
        with self.lock:
            self.process = None
            self.pid = None
            self.started = None
            self.adopted = False
        try:
            self.pid_path.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Panel: config + discovery + session + snapshot
# --------------------------------------------------------------------------- #


def crazy_frame(elapsed: float, seconds: float, index: int = 0) -> dict:
    """One crazy-mode frame: fast hue drift plus a brightness sweep.

    The sweep is a cosine so it starts at 10%, peaks at 100% halfway through
    the burst and comes back down, instead of jumping between two levels.
    """
    phase = 0.0 if seconds <= 0 else min(1.0, max(0.0, elapsed / seconds))
    hue = (elapsed * 0.6 + index * 0.11) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    level = 10 + 90 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
    return {
        "r": int(round(r * 255)),
        "g": int(round(g * 255)),
        "b": int(round(b * 255)),
        "dimming": int(round(level)),
    }


def restore_params(info) -> dict:
    """Translate a getPilot result into a setPilot payload.

    Crazy mode uses this to put the bulbs back the way they were. Anything
    that cannot be represented safely is left out; a scene wins over rgb
    because replaying the scene keeps its animation, and an off bulb is simply
    turned off.
    """
    if not isinstance(info, dict):
        return {}
    if info.get("state") is False:
        return {"state": False}
    params = {"state": True}
    if info.get("dimming") is not None:
        try:
            params["dimming"] = max(10, min(100, int(info["dimming"])))
        except (TypeError, ValueError):
            pass
    try:
        scene = int(info.get("sceneId") or 0)
    except (TypeError, ValueError):
        scene = 0
    if scene > 0:
        params["sceneId"] = scene
        return params
    channels = {}
    for key in ("r", "g", "b"):
        try:
            channels[key] = max(0, min(255, int(info.get(key))))
        except (TypeError, ValueError):
            channels = {}
            break
    if len(channels) == 3:
        params.update(channels)
        return params
    if info.get("temp") is not None:
        try:
            params["temp"] = max(2200, min(6500, int(info["temp"])))
        except (TypeError, ValueError):
            pass
    return params


# --------------------------------------------------------------------------- #
# Resource sampling (stdlib only; /proc on Linux, graceful elsewhere)
# --------------------------------------------------------------------------- #


def _sysconf(name: str, default: int) -> int:
    try:
        return int(os.sysconf(name))
    except (AttributeError, ValueError, OSError):
        return default


def _proc_stat(pid: int):
    """Return (ppid, cpu ticks, rss pages) for a Linux process, or None."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # The comm field can contain spaces and parentheses; everything we need
    # starts after the last ')'.
    end = text.rfind(")")
    if end < 0:
        return None
    fields = text[end + 2 :].split()
    if len(fields) < 22:
        return None
    try:
        return int(fields[1]), int(fields[11]) + int(fields[12]), int(fields[21])
    except ValueError:
        return None


def _proc_table():
    """Every readable process as pid -> (ppid, cpu ticks, rss pages)."""
    if not Path("/proc").is_dir():
        return None
    stats = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        info = _proc_stat(pid)
        if info is not None:
            stats[pid] = info
    return stats


def _descendants(stats, roots):
    """The roots plus every process below them, from one /proc snapshot."""
    children = {}
    for pid, (ppid, _ticks, _rss) in stats.items():
        children.setdefault(ppid, []).append(pid)
    seen = set()
    stack = [pid for pid in roots if isinstance(pid, int) and pid > 0]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, ()))
    return {pid: stats[pid] for pid in seen if pid in stats}


def _fresh_state(max_age: float = 4.0):
    """The newest live Lua state file, or None if every file is stale."""
    try:
        paths = list(runtime_dir().glob("state*.json"))
    except OSError:
        return None
    now = time.time()
    newest = None
    for path in paths:
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if now - modified > max_age:
            continue
        data = read_json(path, None)
        if not isinstance(data, dict):
            continue
        pid = data.get("pid")
        if not (isinstance(pid, int) and pid > 0 and _pid_alive(pid)):
            continue
        if newest is None or modified > newest[0]:
            newest = (modified, data)
    return newest[1] if newest else None


def _fresh_state_pid(max_age: float = 4.0):
    """The mpv pid in the newest fresh Lua state file, or None.

    Attach mode has no parent link to follow, so the Lua script writes its own
    pid. Old scripts do not, and a stale file from a closed player is ignored.
    """
    data = _fresh_state(max_age)
    pid = data.get("pid") if data else None
    return pid if isinstance(pid, int) and pid > 0 else None


def _milliwatts_to_watts(value):
    """A getPower/pilot reading in milliwatts as watts, or None."""
    if isinstance(value, bool):
        return None
    try:
        milliwatts = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(milliwatts) or milliwatts < 0:
        return None
    return round(milliwatts / 1000.0, 2)


def _pilot_watts(info: dict):
    """The `pc` reading newer metering firmware puts in getPilot, in watts."""
    return _milliwatts_to_watts((info or {}).get("pc"))


class Panel:
    def __init__(self, core, port: int = DEFAULT_PORT, demo: bool = False):
        self.core = core
        self.port = port
        self.demo = demo
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.RLock()
        self.config = load_config(core)
        self.scenes = load_scenes()
        self.live = {}
        self.reachable = set()
        self.scanned = 0.0
        self._power = {}
        self._power_at = 0.0
        self._power_misses = {}
        self._no_power = set()
        self._power_thread = None
        self._res_lock = threading.Lock()
        self._res_prev = {}
        self._res_prev_time = 0.0
        self._res_cpu = {}
        self._crazy_stop = threading.Event()
        self._crazy_thread = None
        self._crazy_target = "all"
        self._crazy_until = 0.0
        self._crazy_restore = {}
        self._crazy_resume = False
        self._closing = False
        self.session = Session(self)
        self.session.adopt()
        if demo:
            self.config["dry_run"] = True
            self.live = json.loads(json.dumps(DEMO_LIGHTS))
            self.reachable = set(self.live)
            # Demo fixtures replace the saved bulbs instead of being merged
            # into them. Mixing both lists made the same hardware appear twice
            # (a real IP and a 192.0.2.x fixture) with blank names.
            self.config["lights"] = {}
            groups = {}
            for name, members in self.config["groups"].items():
                keep = [ip for ip in members if ip in self.live]
                if keep:
                    groups[name] = keep
            self.config["groups"] = groups
            for ip, info in self.live.items():
                self.config["lights"][ip] = {
                    "name": info.get("name") or "",
                    "enabled": True,
                    "zone": info.get("zone") or "",
                    "model": info.get("model") or "",
                    "mac": info.get("mac") or "",
                    "firmware": info.get("firmware") or "",
                }

    # -- discovery -------------------------------------------------------- #

    def scan(self, deep: bool = True) -> int:
        if self.demo:
            return len(self.live)
        found = self.core.discover_lights(timeout=2.5 if deep else 1.8, deep=deep)
        details = self.core.query_lights(
            sorted(found), timeout=1.2 if deep else 0.7
        )
        live = {}
        for ip, info in found.items():
            system = details.get(ip) or {}
            merged = dict(info)
            merged["model"] = system.get("moduleName")
            merged["firmware"] = system.get("fwVersion")
            merged["mac"] = system.get("mac") or merged.get("mac")
            live[ip] = merged

        with self.lock:
            self.live = live
            self.scanned = time.time()
            if deep:
                self.reachable = set(live)
                # A manual scan may follow a firmware update or a new plug,
                # so give every device another chance to report power.
                self._no_power.clear()
                self._power_misses.clear()
            else:
                # A light scan may miss a bulb that only answers unicast, so it
                # must never take a known bulb offline.
                self.reachable |= set(live)
            before = [ip for ip, _ in enabled_lights(self.config)]
            merge_discovered(self.config, live)
            self._persist()
            after = [ip for ip, _ in enabled_lights(self.config)]
        if after != before and self.session.running():
            self.restart()
        return len(live)

    def maybe_scan(self) -> None:
        if self.demo:
            return
        if time.time() - self.scanned > 12.0:
            try:
                self.scan(deep=False)
            except OSError:
                pass

    def maybe_power(self) -> None:
        """Refresh metered watts in the background, off the request thread.

        `getPilot` often carries `pc` already, so only the devices that leave
        it out are asked, and only until they refuse or stay silent.
        """
        if self.demo:
            return
        now = time.monotonic()
        if now - self._power_at < POWER_REFRESH:
            return
        self._power_at = now
        with self.lock:
            ips = [
                ip
                for ip, info in self.live.items()
                if ip not in self._no_power and _pilot_watts(info) is None
            ]
        if not ips:
            return
        thread = self._power_thread
        if thread is not None and thread.is_alive():
            return
        self._power_thread = threading.Thread(
            target=self._poll_power,
            args=(ips,),
            name="wiz-power",
            daemon=True,
        )
        self._power_thread.start()

    def _poll_power(self, ips) -> None:
        try:
            replies = self.core.query_lights(ips, "getPower", timeout=0.6)
        except OSError:
            return
        now = time.monotonic()
        with self.lock:
            if self._closing:
                return
            for ip in ips:
                watts = _milliwatts_to_watts((replies.get(ip) or {}).get("power"))
                if watts is None:
                    misses = self._power_misses.get(ip, 0) + 1
                    self._power_misses[ip] = misses
                    if misses >= POWER_ATTEMPTS:
                        self._no_power.add(ip)
                        self._power.pop(ip, None)
                    continue
                self._power_misses.pop(ip, None)
                self._power[ip] = (watts, now)

    def _power_watts(self, ip: str, info: dict):
        """The last metered draw for one bulb, in watts, or None."""
        watts = _pilot_watts(info)
        if watts is not None:
            return watts
        entry = self._power.get(ip)
        if entry is None:
            return None
        watts, at = entry
        if time.monotonic() - at > POWER_STALE:
            return None
        return watts

    # -- state ------------------------------------------------------------ #

    def light_rows(self) -> list:
        with self.lock:
            config = self.config
            zones = dict(zip([ip for ip, _ in enabled_lights(config)], effective_zones(config, self.core)))
            rows = []
            for ip, entry in config["lights"].items():
                info = self.live.get(ip) or {}
                rgb = self.core.pilot_rgb(info)
                rows.append(
                    {
                        "ip": ip,
                        "name": entry.get("name") or "",
                        "enabled": bool(entry.get("enabled", True)),
                        "zone": entry.get("zone") or "",
                        "effective_zone": zones.get(ip, "all"),
                        "model": info.get("model") or entry.get("model") or "",
                        "mac": info.get("mac") or entry.get("mac") or "",
                        "firmware": info.get("firmware") or entry.get("firmware") or "",
                        "online": ip in self.reachable if not self.demo else True,
                        "state": bool(info.get("state", False)),
                        "dimming": info.get("dimming"),
                        "temp": info.get("temp"),
                        "r": info.get("r"),
                        "g": info.get("g"),
                        "b": info.get("b"),
                        # A white bulb has no RGB values; the panel derives a
                        # warm swatch from `temp` instead of inventing a color.
                        "hex": self.core.rgb_to_hex(rgb) if rgb else None,
                        # Only Direct control shows this, and only when the
                        # firmware meters power; most bulbs do not.
                        "power": self._power_watts(ip, info),
                    }
                )
            rows.sort(key=lambda row: [int(part) for part in row["ip"].split(".")])
            return rows

    def lua_status(self) -> dict:
        destination = self.core.installed_script_path()
        installed = destination.exists()
        stale = False
        if installed:
            try:
                stale = destination.read_bytes() != self.core.LUA_SCRIPT.read_bytes()
            except OSError:
                stale = False
        return {
            "installed": installed,
            "stale": stale,
            "path": str(destination),
        }

    def meter(self) -> dict:
        """Live audio levels for the panel's signal timeline.

        The Lua state beats at 30 Hz in audio mode, so this is a cheap read of
        the newest fresh file instead of another mpv round trip. `ceiling` is
        the top of the profile's dB window and `window` its minimum width; the
        panel needs both to draw the light-drive curve in red without
        duplicating the profile table.
        """
        state = _fresh_state()
        audio = state.get("audio") if isinstance(state, dict) else None
        audio = audio if isinstance(audio, dict) else {}
        db = self.core.hot_db(audio.get("rms"), audio.get("peak"))

        def number(value):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return value if math.isfinite(value) else None

        mode = self.config.get("react")
        profiles = self.core.REACTION_PROFILES.get(mode, {})
        profile = profiles.get(self.config.get("react_profile"), {})
        ceiling = profile.get("high", self.core.AUDIO_CEILING_DB)
        window = self.core.AUDIO_WINDOW_DB
        bands = audio.get("bands")
        bands = bands if isinstance(bands, (list, tuple)) else []
        return {
            "at": time.time(),
            "active": db is not None,
            "db": round(db, 1) if db is not None else None,
            "ceiling": number(ceiling),
            "window": number(window),
            "rms": number(audio.get("rms")),
            "peak": number(audio.get("peak")),
            "bands": [number(value) for value in bands[: self.core.MAX_BANDS]],
        }

    def _sync_stats(self, pid):
        """Newest live stats-<pid>.json for the running sync process."""
        if not isinstance(pid, int):
            return None
        try:
            paths = list(runtime_dir().glob("stats-*.json"))
        except OSError:
            return None
        now = time.time()
        newest = None
        for path in paths:
            data = read_json(path, None)
            if not isinstance(data, dict) or data.get("pid") != pid:
                continue
            at = data.get("at")
            if not isinstance(at, (int, float)) or now - at > 6.0:
                continue
            if newest is None or at > newest.get("at", 0):
                newest = data
        return newest

    def _mpv_pid(self, sync_pid, stats):
        """The mpv process that feeds the sync, or None when it cannot be told.

        The Lua script writes its own pid into the state file, which is the only
        link in attach mode. Launch mode also has mpv as a child of the sync,
        so an older installed script still works through the process tree.
        """
        pid = _fresh_state_pid()
        if pid:
            return pid
        if isinstance(sync_pid, int) and stats is not None:
            for child in _descendants(stats, [sync_pid]):
                if child == sync_pid:
                    continue
                argv0 = _read_cmdline(child).split(" ", 1)[0]
                if os.path.basename(argv0).startswith("mpv"):
                    return child
        return None

    def resources(self) -> dict:
        """Per-process CPU and RSS for mpv and the panel, plus WiZ UDP traffic.

        CPU is a share of the whole processor: 100 % means every logical core
        is busy, so two saturated cores on an eight-core machine read 25 %.
        Linux exposes all of this through /proc; elsewhere the function still
        returns a well-formed payload so the chart can say "unavailable".
        """
        session = self.session.snapshot()
        running = bool(session.get("running"))
        sync_pid = session.get("pid") if running else None
        if not isinstance(sync_pid, int):
            sync_pid = None
        stats = _proc_table()
        available = stats is not None
        now = time.monotonic()
        cores = os.cpu_count() or 1
        mpv_pid = self._mpv_pid(sync_pid, stats) if running else None

        cpu_wiz = cpu_mpv = None
        ram_wiz = ram_mpv = None
        processes = 0
        if stats is not None:
            roots = [os.getpid()]
            if sync_pid:
                roots.append(sync_pid)
            wiz = _descendants(stats, roots)
            mpv = _descendants(stats, [mpv_pid]) if mpv_pid else {}
            # In launch mode mpv is a child of the sync; never count it twice.
            wiz = {pid: info for pid, info in wiz.items() if pid not in mpv}
            page_size = _sysconf("SC_PAGE_SIZE", 4096)
            ram_wiz = round(
                sum(info[2] for info in wiz.values()) * page_size / (1024 * 1024), 1
            )
            if mpv:
                ram_mpv = round(
                    sum(info[2] for info in mpv.values()) * page_size / (1024 * 1024), 1
                )
            processes = len(wiz) + len(mpv)
            ticks_wiz = {pid: info[1] for pid, info in wiz.items()}
            ticks_mpv = {pid: info[1] for pid, info in mpv.items()}
            with self._res_lock:
                if self._res_prev and now - self._res_prev_time >= 0.4:
                    elapsed = now - self._res_prev_time
                    clock = _sysconf("SC_CLK_TCK", 100)

                    def share(ticks):
                        shared = ticks.keys() & self._res_prev.keys()
                        delta = sum(max(0, ticks[pid] - self._res_prev[pid]) for pid in shared)
                        return round(delta / clock / elapsed / cores * 100.0, 2)

                    cpu_wiz = share(ticks_wiz)
                    cpu_mpv = share(ticks_mpv) if ticks_mpv else None
                    self._res_cpu = {"wiz": cpu_wiz, "mpv": cpu_mpv}
                else:
                    cpu_wiz = self._res_cpu.get("wiz")
                    cpu_mpv = self._res_cpu.get("mpv") if ticks_mpv else None
                if not self._res_prev or now - self._res_prev_time >= 0.4:
                    self._res_prev = {**ticks_wiz, **ticks_mpv}
                    self._res_prev_time = now

        stats_file = self._sync_stats(sync_pid) if running else None
        network_bps = 0.0
        if running:
            network_bps = None
            if stats_file is not None and isinstance(stats_file.get("tx_bps"), (int, float)):
                network_bps = round(float(stats_file["tx_bps"]), 1)
        udp_kbps = (
            round(network_bps / 1024.0, 2)
            if isinstance(network_bps, (int, float))
            else None
        )

        def number(key):
            value = stats_file.get(key) if stats_file else None
            return value if isinstance(value, (int, float)) else None

        return {
            "at": time.time(),
            "available": available,
            "cores": cores,
            "cpu": cpu_wiz,
            "ram_mb": ram_wiz,
            "cpu_wiz": cpu_wiz,
            "ram_wiz": ram_wiz,
            "cpu_mpv": cpu_mpv,
            "ram_mpv": ram_mpv,
            "mpv_pid": mpv_pid,
            "processes": processes,
            "network_bps": network_bps,
            "udp_kbps": udp_kbps,
            "network_ready": stats_file is not None,
            "capture_fps": number("capture_fps"),
            "capture_w": number("w"),
            "capture_h": number("h"),
            "video_w": number("vw"),
            "video_h": number("vh"),
            "capture": stats_file.get("capture") if stats_file else None,
        }

    def lux_status(self):
        """The optional bridge's latest reading, with its age.

        The panel is only a viewer here: the sync and the bridge own the file
        and the control loop. Returning None is the normal state without a
        sensor, not an error.
        """
        path = runtime_dir() / "lux.json"
        try:
            stat = path.stat()
        except OSError:
            return None
        value = self.core.read_lux(path, max_age=None)
        if value is None:
            return None
        age = max(0.0, time.time() - stat.st_mtime)
        return {
            "value": round(value, 1),
            "age": round(age, 1),
            "fresh": age <= self.core.LUX_STALE_SECONDS,
        }

    def snapshot(self) -> dict:
        with self.lock:
            config = json.loads(json.dumps(self.config))
            scenes = [
                {"name": name, "count": len(entries)}
                for name, entries in sorted(self.scenes.items())
            ]
        pairs = enabled_lights(config)
        eq_bands = config.get("react_eq") or self.core.normalize_eq_bands(
            None, config.get("react_eq_bands", self.core.DEFAULT_EQ_BANDS)
        )
        eq_colors = [
            self.core.rgb_to_hex(color)
            for color in self.core.normalize_band_colors(
                config.get("react_bands"), len(eq_bands)
            )
        ]
        return {
            "version": self.core.VERSION,
            "demo": self.demo,
            "config": config,
            "lights": self.light_rows(),
            "zones": sorted(self.core.ZONE_NAMES),
            "layouts": ["auto", *self.core.LAYOUTS],
            "styles": list(self.core.STYLES),
            "style_details": {
                name: dict(values) for name, values in self.core.STYLES.items()
            },
            "reactions": [
                {
                    "id": key,
                    "group": details["group"],
                    "label": details["label"],
                    "hint": details["hint"],
                    "detail": details.get("detail", details["hint"]),
                    "audio": key in self.core.AUDIO_REACTIONS,
                    "profiles": [
                        {
                            "id": profile,
                            "label": self.core.PROFILE_LABELS[profile],
                            "hint": values.get("hint", ""),
                        }
                        for profile, values in self.core.REACTION_PROFILES.get(
                            key, {}
                        ).items()
                    ],
                }
                for key, details in self.core.REACTIONS.items()
            ],
            "bands": [
                {
                    "id": f"band-{index + 1}",
                    "label": self.core.format_freq(band["freq"]),
                    "color": color,
                    **band,
                }
                for index, (band, color) in enumerate(
                    zip(eq_bands, eq_colors)
                )
            ],
            "lamps": [
                {
                    "index": index,
                    "ip": ip,
                    "name": entry.get("name") or ip,
                }
                for index, (ip, entry) in enumerate(pairs)
            ],
            "eq_limits": {
                "min": self.core.MIN_BANDS,
                "max": self.core.MAX_BANDS,
                "freq_min": self.core.EQ_FREQ_MIN,
                "freq_max": self.core.EQ_FREQ_MAX,
                "gain": self.core.EQ_GAIN_LIMIT,
                "q_min": 0.4,
                "q_max": 8.0,
                "types": [
                    {"id": key, "label": self.core.EQ_TYPE_LABELS[key]}
                    for key in self.core.EQ_BAND_TYPES
                ],
                "slopes": list(self.core.EQ_SLOPES),
                "default_type": "bell",
                "default_slope": self.core.EQ_DEFAULT_SLOPE,
            },
            "auto_modes": [
                {
                    "id": key,
                    "label": label,
                    "hint": self.core.AUTO_HINTS.get(key, ""),
                }
                for key, label in self.core.AUTO_MODES.items()
            ],
            "color_modes": [
                {
                    "id": key,
                    "label": label,
                    "hint": self.core.AUDIO_COLOR_HINTS.get(key, ""),
                }
                for key, label in self.core.AUDIO_COLOR_MODES.items()
            ],
            "reaction_groups": [
                {
                    "id": group,
                    "label": group.capitalize(),
                }
                for group in self.core.REACTION_GROUPS
            ],
            "dynamics": [
                {"id": key, **values}
                for key, values in self.core.AUDIO_PRESETS.items()
            ],
            "scenes": scenes,
            "wiz_scenes": [
                {"id": scene_id, "name": name}
                for scene_id, name in sorted(self.core.WIZ_SCENES.items())
            ],
            "session": self.session.snapshot(),
            "lua": self.lua_status(),
            "lux": self.lux_status(),
            "scanned": self.scanned,
            "network": [
                f"{address}/{prefix}"
                for address, prefix in self.core.local_ipv4_networks()
            ],
            "crazy": self.crazy_status(),
            "resources": self.resources(),
            "config_path": str(config_path()),
            "config_display": display_path(config_path()),
        }

    # -- mutations -------------------------------------------------------- #

    def _persist(self) -> None:
        if not self.demo:
            self.config = save_config(self.config, self.core)

    def update_config(self, patch: dict) -> dict:
        if not isinstance(patch, dict):
            raise ValueError("expected a JSON object")
        with self.lock:
            merged = json.loads(json.dumps(self.config))
            for key in CONFIG_KEYS:
                if key in patch:
                    merged[key] = patch[key]
            if isinstance(patch.get("lights"), dict):
                for ip, entry in patch["lights"].items():
                    if ip in merged["lights"] and isinstance(entry, dict):
                        for field in ("name", "enabled", "zone"):
                            if field in entry:
                                merged["lights"][ip][field] = entry[field]
            self.config = normalize_config(merged, self.core)
            if self.demo:
                self.config["dry_run"] = True
            self._persist()
        if self.session.running() and (
            "lights" in patch
            or any(k in patch for k in CONFIG_KEYS if k not in ("groups", "colors"))
        ):
            self.restart()
        return self.snapshot()

    def set_light(self, ip: str, fields: dict) -> dict:
        with self.lock:
            if ip not in self.config["lights"]:
                raise ValueError("unknown light")
            for field in ("name", "enabled", "zone"):
                if field in fields:
                    self.config["lights"][ip][field] = fields[field]
            self._persist()
        if self.session.running():
            self.restart()
        return self.snapshot()

    def delete_light(self, ip: str) -> dict:
        """Forget one bulb: remove the row and any room membership.

        This only edits `lights.json`; the bulb itself keeps its current
        colour. A later **Scan network** adds a reachable bulb back, so
        deleting is for stale addresses and duplicates, while the inclusion
        switch is the way to keep a bulb out of the sync.
        """
        ip = str(ip or "").strip()
        with self.lock:
            if ip not in self.config["lights"]:
                raise ValueError("unknown light")
            entry = self.config["lights"].pop(ip)
            groups = {}
            for name, members in self.config["groups"].items():
                keep = [member for member in members if member != ip]
                if keep:
                    groups[name] = keep
            self.config["groups"] = groups
            self.live.pop(ip, None)
            self.reachable.discard(ip)
            self._power.pop(ip, None)
            self._no_power.discard(ip)
            self._power_misses.pop(ip, None)
            self._persist()
        label = entry.get("name") or ip
        self.session.write_log(f"forgot light {label} ({ip})")
        if self.session.running():
            self.restart()
        return self.snapshot()

    def set_group(self, payload: dict) -> dict:
        """Create, rename, update or delete a room.

        Rooms only steer direct control, so changing one never restarts the
        sync. A rename is one request: `previous` names the old key.
        """
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        name = "".join(
            ch for ch in str(payload.get("name") or "") if ch.isprintable()
        ).strip()[:40]
        if not name:
            raise ValueError("give the room a name")
        previous = "".join(
            ch for ch in str(payload.get("previous") or "") if ch.isprintable()
        ).strip()[:40]
        with self.lock:
            groups = json.loads(json.dumps(self.config["groups"]))
            if payload.get("delete"):
                if name not in groups:
                    raise ValueError("unknown room")
                groups.pop(name, None)
            else:
                raw_ips = payload.get("ips")
                if not isinstance(raw_ips, list):
                    raise ValueError("ips must be a list")
                members = []
                for ip in raw_ips:
                    ip = str(ip).strip()
                    if ip in self.config["lights"] and ip not in members:
                        members.append(ip)
                if not members:
                    raise ValueError("a room needs at least one light")
                if previous and previous != name:
                    groups.pop(previous, None)
                groups[name] = members
            self.config["groups"] = groups
            self._persist()
        return self.snapshot()

    def save_color(self, payload: dict) -> dict:
        """Add or remove a saved color without touching the running sync."""
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        value = str(payload.get("hex") or "").strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            raise ValueError("use a hex color like #ff8800")
        try:
            brightness = max(10, min(100, int(payload.get("brightness", 100))))
        except (TypeError, ValueError):
            raise ValueError("brightness must be a number between 10 and 100")
        with self.lock:
            colors = [dict(color) for color in self.config["colors"]]
            if payload.get("remove"):
                colors = [color for color in colors if color["hex"] != value]
            else:
                match = next((color for color in colors if color["hex"] == value), None)
                if match is not None:
                    match["brightness"] = brightness
                else:
                    colors.append({"hex": value, "brightness": brightness})
                    colors = colors[-12:]
            self.config["colors"] = colors
            self._persist()
        return self.snapshot()

    def restart(self) -> None:
        was_running = self.session.running()
        self.session.stop()
        if was_running:
            self.start()

    def start(self, argv=None) -> dict:
        self._cancel_crazy()
        with self.lock:
            config = json.loads(json.dumps(self.config))
        if argv is None:
            argv, _ips, _zones = build_command(config, self.core, demo=self.demo)
        self.session.start(argv)
        return self.snapshot()

    def stop(self) -> dict:
        self.session.stop()
        return self.snapshot()

    # -- direct control --------------------------------------------------- #

    def _target_ips(self, target: str):
        target = str(target or "all")
        with self.lock:
            if target.startswith("group:"):
                name = target[len("group:"):]
                ips = list(self.config["groups"].get(name, []))
                if not ips:
                    raise ValueError("unknown room")
                return ips
            if target in ("all", "enabled"):
                pairs = enabled_lights(self.config) if target == "enabled" else None
                if pairs is not None:
                    return [ip for ip, _ in pairs]
                ips = list(self.config["lights"])
                ips.extend(ip for ip in self.live if ip not in self.config["lights"])
                return ips
            return [self._known_ip(target)]

    def _apply_live(self, ip: str, params: dict, power=None) -> None:
        with self.lock:
            info = self.live.setdefault(ip, {})
            if power is False:
                info["state"] = False
                return
            if "r" in params:
                info["r"] = params["r"]
                info["g"] = params.get("g", 0)
                info["b"] = params.get("b", 0)
                info.pop("temp", None)
            if "temp" in params:
                info["temp"] = params["temp"]
                for channel in ("r", "g", "b"):
                    info.pop(channel, None)
            if "dimming" in params:
                info["dimming"] = params["dimming"]
            if "sceneId" in params:
                info["sceneId"] = params["sceneId"]
                if "speed" in params:
                    info["speed"] = params["speed"]
            if params or power is True:
                info["state"] = True

    def _unreachable_note(self, ips) -> str:
        networks = self.core.local_ipv4_networks()
        where = (
            ", ".join(f"{address}/{prefix}" for address, prefix in networks)
            or "no active IPv4 network"
        )
        return (
            f"No reply from {', '.join(ips)}. This computer is on {where}; "
            "check that the bulb is powered and on the same Wi-Fi/VLAN."
        )

    # -- crazy mode ------------------------------------------------------- #

    def crazy_status(self) -> dict:
        thread = self._crazy_thread
        active = (
            thread is not None
            and thread.is_alive()
            and self._crazy_until > time.time()
        )
        return {
            "active": active,
            "remaining": round(max(0.0, self._crazy_until - time.time()), 1)
            if active
            else 0.0,
            "target": self._crazy_target,
            "max_hz": CRAZY_MAX_HZ,
        }

    def _cancel_crazy(self) -> None:
        with self.lock:
            stop = self._crazy_stop
            self._crazy_until = 0.0
        if stop is not None:
            stop.set()

    def stop_crazy(self) -> dict:
        self._cancel_crazy()
        return self.snapshot()

    def start_crazy(self, target: str = "all", seconds=CRAZY_SECONDS, hz=CRAZY_HZ) -> dict:
        """Stream a rainbow and a brightness sweep, then restore the bulbs."""
        resume = False
        if self.session.running():
            # Attach mode can be paused and resumed without losing the movie.
            # Launch mode owns mpv, so stopping it would close the player.
            if self.session.mode == "attach":
                self.session.stop()
                resume = True
            else:
                raise ValueError("stop the player first — crazy mode needs the bulbs")
        ips = self._target_ips(target)
        if not ips:
            raise ValueError("no lights available")
        restore = {}
        if not self.demo:
            # One short getPilot pass, then put the bulbs back after the burst.
            probes = self.core.query_lights(ips, "getPilot", timeout=0.45)
            restore = {
                ip: params
                for ip, info in probes.items()
                if (params := restore_params(info))
            }
        seconds = max(2.0, min(30.0, float(seconds)))
        # Cap the rate: above ~20 updates/s the bulb radio starts losing
        # packets, which looks like stutter rather than more speed.
        hz = max(1.0, min(CRAZY_MAX_HZ, float(hz)))
        self._cancel_crazy()
        stop = threading.Event()
        thread = threading.Thread(
            target=self._crazy_loop,
            args=(ips, seconds, hz, stop, restore),
            name="wiz-crazy",
            daemon=True,
        )
        with self.lock:
            self._crazy_stop = stop
            self._crazy_thread = thread
            self._crazy_target = str(target)
            self._crazy_until = time.time() + seconds
            self._crazy_restore = restore
            self._crazy_resume = resume
        thread.start()
        return self.snapshot()

    def _crazy_loop(self, ips, seconds, hz, stop, restore=None) -> None:
        sender = self.core.WizSender(
            dry_run=self.demo,
            white_leds=bool(self.config.get("white_leds")),
        )
        started = time.monotonic()
        step = 0
        try:
            while not stop.is_set():
                elapsed = time.monotonic() - started
                if elapsed >= seconds:
                    break
                for index, ip in enumerate(ips):
                    params = crazy_frame(elapsed, seconds, index)
                    if step == 0:
                        params["state"] = True
                    sender.set_pilot(ip, params)
                step += 1
                stop.wait(1.0 / hz)
            if not stop.is_set():
                # Never leave a bulb at the dim end of the sweep if the state
                # snapshot was unavailable.
                for ip in ips:
                    sender.set_pilot(ip, {"r": 255, "g": 190, "b": 17, "dimming": 100})
        finally:
            for ip, params in (restore or {}).items():
                sender.set_pilot(ip, params)
            sender.close()
            resume = False
            with self.lock:
                if self._crazy_stop is stop:
                    self._crazy_thread = None
                    self._crazy_until = 0.0
                    self._crazy_restore = {}
                    resume = self._crazy_resume
                    self._crazy_resume = False
            if resume and not self._closing:
                try:
                    self.start()
                except (ValueError, OSError) as exc:
                    self.session.write_log(f"crazy: could not resume the sync: {exc}")

    def crazy(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        if payload.get("stop") or self.crazy_status()["active"]:
            return self.stop_crazy()
        return self.start_crazy(str(payload.get("target") or "all"))

    def control(self, target: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("expected a JSON object")
        ips = self._target_ips(target)
        if not ips:
            raise ValueError("no lights available")

        params = {}
        if payload.get("hex"):
            r, g, b = self.core.hex_to_rgb(payload["hex"])
            params.update({"r": r, "g": g, "b": b})
        if payload.get("temp") is not None:
            if "r" in params:
                raise ValueError("choose a color or a white temperature, not both")
            params["temp"] = max(2200, min(6500, int(payload["temp"])))
        if payload.get("brightness") is not None:
            params["dimming"] = max(10, min(100, int(payload["brightness"])))
        if payload.get("scene") is not None:
            scene_id = int(payload["scene"])
            if not 1 <= scene_id <= 999:
                raise ValueError("scene id out of range")
            params["sceneId"] = scene_id
            if payload.get("speed") is not None:
                params["speed"] = max(20, min(200, int(payload["speed"])))
        if payload.get("speed") is not None and "sceneId" not in params:
            raise ValueError("pick a scene before setting its speed")

        power = payload.get("power")
        if power is not None and not isinstance(power, bool):
            raise ValueError("power must be true or false")
        if power is False and params:
            raise ValueError("turn off cannot be combined with color or brightness")
        if not params and power is None:
            raise ValueError("nothing to change")

        commands = []
        white_leds = bool(self.config.get("white_leds"))
        for ip in ips:
            if power is False:
                commands.append((ip, "setState", {"state": False}))
                continue
            if params:
                outgoing = dict(params)
                if power is True:
                    outgoing["state"] = True
                if white_leds:
                    outgoing = self.core.white_led_params(outgoing)
                commands.append((ip, "setPilot", outgoing))
            else:
                commands.append((ip, "setState", {"state": True}))

        if self.demo:
            for ip, method, outgoing in commands:
                print(f"{ip} {method} {outgoing}", flush=True)
            acked = {ip for ip, _method, _params in commands}
        else:
            acked = set(self.core.send_commands(commands, timeout=0.9))
            silent = [ip for ip, _method, _params in commands if ip not in acked]
            if silent:
                # Not every firmware acknowledges a write. A getPilot reply
                # still proves the bulb is reachable and the packet left here.
                probes = self.core.query_lights(silent, "getPilot", timeout=0.8)
                with self.lock:
                    for ip, info in probes.items():
                        if isinstance(info, dict):
                            self.live.setdefault(ip, {}).update(info)
                acked |= set(probes)

        with self.lock:
            for ip, _method, outgoing in commands:
                if ip not in acked:
                    self.reachable.discard(ip)
                    continue
                self.reachable.add(ip)
                if outgoing.get("state") is False and len(outgoing) == 1:
                    self._apply_live(ip, {}, power=False)
                else:
                    self._apply_live(ip, params, power=power)

        missing = [ip for ip, _method, _params in commands if ip not in acked]
        snapshot = self.snapshot()
        if missing:
            snapshot["warning"] = self._unreachable_note(missing)
        return snapshot

    def _scene_from_live(self):
        entries = {}
        with self.lock:
            for ip in self.config["lights"]:
                info = self.live.get(ip)
                if not info:
                    continue
                params = {}
                if "state" in info:
                    params["state"] = bool(info["state"])
                if info.get("sceneId") is not None:
                    params["sceneId"] = int(info["sceneId"])
                    if info.get("speed") is not None:
                        params["speed"] = max(20, min(200, int(info["speed"])))
                else:
                    rgb = self.core.pilot_rgb(info)
                    if rgb:
                        for channel, value in zip(("r", "g", "b"), rgb):
                            params[channel] = value
                    elif info.get("temp") is not None:
                        params["temp"] = max(2200, min(6500, int(info["temp"])))
                if info.get("dimming") is not None:
                    params["dimming"] = max(10, min(100, int(info["dimming"])))
                if len(params) > 1 or params.get("state") is False:
                    entries[ip] = params
        return entries

    def save_scene(self, name: str) -> dict:
        name = "".join(ch for ch in str(name or "") if ch.isprintable()).strip()[:40]
        if not name:
            raise ValueError("give the scene a name")
        entries = self._scene_from_live()
        if not entries:
            raise ValueError("no live lights to save")
        with self.lock:
            self.scenes[name] = entries
            if not self.demo:
                self.scenes = save_scenes(self.scenes)
        return self.snapshot()

    def apply_scene(self, name: str) -> dict:
        with self.lock:
            entries = self.scenes.get(str(name))
            if not entries:
                raise ValueError("unknown scene")
            entries = json.loads(json.dumps(entries))
            known = set(self.config["lights"]) | set(self.live)
            white_leds = bool(self.config.get("white_leds"))
        sender = self.core.WizSender(dry_run=self.demo, white_leds=white_leds)
        try:
            for ip, params in entries.items():
                if ip not in known:
                    continue
                if params.get("state") is False:
                    sender.set_power(ip, False)
                    self._apply_live(ip, {}, power=False)
                else:
                    sender.set_pilot(ip, dict(params))
                    self._apply_live(ip, params)
        finally:
            sender.close()
        return self.snapshot()

    def delete_scene(self, name: str) -> dict:
        with self.lock:
            if str(name) not in self.scenes:
                raise ValueError("unknown scene")
            self.scenes.pop(str(name), None)
            if not self.demo:
                self.scenes = save_scenes(self.scenes)
        return self.snapshot()

    def _known_ip(self, ip: str) -> str:
        """Only allow actions on bulbs this panel knows about."""
        ip = str(ip or "").strip()
        with self.lock:
            if ip not in self.config["lights"] and ip not in self.live:
                raise ValueError("unknown light")
        if not _IP_RE.match(ip):
            raise ValueError("invalid light address")
        return ip

    def identify(self, ip: str) -> None:
        ip = self._known_ip(ip)
        if self.demo:
            self.session.write_log(f"demo: identify {ip}")
            return
        info = dict(self.live.get(ip) or {})
        sender = self.core.WizSender(
            white_leds=bool(self.config.get("white_leds")),
        )
        try:
            sender.set_temp(ip, 4000, 100)
            time.sleep(0.45)
            state = bool(info.get("state", True))
            if state:
                if info.get("temp"):
                    sender.set_temp(ip, int(info["temp"]), int(info.get("dimming") or 100))
                elif all(channel in info for channel in ("r", "g", "b")):
                    sender.set_color(
                        ip,
                        (info["r"], info["g"], info["b"]),
                        int(info.get("dimming") or 100),
                    )
            else:
                sender.set_power(ip, False)
        finally:
            sender.close()

    def set_power(self, ip: str, on: bool) -> dict:
        return self.control(ip, {"power": bool(on)})

    def install_script(self) -> str:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = self.core.install_lua_script(True)
        text = buffer.getvalue().strip() or f"exit code {code}"
        self.session.write_log(text)
        return text


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/fonts/Merriweather-Bold.ttf": ("fonts/Merriweather-Bold.ttf", "font/ttf"),
}


class Handler(BaseHTTPRequestHandler):
    panel: Panel = None  # set by make_server
    server_version = f"wiz-ambilight/{getattr(sys.modules.get('mpv_ambilight'), 'VERSION', '?')}"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        port = self.panel.port
        return host in {
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            f"[::1]:{port}",
            "127.0.0.1",
            "localhost",
            "[::1]",
        }

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # non-browser clients still need the token
        allowed = {
            f"http://127.0.0.1:{self.panel.port}",
            f"http://localhost:{self.panel.port}",
        }
        return origin in allowed

    def _token_ok(self) -> bool:
        supplied = self.headers.get("X-Wiz-Token") or ""
        return secrets.compare_digest(supplied, self.panel.token)

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self._send(status, body, "application/json")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def do_GET(self):
        if not self._host_ok():
            self._error("bad host", 403)
            return
        path = urlparse(self.path).path
        if path == "/api/state":
            self.panel.maybe_scan()
            self.panel.maybe_power()
            self._json(self.panel.snapshot())
            return
        if path == "/api/meter":
            self._json(self.panel.meter())
            return
        target = STATIC_FILES.get(path)
        if target is None:
            self._error("not found", 404)
            return
        name, ctype = target
        try:
            body = (WEB_DIR / name).read_bytes()
        except OSError:
            self._error("missing web asset", 500)
            return
        if name == "index.html":
            body = body.replace(b"__WIZ_TOKEN__", self.panel.token.encode())
        self._send(200, body, ctype)

    def do_POST(self):
        if not self._host_ok():
            self._error("bad host", 403)
            return
        if not self._origin_ok():
            self._error("bad origin", 403)
            return
        if not self._token_ok():
            self._error("invalid token", 403)
            return
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._error("expected application/json", 415)
            return
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > 65536:
            self._error("payload too large", 413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._error("invalid JSON")
            return

        try:
            if path == "/api/config":
                self._json(self.panel.update_config(payload))
            elif path == "/api/light":
                self._json(
                    self.panel.set_light(str(payload.get("ip") or ""), payload)
                )
            elif path == "/api/light/delete":
                self._json(self.panel.delete_light(str(payload.get("ip") or "")))
            elif path == "/api/group":
                self._json(self.panel.set_group(payload))
            elif path == "/api/color":
                self._json(self.panel.save_color(payload))
            elif path == "/api/scan":
                count = self.panel.scan()
                snapshot = self.panel.snapshot()
                silent = [
                    row["ip"]
                    for row in snapshot["lights"]
                    if not row["online"] and row["enabled"]
                ]
                if silent:
                    snapshot["warning"] = self.panel._unreachable_note(silent)
                self._json({"found": count, **snapshot})
            elif path == "/api/start":
                self._json(self.panel.start())
            elif path == "/api/stop":
                self._json(self.panel.stop())
            elif path == "/api/control":
                self._json(
                    self.panel.control(str(payload.get("target") or "all"), payload)
                )
            elif path == "/api/scene/save":
                self._json(self.panel.save_scene(str(payload.get("name") or "")))
            elif path == "/api/scene/apply":
                self._json(self.panel.apply_scene(str(payload.get("name") or "")))
            elif path == "/api/scene/delete":
                self._json(self.panel.delete_scene(str(payload.get("name") or "")))
            elif path == "/api/pick-file":
                self._json({"path": pick_file()})
            elif path == "/api/identify":
                self.panel.identify(str(payload.get("ip") or ""))
                self._json({"ok": True})
            elif path == "/api/power":
                ip = str(payload.get("ip") or "")
                self._json(self.panel.set_power(ip, bool(payload.get("on"))))
            elif path == "/api/crazy":
                self._json(self.panel.crazy(payload))
            elif path == "/api/install-script":
                self._json({"message": self.panel.install_script(), **self.panel.snapshot()})
            elif path == "/api/quit":
                self._json({"ok": True})
                self.panel._closing = True
                self.panel._cancel_crazy()
                self.panel.stop()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._error("not found", 404)
        except ValueError as exc:
            self._error(str(exc))
        except TypeError as exc:
            self._error(f"invalid value: {exc}")
        except OSError as exc:
            self._error(str(exc), 500)


def make_server(panel: Panel, port: int = DEFAULT_PORT):
    handler = type(
        "BoundHandler",
        (Handler,),
        {"panel": panel, "server_version": f"wiz-ambilight/{panel.core.VERSION}"},
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    panel.port = server.server_address[1]
    return server


# --------------------------------------------------------------------------- #
# Native file picker / entry point
# --------------------------------------------------------------------------- #


def pick_file() -> str:
    candidates = []
    if sys.platform == "darwin":
        candidates.append(
            [
                "osascript",
                "-e",
                'POSIX path of (choose file with prompt "Choose a video for Ambilight")',
            ]
        )
    candidates.extend(
        [
            [
                "zenity",
                "--file-selection",
                "--title=Choose a video for Ambilight",
                "--file-filter=Video files | *.mkv *.mp4 *.webm *.avi *.mov *.m4v *.ts *.m2ts",
                "--file-filter=All files | *",
            ],
            [
                "kdialog",
                "--getopenfilename",
                str(Path.home()),
                "video/*|Video files\n*|All files",
            ],
        ]
    )
    for argv in candidates:
        if not shutil.which(argv[0]):
            continue
        try:
            result = subprocess.run(
                argv, capture_output=True, text=True, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
        return ""
    return ""


def run(core, port: int = DEFAULT_PORT, demo: bool = False, open_browser: bool = True) -> int:
    if not (WEB_DIR / "index.html").exists():
        print(f"error: missing {WEB_DIR / 'index.html'}", file=sys.stderr)
        return 1

    panel = Panel(core, port=port, demo=demo)
    try:
        server = make_server(panel, port)
    except OSError as exc:
        print(f"error: cannot listen on 127.0.0.1:{port}: {exc}", file=sys.stderr)
        print("       try --gui-port with a free port", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Wiz Ambilight panel: {url}")
    print(f"config: {config_path()}")
    print("press Ctrl+C to quit")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        panel.stop()
        server.server_close()
    return 0
