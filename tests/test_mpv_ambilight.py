"""Unit tests for the parts that do not need bulbs or a running mpv."""

import contextlib
import io
import sys
import unittest
from pathlib import Path

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
