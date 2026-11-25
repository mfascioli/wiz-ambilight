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
import ipaddress
import json
import math
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

VERSION = "1.12.0"
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
        white_leds: bool = False,
    ):
        self.port = port
        self.dry_run = dry_run
        self.refresh = max(0.0, refresh)
        self.white_leds = bool(white_leds)
        self._seq = 0
        self._last = {}
        self._last_time = {}
        self._warned = set()
        self._sock = None
        # Cumulative counters for the panel's WiZ UDP graph. They only move
        # for real datagrams: dry-run never touches the network.
        self.bytes_sent = 0
        self.packets_sent = 0
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
            self.bytes_sent += len(payload)
            self.packets_sent += 1
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
        params = {
            "r": int(r),
            "g": int(g),
            "b": int(b),
            "dimming": int(dimming),
            "state": True,
        }
        if self.white_leds:
            params = white_led_params(params)
        sent = self._send(ip, "setPilot", params)
        if sent:
            self._last[ip] = key

    def set_power(self, ip: str, on: bool) -> None:
        self._last.pop(ip, None)
        self._send(ip, "setState", {"state": bool(on)})

    def set_pilot(self, ip: str, params: dict) -> bool:
        """Send direct controls (color, white, scene, brightness) to a bulb."""
        self._last.pop(ip, None)
        payload = dict(params)
        if self.white_leds:
            payload = white_led_params(payload)
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


def _interface_is_up(name: str) -> bool:
    """Best effort: ignore an interface whose carrier is down."""
    try:
        state = Path(f"/sys/class/net/{name}/operstate").read_text().strip()
    except OSError:
        return True
    return state in {"up", "unknown"}


def local_ipv4_networks():
    """Return (address, prefix) for active IPv4 interfaces, best effort."""
    networks = set()
    if sys.platform.startswith("linux"):
        import fcntl

        for _index, name in socket.if_nameindex():
            if name == "lo" or not _interface_is_up(name):
                continue
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                request = struct.pack("256s", name.encode()[:15])
                address = socket.inet_ntoa(
                    fcntl.ioctl(probe.fileno(), 0x8915, request)[20:24]
                )
                mask = socket.inet_ntoa(
                    fcntl.ioctl(probe.fileno(), 0x891B, request)[20:24]
                )
            except OSError:
                continue
            finally:
                probe.close()
            try:
                prefix = ipaddress.IPv4Network(f"{address}/{mask}", strict=False).prefixlen
            except ValueError:
                continue
            if prefix < 31:
                networks.add((address, prefix))

    if not networks:
        # Portable fallback: the address the default route would use.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
        except OSError:
            address = ""
        finally:
            probe.close()
        if address and not address.startswith("127."):
            networks.add((address, 24))
    return sorted(networks)


def broadcast_targets(networks) -> list:
    """Global broadcast plus the broadcast address of every local subnet."""
    targets = {"255.255.255.255"}
    for address, prefix in networks:
        try:
            network = ipaddress.IPv4Network(f"{address}/{prefix}", strict=False)
        except ValueError:
            continue
        if network.prefixlen <= 30:
            targets.add(str(network.broadcast_address))
    return sorted(targets)


def sweep_targets(networks) -> list:
    """Hosts of the local /24 (or smaller) around each interface address."""
    hosts = set()
    for address, prefix in networks:
        # Cap the sweep at /24: enough for home LANs, never 65k packets.
        try:
            network = ipaddress.IPv4Network(f"{address}/{max(24, prefix)}", strict=False)
        except ValueError:
            continue
        if network.num_addresses < 4:
            continue
        hosts.update(str(host) for host in network.hosts())
        hosts.discard(address)
    return sorted(hosts)


def discover_lights(timeout: float = 2.2, deep: bool = False) -> dict:
    """Broadcast getPilot and collect the bulbs that answer.

    Wi-Fi power saving and broadcast filtering lose replies often enough that a
    single probe is unreliable, so send a few and wait for a quiet period after
    the last answer. `deep=True` also probes every host in the local /24, which
    finds bulbs that ignore broadcast without needing to know their address.
    """
    networks = local_ipv4_networks()
    targets = broadcast_targets(networks)
    hosts = sweep_targets(networks) if deep else []
    payload = json.dumps(
        {"id": 1, "method": "getPilot", "params": {}}, separators=(",", ":")
    ).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    found = {}
    try:
        # Deep mode probes every host in the local /24. Resolving ARP for 250+
        # addresses can take seconds, so the sweep runs before the listen
        # window starts; otherwise the timeout expires while we are still
        # sending and only the first queued reply is read.
        for host in hosts:
            try:
                sock.sendto(payload, (host, DEFAULT_PORT))
            except OSError:
                pass

        deadline = time.monotonic() + timeout
        next_probe = 0.0
        probes_left = 3
        quiet_deadline = None
        while True:
            now = time.monotonic()
            if now >= deadline:
                break

            if probes_left and now >= next_probe:
                for target in targets:
                    try:
                        sock.sendto(payload, (target, DEFAULT_PORT))
                    except OSError:
                        pass
                probes_left -= 1
                next_probe = now + 0.35

            wait_until = deadline
            if quiet_deadline is not None:
                wait_until = min(wait_until, quiet_deadline)
            if probes_left:
                wait_until = min(wait_until, next_probe)
            sock.settimeout(max(0.02, wait_until - now))
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
                # Give slow bulbs a chance, but do not always burn the timeout.
                quiet_deadline = time.monotonic() + 0.7
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


def send_commands(commands, timeout: float = 0.7, port: int = DEFAULT_PORT) -> dict:
    """Send (ip, method, params) commands and collect the replies.

    Manual controls in the panel use this instead of fire-and-forget: a reply
    proves the bulb received the datagram, so the UI can tell "the bulb ignored
    it" apart from "the packet never left this computer".
    """
    if not commands:
        return {}
    targets = {ip for ip, _method, _params in commands}
    replies = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for index, (ip, method, params) in enumerate(commands, start=1):
            payload = json.dumps(
                {"id": index, "method": method, "params": params or {}},
                separators=(",", ":"),
            ).encode()
            try:
                sock.sendto(payload, (ip, port))
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
            # Match by address: some firmwares reuse their own request ids.
            if addr[0] in targets and "result" in message:
                replies[addr[0]] = message["result"]
    finally:
        sock.close()
    return replies


# --------------------------------------------------------------------------- #
# Color pipeline
# --------------------------------------------------------------------------- #


def clamp8(value: float) -> int:
    return max(0, min(255, int(round(value))))


def white_led_params(params: dict) -> dict:
    """Move the grey part of an RGB color to the bulb's white LEDs.

    The mapping follows cB-Sigma/wiz (Apache-2.0): the smallest channel is
    what red, green and blue have in common, so it is sent on both white
    LEDs instead of being mixed from the three colored ones. Whites come out
    cleaner and brighter; saturated colors are unchanged. Params without all
    of r, g and b are returned as a copy.
    """
    out = dict(params)
    if not all(channel in out for channel in ("r", "g", "b")):
        return out
    try:
        r, g, b = (int(out[channel]) for channel in ("r", "g", "b"))
    except (TypeError, ValueError):
        return out
    grey = max(0, min(255, min(r, g, b)))
    out.update(
        {
            "r": max(0, min(255, r - grey)),
            "g": max(0, min(255, g - grey)),
            "b": max(0, min(255, b - grey)),
            "c": grey,
            "w": grey,
        }
    )
    return out


def pilot_rgb(info: dict):
    """The RGB a getPilot result describes, with the white LEDs folded back.

    A bulb driven with the white-LED mapping can report r=g=b=0 and carry the
    grey part in `c` and `w`. Adding it back keeps swatches and saved scenes
    the color that was sent; a genuinely black bulb has c=w=0.
    """
    try:
        r, g, b = (int(info[channel]) for channel in ("r", "g", "b"))
    except (KeyError, TypeError, ValueError):
        return None
    try:
        grey = int(round(max(float(info.get("c") or 0), float(info.get("w") or 0))))
    except (TypeError, ValueError):
        grey = 0
    grey = max(0, min(255, grey))
    return tuple(max(0, min(255, channel + grey)) for channel in (r, g, b))


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


# --------------------------------------------------------------------------- #
# Reactive modes
# --------------------------------------------------------------------------- #

# "color" is the classic ambilight. The other modes layer one reaction on top
# of it; every one of them is scaled by --react-amount so `0` is a safe no-op.
REACTIONS = {
    "color": {
        "group": "video",
        "label": "Color — follow the picture",
        "hint": "The classic ambilight: each bulb copies its own zone.",
        "detail": (
            "Samples the frame and sends each bulb its own zone. Nothing is "
            "reacted to; this is the baseline look."
        ),
    },
    "equalize": {
        "group": "video",
        "label": "Equalize — hold the room brightness",
        "hint": "Bright scenes dim the bulbs and dark scenes lift them, slowly.",
        "detail": (
            "Measures the average brightness of the frame and slowly raises or "
            "lowers every bulb to hold the room near the target. Bright scenes "
            "dim, dark scenes lift; the correction is capped and never goes "
            "black."
        ),
    },
    "cut": {
        "group": "video",
        "label": "Cut flash — pulse on hard cuts",
        "hint": "A short flash when the picture cuts, at most six per minute.",
        "detail": (
            "A cut is one hard edit, not camera motion. When the whole frame "
            "jumps to a new scene, the bulbs flash at full brightness for a "
            "moment; between cuts they sit slightly dimmer so the flash reads "
            "as a pulse. Rate-limited."
        ),
    },
    "motion": {
        "group": "video",
        "label": "Motion — follow the action",
        "hint": "Still shots stay calm; movement adds brightness and punch.",
        "detail": (
            "Compares each zone with the previous frame. Still shots stay calm "
            "and slightly dim; movement adds brightness and saturation to the "
            "bulbs watching the action."
        ),
    },
    "duotone": {
        "group": "video",
        "label": "Duotone — dominant and complement",
        "hint": "Bulbs alternate the zone color and its opposite hue.",
        "detail": (
            "Even bulbs keep the sampled color, odd bulbs get the opposite hue. "
            "With two bulbs you get a complementary pair; with more, a striped "
            "duotone."
        ),
    },
    "beat": {
        "group": "audio",
        "label": "Beat — pulse on the beat",
        "hint": "Band hits slam the bulbs; the audio analyser runs only now.",
        "detail": (
            "Listens to the graphic EQ bands. Each bulb owns one band, or a "
            "group of bands, and slams to full brightness when that band jumps "
            "above its recent average and clears the threshold. With one bulb "
            "it pulses on the overall beat."
        ),
    },
    "vu": {
        "group": "audio",
        "label": "VU — EQ meter",
        "hint": "Each bulb follows its bands as a punchy level meter.",
        "detail": (
            "Turns the bulbs into a graphic-EQ pulse meter. Each bulb follows "
            "its assigned bands from the threshold to full, in the strongest "
            "band's color; the compressor curve and punch make the level pump. "
            "With one bulb it follows the overall volume and takes the color of "
            "the loudest band."
        ),
    },
}
REACTION_GROUPS = ("video", "audio")
AUDIO_REACTIONS = frozenset({"beat", "vu"})

# Legacy five-band layout, lowest first. A `Reaction` built without an explicit
# EQ (old tests, direct API users) keeps these five slices; the panel and CLI
# always pass a `react_eq` list of 2–16 bands with their own frequencies.
BANDS = ("sub", "low", "low-mid", "mid", "high")
BAND_LABELS = {
    "sub": "Sub",
    "low": "Low",
    "low-mid": "Low-mid",
    "mid": "Mid",
    "high": "High",
}
DEFAULT_BAND_COLORS = (
    "#ff5a3c",
    "#fcbe11",
    "#7ad66b",
    "#38bdf8",
    "#a78bfa",
)
# A graphic EQ can use up to 16 analysis bands. The palette cycles after the
# five classic colours so every band still gets a distinct swatch.
BAND_COLOR_PALETTE = DEFAULT_BAND_COLORS + (
    "#f472b6",
    "#2dd4bf",
    "#fb923c",
    "#a3e635",
    "#67e8f9",
    "#c084fc",
    "#f87171",
    "#facc15",
    "#4ade80",
    "#60a5fa",
    "#e879f9",
)
MAX_BANDS = 16
MIN_BANDS = 2
DEFAULT_EQ_BANDS = 8
EQ_DEFAULT_Q = 1.4
# Detection shapes. `bell` is the gentle two-pole band the original analyser
# emulated; the cuts and the band pass reuse the same centre and Q but let the
# band isolate everything below or above it, or a steeper slice around it.
EQ_BAND_TYPES = ("bell", "bandpass", "lowpass", "highpass", "notch", "flat")
EQ_TYPE_LABELS = {
    "bell": "Bell",
    "bandpass": "Band pass",
    "lowpass": "Low cut",
    "highpass": "High cut",
    "notch": "Notch",
    "flat": "Flat",
}
EQ_SLOPES = (12, 24, 48)
EQ_DEFAULT_SLOPE = 24
EQ_GAIN_LIMIT = 18.0
EQ_FREQ_MIN = 20.0
EQ_FREQ_MAX = 20000.0
EQ_FREQ_LOW = 32.0
EQ_FREQ_HIGH = 16000.0
# Active-band detection ignores a band until it rises this far above its own
# slow noise floor, then holds it briefly so a drum hit does not flicker.
ACTIVE_MARGIN_DB = 4.0
ACTIVE_HOLD = 0.18
# Compressor auto modes, inspired by the SSL G bus and API 2500. They shape the
# envelope only; the audio leaves mpv untouched.
AUTO_MODES = {
    "off": "Off",
    "ssl": "SSL",
    "api": "API 2500",
    "hybrid": "Hybrid",
}
AUTO_HINTS = {
    "off": "Fixed attack and release from the knobs.",
    "ssl": "Program-dependent dual release: quick on hits, slow on sustained level.",
    "api": "Softer knee and a gentle low-end thrust, with a steadier release.",
    "hybrid": "SSL-style dual release with the API soft knee and low-end thrust.",
}
# Audio colours do not have to follow the per-band swatches. The mode picks
# where the colour comes from; `bands` keeps the old per-band behaviour.
AUDIO_COLOR_MODES = {
    "bands": "Bands",
    "spectrum": "Spectrum",
    "rainbow": "Rainbow",
    "range": "Color range",
    "level": "Level blend",
    "single": "Single color",
}
AUDIO_COLOR_HINTS = {
    "bands": "One bulb follows the mix; more bulbs split the EQ bands.",
    "spectrum": "A fixed spectral spread across the EQ bands.",
    "rainbow": "Hue drifts over time with an offset for every bulb.",
    "range": "Blend from the low color to the high color across the bands.",
    "level": "Blend from the soft color to the loud color as the level rises.",
    "single": "Every bulb uses one fixed color.",
}
DEFAULT_AUDIO_COLOR_A = "#fcbe11"
DEFAULT_AUDIO_COLOR_B = "#38bdf8"
PROFILE_LABELS = {
    "soft": "Soft",
    "balanced": "Balanced",
    "strong": "Strong",
}

# Room and TV defaults. The living room is 3.6 x 3.3 m with a 2.40 m ceiling
# (28.5 m3, 11.9 m2): two bulbs can dominate it, so every effect stays modest.
REACTION_TARGET = 0.45
REACTION_SPAN = 0.35
REACTION_FLOOR = 0.35
EQUALIZE_TAU = 4.0
# Optional measured-light input. A sensor bridge writes `lux.json` in the
# runtime directory; Auto Lux applies it as a brightness layer over any
# reaction while it is fresh and drops it when it goes stale. 65535 lx is the
# ceiling the bridge and the parser accept; the sketch clamps brighter sensors.
LUX_MAX = 65535.0
LUX_STALE_SECONDS = 5.0
LUX_TARGET = 50.0
LUX_TARGET_MAX = 5000.0
CUT_THRESHOLD = 0.22
CUT_SECONDS = 0.12
CUT_COOLDOWN = 1.5
CUT_PER_MINUTE = 6
CUT_SPAN = 0.22
MOTION_SPAN = 0.28
MOTION_TAU = 0.35
MOTION_DISTANCE = 0.12
BEAT_THRESHOLD_DB = 3.0
BEAT_COOLDOWN = 0.12
# `span` is the headroom kept between hits: 0.75 means the bulbs idle at 25 %
# of the configured brightness and the flash covers the rest. That gap is what
# makes the pulse read as a strobe instead of a tremble.
BEAT_SPAN = 0.75
VU_LOW_DB = -45.0
VU_HIGH_DB = -12.0
VU_SPAN = 1.0

# Audio dynamics, in the spirit of a bus compressor. `threshold` is the dBFS
# gate where the bulbs start to open, `attack` and `release` are the envelope
# in seconds, and `punch` is how hard the levels above the gate drive the
# brightness. A punch above 1 lifts the middle of the window, so a hit lands
# near full instead of halfway: that is what reads as a pulse.
AUDIO_THRESHOLD_DB = -18.0
AUDIO_ATTACK = 0.001
AUDIO_RELEASE = 0.055
AUDIO_PUNCH = 3.0
AUDIO_CEILING_DB = -6.0
# The gate must leave room to move. Without this floor, raising the threshold
# toward the ceiling collapses the window to a couple of dB and the bulbs turn
# into an on/off switch. The window only widens: a profile ceiling that is
# already farther away still wins.
AUDIO_WINDOW_DB = 12.0
# The balanced beat profile shares the audio envelope defaults.
BEAT_ATTACK = AUDIO_ATTACK
BEAT_RELEASE = AUDIO_RELEASE

# Named starting points for the threshold/attack/release/punch controls. The
# panel writes the four values when one is chosen; the CLI reaches the same
# place with --react-profile and the individual flags.
AUDIO_PRESETS = {
    "mellow": {
        "label": "Smooth",
        "threshold": -28.0,
        "attack": 12.0,
        "release": 200.0,
        "punch": 1.4,
        "hint": "Slow swells; the bulbs breathe with the track, no flashing.",
    },
    "glue": {
        "label": "Steady",
        "threshold": -24.0,
        "attack": 6.0,
        "release": 120.0,
        "punch": 2.0,
        "hint": "Even pulses that follow the mix without strobing.",
    },
    "punch": {
        "label": "Punchy",
        "threshold": -18.0,
        "attack": 1.0,
        "release": 55.0,
        "punch": 3.0,
        "hint": "Sharp hits on every beat; the default.",
    },
    "strobe": {
        "label": "Strobe",
        "threshold": -14.0,
        "attack": 0.0,
        "release": 30.0,
        "punch": 4.0,
        "hint": "Only the loudest hits flash; the most extreme.",
    },
}

# Audio follows a faster clock than the video capture. The analyser metadata
# changes on every audio frame, so a 30 Hz state file keeps kicks and meter
# movements from being rounded down to the frame rate. Video analysis still
# obeys the sampling profile; only the heartbeat is faster.
AUDIO_FPS = 30.0
# A sample peak this many dB above the RMS is treated as the current level.
# Pure RMS sounds smooth but hides the attack of a kick; pure peak saturates
# on every mastered track. Taking the hotter of the two keeps the punch.
AUDIO_PEAK_DB = 8.0

# Motion still uses the shared low-pass below. VU uses the asymmetric envelope
# in `Reaction.dimming`, so a hit reaches the bulb on the next send tick while
# the fall-back stays visible.
REACTION_SMOOTH = 0.08
# Audio-only files have no zone colour, so the bulbs hold this warm base while
# the beat or the VU meter drives their brightness.
REACTION_FALLBACK_RGB = (255, 190, 120)

# One profile id per intensity level, shared by every reaction that has
# profiles. The values replace the module defaults above; `react_amount`
# still scales the spans, so a profile and the strength knob compose.
REACTION_PROFILES = {
    "equalize": {
        "soft": {
            "span": 0.20,
            "tau": 6.0,
            "floor": 0.55,
            "hint": "Small, slow corrections; keeps the room's mood.",
        },
        "balanced": {
            "span": REACTION_SPAN,
            "tau": EQUALIZE_TAU,
            "floor": REACTION_FLOOR,
            "hint": "The default: visible correction without pumping.",
        },
        "strong": {
            "span": 0.55,
            "tau": 2.0,
            "floor": 0.20,
            "hint": "Large, fast corrections; the room tracks the scene.",
        },
    },
    "cut": {
        "soft": {
            "threshold": 0.30,
            "cooldown": 2.5,
            "per_minute": 3,
            "span": 0.15,
            "seconds": 0.10,
            "hint": "Only obvious cuts, with gentle headroom.",
        },
        "balanced": {
            "threshold": CUT_THRESHOLD,
            "cooldown": CUT_COOLDOWN,
            "per_minute": CUT_PER_MINUTE,
            "span": CUT_SPAN,
            "seconds": CUT_SECONDS,
            "hint": "Responsive without flashing on camera moves.",
        },
        "strong": {
            "threshold": 0.14,
            "cooldown": 0.8,
            "per_minute": 12,
            "span": 0.35,
            "seconds": 0.16,
            "hint": "Picks up small cuts and flashes harder.",
        },
    },
    "motion": {
        "soft": {
            "span": 0.18,
            "tau": 0.55,
            "distance": 0.18,
            "hint": "Subtle lift for movement.",
        },
        "balanced": {
            "span": MOTION_SPAN,
            "tau": MOTION_TAU,
            "distance": MOTION_DISTANCE,
            "hint": "The default balance of calm and punch.",
        },
        "strong": {
            "span": 0.40,
            "tau": 0.20,
            "distance": 0.07,
            "hint": "Action scenes drive the bulbs hard.",
        },
    },
    "beat": {
        "soft": {
            "threshold": 4.5,
            "cooldown": 0.28,
            "span": 0.55,
            "gate": -30.0,
            "high": -12.0,
            "attack": 0.012,
            "release": 0.20,
            "punch": 1.4,
            "hint": "Only clear hits; slow, rounded flashes with headroom.",
        },
        "balanced": {
            "threshold": BEAT_THRESHOLD_DB,
            "cooldown": BEAT_COOLDOWN,
            "span": BEAT_SPAN,
            "gate": AUDIO_THRESHOLD_DB,
            "high": AUDIO_CEILING_DB,
            "attack": AUDIO_ATTACK,
            "release": AUDIO_RELEASE,
            "punch": AUDIO_PUNCH,
            "hint": "The default: hard, short flashes on the beat.",
        },
        "strong": {
            "threshold": 1.5,
            "cooldown": 0.09,
            "span": 0.95,
            "gate": -14.0,
            "high": -2.0,
            "attack": 0.0,
            "release": 0.030,
            "punch": 4.0,
            "hint": "Sensitive, full-scale strobes on almost every hit.",
        },
    },
    "vu": {
        "soft": {
            "high": -12.0,
            "span": 0.70,
            "gate": -30.0,
            "attack": 0.012,
            "release": 0.20,
            "punch": 1.4,
            "hint": "Slow, rounded fades; the meter breathes with the track.",
        },
        "balanced": {
            "high": AUDIO_CEILING_DB,
            "span": VU_SPAN,
            "gate": AUDIO_THRESHOLD_DB,
            "attack": AUDIO_ATTACK,
            "release": AUDIO_RELEASE,
            "punch": AUDIO_PUNCH,
            "hint": "The default: a punchy −18…−6 dBFS pulse meter.",
        },
        "strong": {
            "high": -2.0,
            "span": 1.0,
            "gate": -14.0,
            "attack": 0.0,
            "release": 0.030,
            "punch": 4.0,
            "hint": "Full-scale, fast; quiet parts go dark and hits strobe.",
        },
    },
}


def finite_float(value):
    """A finite float, or None for missing, NaN and infinite values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_lux(path: Path, max_age=LUX_STALE_SECONDS):
    """Read `{"lux": 42.5}` from `path`, or None when it is missing or stale.

    The bridge owns the file; the sync only reads it. A malformed body, a
    boolean, a negative value or a value above `LUX_MAX` is treated exactly
    like a missing file, so a broken sensor never changes the look.
    """
    try:
        stat = path.stat()
        if max_age is not None and time.time() - stat.st_mtime > max_age:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("lux")
    if isinstance(value, bool):
        return None
    value = finite_float(value)
    if value is None or value < 0.0 or value > LUX_MAX:
        return None
    return value


def band_for(index: int, count: int, bands: int = len(BANDS)):
    """Which analysis band bulb `index` follows; None means overall.

    With more bulbs than bands the assignment repeats, so every bulb still has
    a band. With fewer bulbs the bands are spread from low to high.
    """
    bands = max(MIN_BANDS, min(MAX_BANDS, int(bands)))
    if count <= 1:
        return None
    if count > bands:
        return index % bands
    return int(round(index * (bands - 1) / (count - 1)))


def default_eq_freqs(count: int):
    """Log-spaced band centres between 32 Hz and 16 kHz."""
    count = max(MIN_BANDS, min(MAX_BANDS, int(count)))
    ratio = (EQ_FREQ_HIGH / EQ_FREQ_LOW) ** (1.0 / (count - 1))
    return [EQ_FREQ_LOW * ratio**index for index in range(count)]


def normalize_eq_bands(value, count=None):
    """Per-band frequency, shape, Q, slope, gain, lamp and solo flag.

    Bands are kept in frequency order so the panel's low-to-high palette and
    the legacy crossover fallback stay stable. A missing or malformed entry
    falls back to a log-spaced default at that position, so the rest of the
    curve never shifts. Unknown shapes become `bell`, and a slope snaps to the
    nearest of 12, 24 or 48 dB/oct.
    """
    raw = list(value) if isinstance(value, (list, tuple)) else []
    if count is None:
        count = len(raw) if raw else DEFAULT_EQ_BANDS
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = DEFAULT_EQ_BANDS
    count = max(MIN_BANDS, min(MAX_BANDS, count))
    defaults = default_eq_freqs(count)
    bands = []
    for index in range(count):
        item = raw[index] if index < len(raw) else None
        if not isinstance(item, dict):
            item = {}
        freq = finite_float(item.get("freq"))
        gain = finite_float(item.get("gain"))
        q = finite_float(item.get("q"))
        kind = (
            str(item.get("type") or "bell")
            .strip()
            .lower()
            .replace("-", "")
            .replace(" ", "")
        )
        if kind not in EQ_BAND_TYPES:
            kind = "bell"
        slope = finite_float(item.get("slope"))
        if slope is None:
            slope = EQ_DEFAULT_SLOPE
        elif slope >= 36:
            slope = 48
        elif slope >= 18:
            slope = 24
        else:
            slope = 12
        solo = item.get("solo") is True or item.get("solo") == 1
        try:
            lamp = int(item.get("lamp"))
        except (TypeError, ValueError):
            lamp = -1
        bands.append(
            {
                "freq": round(
                    max(
                        EQ_FREQ_MIN,
                        min(
                            EQ_FREQ_MAX,
                            freq if freq is not None else defaults[index],
                        ),
                    ),
                    2,
                ),
                "type": kind,
                "gain": round(
                    max(
                        -EQ_GAIN_LIMIT,
                        min(
                            EQ_GAIN_LIMIT,
                            gain if gain is not None else 0.0,
                        ),
                    ),
                    2,
                ),
                "q": round(max(0.4, min(8.0, q if q is not None else EQ_DEFAULT_Q)), 2),
                "slope": slope,
                "lamp": max(-1, lamp),
                "solo": solo,
            }
        )
    bands.sort(key=lambda band: band["freq"])
    return bands


def eq_splits(bands):
    """Crossover frequencies between adjacent EQ bands, lowest first.

    The boundary sits between the two bands' Q-derived edges. Equal Qs put it
    on the geometric mean of the centres; a narrower band keeps more of its
    own space. Values are nudged to stay strictly increasing for acrossover.
    """
    centers = [float(band["freq"]) for band in bands]
    splits = []
    for index in range(len(centers) - 1):
        first = max(0.4, float(bands[index].get("q", EQ_DEFAULT_Q)))
        second = max(0.4, float(bands[index + 1].get("q", EQ_DEFAULT_Q)))
        high = centers[index] * 2.0 ** (0.5 / first)
        low = centers[index + 1] * 2.0 ** (-0.5 / second)
        split = math.sqrt(max(1.0, high) * max(1.0, low))
        split = max(centers[index] * 1.001, min(centers[index + 1] * 0.999, split))
        split = max(EQ_FREQ_MIN, min(EQ_FREQ_MAX, split))
        if splits and split <= splits[-1]:
            split = splits[-1] * 1.001
        splits.append(round(split, 2))
    return splits


def eq_thrust_db(freq: float) -> float:
    """Gentle low-end de-emphasis used by the API-inspired auto modes."""
    if freq < 120.0:
        return -3.0
    if freq < 250.0:
        return -1.5
    return 0.0


def format_freq(value: float) -> str:
    """Compact frequency label for the EQ's band columns."""
    value = float(value)
    if value >= 1000.0:
        text = f"{value / 1000.0:.1f}".rstrip("0").rstrip(".")
        return f"{text}k"
    return f"{round(value)}"


def normalize_band_colors(value, count: int = len(BANDS)):
    """RGB triplets, in band order, from hex strings or RGB tuples.

    A missing or malformed entry falls back to that band's palette colour, so
    the remaining bands never shift position.
    """
    raw = list(value) if isinstance(value, (list, tuple)) else []
    count = max(MIN_BANDS, min(MAX_BANDS, int(count)))
    colors = []
    for index in range(count):
        item = raw[index] if index < len(raw) else None
        try:
            if isinstance(item, str):
                colors.append(hex_to_rgb(item))
            else:
                channels = tuple(int(channel) for channel in item)
                if len(channels) != 3:
                    raise ValueError
                colors.append(
                    tuple(max(0, min(255, channel)) for channel in channels)
                )
        except (TypeError, ValueError):
            colors.append(hex_to_rgb(BAND_COLOR_PALETTE[index % len(BAND_COLOR_PALETTE)]))
    return tuple(colors)


def normalize_audio_color(value, fallback=DEFAULT_AUDIO_COLOR_A):
    """One RGB triplet from a hex string or RGB tuple, with a safe fallback."""
    try:
        if isinstance(value, str):
            return hex_to_rgb(value)
        channels = tuple(int(channel) for channel in value)
        if len(channels) != 3:
            raise ValueError
        return tuple(max(0, min(255, channel)) for channel in channels)
    except (TypeError, ValueError):
        return hex_to_rgb(fallback)


def blend_rgb(first, second, ratio: float):
    """Linear blend between two RGB triplets; `ratio` 0 is first, 1 is second."""
    t = max(0.0, min(1.0, float(ratio)))
    return tuple(
        clamp8(a + (b - a) * t) for a, b in zip(first, second)
    )


def parse_band_colors(value, count: int = len(BANDS)):
    """Parse comma-separated hex colors for the configured band count."""
    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    count = max(MIN_BANDS, min(MAX_BANDS, int(count)))
    if len(parts) != count:
        raise ValueError(f"expected {count} comma-separated colors")
    return tuple(hex_to_rgb(part) for part in parts)


def scene_luma(rgb) -> float:
    """Rec. 709 luma of an RGB triplet, normalised to 0..1.

    The Lua script samples pixel colours; this mirrors the weights it uses for
    letterbox detection so Equalize and the edge crop agree on "bright".
    """
    r, g, b = (float(channel) for channel in rgb)
    return max(0.0, min(1.0, (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0))


def rgb_distance(first, second) -> float:
    """Mean absolute channel difference, 0..1. Used for cuts and motion."""
    a = [float(channel) for channel in first]
    b = [float(channel) for channel in second]
    if len(a) != 3 or len(b) != 3:
        return 0.0
    return sum(abs(a[index] - b[index]) for index in range(3)) / 765.0


def hue_shift(rgb, degrees: float):
    """Rotate the hue of an RGB triplet, keeping saturation and value."""
    r, g, b = (max(0.0, min(1.0, channel / 255.0)) for channel in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + float(degrees) / 360.0) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (clamp8(r * 255), clamp8(g * 255), clamp8(b * 255))


def hsv_rgb(hue: float, saturation: float = 0.9, value: float = 1.0):
    """An RGB triplet from a hue in turns, clamped to 0..255 channels."""
    r, g, b = colorsys.hsv_to_rgb(
        float(hue) % 1.0,
        max(0.0, min(1.0, float(saturation))),
        max(0.0, min(1.0, float(value))),
    )
    return (clamp8(r * 255), clamp8(g * 255), clamp8(b * 255))


def equalize_gain(
    luma: float,
    target: float = REACTION_TARGET,
    span: float = REACTION_SPAN,
    floor: float = REACTION_FLOOR,
) -> float:
    """Brightness multiplier that pulls a scene luma toward `target`.

    A bright scene (luma above target) returns a multiplier below 1 and a dark
    scene returns one above 1. The correction is capped at `±span` and never
    falls below `floor`, so the room cannot be driven to black.
    """
    target = max(0.05, min(0.95, float(target)))
    span = max(0.0, min(1.0, float(span)))
    floor = max(0.0, min(1.0, float(floor)))
    gain = target / max(0.04, float(luma))
    gain = max(1.0 - span, min(1.0 + span, gain))
    return max(floor, gain)


def lux_gain(
    lux: float,
    target: float = LUX_TARGET,
    span: float = REACTION_SPAN,
    floor: float = REACTION_FLOOR,
) -> float:
    """Brightness multiplier that pulls measured lux toward `target`.

    Same shape and limits as `equalize_gain`, but the ratio is illuminance:
    a room at half the target wants a 2x boost before the profile's span caps
    it. That cap (and the reaction strength) is what keeps the loop stable
    when the bulbs themselves contribute to the reading.
    """
    lux = max(0.1, min(LUX_MAX, float(lux)))
    target = max(1.0, min(LUX_TARGET_MAX, float(target)))
    span = max(0.0, min(1.0, float(span)))
    floor = max(0.0, min(1.0, float(floor)))
    gain = target / lux
    gain = max(1.0 - span, min(1.0 + span, gain))
    return max(floor, gain)


def vu_level(db, low: float = VU_LOW_DB, high: float = VU_HIGH_DB) -> float:
    """Map a negative dBFS value onto 0..1; silence and `None` are zero."""
    if db is None:
        return 0.0
    try:
        value = float(db)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def pulse_level(
    db,
    threshold: float = AUDIO_THRESHOLD_DB,
    ceiling: float = AUDIO_CEILING_DB,
    punch: float = AUDIO_PUNCH,
) -> float:
    """Map a dBFS level onto 0..1 with a gate and a punch curve.

    Below `threshold` the bulbs idle. The window up to `ceiling` reaches full
    scale, but it never shrinks below `AUDIO_WINDOW_DB`: a high gate keeps a
    usable range instead of turning the meter into an on/off switch. `punch`
    raises the middle of that window, so a hit lands near full instead of
    halfway; that is the difference between a smooth meter and a visible pulse.
    """
    value = finite_float(db)
    if value is None:
        return 0.0
    low = float(threshold)
    high = max(low + AUDIO_WINDOW_DB, float(ceiling))
    level = (value - low) / (high - low)
    level = max(0.0, min(1.0, level))
    return level ** (1.0 / max(1.0, float(punch)))


def hot_db(rms, peak, peak_db: float = AUDIO_PEAK_DB):
    """The hotter of RMS and sample peak, with a fixed peak headroom.

    RMS is the level people hear over a moment; the sample peak carries the
    attack of a kick or a snare. Subtracting `peak_db` before the comparison
    keeps a mastered track from sitting at full scale all the time.
    """
    rms = finite_float(rms)
    peak = finite_float(peak)
    values = []
    if rms is not None:
        values.append(rms)
    if peak is not None:
        values.append(peak - peak_db)
    return max(values) if values else None


def beat_pulse(
    age: float, attack: float = BEAT_ATTACK, release: float = BEAT_RELEASE
) -> float:
    """Envelope of one beat: a short attack ramp and a linear decay."""
    if age < 0.0:
        return 0.0
    if attack > 0.0 and age < attack:
        return age / attack
    if age <= attack + release:
        return 1.0 - (age - attack) / release if release > 0.0 else 0.0
    return 0.0


def cut_pulse(age: float, seconds: float = CUT_SECONDS) -> float:
    """A cut is a square flash: full brightness for `seconds`, then nothing."""
    return 1.0 if 0.0 <= age < seconds else 0.0


class Reaction:
    """State for one reactive mode, updated per frame and sampled per send.

    Video modes read `zones`; audio modes read the `audio` object the Lua
    script adds only while `beat` or `vu` is selected. Colour changes are made
    on the raw zone colours before saturation/gamma, brightness changes are
    applied per bulb at send time so short pulses are not lost between frames.
    """

    def __init__(
        self,
        mode: str = "color",
        amount: float = 0.8,
        target: float = REACTION_TARGET,
        profile: str = "balanced",
        bands=None,
        threshold=None,
        attack=None,
        release=None,
        punch=None,
        color_mode: str = "bands",
        color_a=None,
        color_b=None,
        eq=None,
        auto: str = "off",
        active_bands: bool = False,
        lux_target: float = LUX_TARGET,
        auto_lux: bool = False,
    ):
        self.mode = mode if mode in REACTIONS else "color"
        self.amount = max(0.0, min(1.0, float(amount)))
        self.target = max(0.05, min(0.95, float(target)))
        self.lux_target = max(1.0, min(LUX_TARGET_MAX, float(lux_target)))
        self.auto_lux = bool(auto_lux)
        self.profile = profile if profile in PROFILE_LABELS else "balanced"
        values = REACTION_PROFILES.get(self.mode, {}).get(self.profile, {})
        # Auto Lux is a layer over every reaction, so it always uses the
        # Equalize profile values: `cut` or `motion` spans would otherwise
        # change the ambient controller just by switching reactions.
        ambient = REACTION_PROFILES.get("equalize", {}).get(self.profile, {})
        self.lux_span = float(ambient.get("span", REACTION_SPAN))
        self.lux_tau = float(ambient.get("tau", EQUALIZE_TAU))
        self.lux_floor = float(ambient.get("floor", REACTION_FLOOR))
        self.audio = self.mode in AUDIO_REACTIONS
        if isinstance(eq, (list, tuple)) and eq:
            self.eq = normalize_eq_bands(eq, len(eq))
        else:
            # Direct Reaction users (and old tests) keep the classic five-band
            # layout; the panel and CLI always pass an explicit EQ.
            self.eq = normalize_eq_bands(None, len(BANDS))
        self.band_count = len(self.eq)
        self.band_colors = normalize_band_colors(bands, self.band_count)
        self.color_mode = color_mode if color_mode in AUDIO_COLOR_MODES else "bands"
        self.color_a = normalize_audio_color(color_a, DEFAULT_AUDIO_COLOR_A)
        self.color_b = normalize_audio_color(color_b, DEFAULT_AUDIO_COLOR_B)
        self.auto = auto if auto in AUTO_MODES else "off"
        self.active_bands = bool(active_bands)
        self.eq_span = float(values.get("span", REACTION_SPAN))
        self.eq_tau = float(values.get("tau", EQUALIZE_TAU))
        self.eq_floor = float(values.get("floor", REACTION_FLOOR))
        self.cut_threshold = float(values.get("threshold", CUT_THRESHOLD))
        self.cut_seconds = float(values.get("seconds", CUT_SECONDS))
        self.cut_cooldown = float(values.get("cooldown", CUT_COOLDOWN))
        self.cut_per_minute = int(values.get("per_minute", CUT_PER_MINUTE))
        self.cut_span = float(values.get("span", CUT_SPAN))
        self.motion_span = float(values.get("span", MOTION_SPAN))
        self.motion_tau = float(values.get("tau", MOTION_TAU))
        self.motion_distance = float(values.get("distance", MOTION_DISTANCE))
        self.beat_threshold = float(values.get("threshold", BEAT_THRESHOLD_DB))
        self.beat_cooldown = float(values.get("cooldown", BEAT_COOLDOWN))
        self.beat_span = float(values.get("span", BEAT_SPAN))
        self.beat_attack = float(values.get("attack", BEAT_ATTACK))
        self.beat_release = float(values.get("release", BEAT_RELEASE))
        self.vu_span = float(values.get("span", VU_SPAN))
        # The dynamics controls are explicit overrides: the CLI leaves them
        # unset so a profile still works, while the panel always sends values.
        self.audio_threshold = float(
            values.get("gate", AUDIO_THRESHOLD_DB) if threshold is None else threshold
        )
        self.audio_ceiling = float(values.get("high", AUDIO_CEILING_DB))
        self.audio_attack = float(
            values.get("attack", AUDIO_ATTACK) if attack is None else attack
        )
        self.audio_release = float(
            values.get("release", AUDIO_RELEASE) if release is None else release
        )
        self.audio_punch = float(
            values.get("punch", AUDIO_PUNCH) if punch is None else punch
        )
        self.last_frame_at = None
        self.luma = None
        self.lux = None
        self.lux_smoothed = None
        self.ambient_gain = 1.0
        self.gain = 1.0
        self.prev_all = None
        self.prev_zones = {}
        self.motion = {}
        self.cut_times = deque()
        self.flash_at = None
        self.last_cut_at = float("-inf")
        self.beat_base = None
        self.beat_at = None
        self.band_db = [None] * self.band_count
        self.band_peak_db = [None] * self.band_count
        self.band_levels = [0.0] * self.band_count
        self.band_bases = [None] * self.band_count
        self.band_at = [None] * self.band_count
        self.band_floor = [None] * self.band_count
        self.band_active_until = [0.0] * self.band_count
        self.pulse_at = {}
        self.assignments = {}
        self.levels = {}
        self.smoothed = {}
        self.vu_env = {}
        self.sustain = {}

    def _elapsed(self, now: float) -> float:
        if self.last_frame_at is None:
            self.last_frame_at = now
            return 0.0
        dt = max(0.0, min(1.0, now - self.last_frame_at))
        self.last_frame_at = now
        return dt

    def update(self, now: float, state: dict, raw_colors: dict, lights, zone_names):
        """Fold one mpv state snapshot into the reaction.

        `raw_colors` maps each bulb IP to the unadjusted zone colour and is
        updated in place by Duotone and by the audio band colours.
        """
        dt = self._elapsed(now)
        zones = state.get("zones") if isinstance(state.get("zones"), dict) else {}
        all_rgb = zones.get("all")
        if not isinstance(all_rgb, (list, tuple)):
            all_rgb = None
        audio = state.get("audio") if isinstance(state.get("audio"), dict) else {}

        # Auto Lux is a brightness layer over every reaction. A fresh reading
        # is smoothed with the Equalize profile's tau and applied in
        # `dimming()`; without one the layer is neutral and the mode runs as
        # usual (Equalize falls back to scene luma).
        self.ambient_gain = 1.0
        if self.auto_lux and self.lux is not None:
            if self.lux_smoothed is None:
                self.lux_smoothed = self.lux
            else:
                alpha = 1.0 - math.exp(-max(0.0, dt) / max(0.5, self.lux_tau))
                self.lux_smoothed += (self.lux - self.lux_smoothed) * alpha
            self.ambient_gain = lux_gain(
                self.lux_smoothed,
                self.lux_target,
                self.lux_span * self.amount,
                self.lux_floor,
            )
        else:
            self.lux_smoothed = None

        if self.mode == "equalize":
            if self.auto_lux and self.lux is not None:
                # Auto Lux owns brightness; the luma estimate would fight it.
                self.luma = None
                self.gain = 1.0
            elif all_rgb is not None:
                luma = scene_luma(all_rgb)
                if self.luma is None:
                    self.luma = luma
                else:
                    alpha = 1.0 - math.exp(-max(0.0, dt) / max(0.1, self.eq_tau))
                    self.luma += (luma - self.luma) * alpha
                self.gain = equalize_gain(
                    self.luma,
                    self.target,
                    self.eq_span * self.amount,
                    self.eq_floor,
                )

        elif self.mode == "cut" and all_rgb is not None:
            rgb = tuple(float(channel) for channel in all_rgb)
            if self.prev_all is not None:
                distance = rgb_distance(rgb, self.prev_all)
                while self.cut_times and now - self.cut_times[0] > 60.0:
                    self.cut_times.popleft()
                if (
                    distance >= self.cut_threshold
                    and now - self.last_cut_at >= self.cut_cooldown
                    and len(self.cut_times) < self.cut_per_minute
                ):
                    self.cut_times.append(now)
                    self.last_cut_at = now
                    self.flash_at = now
            self.prev_all = rgb

        elif self.mode == "motion":
            alpha = 1.0 - math.exp(-max(0.0, dt) / max(0.05, self.motion_tau))
            for ip, zone in zip(lights, zone_names):
                current = zone_color(zones, zone)
                previous = self.prev_zones.get(ip)
                distance = rgb_distance(current, previous) if previous else 0.0
                energy = max(
                    0.0, min(1.0, distance / max(0.01, self.motion_distance))
                )
                level = self.motion.get(ip, 0.0)
                self.motion[ip] = level + (energy - level) * alpha
                self.prev_zones[ip] = tuple(float(channel) for channel in current)

        elif self.mode == "duotone":
            for index, ip in enumerate(lights):
                rgb = raw_colors.get(ip)
                if rgb is not None and index % 2 == 1:
                    raw_colors[ip] = hue_shift(rgb, 180.0 * self.amount)

        elif self.mode == "beat":
            if self.amount > 0:
                self._read_audio(now, audio, raw_colors, lights, beat=True)

        elif self.mode == "vu":
            if self.amount > 0:
                self._read_audio(now, audio, raw_colors, lights, beat=False)

    def audio_color(self, band: int, level: float, now: float):
        """One bulb's colour for the selected audio colour mode."""
        band = max(0, min(self.band_count - 1, int(band)))
        mode = self.color_mode
        if mode == "bands":
            return self.band_colors[band]
        if mode == "spectrum":
            return hsv_rgb(band / self.band_count, 0.9, 1.0)
        if mode == "rainbow":
            # A full turn every ~12 seconds, offset so nearby bulbs differ.
            return hsv_rgb(now * 0.0833 + band / self.band_count, 0.9, 1.0)
        if mode == "range":
            return blend_rgb(
                self.color_a, self.color_b, band / max(1, self.band_count - 1)
            )
        if mode == "level":
            return blend_rgb(self.color_a, self.color_b, level)
        return self.color_a

    def _shape_bands(self, values, peaks):
        """Apply the graphic EQ's gain and API-style thrust.

        The shape itself is applied by the Lua analyser's filter bank: a bell,
        a band pass, a cut, a notch or a flat pass on a copy of the mix. This
        stage only offsets the detected level, so gain still never touches
        mpv's output.
        """
        gains = [float(band.get("gain", 0.0)) for band in self.eq]
        thrust = [
            eq_thrust_db(float(band.get("freq", 0.0)))
            if self.auto in ("api", "hybrid")
            else 0.0
            for band in self.eq
        ]

        def adjust(value, index):
            number = finite_float(value)
            if number is None:
                return None
            return number + gains[index] + thrust[index]

        shaped = [adjust(value, index) for index, value in enumerate(values)]
        adjusted_peaks = [
            adjust(value, index) for index, value in enumerate(peaks)
        ]
        return shaped, adjusted_peaks

    def _active_bands(self, now: float, values) -> list:
        """Bands that are currently above their own slow noise floor."""
        active = []
        for index, value in enumerate(values):
            number = finite_float(value)
            if number is None:
                active.append(False)
                continue
            floor = self.band_floor[index]
            if floor is None:
                floor = number
            elif number < floor:
                floor += (number - floor) * 0.35
            else:
                floor += (number - floor) * 0.02
            self.band_floor[index] = floor
            hot = (
                number >= self.audio_threshold
                and number - floor >= ACTIVE_MARGIN_DB
            )
            if hot:
                self.band_active_until[index] = now + ACTIVE_HOLD
            active.append(hot or now < self.band_active_until[index])
        return active

    def _read_audio(self, now, audio, raw_colors, lights, beat):
        """Read the EQ band levels, assign bands to bulbs and set colours.

        Both RMS and sample peak drive the meter and the detector. Peak is
        what makes a kick visible on the first state update instead of after
        the RMS window has filled; RMS keeps the level stable in between.
        """
        rms = finite_float(audio.get("rms"))
        if rms is None:
            rms = finite_float(audio.get("l"))
        peak = finite_float(audio.get("peak"))
        raw_bands = audio.get("bands")
        raw_peaks = audio.get("band_peaks")
        values = []
        peaks = []
        for source, target in ((raw_bands, values), (raw_peaks, peaks)):
            if isinstance(source, (list, tuple)):
                target.extend(
                    finite_float(value)
                    for value in list(source)[: self.band_count]
                )
            while len(target) < self.band_count:
                target.append(None)

        combined = [
            hot_db(value, band_peak) for value, band_peak in zip(values, peaks)
        ]
        if (
            rms is None
            and peak is None
            and all(value is None for value in combined)
        ):
            return
        combined, peaks = self._shape_bands(combined, peaks)
        self.band_db = combined
        self.band_peak_db = peaks

        active = (
            self._active_bands(now, combined)
            if self.active_bands
            else [True] * self.band_count
        )
        self.band_levels = [
            pulse_level(
                value,
                self.audio_threshold,
                self.audio_ceiling,
                self.audio_punch,
            )
            if active[index]
            else 0.0
            for index, value in enumerate(combined)
        ]

        soloed = tuple(
            index for index, band in enumerate(self.eq) if band.get("solo")
        )
        explicit = any(int(band.get("lamp", -1)) >= 0 for band in self.eq)
        assignments = {}
        for index, ip in enumerate(lights):
            if soloed:
                # Solo is a global override: every bulb follows the soloed
                # bands, regardless of their lamp assignments.
                assigned = soloed
            elif explicit:
                assigned = tuple(
                    band_index
                    for band_index, band in enumerate(self.eq)
                    if int(band.get("lamp", -1)) == index
                )
            else:
                band = band_for(index, len(lights), self.band_count)
                assigned = () if band is None else (band,)
            assignments[ip] = assigned
        self.assignments = assignments

        if soloed:
            band_hot = max(
                (
                    combined[index]
                    for index in soloed
                    if combined[index] is not None
                ),
                default=None,
            )
        else:
            band_hot = max(
                (value for value in combined if value is not None), default=None
            )
        overall_db = hot_db(rms, peak)
        if overall_db is None or soloed:
            overall_db = band_hot
        elif peak is None and band_hot is not None:
            # Older state files carry only per-band peaks. Let the loudest band
            # stand in for the missing overall peak instead of holding still.
            overall_db = max(overall_db, band_hot)
        overall = (
            pulse_level(
                overall_db,
                self.audio_threshold,
                self.audio_ceiling,
                self.audio_punch,
            )
            if overall_db is not None
            else max(self.band_levels)
        )
        if self.active_bands:
            # A dark band must also darken the one-bulb overall view.
            overall = (
                max((self.band_levels[index] for index in soloed), default=0.0)
                if soloed
                else max(self.band_levels)
            )
        dominant = max(
            soloed if soloed else range(self.band_count),
            key=lambda index: self.band_levels[index],
        )
        if beat:
            for index, value in enumerate(combined):
                self.band_bases[index], self.band_at[index] = self._transient(
                    now, value, self.band_bases[index], self.band_at[index]
                )
            self.beat_base, self.beat_at = self._transient(
                now, overall_db, self.beat_base, self.beat_at
            )
        for index, ip in enumerate(lights):
            assigned = assignments[ip]
            if assigned:
                active_assigned = [
                    band_index
                    for band_index in assigned
                    if active[band_index]
                ]
                if active_assigned:
                    level = sum(
                        self.band_levels[band_index]
                        for band_index in active_assigned
                    ) / len(active_assigned)
                    color_band = max(
                        active_assigned,
                        key=lambda band_index: self.band_levels[band_index],
                    )
                    pulses = [
                        self.band_at[band_index]
                        for band_index in active_assigned
                        if self.band_at[band_index] is not None
                    ]
                    pulse = max(pulses) if pulses else self.beat_at
                else:
                    level = 0.0
                    color_band = assigned[0]
                    pulse = self.beat_at
            else:
                level = overall
                color_band = dominant
                pulse = self.beat_at
            self.levels[ip] = level
            self.pulse_at[ip] = pulse
            raw_colors[ip] = self.audio_color(color_band, level, now)

    def _transient(self, now, value, base, at):
        """One band's beat detector: a jump over the running average."""
        if value is None:
            return base, at
        if base is None:
            return value, at
        if value < self.audio_threshold:
            # Track the quiet level so the next hit still reads as a jump.
            return base + (value - base) * 0.35, at
        if (
            value - base >= self.beat_threshold
            and (at is None or now - at >= self.beat_cooldown)
        ):
            # Re-seed the baseline so one loud hit does not retrigger itself.
            return value, now
        return base + (value - base) * 0.35, at

    def saturation(self, ip: str) -> float:
        """Per-bulb saturation multiplier applied before the style's boost."""
        if self.mode != "motion":
            return 1.0
        motion = self.motion.get(ip, 0.0)
        return max(0.2, 1.0 + 0.35 * self.amount * (motion - 0.5))

    def _auto_release(self, ip: str, dt: float, level: float) -> float:
        """Release time for the selected auto mode, updated per send tick."""
        sustain = self.sustain.get(ip, 0.0)
        if level > 0.05:
            sustain = min(2.0, sustain + max(0.0, dt))
        else:
            sustain = max(0.0, sustain - max(0.0, dt) * 2.0)
        self.sustain[ip] = sustain
        if self.auto == "api":
            return min(1.2, max(0.06, self.audio_release * 1.35))
        if self.auto in ("ssl", "hybrid"):
            # SSL-style dual release: a short time constant for hits, a long
            # one once the program has been compressed for a while.
            program = min(1.0, sustain / 0.9)
            fast = max(0.02, self.audio_release)
            slow = min(2.0, max(0.45, fast * 8.0))
            return fast + (slow - fast) * program
        return self.audio_release

    def _auto_level(self, target: float) -> float:
        """API-inspired soft knee: lift quiet detail instead of gating it."""
        if self.auto in ("api", "hybrid"):
            return max(0.0, min(1.0, target)) ** 0.85
        return target

    def dimming(self, ip: str, base: int, now: float, dt: float) -> int:
        """Per-bulb dimming for this send tick, including short pulses."""
        if self.mode == "equalize":
            mult = self.gain
        elif self.mode == "cut":
            steady = 1.0 - self.cut_span * self.amount
            age = now - self.flash_at if self.flash_at is not None else float("inf")
            mult = 1.0 if cut_pulse(age, self.cut_seconds) else steady
        elif self.mode == "motion":
            span = self.motion_span * self.amount
            mult = 1.0 - span + span * self.motion.get(ip, 0.0)
        elif self.mode == "beat":
            steady = 1.0 - self.beat_span * self.amount
            pulse_at = self.pulse_at.get(ip, self.beat_at)
            age = now - pulse_at if pulse_at is not None else float("inf")
            power = self.levels.get(ip, 0.0)
            release = self._auto_release(ip, dt, power)
            flash = beat_pulse(age, self.audio_attack, release)
            # Any solid hit reaches full brightness; the gate already rejects
            # quiet ticks, so the remaining level only tapers the softest.
            gain = min(1.0, 0.5 + power)
            mult = steady + (1.0 - steady) * flash * gain
        elif self.mode == "vu":
            span = self.vu_span * self.amount
            target = self._auto_level(
                1.0 - span + span * self.levels.get(ip, 0.0)
            )
            previous = self.vu_env.get(ip, target)
            release = self._auto_release(ip, dt, target)
            tau = self.audio_attack if target >= previous else release
            alpha = 1.0 - math.exp(-max(0.0, dt) / max(0.001, tau))
            mult = previous + (target - previous) * alpha
            self.vu_env[ip] = mult
        else:
            mult = 1.0

        if self.mode == "motion":
            alpha = 1.0 - math.exp(-max(0.0, dt) / REACTION_SMOOTH)
            previous = self.smoothed.get(ip, mult)
            mult = previous + (mult - previous) * alpha
            self.smoothed[ip] = mult
        # Auto Lux is the base brightness for every mode; reactions keep their
        # own pulses and headroom on top of it.
        mult *= self.ambient_gain
        return max(10, min(100, int(round(base * mult))))


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

# Sampling is deliberately separate from the style: the style chooses the
# look (fade, saturation, edge band, send rate), while these profiles choose
# how much of the frame is copied and averaged. Every profile is still
# resolution-aware: `auto` asks the Lua script to pick its grid, block size
# and fps cap from the size of the frame it actually captured.
SAMPLING_PROFILES = {
    "lean": {"grid": 48, "block": 1, "capture": "scaled", "fps_cap": 10.0},
    "balanced": {"grid": 80, "block": 2, "capture": "scaled", "fps_cap": 15.0},
    "quality": {"grid": 120, "block": 3, "capture": "video", "fps_cap": 30.0},
}
SAMPLING_CHOICES = ("auto", "lean", "balanced", "quality", "manual")


def resolve_sampling(args, explicit=None):
    """Fill the capture knobs from --sampling without touching the style.

    `explicit` marks flags the user typed by hand. An explicit --fps or
    --capture always wins over the profile, because it is the only way to
    escape the preset from the command line.
    """
    explicit = explicit or {}
    if args.sampling not in SAMPLING_CHOICES:
        args.sampling = "auto"
    profile = SAMPLING_PROFILES.get(args.sampling)
    if args.sampling == "manual":
        grid = args.sample_grid if args.sample_grid is not None else 80
        block = args.sample_block if args.sample_block is not None else 1
        capture = args.capture or "scaled"
    elif profile:
        grid = profile["grid"]
        block = profile["block"]
        capture = args.capture if explicit.get("capture") and args.capture else profile["capture"]
    else:
        # `auto` leaves zero sentinels: the Lua script resolves them from the
        # real capture size on every mpv instance.
        grid = 0
        block = 0
        capture = args.capture or "scaled"

    args.sample_grid = 0 if int(grid) <= 0 else max(24, min(240, int(grid)))
    args.sample_block = 0 if int(block) <= 0 else max(1, min(4, int(block)))
    args.capture = "video" if capture == "source" else capture
    if args.capture not in ("scaled", "video"):
        args.capture = "scaled"
    if profile and not explicit.get("fps"):
        args.fps = min(args.fps, profile["fps_cap"])
    return args


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
    sender = WizSender(
        dry_run=args.dry_run,
        white_leds=getattr(args, "white_leds", False),
    )
    smoother = Smoother(args.smooth / 1000.0)
    base_dimming = max(10, min(100, args.brightness))
    attack = getattr(args, "react_attack", None)
    release = getattr(args, "react_release", None)
    reaction = Reaction(
        getattr(args, "react", "color"),
        getattr(args, "react_amount", 0.8),
        getattr(args, "react_target", REACTION_TARGET),
        getattr(args, "react_profile", "balanced"),
        getattr(args, "react_bands", None),
        threshold=getattr(args, "react_threshold", None),
        attack=None if attack is None else attack / 1000.0,
        release=None if release is None else release / 1000.0,
        punch=getattr(args, "react_punch", None),
        color_mode=getattr(args, "react_color_mode", "bands"),
        color_a=getattr(args, "react_color_a", None),
        color_b=getattr(args, "react_color_b", None),
        eq=getattr(args, "react_eq", None),
        auto=getattr(args, "react_auto", "off"),
        active_bands=getattr(args, "react_active_bands", False),
        lux_target=getattr(args, "lux_target", LUX_TARGET),
        auto_lux=getattr(args, "auto_lux", False),
    )
    lux_path = (
        Path(args.lux_file)
        if getattr(args, "lux_file", None)
        else runtime_dir() / "lux.json"
    )
    # Audio envelopes are short: a 55 ms release at an 18 Hz send rate can be
    # missed between datagrams. Audio modes always push at 30 Hz, like the
    # `raw` style, while the style still controls the video-only rate.
    audio_send_hz = max(args.send_hz, AUDIO_FPS) if reaction.audio else args.send_hz
    send_interval = 1.0 / max(1.0, audio_send_hz)
    pid = os.getpid()
    stats_path = runtime_dir() / f"stats-{pid}.json"

    print(
        "lights: "
        + ", ".join(f"{ip} ({zone})" for ip, zone in zip(lights, zone_names)),
        file=sys.stderr,
    )
    print(
        f"style: {args.style} | capture: {args.fps:g} fps | edge {args.edge:.0%} | "
        f"smooth {args.smooth:g} ms | saturation {args.saturation:g}x | "
        f"dimming {base_dimming} | send {args.send_hz:g} Hz",
        file=sys.stderr,
    )
    if reaction.mode != "color":
        print(
            f"reaction: {reaction.mode} ({reaction.amount:.0%} amount"
            + (
                f", {reaction.profile} profile"
                if REACTION_PROFILES.get(reaction.mode)
                else ""
            )
            + (
                f", target luma {reaction.target:.2f}"
                if reaction.mode == "equalize"
                else ""
            )
            + ")",
            file=sys.stderr,
        )
    if reaction.auto_lux:
        print(
            f"auto lux: {lux_path} (target {reaction.lux_target:g} lx, "
            f"{LUX_STALE_SECONDS:g} s freshness; stale readings are ignored)",
            file=sys.stderr,
        )
    if getattr(args, "sampling", "auto") == "auto":
        sampling = "auto (scaled, resolution-aware grid and fps)"
    elif getattr(args, "sampling", "auto") == "manual":
        sampling = (
            f"manual ({args.capture} capture, {args.sample_grid} columns, "
            f"{args.sample_block}x{args.sample_block} blocks, {args.fps:g} fps)"
        )
    else:
        sampling = (
            f"{args.sampling} ({args.capture} capture, {args.sample_grid} columns, "
            f"{args.sample_block}x{args.sample_block} blocks, {args.fps:g} fps)"
        )
    print(f"sampling: {sampling}", file=sys.stderr)
    print(f"state: {state_path}", file=sys.stderr)

    targets = {}
    current = {}
    last_key = None
    last_tick = time.monotonic()
    last_send = 0.0
    last_error = None
    last_stats = time.monotonic()
    stats_bytes = sender.bytes_sent
    stats_packets = sender.packets_sent
    stats_frames = 0
    capture_size = (None, None)
    capture_video = (None, None)
    capture_source = None
    capture_grid = None
    last_state_at = None
    last_lux_check = 0.0

    def write_stats(now: float) -> None:
        nonlocal last_stats, stats_bytes, stats_packets, stats_frames
        elapsed = max(1e-6, now - last_stats)
        # mpv writes a frame or a 0.5 s heartbeat while it is alive. Once it
        # closes, the state file goes quiet; drop the size instead of showing
        # the resolution of a movie that is no longer loaded.
        fresh = last_state_at is not None and (now - last_state_at) < 3.0
        payload = {
            "pid": pid,
            "at": time.time(),
            "tx_bytes": sender.bytes_sent,
            "tx_packets": sender.packets_sent,
            "tx_bps": max(0.0, sender.bytes_sent - stats_bytes) / elapsed,
            "capture_fps": stats_frames / elapsed,
            "w": capture_size[0] if fresh else None,
            "h": capture_size[1] if fresh else None,
            "vw": capture_video[0] if fresh else None,
            "vh": capture_video[1] if fresh else None,
            "capture": capture_source if fresh else None,
            "grid": capture_grid,
            "sampling": getattr(args, "sampling", "auto"),
        }
        try:
            write_json_atomic(stats_path, payload)
        except OSError:
            pass
        last_stats = now
        stats_bytes = sender.bytes_sent
        stats_packets = sender.packets_sent
        stats_frames = 0

    try:
        while True:
            if stop_check is not None and stop_check():
                break

            now = time.monotonic()
            dt = min(0.25, max(0.0, now - last_tick))
            last_tick = now

            # The bridge writes at about 1 Hz; polling twice a second is
            # enough to notice a fresh or a stale reading without touching
            # the disk on every 3-6 ms fade pass.
            if reaction.auto_lux and now - last_lux_check >= 0.5:
                last_lux_check = now
                reaction.lux = read_lux(lux_path)

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
                    if isinstance(state.get("w"), int) and isinstance(state.get("h"), int):
                        if state["w"] > 0 and state["h"] > 0:
                            capture_size = (state["w"], state["h"])
                    if isinstance(state.get("vw"), int) and isinstance(state.get("vh"), int):
                        if state["vw"] > 0 and state["vh"] > 0:
                            capture_video = (state["vw"], state["vh"])
                    last_state_at = now
                    if isinstance(state.get("capture"), str):
                        capture_source = state["capture"]
                    if isinstance(state.get("grid"), int):
                        capture_grid = state["grid"]
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
                        audio = state.get("audio")
                        has_zones = isinstance(zones, dict)
                        # Audio-only files have no frame to sample, but their
                        # heartbeat still carries the analyser levels.
                        has_audio = reaction.audio and isinstance(audio, dict)
                        if has_zones or has_audio:
                            last_error = None
                            if has_zones:
                                stats_frames += 1
                            raw = {}
                            if has_zones:
                                for ip, zone in zip(lights, zone_names):
                                    raw[ip] = zone_color(zones, zone)
                            reaction.update(now, state, raw, lights, zone_names)
                            for ip in lights:
                                rgb = raw.get(ip)
                                if rgb is None:
                                    # No frame to sample: hold the base color
                                    # and let the audio reaction drive it.
                                    if ip in targets:
                                        continue
                                    rgb = REACTION_FALLBACK_RGB
                                targets[ip] = adjust_color(
                                    rgb,
                                    args.saturation * reaction.saturation(ip),
                                    args.gamma,
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
                # The reaction envelope must advance with the send tick, not
                # with the 3-6 ms polling loop: dimming() only runs when a
                # datagram is built, so the loop's dt would stretch a 140 ms
                # release into almost a second.
                send_dt = min(0.25, max(0.0, now - last_send))
                last_send = now
                for ip in lights:
                    cur = current.get(ip)
                    if cur is None:
                        continue
                    sender.set_color(
                        ip,
                        (clamp8(cur[0]), clamp8(cur[1]), clamp8(cur[2])),
                        reaction.dimming(ip, base_dimming, now, send_dt),
                    )

            if now - last_stats >= 1.0:
                write_stats(now)

            # Fast polling while a fade is in progress; idle polling otherwise.
            time.sleep(0.003 if moving else 0.006)
    finally:
        if args.on_exit == "off":
            for ip in lights:
                sender.set_power(ip, False)
        sender.close()
        try:
            stats_path.unlink()
        except OSError:
            pass


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
            "sampling": args.sampling,
            "grid_x": args.sample_grid,
            "sample": args.sample_block,
            "capture": args.capture,
            "react": args.react,
            "bands": eq_splits(args.react_eq),
            "eq": args.react_eq,
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
        "sampling": args.sampling,
        "grid_x": args.sample_grid,
        "sample": args.sample_block,
        "capture": args.capture,
        "react": args.react,
        "bands": eq_splits(args.react_eq),
        "eq": args.react_eq,
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
        ips = sorted(discover_lights(deep=True))
    if not ips:
        print("error: no WiZ lights found. Use --lights or set WIZ_LIGHTS.", file=sys.stderr)
        return 1

    sender = WizSender(
        dry_run=args.dry_run,
        white_leds=getattr(args, "white_leds", False),
    )
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
            "  ./mpv_ambilight.py --react equalize movie.mkv\n"
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
        "--react",
        default="color",
        choices=[*REACTIONS],
        help=(
            "how the lights react: color, equalize, cut, motion, duotone, "
            "beat or vu (default: color)"
        ),
    )
    parser.add_argument(
        "--react-amount",
        type=float,
        default=None,
        help="strength of the reaction, 0-1 (default: 0.8; 0 keeps the source only)",
    )
    parser.add_argument(
        "--react-target",
        type=float,
        default=None,
        help=(
            "equalize only: target scene luma, 0.05-0.95 (default: 0.45); "
            "ignored while Auto Lux has a fresh reading"
        ),
    )
    parser.add_argument(
        "--auto-lux",
        action="store_true",
        help=(
            "use the light sensor with any reaction: hold the room at "
            "--lux-target while a fresh reading exists"
        ),
    )
    parser.add_argument(
        "--lux-file",
        default=None,
        help=(
            "with --auto-lux: read measured lux from this JSON file "
            "(default: $XDG_RUNTIME_DIR/wiz-ambilight/lux.json)"
        ),
    )
    parser.add_argument(
        "--lux-target",
        type=float,
        default=None,
        help="with --auto-lux: target illuminance in lux, 1-5000 (default: 50)",
    )
    parser.add_argument(
        "--react-profile",
        default="balanced",
        choices=[*PROFILE_LABELS],
        help=(
            "reaction intensity profile: soft, balanced or strong "
            "(default: balanced)"
        ),
    )
    parser.add_argument(
        "--react-bands",
        default=None,
        help=(
            "band colors as #rrggbb,#rrggbb,... in low-to-high order; the count "
            "must match --react-eq-bands"
        ),
    )
    parser.add_argument(
        "--react-eq-bands",
        type=int,
        default=None,
        help=(
            f"audio EQ bands, {MIN_BANDS}-{MAX_BANDS} "
            f"(default: {DEFAULT_EQ_BANDS})"
        ),
    )
    parser.add_argument(
        "--react-eq",
        default=None,
        help=(
            "audio EQ as JSON: [{freq,gain,q,lamp},...], low to high; lamp is "
            "a 0-based index into the enabled bulbs, or -1 for auto"
        ),
    )
    parser.add_argument(
        "--react-auto",
        default="off",
        choices=[*AUTO_MODES],
        help=(
            "compressor auto behavior: off, ssl, api or hybrid "
            "(default: off)"
        ),
    )
    parser.add_argument(
        "--react-active-bands",
        action="store_true",
        help="audio modes: only bands above their own noise floor light a bulb",
    )
    parser.add_argument(
        "--react-color-mode",
        default="bands",
        choices=[*AUDIO_COLOR_MODES],
        help=(
            "audio color source: bands, spectrum, rainbow, range, level or "
            "single (default: bands)"
        ),
    )
    parser.add_argument(
        "--react-color-a",
        default=None,
        help=(
            "audio color A as #rrggbb: low end of range, soft of level or the "
            f"only color (default: {DEFAULT_AUDIO_COLOR_A})"
        ),
    )
    parser.add_argument(
        "--react-color-b",
        default=None,
        help=(
            "audio color B as #rrggbb: high end of range or loud of level "
            f"(default: {DEFAULT_AUDIO_COLOR_B})"
        ),
    )
    parser.add_argument(
        "--react-threshold",
        type=float,
        default=None,
        help="audio modes: dBFS gate where the bulbs start to open (-36 to 0)",
    )
    parser.add_argument(
        "--react-attack",
        type=float,
        default=None,
        help="audio modes: envelope attack in ms (0-200)",
    )
    parser.add_argument(
        "--react-release",
        type=float,
        default=None,
        help="audio modes: envelope release in ms (20-1000)",
    )
    parser.add_argument(
        "--react-punch",
        type=float,
        default=None,
        help="audio modes: how hard levels above the gate hit, 1-4",
    )
    parser.add_argument(
        "--sampling",
        default="auto",
        choices=SAMPLING_CHOICES,
        help=(
            "capture budget: auto adapts to the frame size; lean, balanced "
            "and quality trade detail for CPU; manual uses the flags below "
            "(default: auto)"
        ),
    )
    parser.add_argument(
        "--sample-grid",
        type=int,
        default=None,
        help="with --sampling manual: sample columns across the frame (24-240)",
    )
    parser.add_argument(
        "--sample-block",
        type=int,
        default=None,
        help="with --sampling manual: average an NxN block per cell (1-4)",
    )
    parser.add_argument(
        "--capture",
        choices=["auto", "scaled", "source"],
        default=None,
        help=(
            "with --sampling manual: scaled copies the window, source copies "
            "the decoded frame (default: scaled)"
        ),
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
        "--vibrance",
        type=float,
        default=None,
        help="multiply the style's saturation, 0-2 (1 = unchanged)",
    )
    parser.add_argument(
        "--gamma", type=float, default=None, help="output gamma (>1 brightens midtones)"
    )
    parser.add_argument(
        "--brightness", type=int, default=None, help="bulb dimming, 10-100"
    )
    parser.add_argument(
        "--white-leds",
        action="store_true",
        help="drive the bulb's white LEDs with the grey part of each color",
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
        found = discover_lights(deep=True)
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
        found = discover_lights(deep=True)
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
    explicit = {
        "fps": args.fps is not None,
        "capture": args.capture is not None,
    }
    preset = DEFAULT_STYLE if args.style == "custom" else STYLES[args.style]
    for name, value in preset.items():
        if getattr(args, name) is None:
            setattr(args, name, value)

    args.fps = max(1.0, min(30.0, args.fps))
    args.edge = max(0.02, min(0.45, args.edge))
    args.send_hz = max(1.0, min(30.0, args.send_hz))
    args.vibrance = 1.0 if args.vibrance is None else max(0.0, min(2.0, args.vibrance))
    args.saturation = max(0.0, min(4.0, args.saturation * args.vibrance))
    args.gamma = max(0.2, min(3.0, args.gamma))
    args.smooth = max(0.0, min(2000.0, args.smooth))
    args.brightness = max(10, min(100, args.brightness))
    if args.react not in REACTIONS:
        args.react = "color"
    args.react_amount = 0.8 if args.react_amount is None else args.react_amount
    args.react_amount = max(0.0, min(1.0, float(args.react_amount)))
    args.react_target = (
        REACTION_TARGET if args.react_target is None else args.react_target
    )
    args.react_target = max(0.05, min(0.95, float(args.react_target)))
    raw_eq = None
    if args.react_eq:
        try:
            raw_eq = json.loads(args.react_eq)
        except ValueError as error:
            parser.error(f"--react-eq: {error}")
        if not isinstance(raw_eq, list):
            parser.error("--react-eq: expected a JSON array")
    if args.react_eq_bands is None:
        count = len(raw_eq) if raw_eq else DEFAULT_EQ_BANDS
    else:
        count = args.react_eq_bands
    try:
        count = max(MIN_BANDS, min(MAX_BANDS, int(count)))
    except (TypeError, ValueError):
        parser.error("--react-eq-bands: expected a number")
    args.react_eq = normalize_eq_bands(raw_eq, count)
    args.react_eq_bands = count
    args.lux_target = LUX_TARGET if args.lux_target is None else args.lux_target
    args.lux_target = max(1.0, min(LUX_TARGET_MAX, float(args.lux_target)))
    if args.react_bands is None:
        args.react_bands = normalize_band_colors(None, count)
    else:
        try:
            args.react_bands = parse_band_colors(args.react_bands, count)
        except ValueError as error:
            parser.error(f"--react-bands: {error}")
    if args.react_threshold is not None:
        args.react_threshold = max(-36.0, min(0.0, float(args.react_threshold)))
    if args.react_attack is not None:
        args.react_attack = max(0.0, min(200.0, float(args.react_attack)))
    if args.react_release is not None:
        args.react_release = max(20.0, min(1000.0, float(args.react_release)))
    if args.react_punch is not None:
        args.react_punch = max(1.0, min(4.0, float(args.react_punch)))
    if args.react_color_mode not in AUDIO_COLOR_MODES:
        args.react_color_mode = "bands"
    for flag, default in (
        ("react_color_a", DEFAULT_AUDIO_COLOR_A),
        ("react_color_b", DEFAULT_AUDIO_COLOR_B),
    ):
        value = getattr(args, flag, None)
        if value is None:
            setattr(args, flag, hex_to_rgb(default))
        else:
            try:
                setattr(args, flag, hex_to_rgb(value))
            except ValueError as error:
                parser.error(f"--{flag.replace('_', '-')}: {error}")
    resolve_sampling(args, explicit)

    if args.attach:
        run_attach(args, lights, zone_names)
        return 0

    return run_launcher(args, lights, zone_names, mpv_extra)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
