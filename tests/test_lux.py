"""Tests for the optional lux bridge and the lux.json contract."""

import importlib.util
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lux_bridge", ROOT / "contrib" / "lux-bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class ParseTests(unittest.TestCase):
    def test_accepts_a_number_in_range(self):
        self.assertEqual(bridge.parse_lux(b'{"lux": 42.5}'), 42.5)
        self.assertEqual(bridge.parse_lux(b'{"lux": 0}'), 0.0)
        self.assertEqual(bridge.parse_lux(b'{"lux": 65535}'), 65535.0)

    def test_rejects_bad_bodies(self):
        for body in (
            b"",
            b"not json",
            b"[]",
            b"42",
            b'{"lux": true}',
            b'{"lux": -1}',
            b'{"lux": 70000}',
            b'{"lux": "bright"}',
            b'{"lux": null}',
        ):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    bridge.parse_lux(body)


class WriteTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX file modes are not reported on Windows")
    def test_file_is_private_and_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lux.json"
            bridge.write_lux(path, 42.5)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text()), {"lux": 42.5})
            bridge.write_lux(path, 10.0)
            self.assertEqual(json.loads(path.read_text()), {"lux": 10.0})
            self.assertEqual(
                [entry.name for entry in Path(tmp).iterdir()], ["lux.json"]
            )


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lux.json"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
        self.server.token = "secret"
        self.server.lux_path = self.path
        self.server.verbose = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def post(self, body, token="secret", path="/lux"):
        request = urllib.request.Request(
            self.url + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if token is not None:
            request.add_header("X-Lux-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code

    def test_a_token_protected_post_writes_the_file(self):
        self.assertEqual(self.post(b'{"lux": 12.5}'), 204)
        self.assertEqual(json.loads(self.path.read_text()), {"lux": 12.5})

    def test_wrong_or_missing_token_is_rejected(self):
        self.assertEqual(self.post(b'{"lux": 12.5}', token="nope"), 401)
        self.assertEqual(self.post(b'{"lux": 12.5}', token=None), 401)
        self.assertFalse(self.path.exists())

    def test_bad_body_is_rejected_and_leaves_the_file_alone(self):
        self.assertEqual(self.post(b'{"lux": 12.5}'), 204)
        before = self.path.read_text()
        self.assertEqual(self.post(b'{"lux": "x"}'), 400)
        self.assertEqual(self.path.read_text(), before)

    def test_oversize_or_missing_body_is_rejected(self):
        self.assertEqual(self.post(b"{" + b" " * 600 + b"}"), 413)
        self.assertEqual(self.post(b""), 413)
        self.assertFalse(self.path.exists())

    def test_unknown_path_and_health(self):
        self.assertEqual(self.post(b'{"lux": 1}', path="/other"), 404)
        with urllib.request.urlopen(self.url + "/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read()), {"ok": True})

    def test_an_empty_token_accepts_any_sender(self):
        self.server.token = ""
        self.assertEqual(self.post(b'{"lux": 7}', token=None), 204)


if __name__ == "__main__":
    unittest.main()
