"""Unit tests for the parts that do not need bulbs or a running mpv."""

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mpv_ambilight as m  # noqa: E402


class ColorTests(unittest.TestCase):
    def test_clamp8(self):
        self.assertEqual(m.clamp8(-10), 0)
        self.assertEqual(m.clamp8(12.6), 13)
        self.assertEqual(m.clamp8(999), 255)

    def test_adjust_color_identity(self):
        self.assertEqual(m.adjust_color((10, 20, 30), 1.0, 1.0), (10, 20, 30))

    def test_adjust_color_saturation(self):
        rgb = m.adjust_color((200, 100, 100), 1.5, 1.0)
        self.assertGreater(rgb[0], rgb[1])
        self.assertGreaterEqual(rgb[0], 200)

    def test_adjust_color_gamma_brightens(self):
        normal = m.adjust_color((100, 100, 100), 1.0, 1.0)
        bright = m.adjust_color((100, 100, 100), 1.0, 2.2)
        self.assertGreater(bright[0], normal[0])

    def test_adjust_color_keeps_channels_in_range(self):
        for rgb in [(0, 0, 0), (255, 255, 255), (255, 0, 128)]:
            result = m.adjust_color(rgb, 4.0, 3.0)
            self.assertTrue(all(0 <= channel <= 255 for channel in result))

    def test_rgb_to_hex(self):
        self.assertEqual(m.rgb_to_hex((255, 136, 0)), "#ff8800")
        self.assertEqual(m.rgb_to_hex((-5, 12.6, 999)), "#000dff")

    def test_hex_to_rgb(self):
        self.assertEqual(m.hex_to_rgb("#ff8800"), (255, 136, 0))
        self.assertEqual(m.hex_to_rgb("00FF7f"), (0, 255, 127))
        self.assertEqual(m.hex_to_rgb("#f80"), (255, 136, 0))

    def test_hex_to_rgb_rejects_bad_values(self):
        for value in ("", "#12345", "#gggggg", "#1234567", None):
            with self.assertRaises(ValueError):
                m.hex_to_rgb(value)


class LayoutTests(unittest.TestCase):
    def test_auto_layouts(self):
        self.assertEqual(m.zones_for_layout("auto", 1), ["all"])
        self.assertEqual(m.zones_for_layout("auto", 2), ["left", "right"])
        self.assertEqual(m.zones_for_layout("auto", 3), ["t1", "t2", "t3"])
        self.assertEqual(
            m.zones_for_layout("auto", 4), ["left", "right", "top", "bottom"]
        )

    def test_two_bulbs_use_outer_thirds(self):
        self.assertEqual(m.zones_for_layout("thirds", 2), ["t1", "t3"])

    def test_more_bulbs_than_zones_cycles(self):
        self.assertEqual(
            m.zones_for_layout("left-right", 3), ["left", "right", "left"]
        )

    def test_explicit_layouts(self):
        self.assertEqual(m.zones_for_layout("all", 2), ["all", "all"])
        self.assertEqual(m.zones_for_layout("top-bottom", 2), ["top", "bottom"])

    def test_zone_color_falls_back_to_all(self):
        zones = {"all": (11, 22, 33)}
        self.assertEqual(m.zone_color(zones, "left"), (11, 22, 33))

    def test_zone_color_thirds(self):
        zones = {"all": (0, 0, 0), "thirds": [(1, 2, 3), (4, 5, 6), (7, 8, 9)]}
        self.assertEqual(m.zone_color(zones, "t2"), (4, 5, 6))
        self.assertEqual(m.zone_color(zones, "t9"), (0, 0, 0))


class ParsingTests(unittest.TestCase):
    def test_parse_lights_deduplicates_and_trims(self):
        self.assertEqual(
            m.parse_lights(" 192.168.1.5, 192.168.1.7,192.168.1.5 "),
            ["192.168.1.5", "192.168.1.7"],
        )

    def test_parse_lights_accepts_spaces(self):
        self.assertEqual(
            m.parse_lights("192.168.1.5 192.168.1.7"),
            ["192.168.1.5", "192.168.1.7"],
        )


class DiscoveryTargetTests(unittest.TestCase):
    def test_broadcast_targets_include_global_and_subnet(self):
        targets = m.broadcast_targets([("192.168.1.42", 24), ("10.0.0.5", 28)])
        self.assertIn("255.255.255.255", targets)
        self.assertIn("192.168.1.255", targets)
        self.assertIn("10.0.0.15", targets)

    def test_sweep_targets_cover_the_local_24(self):
        hosts = m.sweep_targets([("192.168.1.42", 24)])
        self.assertEqual(len(hosts), 253)
        self.assertIn("192.168.1.5", hosts)
        self.assertIn("192.168.1.7", hosts)
        self.assertNotIn("192.168.1.42", hosts)
        self.assertNotIn("192.168.1.255", hosts)

    def test_sweep_respects_smaller_subnets(self):
        hosts = m.sweep_targets([("10.0.0.5", 28)])
        self.assertEqual(len(hosts), 13)
        self.assertIn("10.0.0.14", hosts)
        self.assertNotIn("10.0.0.5", hosts)

    def test_sweep_is_capped_at_a_24(self):
        hosts = m.sweep_targets([("10.1.2.3", 16)])
        self.assertEqual(len(hosts), 253)
        self.assertIn("10.1.2.99", hosts)
        self.assertNotIn("10.1.3.1", hosts)


class SmootherTests(unittest.TestCase):
    def test_zero_tau_snaps(self):
        smoother = m.Smoother(0)
        self.assertEqual(smoother.apply("a", (10, 20, 30), 0.016), (10, 20, 30))

    def test_interpolates_towards_target(self):
        smoother = m.Smoother(0.1)
        smoother.apply("a", (0, 0, 0), 0.016)
        value = smoother.apply("a", (100, 100, 100), 0.016)
        self.assertTrue(0 < value[0] < 100)

    def test_converges(self):
        smoother = m.Smoother(0.05)
        smoother.apply("a", (0, 0, 0), 0.016)
        for _ in range(300):
            value = smoother.apply("a", (200, 100, 50), 0.016)
        self.assertEqual(value, (200, 100, 50))

    def test_hard_cut_snaps(self):
        smoother = m.Smoother(10.0)
        smoother.apply("a", (0, 0, 0), 0.016)
        self.assertEqual(smoother.apply("a", (220, 40, 10), 0.016), (220, 40, 10))

    def test_small_change_still_fades(self):
        smoother = m.Smoother(1.0)
        smoother.apply("a", (100, 100, 100), 0.016)
        value = smoother.apply("a", (120, 100, 100), 0.5)
        self.assertGreater(value[0], 100)
        self.assertLess(value[0], 120)

    def test_cut_snap_can_be_disabled(self):
        smoother = m.Smoother(10.0, cut_delta=0)
        smoother.apply("a", (0, 0, 0), 0.016)
        value = smoother.apply("a", (220, 220, 220), 0.016)
        self.assertLess(value[0], 50)


class DirectControlTests(unittest.TestCase):
    @staticmethod
    def args(**overrides):
        values = {
            "lights": "192.168.1.5",
            "hex": None,
            "temp": None,
            "brightness": None,
            "scene": None,
            "speed": None,
            "power": None,
            "dry_run": True,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def run_quiet(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = m.run_set(args)
        return code, out.getvalue(), err.getvalue()

    def test_sets_color_and_brightness(self):
        code, out, _err = self.run_quiet(self.args(hex="#ff8800", brightness=40))
        self.assertEqual(code, 0)
        self.assertIn("'r': 255", out)
        self.assertIn("'g': 136", out)
        self.assertIn("'dimming': 40", out)

    def test_sets_scene_and_speed(self):
        code, out, _err = self.run_quiet(self.args(scene=3, speed=120))
        self.assertEqual(code, 0)
        self.assertIn("'sceneId': 3", out)
        self.assertIn("'speed': 120", out)

    def test_power_off(self):
        code, out, _err = self.run_quiet(self.args(power="off"))
        self.assertEqual(code, 0)
        self.assertIn("setState", out)
        self.assertIn("'state': False", out)

    def test_power_on(self):
        code, out, _err = self.run_quiet(self.args(power="on"))
        self.assertEqual(code, 0)
        self.assertIn("'state': True", out)

    def test_rejects_bad_combinations(self):
        cases = [
            {"hex": "nope"},
            {"hex": "#ff8800", "temp": 3000},
            {"temp": 1000},
            {"speed": 50},
            {"scene": 1000},
            {"power": "off", "brightness": 50},
            {},
            {"lights": "not-an-ip", "hex": "#ff8800"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                code, _out, err = self.run_quiet(self.args(**overrides))
                self.assertEqual(code, 2)
                self.assertIn("error:", err)

    def test_invalid_input_does_not_scan(self):
        args = self.args(lights="", hex="nope")
        with mock.patch.dict(os.environ, {"WIZ_LIGHTS": "", "WIZ_LIGHT_IPS": ""}):
            with mock.patch.object(m, "discover_lights") as discover:
                code, _out, err = self.run_quiet(args)
        discover.assert_not_called()
        self.assertEqual(code, 2)
        self.assertIn("expected a hex color", err)

    def test_ipv4_validation(self):
        self.assertTrue(m.is_ipv4("192.168.1.5"))
        self.assertFalse(m.is_ipv4("192.168.1"))
        self.assertFalse(m.is_ipv4("example.com"))
        self.assertFalse(m.is_ipv4("999.1.1.1"))


class SenderTests(unittest.TestCase):
    def test_dry_run_deduplicates(self):
        sender = m.WizSender(dry_run=True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            sender.set_color("127.0.0.1", (1, 2, 3), 80)
            sender.set_color("127.0.0.1", (1, 2, 3), 80)
        self.assertEqual(len(buffer.getvalue().splitlines()), 1)

    def test_dry_run_sends_changes(self):
        sender = m.WizSender(dry_run=True)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            sender.set_color("127.0.0.1", (1, 2, 3), 80)
            sender.set_color("127.0.0.1", (4, 5, 6), 80)
        self.assertEqual(len(buffer.getvalue().splitlines()), 2)

    def test_query_lights_without_ips(self):
        self.assertEqual(m.query_lights([]), {})


if __name__ == "__main__":
    unittest.main()
