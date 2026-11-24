#!/usr/bin/env python3
"""Receive lux readings from a sensor and write `lux.json` for Equalize.

No third-party packages: a small HTTP server takes `POST /lux` with
`{"lux": 42.5}`, validates it and atomically replaces the file the sync already
knows how to read. Any HTTP-capable device works, and so does `curl`:

    curl -X POST http://127.0.0.1:8766/lux -d '{"lux": 42.5}'

The bridge only writes one file. It never drives the bulbs, never talks to
mpv and holds no state beyond the last reading, so it can be restarted or
replaced without touching a running sync.

Security: the server binds to `0.0.0.0` by default so the ESP32 can reach it
over the LAN. Anyone who can reach the port can post a reading, which can only
change how bright Equalize makes the bulbs. Set `WIZ_LUX_TOKEN` (or
`--token`) and the matching `BRIDGE_TOKEN` in the sketch to require a shared
header; use `--host 127.0.0.1` when the sensor runs on the same machine.
"""

import argparse
import hmac
import json
import math
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 512
MAX_LUX = 65535.0  # BH1750 full scale; also the ceiling the sync accepts.
DEFAULT_PORT = 8766


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(base) / "wiz-ambilight"


def write_lux(path: Path, value: float) -> None:
    """Replace `path` atomically with `{"lux": value}` and mode 0600.

    The sync polls the mtime, so a half-written file must never be visible:
    write a sibling temporary file, then `os.replace` swaps it in one step.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"lux": round(value, 2)}, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_lux(body: bytes) -> float:
    """The reading in `body`, or ValueError with a short reason."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("body is not JSON")
    if not isinstance(payload, dict):
        raise ValueError("body is not a JSON object")
    value = payload.get("lux")
    if isinstance(value, bool):
        raise ValueError("lux must be a number")
    try:
        lux = float(value)
    except (TypeError, ValueError):
        raise ValueError("lux must be a number")
    if not math.isfinite(lux):
        raise ValueError("lux must be finite")
    if lux < 0.0 or lux > MAX_LUX:
        raise ValueError(f"lux must be between 0 and {MAX_LUX:g}")
    return lux


class Handler(BaseHTTPRequestHandler):
    server_version = "wiz-ambilight-lux/1.0"
    protocol_version = "HTTP/1.1"

    def _reply(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorised(self) -> bool:
        token = self.server.token
        if not token:
            return True
        supplied = self.headers.get("X-Lux-Token", "")
        return hmac.compare_digest(supplied.encode(), token.encode())

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self.close_connection = True
            self._reply(413, b'{"error":"bad length"}')
            return
        if length > MAX_BODY:
            # Drain a bounded amount first: replying before the client finishes
            # sending can reset the connection and lose the 413.
            self.rfile.read(min(length, 64 * 1024))
            self.close_connection = True
            self._reply(413, b'{"error":"bad length"}')
            return
        body = self.rfile.read(length)
        if self.path.split("?", 1)[0] != "/lux":
            self._reply(404, b'{"error":"not found"}')
            return
        if not self._authorised():
            self._reply(401, b'{"error":"bad token"}')
            return
        try:
            lux = parse_lux(body)
        except ValueError as error:
            self._reply(400, json.dumps({"error": str(error)}).encode())
            return
        try:
            write_lux(self.server.lux_path, lux)
        except OSError as error:
            self._reply(500, json.dumps({"error": str(error)}).encode())
            return
        if self.server.verbose:
            print(f"lux: {lux:.1f} -> {self.server.lux_path}", file=sys.stderr)
        self._reply(204)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.split("?", 1)[0] == "/healthz":
            self._reply(200, b'{"ok":true}\n')
        else:
            self._reply(404, b'{"error":"not found"}')

    def log_message(self, fmt, *args) -> None:
        if self.server.verbose:
            super().log_message(fmt, *args)


def default_port() -> int:
    try:
        return int(os.environ.get("WIZ_LUX_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Receive lux readings and write lux.json for WiZ Ambilight.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="address to bind (default: 0.0.0.0, reachable on the LAN)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port(),
        help=f"TCP port (default: $WIZ_LUX_PORT or {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="lux.json to write (default: $XDG_RUNTIME_DIR/wiz-ambilight/lux.json)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("WIZ_LUX_TOKEN", ""),
        help="shared secret required in X-Lux-Token (default: $WIZ_LUX_TOKEN)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="log every accepted reading and HTTP request",
    )
    args = parser.parse_args(argv)
    args.port = max(1, min(65535, args.port))
    args.path = Path(args.path) if args.path else runtime_dir() / "lux.json"
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.token = args.token
    server.lux_path = args.path
    server.verbose = args.verbose
    scheme = "http://"
    host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(
        f"lux bridge on {scheme}{host}:{server.server_address[1]}/lux -> "
        f"{args.path} "
        f"({'token required' if args.token else 'no token'})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
