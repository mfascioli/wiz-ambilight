"""Tests for the local web panel (no bulbs, no browser)."""

import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

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
        self.assertEqual(config["groups"], {})
        self.assertEqual(config["colors"], [])

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

    def test_vibrance_defaults_and_clamps(self):
        self.assertEqual(webui.normalize_config({}, m)["vibrance"], 1.0)
        self.assertEqual(webui.normalize_config({"vibrance": 0.5}, m)["vibrance"], 0.5)
        self.assertEqual(webui.normalize_config({"vibrance": 9}, m)["vibrance"], 2.0)
        self.assertEqual(webui.normalize_config({"vibrance": -1}, m)["vibrance"], 0.0)
        self.assertEqual(webui.normalize_config({"vibrance": "x"}, m)["vibrance"], 1.0)

    def test_audio_dynamics_defaults_and_clamps(self):
        config = webui.normalize_config({}, m)
        self.assertEqual(config["react_threshold"], m.AUDIO_THRESHOLD_DB)
        self.assertEqual(config["react_attack"], 1.0)
        self.assertEqual(config["react_release"], 55.0)
        self.assertEqual(config["react_punch"], m.AUDIO_PUNCH)
        self.assertEqual(
            webui.normalize_config({"react_threshold": -99}, m)["react_threshold"],
            -60.0,
        )
        self.assertEqual(
            webui.normalize_config({"react_threshold": 4}, m)["react_threshold"],
            0.0,
        )
        self.assertEqual(
            webui.normalize_config({"react_attack": -1}, m)["react_attack"], 0.0
        )
        self.assertEqual(
            webui.normalize_config({"react_release": 1}, m)["react_release"], 20.0
        )
        self.assertEqual(
            webui.normalize_config({"react_punch": 9}, m)["react_punch"], 4.0
        )
        self.assertEqual(
            webui.normalize_config({"react_punch": "x"}, m)["react_punch"], 3.0
        )

    def test_sampling_defaults_and_normalization(self):
        config = webui.normalize_config({}, m)
        self.assertEqual(config["sampling"], "auto")
        self.assertEqual(config["sampling_fps"], 15)
        self.assertEqual(config["sampling_grid"], 80)
        self.assertEqual(config["sampling_block"], 1)
        self.assertEqual(config["sampling_capture"], "auto")

        bad = webui.normalize_config(
            {
                "sampling": "ultra",
                "sampling_fps": 99,
                "sampling_grid": 5,
                "sampling_block": 9,
                "sampling_capture": "gpu",
            },
            m,
        )
        self.assertEqual(bad["sampling"], "auto")
        self.assertEqual(bad["sampling_fps"], 30)
        self.assertEqual(bad["sampling_grid"], 24)
        self.assertEqual(bad["sampling_block"], 4)
        self.assertEqual(bad["sampling_capture"], "auto")

    def test_known_sampling_profiles_survive(self):
        for profile in ("auto", "manual", *m.SAMPLING_PROFILES):
            with self.subTest(profile=profile):
                self.assertEqual(
                    webui.normalize_config({"sampling": profile}, m)["sampling"], profile
                )

    def test_reaction_defaults_and_normalization(self):
        config = webui.normalize_config({}, m)
        self.assertEqual(config["react"], "color")
        self.assertEqual(config["react_amount"], 0.8)
        self.assertEqual(config["react_target"], 0.45)
        self.assertEqual(config["react_profile"], "balanced")
        self.assertEqual(config["react_bands"], list(m.DEFAULT_BAND_COLORS))

        bad = webui.normalize_config(
            {
                "react": "strobe",
                "react_amount": 9,
                "react_target": "x",
                "react_profile": "extreme",
                "react_bands": ["#FF0000"],
            },
            m,
        )
        self.assertEqual(bad["react"], "color")
        self.assertEqual(bad["react_amount"], 1.0)
        self.assertEqual(bad["react_target"], 0.45)
        self.assertEqual(bad["react_profile"], "balanced")
        self.assertEqual(bad["react_bands"][0], "#ff0000")
        self.assertEqual(bad["react_bands"][1:], list(m.DEFAULT_BAND_COLORS[1:]))

        self.assertEqual(
            webui.normalize_config({"react_amount": -3}, m)["react_amount"], 0.0
        )
        self.assertEqual(
            webui.normalize_config({"react_target": 2}, m)["react_target"], 0.95
        )

    def test_every_reaction_survives_normalization(self):
        for reaction in m.REACTIONS:
            with self.subTest(reaction=reaction):
                self.assertEqual(
                    webui.normalize_config({"react": reaction}, m)["react"], reaction
                )

    def test_rooms_and_saved_colors_are_normalized(self):
        config = webui.normalize_config(
            {
                "lights": {"10.0.0.1": {}, "10.0.0.2": {}},
                "groups": {
                    "Desk": ["10.0.0.1", "10.0.0.9", "10.0.0.1"],
                    "Empty": [],
                    "  ": ["10.0.0.2"],
                    7: [],
                },
                "colors": [
                    "#ABCDEF",
                    "red",
                    "#abcdef",
                    {"hex": "#123456", "brightness": 35},
                    {"hex": "#12345", "brightness": 70},
                    {"hex": "#654321", "brightness": 900},
                    {"hex": "#abcdef", "brightness": 55},
                    {"brightness": 20},
                ],
            },
            m,
        )
        self.assertEqual(config["groups"], {"Desk": ["10.0.0.1"]})
        self.assertEqual(
            config["colors"],
            [
                {"hex": "#abcdef", "brightness": 55},
                {"hex": "#123456", "brightness": 35},
                {"hex": "#654321", "brightness": 100},
            ],
        )

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
        self.assertEqual(argv[argv.index("--sampling") + 1], "auto")

    def test_manual_sampling_passes_every_knob(self):
        config = make_config(
            sampling="manual",
            sampling_fps=12,
            sampling_grid=96,
            sampling_block=3,
            sampling_capture="source",
        )
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(config, m)
        self.assertEqual(argv[argv.index("--fps") + 1], "12")
        self.assertEqual(argv[argv.index("--sample-grid") + 1], "96")
        self.assertEqual(argv[argv.index("--sample-block") + 1], "3")
        self.assertEqual(argv[argv.index("--capture") + 1], "source")

    def test_reaction_flags_are_passed_to_the_sync(self):
        config = make_config(
            react="beat",
            react_amount=0.55,
            react_target=0.6,
            react_profile="strong",
            react_bands=["#010203", "#040506", "#070809", "#0a0b0c", "#0d0e0f"],
            react_threshold=-24,
            react_attack=2,
            react_release=60,
            react_punch=3.5,
        )
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(config, m)
        self.assertEqual(argv[argv.index("--react") + 1], "beat")
        self.assertEqual(argv[argv.index("--react-amount") + 1], "0.55")
        self.assertEqual(argv[argv.index("--react-target") + 1], "0.6")
        self.assertEqual(argv[argv.index("--react-profile") + 1], "strong")
        self.assertEqual(
            argv[argv.index("--react-bands") + 1],
            "#010203,#040506,#070809,#0a0b0c,#0d0e0f",
        )
        self.assertEqual(argv[argv.index("--react-threshold") + 1], "-24")
        self.assertEqual(argv[argv.index("--react-attack") + 1], "2")
        self.assertEqual(argv[argv.index("--react-release") + 1], "60")
        self.assertEqual(argv[argv.index("--react-punch") + 1], "3.5")

    def test_vibrance_is_passed_to_the_sync(self):
        config = make_config(vibrance=1.5)
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(config, m)
        self.assertEqual(argv[argv.index("--vibrance") + 1], "1.5")

        old = make_config()
        old.pop("vibrance", None)
        old["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(old, m)
        self.assertEqual(argv[argv.index("--vibrance") + 1], "1")

    def test_reaction_flags_use_defaults_for_old_configs(self):
        config = make_config()
        config.pop("react_profile", None)
        config.pop("react_bands", None)
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(config, m)
        self.assertEqual(argv[argv.index("--react-profile") + 1], "balanced")
        self.assertEqual(
            argv[argv.index("--react-bands") + 1],
            ",".join(m.DEFAULT_BAND_COLORS),
        )
        self.assertEqual(argv[argv.index("--react-threshold") + 1], "-22")
        self.assertEqual(argv[argv.index("--react-attack") + 1], "1")
        self.assertEqual(argv[argv.index("--react-release") + 1], "55")
        self.assertEqual(argv[argv.index("--react-punch") + 1], "3")

    def test_missing_reaction_keys_fall_back_to_color(self):
        config = make_config()
        config.pop("react", None)
        config["lights"] = {"10.0.0.1": {"enabled": True}}
        argv, _ips, _zones = webui.build_command(config, m)
        self.assertEqual(argv[argv.index("--react") + 1], "color")

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
        self.old_scenes = os.environ.get("WIZ_AMBILIGHT_SCENES_CONFIG")
        self.old_runtime = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = str(Path(self.tmp.name) / "lights.json")
        os.environ["WIZ_AMBILIGHT_SCENES_CONFIG"] = str(Path(self.tmp.name) / "scenes.json")
        # Keep Session.adopt() away from the panel the developer may be running.
        os.environ["XDG_RUNTIME_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("WIZ_AMBILIGHT_GUI_CONFIG", None)
        else:
            os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = self.old
        if self.old_scenes is None:
            os.environ.pop("WIZ_AMBILIGHT_SCENES_CONFIG", None)
        else:
            os.environ["WIZ_AMBILIGHT_SCENES_CONFIG"] = self.old_scenes
        if self.old_runtime is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self.old_runtime
        self.tmp.cleanup()

    def test_snapshot_shape(self):
        panel = webui.Panel(m, demo=True)
        snapshot = panel.snapshot()
        self.assertTrue(snapshot["demo"])
        self.assertEqual(snapshot["version"], m.VERSION)
        self.assertEqual(len(snapshot["lights"]), len(webui.DEMO_LIGHTS))
        self.assertTrue(all(row["name"] for row in snapshot["lights"]))
        self.assertIn("model", snapshot["lights"][0])
        self.assertEqual(snapshot["session"]["running"], False)
        self.assertIn("hue", snapshot["styles"])
        self.assertIn("fps", snapshot["style_details"]["hue"])
        self.assertEqual(snapshot["config"]["react"], "color")
        reactions = {reaction["id"]: reaction for reaction in snapshot["reactions"]}
        self.assertEqual(len(reactions), len(m.REACTIONS))
        self.assertEqual(reactions["beat"]["group"], "audio")
        self.assertEqual(reactions["equalize"]["group"], "video")
        self.assertTrue(reactions["beat"]["audio"])
        self.assertFalse(reactions["cut"]["audio"])
        self.assertTrue(reactions["cut"]["detail"])
        self.assertEqual(
            [profile["id"] for profile in reactions["equalize"]["profiles"]],
            ["soft", "balanced", "strong"],
        )
        self.assertEqual(reactions["color"]["profiles"], [])
        self.assertEqual(
            [band["id"] for band in snapshot["bands"]],
            list(m.BANDS),
        )
        self.assertEqual(
            [band["color"] for band in snapshot["bands"]],
            list(m.DEFAULT_BAND_COLORS),
        )
        self.assertEqual(snapshot["config"]["react_profile"], "balanced")
        self.assertEqual(
            snapshot["config"]["react_bands"], list(m.DEFAULT_BAND_COLORS)
        )
        self.assertEqual(
            [group["id"] for group in snapshot["reaction_groups"]], ["video", "audio"]
        )
        self.assertEqual(
            [preset["id"] for preset in snapshot["dynamics"]],
            list(m.AUDIO_PRESETS),
        )
        self.assertTrue(snapshot["dynamics"][0]["hint"])
        self.assertTrue(snapshot["config_path"].endswith("lights.json"))
        self.assertIsInstance(snapshot["network"], list)
        self.assertIn("active", snapshot["crazy"])
        self.assertIn("resources", snapshot)

    def test_snapshot_reflects_custom_reaction_config(self):
        path = Path(os.environ["WIZ_AMBILIGHT_GUI_CONFIG"])
        colors = ["#010203", "#040506", "#070809", "#0a0b0c", "#0d0e0f"]
        path.write_text(
            json.dumps(
                {
                    "react": "vu",
                    "react_profile": "strong",
                    "react_bands": colors,
                }
            ),
            encoding="utf-8",
        )
        panel = webui.Panel(m, demo=True)
        snapshot = panel.snapshot()
        self.assertEqual(snapshot["config"]["react"], "vu")
        self.assertEqual(snapshot["config"]["react_profile"], "strong")
        self.assertEqual([band["color"] for band in snapshot["bands"]], colors)

    def test_mpv_pid_comes_from_a_fresh_state_file(self):
        panel = webui.Panel(m, demo=True)
        path = webui.runtime_dir() / "state-check.json"
        path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        try:
            # Attach mode has no parent link, so the Lua pid is the only source.
            self.assertEqual(panel._mpv_pid(None, None), os.getpid())

            stale = time.time() - 3600
            os.utime(path, (stale, stale))
            self.assertIsNone(panel._mpv_pid(None, None))
        finally:
            path.unlink(missing_ok=True)

    def test_meter_reads_the_live_audio_state(self):
        panel = webui.Panel(m, demo=True)
        path = webui.runtime_dir() / "state-meter.json"
        path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "audio": {
                        "rms": -30.0,
                        "peak": -6.0,
                        "bands": [-30.0, -24.0, -12.0, -18.0, -40.0],
                    },
                }
            ),
            encoding="utf-8",
        )
        try:
            meter = panel.meter()
            self.assertTrue(meter["active"])
            self.assertAlmostEqual(meter["db"], -14.0)
            self.assertEqual(len(meter["bands"]), 5)
            self.assertEqual(meter["bands"][2], -12.0)
        finally:
            path.unlink(missing_ok=True)
        self.assertFalse(panel.meter()["active"])

    def test_resources_payload_is_well_formed(self):
        panel = webui.Panel(m, demo=True)
        resources = panel.resources()
        for key in (
            "at",
            "available",
            "cores",
            "cpu",
            "ram_mb",
            "cpu_wiz",
            "ram_wiz",
            "cpu_mpv",
            "ram_mpv",
            "mpv_pid",
            "network_bps",
            "udp_kbps",
            "capture_fps",
            "capture_w",
            "capture_h",
            "video_w",
            "video_h",
        ):
            self.assertIn(key, resources)
        self.assertEqual(resources["network_bps"], 0.0)
        self.assertEqual(resources["udp_kbps"], 0.0)
        self.assertIsNone(resources["mpv_pid"])
        self.assertIsNone(resources["capture_fps"])
        self.assertIsNone(resources["video_w"])
        self.assertGreaterEqual(resources["cores"], 1)
        if Path("/proc").is_dir():
            self.assertTrue(resources["available"])
            self.assertGreater(resources["ram_mb"], 0)
            self.assertGreaterEqual(resources["processes"], 1)

    def test_light_update_is_in_memory_only(self):
        panel = webui.Panel(m, demo=True)
        panel.set_light("192.0.2.11", {"name": "Desk", "zone": "left"})
        self.assertEqual(panel.config["lights"]["192.0.2.11"]["name"], "Desk")
        self.assertEqual(panel.config["lights"]["192.0.2.11"]["zone"], "left")
        self.assertFalse(Path(os.environ["WIZ_AMBILIGHT_GUI_CONFIG"]).exists())

    def test_delete_light_removes_row_and_room_membership(self):
        panel = webui.Panel(m, demo=True)
        first, second, _third = sorted(panel.config["lights"])[:3]
        panel.set_group({"name": "Desk", "ips": [first, second]})
        snapshot = panel.delete_light(first)
        ips = [row["ip"] for row in snapshot["lights"]]
        self.assertNotIn(first, ips)
        self.assertNotIn(first, panel.live)
        self.assertEqual(panel.config["groups"], {"Desk": [second]})
        self.assertEqual(len(ips), len(webui.DEMO_LIGHTS) - 1)
        panel.delete_light(second)
        self.assertEqual(panel.config["groups"], {})
        with self.assertRaises(ValueError):
            panel.delete_light(first)

    def test_demo_is_dry_run(self):
        panel = webui.Panel(m, demo=True)
        argv, _ips, _zones = webui.build_command(panel.config, m, demo=panel.demo)
        self.assertIn("--dry-run", argv)

    def test_snapshot_has_hex_and_scene_catalog(self):
        panel = webui.Panel(m, demo=True)
        snapshot = panel.snapshot()
        self.assertTrue(snapshot["lights"][0]["hex"].startswith("#"))
        self.assertIn(3, [scene["id"] for scene in snapshot["wiz_scenes"]])
        self.assertEqual(snapshot["scenes"], [])

    def test_control_sets_color_and_brightness(self):
        panel = webui.Panel(m, demo=True)
        ip = sorted(panel.config["lights"])[0]
        snapshot = panel.control("all", {"hex": "#123456", "brightness": 40})
        row = next(row for row in snapshot["lights"] if row["ip"] == ip)
        self.assertEqual(row["hex"], "#123456")
        self.assertEqual(row["dimming"], 40)
        self.assertTrue(row["state"])

    def test_white_temperature_and_color_are_exclusive(self):
        panel = webui.Panel(m, demo=True)
        ip = sorted(panel.config["lights"])[0]
        panel.control(ip, {"hex": "#123456"})
        snapshot = panel.control(ip, {"temp": 2700})
        row = next(row for row in snapshot["lights"] if row["ip"] == ip)
        self.assertEqual(row["temp"], 2700)
        self.assertIsNone(row["hex"])
        snapshot = panel.control(ip, {"hex": "#00ff00"})
        row = next(row for row in snapshot["lights"] if row["ip"] == ip)
        self.assertEqual(row["hex"], "#00ff00")
        self.assertIsNone(row["temp"])

    def test_control_power_off_is_per_light(self):
        panel = webui.Panel(m, demo=True)
        first, second = sorted(panel.config["lights"])[:2]
        snapshot = panel.control(first, {"power": False})
        rows = {row["ip"]: row for row in snapshot["lights"]}
        self.assertFalse(rows[first]["state"])
        self.assertNotEqual(rows[second]["state"], False)

    def test_rooms_target_their_lights(self):
        panel = webui.Panel(m, demo=True)
        first, second, third = sorted(panel.config["lights"])[:3]
        panel.set_group({"name": "Desk", "ips": [first, second, "8.8.8.8"]})
        self.assertEqual(panel.config["groups"], {"Desk": [first, second]})

        panel.control("all", {"power": True})
        snapshot = panel.control("group:Desk", {"power": False})
        rows = {row["ip"]: row for row in snapshot["lights"]}
        self.assertFalse(rows[first]["state"])
        self.assertFalse(rows[second]["state"])
        self.assertTrue(rows[third]["state"])

        panel.set_group({"name": "Office", "previous": "Desk", "ips": [first]})
        self.assertEqual(panel.config["groups"], {"Office": [first]})

        panel.set_group({"name": "Office", "delete": True})
        self.assertEqual(panel.config["groups"], {})
        with self.assertRaises(ValueError):
            panel.control("group:Office", {"power": True})
        with self.assertRaises(ValueError):
            panel.set_group({"name": "Empty", "ips": []})

    def test_saved_colors_store_hex_and_brightness(self):
        panel = webui.Panel(m, demo=True)
        panel.save_color({"hex": "#ABCDEF"})
        panel.save_color({"hex": "#abcdef", "brightness": 35})
        self.assertEqual(panel.config["colors"], [{"hex": "#abcdef", "brightness": 35}])
        panel.save_color({"hex": "#123456", "brightness": 70})
        self.assertEqual(
            panel.config["colors"],
            [
                {"hex": "#abcdef", "brightness": 35},
                {"hex": "#123456", "brightness": 70},
            ],
        )
        panel.save_color({"hex": "#abcdef", "remove": True})
        self.assertEqual(panel.config["colors"], [{"hex": "#123456", "brightness": 70}])
        with self.assertRaises(ValueError):
            panel.save_color({"hex": "red"})
        with self.assertRaises(ValueError):
            panel.save_color({"hex": "#ffffff", "brightness": "bright"})

    def test_control_scene_and_speed(self):
        panel = webui.Panel(m, demo=True)
        ip = sorted(panel.config["lights"])[0]
        panel.control(ip, {"scene": 4, "speed": 80})
        self.assertEqual(panel.live[ip]["sceneId"], 4)
        self.assertEqual(panel.live[ip]["speed"], 80)

    def test_control_rejects_bad_input(self):
        panel = webui.Panel(m, demo=True)
        cases = [
            {"hex": "nope"},
            {"hex": "#ff8800", "temp": 3000},
            {"speed": 50},
            {"power": False, "brightness": 20},
            {},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    panel.control("all", payload)
        with self.assertRaises(ValueError):
            panel.control("8.8.8.8", {"brightness": 20})

    def test_scene_lifecycle(self):
        panel = webui.Panel(m, demo=True)
        panel.control("all", {"hex": "#00ff00", "brightness": 70})
        snapshot = panel.save_scene("Movie night")
        self.assertEqual(snapshot["scenes"], [{"name": "Movie night", "count": 3}])

        panel.control("all", {"hex": "#0000ff"})
        snapshot = panel.apply_scene("Movie night")
        row = snapshot["lights"][0]
        self.assertEqual(row["hex"], "#00ff00")
        self.assertEqual(row["dimming"], 70)

        panel.delete_scene("Movie night")
        self.assertEqual(panel.snapshot()["scenes"], [])
        with self.assertRaises(ValueError):
            panel.delete_scene("Movie night")

    def test_scene_needs_a_name(self):
        panel = webui.Panel(m, demo=True)
        panel.control("all", {"brightness": 50})
        with self.assertRaises(ValueError):
            panel.save_scene("   ")


class SceneNormalizeTests(unittest.TestCase):
    def test_clamps_and_drops_invalid_entries(self):
        clean = webui.normalize_scenes(
            {
                " Movie ": {
                    "192.168.1.5": {"dimming": 999, "temp": 100, "r": "x"},
                    "bad": {"dimming": 50},
                    "192.168.1.6": {"state": False},
                    "192.168.1.7": {},
                }
            }
        )
        self.assertEqual(list(clean), ["Movie"])
        entry = clean["Movie"]["192.168.1.5"]
        self.assertEqual(entry["dimming"], 100)
        self.assertEqual(entry["temp"], 2200)
        self.assertNotIn("r", entry)
        self.assertNotIn("bad", clean["Movie"])
        self.assertEqual(clean["Movie"]["192.168.1.6"], {"state": False})
        self.assertNotIn("192.168.1.7", clean["Movie"])

    def test_scene_modes_are_exclusive(self):
        clean = webui.normalize_scenes(
            {
                "Mixed": {
                    "192.168.1.5": {
                        "sceneId": 4,
                        "r": 1,
                        "g": 2,
                        "b": 3,
                        "temp": 3000,
                        "speed": 80,
                    }
                },
                "Partial": {"192.168.1.6": {"r": 10, "temp": 2700}},
                "Stringy": {"192.168.1.7": {"state": "false", "dimming": 40}},
            }
        )
        self.assertEqual(clean["Mixed"]["192.168.1.5"], {"sceneId": 4, "speed": 80})
        self.assertEqual(clean["Partial"]["192.168.1.6"], {"temp": 2700})
        self.assertEqual(clean["Stringy"]["192.168.1.7"], {"dimming": 40})

    def test_round_trip_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("WIZ_AMBILIGHT_SCENES_CONFIG")
            path = Path(tmp) / "scenes.json"
            os.environ["WIZ_AMBILIGHT_SCENES_CONFIG"] = str(path)
            try:
                saved = webui.save_scenes(
                    {"Movie": {"192.168.1.5": {"dimming": 50, "r": 1, "g": 2, "b": 3}}}
                )
                self.assertEqual(webui.load_scenes(), saved)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            finally:
                if old is None:
                    os.environ.pop("WIZ_AMBILIGHT_SCENES_CONFIG", None)
                else:
                    os.environ["WIZ_AMBILIGHT_SCENES_CONFIG"] = old


class PanelDeliveryTests(unittest.TestCase):
    """The panel must say when a bulb never answered a manual command."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vars = {}
        for key, value in {
            "WIZ_AMBILIGHT_GUI_CONFIG": str(Path(self.tmp.name) / "lights.json"),
            "WIZ_AMBILIGHT_SCENES_CONFIG": str(Path(self.tmp.name) / "scenes.json"),
            "XDG_RUNTIME_DIR": self.tmp.name,
        }.items():
            self.vars[key] = os.environ.get(key)
            os.environ[key] = value
        self.panel = webui.Panel(m)
        self.panel.config["lights"] = {
            "10.0.0.5": {
                "name": "Desk",
                "enabled": True,
                "zone": "",
                "model": "ESP24_SHRGBC_01",
                "mac": "",
                "firmware": "",
            }
        }

    def tearDown(self):
        for key, value in self.vars.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_silent_bulb_gets_a_warning_and_goes_offline(self):
        with mock.patch.object(m, "send_commands", return_value={}), mock.patch.object(
            m, "query_lights", return_value={}
        ), mock.patch.object(
            m, "local_ipv4_networks", return_value=[("10.0.0.2", 24)]
        ):
            snapshot = self.panel.control("all", {"power": True})
        self.assertIn("10.0.0.5", snapshot["warning"])
        self.assertIn("10.0.0.2/24", snapshot["warning"])
        self.assertEqual([row["online"] for row in snapshot["lights"]], [False])

    def test_acknowledged_bulb_is_online_and_quiet(self):
        with mock.patch.object(
            m, "send_commands", return_value={"10.0.0.5": {"success": True}}
        ), mock.patch.object(m, "local_ipv4_networks", return_value=[("10.0.0.2", 24)]):
            snapshot = self.panel.control("all", {"power": True})
        self.assertNotIn("warning", snapshot)
        self.assertEqual([row["online"] for row in snapshot["lights"]], [True])

    def test_a_get_pilot_reply_counts_as_reachable(self):
        with mock.patch.object(m, "send_commands", return_value={}), mock.patch.object(
            m, "query_lights", return_value={"10.0.0.5": {"state": True, "dimming": 55}}
        ), mock.patch.object(m, "local_ipv4_networks", return_value=[("10.0.0.2", 24)]):
            snapshot = self.panel.control("all", {"brightness": 55})
        self.assertNotIn("warning", snapshot)
        self.assertEqual(snapshot["lights"][0]["dimming"], 55)


class CrazyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vars = {}
        for key, value in {
            "WIZ_AMBILIGHT_GUI_CONFIG": str(Path(self.tmp.name) / "lights.json"),
            "WIZ_AMBILIGHT_SCENES_CONFIG": str(Path(self.tmp.name) / "scenes.json"),
            "XDG_RUNTIME_DIR": self.tmp.name,
        }.items():
            self.vars[key] = os.environ.get(key)
            os.environ[key] = value

    def tearDown(self):
        for key, value in self.vars.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_crazy_streams_then_stops(self):
        panel = webui.Panel(m, demo=True)
        panel.start_crazy(seconds=2)
        thread = panel._crazy_thread
        self.assertTrue(panel.crazy_status()["active"])
        self.assertLessEqual(panel.crazy_status()["remaining"], 2.0)
        panel.stop_crazy()
        thread.join(timeout=1.0)
        self.assertFalse(panel.crazy_status()["active"])

    def test_crazy_toggle_stops_an_active_run(self):
        panel = webui.Panel(m, demo=True)
        panel.start_crazy(seconds=2)
        thread = panel._crazy_thread
        snapshot = panel.crazy({})
        self.assertFalse(snapshot["crazy"]["active"])
        thread.join(timeout=1.0)

    def test_crazy_refuses_to_fight_the_sync(self):
        panel = webui.Panel(m, demo=True)
        with mock.patch.object(panel.session, "running", return_value=True):
            with self.assertRaises(ValueError):
                panel.start_crazy()


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vars = {}
        for key, value in {
            "WIZ_AMBILIGHT_GUI_CONFIG": str(Path(self.tmp.name) / "lights.json"),
            "WIZ_AMBILIGHT_SCENES_CONFIG": str(Path(self.tmp.name) / "scenes.json"),
            "XDG_RUNTIME_DIR": self.tmp.name,
        }.items():
            self.vars[key] = os.environ.get(key)
            os.environ[key] = value

    def tearDown(self):
        for key, value in self.vars.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_manual_scan_is_deep(self):
        panel = webui.Panel(m)
        found = {"10.0.0.9": {"state": True}}
        with mock.patch.object(m, "discover_lights", return_value=found) as discover:
            with mock.patch.object(m, "query_lights", return_value={}):
                count = panel.scan()
        self.assertEqual(count, 1)
        discover.assert_called_once_with(timeout=2.5, deep=True)

    def test_background_scan_stays_light(self):
        panel = webui.Panel(m)
        found = {"10.0.0.9": {"state": True}}
        with mock.patch.object(m, "discover_lights", return_value=found) as discover:
            with mock.patch.object(m, "query_lights", return_value={}):
                panel.scan(deep=False)
        discover.assert_called_once_with(timeout=1.8, deep=False)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("WIZ_AMBILIGHT_GUI_CONFIG")
        self.old_scenes = os.environ.get("WIZ_AMBILIGHT_SCENES_CONFIG")
        os.environ["WIZ_AMBILIGHT_GUI_CONFIG"] = str(Path(self.tmp.name) / "lights.json")
        os.environ["WIZ_AMBILIGHT_SCENES_CONFIG"] = str(Path(self.tmp.name) / "scenes.json")
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
        if self.old_scenes is None:
            os.environ.pop("WIZ_AMBILIGHT_SCENES_CONFIG", None)
        else:
            os.environ["WIZ_AMBILIGHT_SCENES_CONFIG"] = self.old_scenes
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
        self.assertIn("font-src 'self'", response.headers["Content-Security-Policy"])

    def test_serves_the_bundled_font(self):
        with self.request("/fonts/Merriweather-Bold.ttf") as response:
            body = response.read()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "font/ttf")
        self.assertGreater(len(body), 50_000)

    def test_stylesheet_uses_the_mpv_config_palette(self):
        with self.request("/style.css") as response:
            css = response.read().decode()
        self.assertIn("--amber: #fcbe11", css)

    def test_config_post(self):
        with self.request(
            "/api/config", {"brightness": 55}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["config"]["brightness"], 55)

    def test_delete_light_endpoint(self):
        ip = sorted(self.panel.config["lights"])[0]
        with self.request(
            "/api/light/delete", {"ip": ip}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertNotIn(ip, [row["ip"] for row in snapshot["lights"]])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/light/delete", {"ip": ip}, self.auth_headers())
        caught.exception.close()
        self.assertEqual(caught.exception.code, 400)

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

    def test_control_endpoint(self):
        with self.request(
            "/api/control",
            {"target": "all", "hex": "#abcdef", "brightness": 55},
            self.auth_headers(),
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["lights"][0]["hex"], "#abcdef")
        self.assertEqual(snapshot["lights"][0]["dimming"], 55)

    def test_control_endpoint_rejects_bad_hex(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/control", {"hex": "nope"}, self.auth_headers())
        caught.exception.close()
        self.assertEqual(caught.exception.code, 400)

    def test_room_and_color_endpoints(self):
        ips = sorted(self.panel.config["lights"])[:2]
        with self.request(
            "/api/group",
            {"name": "Desk", "ips": ips},
            self.auth_headers(),
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["config"]["groups"], {"Desk": ips})

        with self.request(
            "/api/color", {"hex": "#ABCDEF", "brightness": 45}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(
            snapshot["config"]["colors"], [{"hex": "#abcdef", "brightness": 45}]
        )

        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/color", {"hex": "nope"}, self.auth_headers())
        caught.exception.close()
        self.assertEqual(caught.exception.code, 400)

    def test_scene_endpoints(self):
        with self.request(
            "/api/control", {"hex": "#112233"}, self.auth_headers()
        ) as response:
            json.loads(response.read())
        with self.request(
            "/api/scene/save", {"name": "Test"}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["scenes"][0]["name"], "Test")

        with self.request(
            "/api/scene/apply", {"name": "Test"}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["lights"][0]["hex"], "#112233")

        with self.request(
            "/api/scene/delete", {"name": "Test"}, self.auth_headers()
        ) as response:
            snapshot = json.loads(response.read())
        self.assertEqual(snapshot["scenes"], [])

    def test_scene_endpoints_need_token(self):
        headers = {"Content-Type": "application/json", "Origin": self.base}
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/scene/save", {"name": "Test"}, headers)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 403)

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
