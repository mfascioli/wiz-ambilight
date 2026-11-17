"""Tests for the local web panel (no bulbs, no browser)."""

import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mpv_ambilight as m  # noqa: E402
import webui  # noqa: E402


def make_config(**overrides):
    config = {
        "layout": "auto",
        "style": "hue",
        "brightness": 100,
        "mode": "attach",
        "media": "",
        "dry_run": False,
        "lights": {},
    }
    config.update(overrides)
    return config


class NormalizeTests(unittest.TestCase):
    def test_defaults(self):
        config = webui.normalize_config({}, m)
        self.assertEqual(config["style"], "hue")
        self.assertEqual(config["layout"], "auto")
        self.assertEqual(config["brightness"], 100)
        self.assertEqual(config["mode"], "attach")
        self.assertEqual(config["lights"], {})

    def test_rejects_bad_values(self):
        config = webui.normalize_config(
            {"style": "nope", "layout": "diagonal", "mode": "hack", "brightness": "x"},
            m,
        )
        self.assertEqual(config["style"], "hue")
        self.assertEqual(config["layout"], "auto")
        self.assertEqual(config["mode"], "attach")
        self.assertEqual(config["brightness"], 100)

    def test_clamps_brightness(self):
        self.assertEqual(webui.normalize_config({"brightness": 2}, m)["brightness"], 10)
        self.assertEqual(webui.normalize_config({"brightness": 900}, m)["brightness"], 100)

    def test_light_fields(self):
        config = webui.normalize_config(
            {
                "lights": {
                    "192.168.1.5": {
                        "name": "x" * 90,
                        "enabled": 0,
                        "zone": "sideways",
                        "mac": "D8:A0:11:54:F8:18",
                    },
                    "not-an-ip": {"name": "ignored"},
                }
            },
            m,
        )
        light = config["lights"]["192.168.1.5"]
        self.assertEqual(len(light["name"]), 40)
        self.assertFalse(light["enabled"])
        self.assertEqual(light["zone"], "")
        self.assertEqual(light["mac"], "d8a01154f818")
        self.assertNotIn("not-an-ip", config["lights"])

    def test_control_characters_are_stripped_from_names(self):
        config = webui.normalize_config(
            {"lights": {"192.168.1.5": {"name": "Sofa\n\x00glow"}}}, m
        )
        self.assertEqual(config["lights"]["192.168.1.5"]["name"], "Sofaglow")


class DiscoveryMergeTests(unittest.TestCase):
    def test_new_bulb_is_added(self):
        config = make_config()
        webui.merge_discovered(
            config,
            {"192.168.1.9": {"model": "ESP24", "firmware": "1.38", "mac": "aabbccddeeff"}},
        )
        self.assertIn("192.168.1.9", config["lights"])
        self.assertEqual(config["lights"]["192.168.1.9"]["model"], "ESP24")

    def test_mac_migration_keeps_name_and_zone(self):
        config = make_config(
            lights={
                "192.168.1.5": {
                    "name": "Sofa",
                    "enabled": False,
                    "zone": "left",
                    "model": "",
                    "mac": "d8a01154f818",
                    "firmware": "",
                }
            }
        )
        webui.merge_discovered(
            config,
            {"192.168.1.42": {"model": "ESP24", "mac": "d8a01154f818"}},
        )
        self.assertNotIn("192.168.1.5", config["lights"])
        moved = config["lights"]["192.168.1.42"]
        self.assertEqual(moved["name"], "Sofa")
        self.assertEqual(moved["zone"], "left")
        self.assertFalse(moved["enabled"])


class ZoneTests(unittest.TestCase):
    def test_zones_follow_layout(self):
        config = make_config(
            lights={
                "10.0.0.1": {"enabled": True},
                "10.0.0.2": {"enabled": True},
            }
        )
        self.assertEqual(webui.effective_zones(config, m), ["left", "right"])

    def test_explicit_zone_wins(self):
        config = make_config(
            lights={
                "10.0.0.1": {"enabled": True, "zone": "top"},
                "10.0.0.2": {"enabled": True, "zone": ""},
            }
        )
        self.assertEqual(webui.effective_zones(config, m), ["top", "right"])

    def test_disabled_lights_are_skipped(self):
        config = make_config(
            lights={
                "10.0.0.1": {"enabled": False},
                "10.0.0.2": {"enabled": True},
            }
        )
        self.assertEqual(webui.effective_zones(config, m), ["all"])

    def test_duplicate_zones_are_preserved(self):
        self.assertEqual(m.split_list("left,left,right"), ["left", "left", "right"])
        self.assertEqual(m.parse_lights("left,left,right"), ["left", "right"])


class CommandTests(unittest.TestCase):
    def test_attach_command(self):
        config = make_config(
            lights={
                "10.0.0.1": {"enabled": True},
                "10.0.0.2": {"enabled": True},
            }
        )
        argv, ips, zones = webui.build_command(config, m, demo=True)
        self.assertEqual(ips, ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(zones, ["left", "right"])
        self.assertIn("--attach", argv)
        self.assertIn("--dry-run", argv)
        self.assertEqual(argv[argv.index("--zones") + 1], "left,right")

    def test_launch_command_includes_media(self):
        config = make_config(mode="launch", media="/media/movie.mkv")
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(config, m)
        self.assertEqual(argv[-1], "/media/movie.mkv")
        self.assertNotIn("--attach", argv)

    def test_no_lights_is_an_error(self):
        with self.assertRaises(ValueError):
            webui.build_command(make_config(), m)

    def test_launch_without_media_is_an_error(self):
        config = make_config(mode="launch")
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        with self.assertRaises(ValueError):
            webui.build_command(config, m)

    def test_media_cannot_smuggle_mpv_options(self):
        config = make_config(mode="launch", media="--script=/tmp/evil.lua")
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        with self.assertRaises(ValueError):
            webui.build_command(config, m)

    def test_media_with_control_characters_is_rejected(self):
        config = make_config(mode="launch", media="movie.mkv\n--script=x")
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        with self.assertRaises(ValueError):
            webui.build_command(config, m)

    def test_identify_rejects_unknown_ip(self):
        panel = webui.Panel(m, demo=True)
        with self.assertRaises(ValueError):
            panel.identify("8.8.8.8")
        with self.assertRaises(ValueError):
            panel.set_power("8.8.8.8", True)


class DemoPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("WIZ_AMBILIGHT_GUI_CONFIG")
        os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = str(Path(self.tmp.name) / "lights.json")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("WIZ_AMBILIGHT_GUI_CONFIG", None)
        else:
            os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = self.old
        self.tmp.cleanup()

    def test_snapshot_shape(self):
        panel = webui.Panel(m, demo=True)
        snapshot = panel.snapshot()
        self.assertTrue(snapshot["demo"])
        self.assertEqual(snapshot["version"], m.VERSION)
        self.assertEqual(len(snapshot["lights"]), len(webui.DEMO_LIGHTS))
        self.assertIn("model", snapshot["lights"][0])
        self.assertEqual(snapshot["session"]["running"], False)
        self.assertIn("hue", snapshot["styles"])
        self.assertIn("fps", snapshot["style_details"]["hue"])
        self.assertTrue(snapshot["config_path"].endswith("lights.json"))

    def test_light_update_is_in_memory_only(self):
        panel = webui.Panel(m, demo=True)
        panel.set_light("10.0.0.11", {"name": "Desk", "zone": "left"})
        self.assertEqual(panel.config["lights"]["10.0.0.11"]["name"], "Desk")
        self.assertEqual(panel.config["lights"]["10.0.0.11"]["zone"], "left")
        self.assertFalse(Path(os.environ["WIZ_AMBILIGHT_GUI_CONFIG"]).exists())

    def test_demo_is_dry_run(self):
        panel = webui.Panel(m, demo=True)
        argv, _ips, _zones = webui.build_command(panel.config, m, demo=panel.demo)
        self.assertIn("--dry-run", argv)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("WIZ_AMBILIGHT_GUI_CONFIG")
        os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = str(Path(self.tmp.name) / "lights.json")
        self.panel = webui.Panel(m, demo=True)
        self.server = webui.make_server(self.panel, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.old is None:
            os.environ.pop("WIZ_AMBILIGHT_GUI_CONFIG", None)
        else:
            os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = self.old
        self.tmp.cleanup()

    def request(self, path, payload=None, headers=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        return urllib.request.urlopen(request, timeout=5)

    def auth_headers(self, extra=None):
        headers = {
            "Content-Type": "application/json",
            "Origin": self.base,
            "X-Wiz-Token": self.panel.token,
        }
        headers.update(extra or {})
        return headers

    def test_index_and_state(self):
        with self.request("/") as response:
            self.assertIn(b"Wiz Ambilight", response.read())
        with self.request("/api/state") as response:
            snapshot = json.loads(response.read())
        self.assertTrue(snapshot["demo"])

    def test_index_embeds_the_token(self):
        with self.request("/") as response:
            body = response.read()
        self.assertIn(self.panel.token.encode(), body)
        self.assertNotIn(b"__WIZ_TOKEN__", body)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    def test_config_post(self):
        with self.request(
            "/api/config", {"brightness": 55}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["config"]["brightness"], 55)

    def test_rejects_missing_token(self):
        headers = {"Content-Type": "application/json", "Origin": self.base}
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/config", {"brightness": 55}, headers)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 403)

    def test_rejects_wrong_origin(self):
        headers = self.auth_headers({"Origin": "http://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/config", {"brightness": 55}, headers)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 403)

    def test_rejects_wrong_host(self):
        headers = self.auth_headers({"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/config", {"brightness": 55}, headers)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 403)

    def test_get_rejects_wrong_host(self):
        headers = {"Host": "evil.example"}
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/state", headers=headers)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 403)

    def test_rejects_non_json(self):
        headers = self.auth_headers({"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/config", {"brightness": 55}, headers)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 415)

    def test_unknown_asset_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/../mpv_ambilight.py")
        caught.exception.close()
        self.assertEqual(caught.exception.code, 404)


class ConfigPermissionTests(unittest.TestCase):
    def test_config_file_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "lights.json"
            webui.write_json(path, {"lights": {}})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
