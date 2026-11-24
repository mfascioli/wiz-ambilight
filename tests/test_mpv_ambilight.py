"""Unit tests for the parts that do not need bulbs or a running mpv."""

import contextlib
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
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


class SamplingTests(unittest.TestCase):
    def args(self, **overrides):
        base = {
            "sampling": "auto",
            "sample_grid": None,
            "sample_block": None,
            "capture": None,
            "fps": 20.0,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_auto_leaves_resolution_only_sentinels(self):
        args = m.resolve_sampling(self.args())
        self.assertEqual(args.sample_grid, 0)
        self.assertEqual(args.sample_block, 0)
        self.assertEqual(args.capture, "scaled")
        self.assertEqual(args.fps, 20.0)

    def test_profiles_trade_detail_for_fps(self):
        lean = m.resolve_sampling(self.args(sampling="lean"))
        self.assertEqual((lean.sample_grid, lean.sample_block), (48, 1))
        self.assertEqual(lean.capture, "scaled")
        self.assertEqual(lean.fps, 10.0)

        balanced = m.resolve_sampling(self.args(sampling="balanced"))
        self.assertEqual((balanced.sample_grid, balanced.sample_block), (80, 2))
        self.assertEqual(balanced.capture, "scaled")
        self.assertEqual(balanced.fps, 15.0)

        quality = m.resolve_sampling(self.args(sampling="quality"))
        self.assertEqual((quality.sample_grid, quality.sample_block), (120, 3))
        self.assertEqual(quality.capture, "video")
        self.assertEqual(quality.fps, 20.0)

    def test_explicit_flags_beat_the_profile(self):
        args = m.resolve_sampling(
            self.args(sampling="balanced", fps=24.0, capture="source"),
            {"fps": True, "capture": True},
        )
        self.assertEqual(args.fps, 24.0)
        self.assertEqual(args.capture, "video")
        self.assertEqual(args.sample_grid, 80)

    def test_manual_uses_the_knobs(self):
        args = m.resolve_sampling(
            self.args(
                sampling="manual",
                sample_grid=96,
                sample_block=2,
                capture="source",
                fps=12.0,
            )
        )
        self.assertEqual(args.sample_grid, 96)
        self.assertEqual(args.sample_block, 2)
        self.assertEqual(args.capture, "video")
        self.assertEqual(args.fps, 12.0)

    def test_manual_defaults_and_clamps(self):
        args = m.resolve_sampling(self.args(sampling="manual"))
        self.assertEqual((args.sample_grid, args.sample_block), (80, 1))
        self.assertEqual(args.capture, "scaled")
        clamped = m.resolve_sampling(
            self.args(
                sampling="manual",
                sample_grid=999,
                sample_block=99,
                capture="auto",
            )
        )
        self.assertEqual(clamped.sample_grid, 240)
        self.assertEqual(clamped.sample_block, 4)
        self.assertEqual(clamped.capture, "scaled")


class SenderCounterTests(unittest.TestCase):
    def test_real_datagrams_are_counted(self):
        sent = []

        class FakeSocket:
            def setsockopt(self, *_args):
                pass

            def sendto(self, payload, address):
                sent.append((payload, address))

            def close(self):
                pass

        with mock.patch.object(m.socket, "socket", return_value=FakeSocket()):
            sender = m.WizSender()
            sender.set_color("10.0.0.1", (1, 2, 3), 50)
            self.assertEqual(sender.packets_sent, 1)
            self.assertEqual(sender.bytes_sent, len(sent[0][0]))

            # The refresh de-duplication must not inflate the network graph.
            sender.set_color("10.0.0.1", (1, 2, 3), 50)
            self.assertEqual(sender.packets_sent, 1)

            sender.set_color("10.0.0.1", (4, 5, 6), 50)
            self.assertEqual(sender.packets_sent, 2)
            self.assertGreater(sender.bytes_sent, len(sent[0][0]))
            sender.close()

    def test_dry_run_counts_nothing(self):
        sender = m.WizSender(dry_run=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sender.set_color("10.0.0.1", (1, 2, 3), 50)
        self.assertEqual(sender.packets_sent, 0)
        self.assertEqual(sender.bytes_sent, 0)


class WhiteLedTests(unittest.TestCase):
    def test_mapping_moves_the_grey_part_to_both_white_leds(self):
        params = m.white_led_params({"r": 255, "g": 128, "b": 128, "dimming": 60})
        self.assertEqual(
            (params["r"], params["g"], params["b"], params["c"], params["w"]),
            (127, 0, 0, 128, 128),
        )
        self.assertEqual(params["dimming"], 60)

    def test_white_and_grey_become_only_white_leds(self):
        params = m.white_led_params({"r": 200, "g": 200, "b": 200})
        self.assertEqual(
            (params["r"], params["g"], params["b"], params["c"], params["w"]),
            (0, 0, 0, 200, 200),
        )

    def test_params_without_rgb_are_untouched(self):
        params = m.white_led_params({"temp": 3000, "dimming": 40})
        self.assertEqual(params, {"temp": 3000, "dimming": 40})

    def test_pilot_rgb_folds_the_white_leds_back(self):
        self.assertEqual(
            m.pilot_rgb({"r": 127, "g": 0, "b": 0, "c": 128, "w": 128}),
            (255, 128, 128),
        )
        self.assertEqual(m.pilot_rgb({"r": 0, "g": 0, "b": 0}), (0, 0, 0))
        self.assertIsNone(m.pilot_rgb({"temp": 3000}))

    def test_sender_sends_c_and_w_when_enabled(self):
        sent = []

        class FakeSocket:
            def setsockopt(self, *_args):
                pass

            def sendto(self, payload, address):
                sent.append(json.loads(payload))

            def close(self):
                pass

        with mock.patch.object(m.socket, "socket", return_value=FakeSocket()):
            sender = m.WizSender(white_leds=True)
            sender.set_color("10.0.0.1", (255, 128, 128), 60)
            sender.set_pilot("10.0.0.1", {"r": 10, "g": 20, "b": 30, "dimming": 40})
            sender.close()

        first, second = sent
        self.assertEqual(
            (first["params"]["r"], first["params"]["c"], first["params"]["w"]),
            (127, 128, 128),
        )
        self.assertEqual(
            (second["params"]["r"], second["params"]["c"], second["params"]["w"]),
            (0, 10, 10),
        )


class SendCommandTests(unittest.TestCase):
    def test_collects_the_reply_from_a_bulb(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

        def responder():
            data, addr = sock.recvfrom(4096)
            message = json.loads(data)
            sock.sendto(
                json.dumps(
                    {
                        "id": message["id"],
                        "method": message["method"],
                        "result": {"success": True},
                    }
                ).encode(),
                addr,
            )

        thread = threading.Thread(target=responder, daemon=True)
        thread.start()
        try:
            replies = m.send_commands(
                [("127.0.0.1", "setPilot", {"r": 1, "g": 2, "b": 3})],
                timeout=1.0,
                port=port,
            )
        finally:
            sock.close()
        self.assertIn("127.0.0.1", replies)
        self.assertTrue(replies["127.0.0.1"]["success"])

    def test_reports_nothing_when_the_bulb_is_silent(self):
        replies = m.send_commands(
            [("127.0.0.1", "setPilot", {"r": 1})], timeout=0.15, port=9
        )
        self.assertEqual(replies, {})


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


class _Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now


class _ScanSocket:
    """Socket that charges 12 ms per swept host and queues both bulb replies.

    A real /24 sweep takes ~3 s to resolve ARP, which used to consume the
    whole listen timeout and leave only the first queued reply in `found`.
    """

    def __init__(self, clock):
        self.clock = clock
        self.replies = []
        self.timeout = 0.02
        self.bulbs = ("10.0.0.5", "10.0.0.7")
        self.broadcasts = {"255.255.255.255", "10.0.0.255"}

    def setsockopt(self, *args):
        pass

    def sendto(self, payload, addr):
        reply = json.dumps(
            {"id": 1, "method": "getPilot", "result": {"state": True}}
        ).encode()
        if addr[0] in self.broadcasts:
            for ip in self.bulbs:
                self.replies.append((reply, (ip, 38899)))
        else:
            self.clock.now += 0.012

    def settimeout(self, value):
        self.timeout = max(0.02, value)

    def recvfrom(self, size):
        if self.replies:
            return self.replies.pop(0)
        self.clock.now += self.timeout
        raise socket.timeout

    def close(self):
        pass


class DiscoveryTests(unittest.TestCase):
    def test_deep_scan_survives_the_sweep_and_keeps_both_replies(self):
        clock = _Clock()
        fake = _ScanSocket(clock)
        with mock.patch.object(
            m, "local_ipv4_networks", return_value=[("10.0.0.2", 24)]
        ), mock.patch.object(
            m.socket, "socket", return_value=fake
        ), mock.patch.object(
            m, "time", SimpleNamespace(monotonic=clock.monotonic)
        ):
            found = m.discover_lights(timeout=2.5, deep=True)
        self.assertEqual(sorted(found), ["10.0.0.5", "10.0.0.7"])


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


class ReactionMathTests(unittest.TestCase):
    def test_scene_luma_uses_rec709_weights(self):
        self.assertAlmostEqual(m.scene_luma((255, 255, 255)), 1.0)
        self.assertAlmostEqual(m.scene_luma((0, 0, 0)), 0.0)
        # Green carries most of the perceived brightness.
        self.assertGreater(m.scene_luma((0, 255, 0)), m.scene_luma((255, 0, 0)))

    def test_rgb_distance_is_normalised(self):
        self.assertEqual(m.rgb_distance((0, 0, 0), (0, 0, 0)), 0.0)
        self.assertAlmostEqual(m.rgb_distance((0, 0, 0), (255, 255, 255)), 1.0)
        self.assertAlmostEqual(m.rgb_distance((0, 0, 0), (255, 0, 0)), 1 / 3)

    def test_hue_shift_turns_red_into_cyan(self):
        self.assertEqual(m.hue_shift((255, 0, 0), 180), (0, 255, 255))
        self.assertEqual(m.hue_shift((255, 0, 0), 0), (255, 0, 0))
        # A grey has no hue to rotate.
        self.assertEqual(m.hue_shift((128, 128, 128), 180), (128, 128, 128))

    def test_equalize_gain_dims_bright_and_lifts_dark(self):
        self.assertAlmostEqual(m.equalize_gain(0.9, 0.45, 0.35, 0.35), 0.65)
        self.assertAlmostEqual(m.equalize_gain(0.1, 0.45, 0.35, 0.35), 1.35)
        self.assertAlmostEqual(m.equalize_gain(0.45, 0.45, 0.35, 0.35), 1.0)

    def test_equalize_never_goes_below_the_floor(self):
        self.assertGreaterEqual(m.equalize_gain(1.0, 0.95, 1.0, 0.35), 0.35)
        self.assertLessEqual(m.equalize_gain(0.0, 0.05, 1.0, 0.35), 2.0)

    def test_lux_gain_uses_the_same_caps(self):
        self.assertAlmostEqual(m.lux_gain(50.0, 50.0, 0.35, 0.35), 1.0)
        self.assertAlmostEqual(m.lux_gain(10.0, 50.0, 0.35, 0.35), 1.35)
        self.assertAlmostEqual(m.lux_gain(200.0, 50.0, 0.35, 0.35), 0.65)
        self.assertGreaterEqual(m.lux_gain(0.0, 5000.0, 1.0, 0.35), 0.35)

    def test_read_lux_accepts_a_fresh_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lux.json"
            path.write_text('{"lux": 42.5}', encoding="utf-8")
            self.assertEqual(m.read_lux(path), 42.5)
            self.assertEqual(m.read_lux(path, max_age=None), 42.5)

    def test_read_lux_rejects_stale_or_invalid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lux.json"
            path.write_text('{"lux": 42.5}', encoding="utf-8")
            old = time.time() - m.LUX_STALE_SECONDS - 1
            os.utime(path, (old, old))
            self.assertIsNone(m.read_lux(path))
            self.assertEqual(m.read_lux(path, max_age=None), 42.5)

            for body in (
                "",
                "not json",
                "[]",
                '{"lux": true}',
                '{"lux": -1}',
                '{"lux": 999999}',
                '{"lux": "bright"}',
            ):
                with self.subTest(body=body):
                    path.write_text(body, encoding="utf-8")
                    self.assertIsNone(m.read_lux(path, max_age=None))

    def test_vu_level_maps_dbfs(self):
        self.assertEqual(m.vu_level(-60), 0.0)
        self.assertEqual(m.vu_level(-45), 0.0)
        self.assertEqual(m.vu_level(-12), 1.0)
        self.assertEqual(m.vu_level(0), 1.0)
        self.assertAlmostEqual(m.vu_level(-28.5), 0.5)
        self.assertEqual(m.vu_level(None), 0.0)

    def test_beat_pulse_attacks_then_releases(self):
        self.assertEqual(m.beat_pulse(-0.1), 0.0)
        # The 1 ms attack is already complete on the next send tick.
        self.assertEqual(m.beat_pulse(0.0), 0.0)
        self.assertEqual(m.beat_pulse(m.BEAT_ATTACK), 1.0)
        self.assertAlmostEqual(
            m.beat_pulse(m.BEAT_ATTACK + m.BEAT_RELEASE / 2), 0.5
        )
        self.assertEqual(m.beat_pulse(m.BEAT_ATTACK + m.BEAT_RELEASE), 0.0)
        # A profile can still opt into a longer ramp.
        self.assertAlmostEqual(m.beat_pulse(0.025, 0.05, 0.1), 0.5)

    def test_pulse_level_gates_and_punches(self):
        self.assertEqual(m.pulse_level(-60.0), 0.0)
        self.assertEqual(m.pulse_level(m.AUDIO_THRESHOLD_DB), 0.0)
        self.assertEqual(m.pulse_level(m.AUDIO_CEILING_DB), 1.0)
        # Halfway up the dB window is already far above half brightness.
        mid = m.pulse_level(
            m.AUDIO_THRESHOLD_DB + (m.AUDIO_CEILING_DB - m.AUDIO_THRESHOLD_DB) / 2
        )
        self.assertGreater(mid, 0.5)
        self.assertLess(mid, 1.0)
        # More punch lifts the same level closer to full.
        half = m.AUDIO_THRESHOLD_DB + m.AUDIO_WINDOW_DB / 2
        self.assertGreater(
            m.pulse_level(half, punch=4.0),
            m.pulse_level(half, punch=1.0),
        )
        self.assertEqual(m.pulse_level(None), 0.0)

    def test_pulse_level_keeps_a_window_above_a_high_gate(self):
        # Raising the gate toward the ceiling must not collapse the window;
        # at 1 dB of headroom the old curve was effectively a switch.
        low = m.pulse_level(-14.0, -14.0, -13.0)
        high = m.pulse_level(-8.0, -14.0, -13.0)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.5)
        self.assertLess(high, 1.0)
        self.assertEqual(m.pulse_level(-2.0, -14.0, -13.0), 1.0)
        # A ceiling farther away than the minimum window still wins.
        self.assertLess(
            m.pulse_level(-15.0, -20.0, -5.0),
            m.pulse_level(-15.0, -20.0, -17.0),
        )

    def test_hot_db_prefers_the_sample_peak_only_when_it_is_hotter(self):
        self.assertAlmostEqual(m.hot_db(-30.0, -12.0), -20.0)
        self.assertEqual(m.hot_db(-30.0, -45.0), -30.0)
        self.assertEqual(m.hot_db(None, -5.0), -13.0)
        self.assertEqual(m.hot_db(-30.0, None), -30.0)
        self.assertIsNone(m.hot_db(None, None))

    def test_cut_pulse_is_a_short_square(self):
        self.assertEqual(m.cut_pulse(0.0), 1.0)
        self.assertEqual(m.cut_pulse(m.CUT_SECONDS - 0.001), 1.0)
        self.assertEqual(m.cut_pulse(m.CUT_SECONDS), 0.0)

    def test_band_for_spreads_five_bands_across_the_bulbs(self):
        self.assertIsNone(m.band_for(0, 1))
        self.assertEqual([m.band_for(index, 2) for index in range(2)], [0, 4])
        self.assertEqual([m.band_for(index, 3) for index in range(3)], [0, 2, 4])
        self.assertEqual(
            [m.band_for(index, 4) for index in range(4)], [0, 1, 3, 4]
        )
        self.assertEqual(
            [m.band_for(index, 5) for index in range(5)], [0, 1, 2, 3, 4]
        )
        # More than five bulbs repeat the cycle.
        self.assertEqual(
            [m.band_for(index, 7) for index in range(7)], [0, 1, 2, 3, 4, 0, 1]
        )

    def test_normalize_band_colors_repairs_missing_and_bad_values(self):
        colors = m.normalize_band_colors(["#010203", "bogus", (4, 5, 6)])
        self.assertEqual(colors[0], (1, 2, 3))
        self.assertEqual(colors[1], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[1]))
        self.assertEqual(colors[2], (4, 5, 6))
        self.assertEqual(colors[3], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[3]))
        self.assertEqual(len(colors), len(m.BANDS))
        self.assertEqual(
            m.normalize_band_colors(None),
            tuple(m.hex_to_rgb(color) for color in m.DEFAULT_BAND_COLORS),
        )

    def test_parse_band_colors_accepts_five_hex_values(self):
        colors = m.parse_band_colors(
            "#010203, #040506,#070809,#0a0b0c,#0d0e0f"
        )
        self.assertEqual(colors[0], (1, 2, 3))
        self.assertEqual(colors[-1], (13, 14, 15))
        with self.assertRaises(ValueError):
            m.parse_band_colors("#010203")
        with self.assertRaises(ValueError):
            m.parse_band_colors("#010203,#040506,#070809,#0a0b0c,#zzzzzz")

    def test_audio_color_modes_cover_six_sources(self):
        self.assertEqual(
            list(m.AUDIO_COLOR_MODES),
            ["bands", "spectrum", "rainbow", "range", "level", "single"],
        )
        self.assertEqual(set(m.AUDIO_COLOR_HINTS), set(m.AUDIO_COLOR_MODES))
        self.assertEqual(m.normalize_audio_color("bogus"), m.hex_to_rgb("fcbe11"))
        self.assertEqual(m.normalize_audio_color("#010203"), (1, 2, 3))
        self.assertEqual(m.blend_rgb((0, 10, 20), (100, 110, 120), 0.5), (50, 60, 70))

    def test_audio_color_modes_pick_colors_as_described(self):
        bands = ["#010203", "#040506", "#070809", "#0a0b0c", "#0d0e0f"]
        reaction = m.Reaction(
            "vu",
            1.0,
            0.45,
            "balanced",
            bands,
            color_mode="range",
            color_a="#112233",
            color_b="#445566",
        )
        self.assertEqual(reaction.color_mode, "range")
        self.assertEqual(reaction.audio_color(0, 0.0, 100.0), (0x11, 0x22, 0x33))
        self.assertEqual(reaction.audio_color(4, 1.0, 100.0), (0x44, 0x55, 0x66))

        reaction.color_mode = "level"
        self.assertEqual(reaction.audio_color(2, 0.0, 100.0), (0x11, 0x22, 0x33))
        self.assertEqual(reaction.audio_color(2, 1.0, 100.0), (0x44, 0x55, 0x66))

        reaction.color_mode = "spectrum"
        self.assertEqual(reaction.audio_color(0, 0.5, 100.0), m.hsv_rgb(0.0))
        self.assertEqual(reaction.audio_color(2, 0.5, 100.0), m.hsv_rgb(0.4))

        reaction.color_mode = "rainbow"
        self.assertNotEqual(
            reaction.audio_color(0, 0.5, 100.0),
            reaction.audio_color(0, 0.5, 106.0),
        )
        self.assertNotEqual(
            reaction.audio_color(0, 0.5, 100.0),
            reaction.audio_color(2, 0.5, 100.0),
        )

        reaction.color_mode = "single"
        self.assertEqual(reaction.audio_color(3, 0.0, 100.0), (0x11, 0x22, 0x33))

        reaction.color_mode = "bands"
        self.assertEqual(reaction.audio_color(3, 0.5, 100.0), (10, 11, 12))

        bad = m.Reaction("vu", color_mode="neon", color_a="bogus", color_b=None)
        self.assertEqual(bad.color_mode, "bands")
        self.assertEqual(bad.color_a, m.hex_to_rgb(m.DEFAULT_AUDIO_COLOR_A))
        self.assertEqual(bad.color_b, m.hex_to_rgb(m.DEFAULT_AUDIO_COLOR_B))

    def test_profiles_cover_every_reactive_mode(self):
        self.assertEqual(
            set(m.REACTION_PROFILES),
            {"equalize", "cut", "motion", "beat", "vu"},
        )
        self.assertEqual(set(m.PROFILE_LABELS), {"soft", "balanced", "strong"})
        for mode, profiles in m.REACTION_PROFILES.items():
            with self.subTest(mode=mode):
                self.assertEqual(set(profiles), set(m.PROFILE_LABELS))
                for name, values in profiles.items():
                    self.assertTrue(values.get("hint"), f"{mode}/{name} has no hint")
                    self.assertIn("span", values)

    def test_profiles_move_the_parameters_in_the_expected_direction(self):
        soft = m.Reaction("equalize", 1.0, 0.45, "soft")
        strong = m.Reaction("equalize", 1.0, 0.45, "strong")
        self.assertLess(soft.eq_span, strong.eq_span)
        self.assertGreater(soft.eq_tau, strong.eq_tau)
        self.assertGreater(soft.eq_floor, strong.eq_floor)

        soft = m.Reaction("cut", 1.0, 0.45, "soft")
        strong = m.Reaction("cut", 1.0, 0.45, "strong")
        self.assertGreater(soft.cut_threshold, strong.cut_threshold)
        self.assertGreater(soft.cut_cooldown, strong.cut_cooldown)
        self.assertLess(soft.cut_per_minute, strong.cut_per_minute)

        soft = m.Reaction("beat", 1.0, 0.45, "soft")
        strong = m.Reaction("beat", 1.0, 0.45, "strong")
        self.assertGreater(soft.beat_threshold, strong.beat_threshold)
        self.assertLess(soft.beat_span, strong.beat_span)

    def test_unknown_profile_falls_back_to_balanced(self):
        reaction = m.Reaction("equalize", 1.0, 0.45, "extreme")
        balanced = m.Reaction("equalize", 1.0, 0.45, "balanced")
        self.assertEqual(reaction.profile, "balanced")
        self.assertEqual(reaction.eq_span, balanced.eq_span)

    def test_every_reaction_explains_itself(self):
        for mode, details in m.REACTIONS.items():
            with self.subTest(mode=mode):
                self.assertTrue(details["hint"])
                self.assertTrue(details.get("detail"))
                self.assertGreaterEqual(len(details["detail"]), len(details["hint"]))
        # Cut and the audio modes are the ones that needed plain-language copy.
        self.assertIn("hard edit", m.REACTIONS["cut"]["detail"])
        self.assertIn("graphic EQ bands", m.REACTIONS["beat"]["detail"])
        self.assertIn("graphic-EQ pulse meter", m.REACTIONS["vu"]["detail"])


class ReactionModeTests(unittest.TestCase):
    def update(
        self,
        reaction,
        now,
        zones=None,
        audio=None,
        raw=None,
        lights=("a",),
        names=("all",),
    ):
        raw = {} if raw is None else raw
        state = {}
        if zones is not None:
            state["zones"] = zones
        if audio is not None:
            state["audio"] = audio
        reaction.update(now, state, raw, list(lights), list(names))
        return raw

    def test_audio_modes_are_explicit(self):
        self.assertEqual(set(m.AUDIO_REACTIONS), {"beat", "vu"})
        self.assertEqual(m.REACTIONS["beat"]["group"], "audio")
        self.assertEqual(m.REACTIONS["vu"]["group"], "audio")
        for mode in ("color", "equalize", "cut", "motion", "duotone"):
            self.assertEqual(m.REACTIONS[mode]["group"], "video")

    def test_equalize_lowers_bright_scenes_and_lifts_dark_ones(self):
        reaction = m.Reaction("equalize", 1.0, 0.45)
        self.update(
            reaction,
            100.0,
            zones={"all": [230, 230, 230]},
            raw={"a": (230, 230, 230)},
        )
        self.assertLess(reaction.dimming("a", 80, 100.1, 0.05), 80)

        for index in range(80):
            self.update(
                reaction,
                100.1 + index * 0.1,
                zones={"all": [10, 10, 10]},
                raw={"a": (10, 10, 10)},
            )
        self.assertGreater(reaction.dimming("a", 80, 108.0, 0.05), 80)

    def test_equalize_amount_zero_is_a_no_op(self):
        reaction = m.Reaction("equalize", 0.0, 0.45)
        self.update(
            reaction,
            100.0,
            zones={"all": [255, 255, 255]},
            raw={"a": (255, 255, 255)},
        )
        self.assertEqual(reaction.dimming("a", 73, 100.1, 0.05), 73)

    def test_auto_lux_is_a_layer_over_every_reaction(self):
        for mode in ("color", "equalize", "cut", "motion", "duotone"):
            with self.subTest(mode=mode):
                base = m.Reaction(mode, 1.0, 0.45)
                self.update(
                    base,
                    100.0,
                    zones={"all": [128, 128, 128]},
                    raw={"a": (128, 128, 128)},
                )
                reference = base.dimming("a", 60, 100.1, 0.05)

                dark = m.Reaction(mode, 1.0, 0.45, auto_lux=True, lux_target=50.0)
                dark.lux = 10.0
                self.update(
                    dark,
                    100.0,
                    zones={"all": [128, 128, 128]},
                    raw={"a": (128, 128, 128)},
                )
                self.assertGreater(
                    dark.dimming("a", 60, 100.1, 0.05), reference, mode
                )

                bright = m.Reaction(mode, 1.0, 0.45, auto_lux=True, lux_target=50.0)
                bright.lux = 200.0
                self.update(
                    bright,
                    100.0,
                    zones={"all": [128, 128, 128]},
                    raw={"a": (128, 128, 128)},
                )
                self.assertLess(
                    bright.dimming("a", 60, 100.1, 0.05), reference, mode
                )

    def test_auto_lux_off_ignores_the_sensor(self):
        reaction = m.Reaction("color", 1.0, 0.45)
        reaction.lux = 10.0
        self.update(
            reaction,
            100.0,
            zones={"all": [128, 128, 128]},
            raw={"a": (128, 128, 128)},
        )
        self.assertEqual(reaction.dimming("a", 60, 100.1, 0.05), 60)

    def test_auto_lux_without_a_reading_is_neutral(self):
        reaction = m.Reaction("color", 1.0, 0.45, auto_lux=True)
        self.update(
            reaction,
            100.0,
            zones={"all": [128, 128, 128]},
            raw={"a": (128, 128, 128)},
        )
        self.assertEqual(reaction.dimming("a", 60, 100.1, 0.05), 60)

    def test_equalize_falls_back_to_luma_when_auto_lux_has_no_reading(self):
        reaction = m.Reaction("equalize", 1.0, 0.45, auto_lux=True)
        self.update(
            reaction,
            100.0,
            zones={"all": [230, 230, 230]},
            raw={"a": (230, 230, 230)},
        )
        self.assertLess(reaction.dimming("a", 80, 100.1, 0.05), 80)

    def test_auto_lux_uses_the_equalize_profile_in_every_mode(self):
        soft = m.Reaction("color", 1.0, 0.45, "soft", auto_lux=True)
        strong = m.Reaction("color", 1.0, 0.45, "strong", auto_lux=True)
        self.assertLess(soft.lux_span, strong.lux_span)
        self.assertGreater(soft.lux_tau, strong.lux_tau)
        cut = m.Reaction("cut", 1.0, 0.45, "strong", auto_lux=True)
        self.assertEqual(cut.lux_span, strong.lux_span)
        self.assertEqual(cut.lux_floor, strong.lux_floor)

    def test_cut_flashes_then_reserves_headroom(self):
        reaction = m.Reaction("cut", 1.0, 0.45)
        self.update(
            reaction, 100.0, zones={"all": [10, 10, 10]}, raw={"a": (10, 10, 10)}
        )
        self.update(
            reaction, 100.1, zones={"all": [230, 20, 20]}, raw={"a": (230, 20, 20)}
        )
        self.assertEqual(reaction.dimming("a", 100, 100.12, 0.05), 100)
        self.assertEqual(reaction.dimming("a", 100, 100.4, 0.05), 78)

    def test_cut_rate_limit_is_six_per_minute(self):
        reaction = m.Reaction("cut", 1.0, 0.45)
        now = 100.0
        colors = ((10, 10, 10), (220, 30, 30))
        for index in range(12):
            self.update(reaction, now, zones={"all": colors[index % 2]})
            now += 2.0
        self.assertEqual(len(reaction.cut_times), m.CUT_PER_MINUTE)

    def test_duotone_shifts_every_second_bulb(self):
        reaction = m.Reaction("duotone", 1.0, 0.45)
        raw = {"a": (255, 0, 0), "b": (255, 0, 0)}
        self.update(
            reaction,
            100.0,
            zones={"all": [255, 0, 0], "left": (255, 0, 0), "right": (255, 0, 0)},
            raw=raw,
            lights=("a", "b"),
            names=("left", "right"),
        )
        self.assertEqual(raw["a"], (255, 0, 0))
        self.assertEqual(raw["b"], (0, 255, 255))

    def test_motion_raises_saturation_while_the_scene_moves(self):
        reaction = m.Reaction("motion", 1.0, 0.45)
        now = 100.0
        for index in range(12):
            color = (255, 0, 0) if index % 2 == 0 else (0, 0, 255)
            self.update(reaction, now, zones={"all": color}, raw={"a": color})
            now += 0.2
        self.assertGreater(reaction.motion["a"], 0.8)
        self.assertGreater(reaction.saturation("a"), 1.0)
        self.assertGreater(reaction.dimming("a", 80, now, 0.2), 60)

    def test_beat_pulses_only_on_a_loud_transient(self):
        reaction = m.Reaction("beat", 1.0, 0.45)
        self.update(reaction, 100.0, audio={"rms": -40.0})
        self.update(reaction, 100.2, audio={"rms": -38.0})
        self.assertIsNone(reaction.beat_at)
        self.update(reaction, 100.4, audio={"rms": -12.0})
        self.assertEqual(reaction.beat_at, 100.4)
        self.assertEqual(
            reaction.dimming("a", 100, 100.4 + m.BEAT_ATTACK, 0.05), 100
        )
        # The steady level keeps most of the range as headroom, so the flash
        # is a visible jump instead of a small tremble.
        self.assertEqual(reaction.dimming("a", 100, 101.2, 0.05), 25)

    def test_vu_with_one_bulb_uses_overall_volume_and_dominant_color(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        raw = self.update(
            reaction,
            100.0,
            audio={
                "rms": -8.0,
                "bands": [-60.0, -60.0, -8.0, -60.0, -60.0],
            },
        )
        self.assertGreater(reaction.levels["a"], 0.9)
        self.assertEqual(reaction.assignments, {"a": ()})
        self.assertEqual(raw["a"], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[2]))

    def test_vu_with_three_bulbs_tracks_three_bands(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        raw = self.update(
            reaction,
            100.0,
            audio={
                "rms": -20.0,
                "bands": [-6.0, -60.0, -24.0, -60.0, -12.0],
            },
            lights=("a", "b", "c"),
            names=("all", "all", "all"),
        )
        self.assertEqual(reaction.assignments, {"a": (0,), "b": (2,), "c": (4,)})
        self.assertGreater(reaction.levels["a"], reaction.levels["b"])
        self.assertGreater(reaction.levels["c"], reaction.levels["b"])
        self.assertEqual(raw["a"], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[0]))
        self.assertEqual(raw["b"], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[2]))
        self.assertEqual(raw["c"], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[4]))
        self.assertGreater(
            reaction.dimming("a", 100, 100.0, 0.05),
            reaction.dimming("b", 100, 100.0, 0.05),
        )

    def test_vu_with_five_bulbs_assigns_one_band_each(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        self.update(
            reaction,
            100.0,
            audio={"rms": -20.0, "bands": [-6, -12, -18, -30, -45]},
            lights=("a", "b", "c", "d", "e"),
            names=("all",) * 5,
        )
        self.assertEqual(
            reaction.assignments,
            {"a": (0,), "b": (1,), "c": (2,), "d": (3,), "e": (4,)},
        )

    def test_audio_modes_use_the_configured_band_colors(self):
        reaction = m.Reaction("vu", 1.0, 0.45, "balanced", ["#010203"] * 5)
        raw = self.update(
            reaction,
            100.0,
            audio={"rms": -20.0, "bands": [-60.0] * 5},
            lights=("a", "b"),
            names=("all", "all"),
        )
        self.assertEqual(raw["a"], (1, 2, 3))
        self.assertEqual(raw["b"], (1, 2, 3))

    def test_beat_with_two_bulbs_pulses_the_band_that_moved(self):
        reaction = m.Reaction("beat", 1.0, 0.45)
        self.update(
            reaction,
            100.0,
            audio={"rms": -40.0, "bands": [-40, -60, -60, -60, -60]},
            lights=("a", "b"),
            names=("all", "all"),
        )
        self.update(
            reaction,
            100.2,
            audio={"rms": -38.0, "bands": [-40, -60, -60, -60, -10]},
            lights=("a", "b"),
            names=("all", "all"),
        )
        self.assertEqual(reaction.assignments, {"a": (0,), "b": (4,)})
        self.assertIsNone(reaction.band_at[0])
        self.assertEqual(reaction.band_at[4], 100.2)

    def test_vu_uses_band_peaks_to_catch_the_attack(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        self.update(
            reaction,
            100.0,
            audio={"rms": -40.0, "bands": [-40.0] * 5, "band_peaks": [-60.0] * 5},
        )
        quiet = reaction.levels["a"]
        self.update(
            reaction,
            100.1,
            audio={"rms": -40.0, "bands": [-40.0] * 5, "band_peaks": [-4.0] * 5},
        )
        self.assertGreater(reaction.levels["a"], quiet + 0.25)
        self.assertGreater(reaction.band_levels[0], quiet + 0.25)

    def test_vu_attack_is_faster_than_its_release(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        self.update(
            reaction,
            100.0,
            audio={"rms": -60.0, "bands": [-60.0] * 5},
        )
        self.assertEqual(reaction.dimming("a", 100, 100.0, 0.05), 10)
        self.update(
            reaction,
            100.05,
            audio={"rms": -6.0, "bands": [-6.0] * 5},
        )
        attacked = reaction.dimming("a", 100, 100.06, 0.01)
        self.assertGreaterEqual(attacked, 90)
        self.update(
            reaction,
            100.20,
            audio={"rms": -60.0, "bands": [-60.0] * 5},
        )
        released = reaction.dimming("a", 100, 100.21, 0.01)
        self.assertGreater(released, 70)
        self.assertLess(attacked - released, 25)

    def test_beat_detects_a_peak_transient_without_an_rms_jump(self):
        reaction = m.Reaction("beat", 1.0, 0.45)
        self.update(
            reaction,
            100.0,
            audio={"rms": -40.0, "bands": [-40.0] * 5, "band_peaks": [-60.0] * 5},
        )
        self.assertIsNone(reaction.beat_at)
        self.update(
            reaction,
            100.2,
            audio={"rms": -40.0, "bands": [-40.0] * 5, "band_peaks": [-4.0] * 5},
        )
        self.assertEqual(reaction.band_at[0], 100.2)
        self.assertEqual(reaction.beat_at, 100.2)

    def test_audio_works_with_only_band_metadata(self):
        # Some mpv builds expose only the last labelled astats, so wizstats can
        # be empty while the five bands are live.
        reaction = m.Reaction("vu", 1.0, 0.45)
        raw = self.update(
            reaction,
            100.0,
            audio={"bands": [-8.0] * 5, "band_peaks": [-4.0] * 5},
        )
        self.assertGreater(reaction.levels["a"], 0.9)
        self.assertEqual(raw["a"], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[0]))

    def test_audio_modes_still_work_without_band_metadata(self):
        # Older state files and audio-only edge cases carry only the overall
        # RMS; the meter must not go dark just because `bands` is missing.
        reaction = m.Reaction("vu", 1.0, 0.45)
        raw = self.update(reaction, 100.0, audio={"rms": -8.0})
        self.assertGreater(reaction.levels["a"], 0.9)
        self.assertEqual(raw["a"], m.hex_to_rgb(m.DEFAULT_BAND_COLORS[0]))

        beat = m.Reaction("beat", 1.0, 0.45)
        self.update(beat, 100.0, audio={"rms": -40.0})
        self.update(beat, 100.2, audio={"rms": -8.0})
        self.assertEqual(beat.beat_at, 100.2)

    def test_audio_modes_ignore_nan_and_infinite_levels(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        raw = self.update(
            reaction,
            100.0,
            audio={"rms": float("nan"), "bands": [float("inf")] * 5},
        )
        self.assertEqual(raw, {})
        self.assertEqual(reaction.levels, {})

    def test_audio_amount_zero_is_a_no_op(self):
        for mode in ("beat", "vu"):
            with self.subTest(mode=mode):
                reaction = m.Reaction(mode, 0.0, 0.45)
                raw = {"a": (10, 20, 30)}
                self.update(
                    reaction,
                    100.0,
                    audio={"rms": -12.0, "bands": [-12.0] * 5},
                    raw=raw,
                )
                self.assertEqual(raw, {"a": (10, 20, 30)})
                self.assertEqual(reaction.dimming("a", 73, 100.1, 0.05), 73)


class EqTests(unittest.TestCase):
    def test_normalize_eq_bands_clamps_and_sorts(self):
        bands = m.normalize_eq_bands(
            [
                {"freq": 5000, "gain": 99, "q": 0.01, "lamp": 2},
                {"freq": 5, "gain": -99, "q": 99, "lamp": -7},
            ],
            4,
        )
        self.assertEqual(len(bands), 4)
        self.assertEqual([band["freq"] for band in bands], sorted(b["freq"] for b in bands))
        low = bands[0]
        self.assertEqual(low["freq"], m.EQ_FREQ_MIN)
        self.assertEqual(low["gain"], -m.EQ_GAIN_LIMIT)
        self.assertEqual(low["q"], 8.0)
        self.assertEqual(low["lamp"], -1)
        self.assertEqual(low["type"], "bell")
        self.assertEqual(low["slope"], m.EQ_DEFAULT_SLOPE)
        self.assertFalse(low["solo"])
        high = next(band for band in bands if band["freq"] == 5000.0)
        self.assertEqual(high["gain"], m.EQ_GAIN_LIMIT)
        self.assertEqual(high["q"], 0.4)
        self.assertEqual(high["lamp"], 2)
        # Missing entries fall back to the log-spaced default at that slot so
        # the curve never shifts when one band is malformed.
        self.assertIn(
            round(m.default_eq_freqs(4)[2], 2),
            [band["freq"] for band in bands],
        )

    def test_normalize_eq_shapes_slopes_and_solo(self):
        bands = m.normalize_eq_bands(
            [
                {"freq": 100, "type": "LOW-PASS", "slope": 40, "solo": 1},
                {"freq": 200, "type": "band pass", "slope": 5},
                {"freq": 300, "type": "notch", "solo": "yes"},
                {"freq": 400, "type": "nonsense"},
            ],
            4,
        )
        self.assertEqual(bands[0]["type"], "lowpass")
        self.assertEqual(bands[0]["slope"], 48)
        self.assertTrue(bands[0]["solo"])
        self.assertEqual(bands[1]["type"], "bandpass")
        self.assertEqual(bands[1]["slope"], 12)
        self.assertFalse(bands[1]["solo"])
        self.assertEqual(bands[2]["type"], "notch")
        self.assertFalse(bands[2]["solo"])
        self.assertEqual(bands[3]["type"], "bell")

    def test_eq_splits_stay_between_adjacent_centres(self):
        bands = m.normalize_eq_bands(None, 8)
        splits = m.eq_splits(bands)
        self.assertEqual(len(splits), 7)
        for index, split in enumerate(splits):
            self.assertGreater(split, bands[index]["freq"])
            self.assertLess(split, bands[index + 1]["freq"])
            if index:
                self.assertGreater(split, splits[index - 1])

    def test_band_for_spreads_and_repeats(self):
        self.assertEqual(
            [m.band_for(index, 3, 5) for index in range(3)], [0, 2, 4]
        )
        self.assertEqual(
            [m.band_for(index, 7, 5) for index in range(7)], [0, 1, 2, 3, 4, 0, 1]
        )
        self.assertIsNone(m.band_for(0, 1, 8))

    def test_explicit_lamp_assignment_averages_its_bands(self):
        eq = [
            {"freq": 80, "gain": 0, "q": 4.0, "lamp": 0},
            {"freq": 160, "gain": 0, "q": 4.0, "lamp": 0},
            {"freq": 2500, "gain": 0, "q": 4.0, "lamp": 1},
            {"freq": 5000, "gain": 0, "q": 4.0, "lamp": 1},
        ]
        reaction = m.Reaction("vu", 1.0, 0.45, eq=eq)
        ReactionModeTests.update(
            self,
            reaction,
            100.0,
            audio={"rms": -10.0, "bands": [-8.0, -30.0, -60.0, -60.0]},
            lights=("a", "b"),
            names=("all", "all"),
        )
        self.assertEqual(reaction.assignments, {"a": (0, 1), "b": (2, 3)})
        self.assertGreater(reaction.levels["a"], 0.2)
        self.assertLess(reaction.levels["a"], 1.0)
        self.assertEqual(reaction.levels["b"], 0.0)
        # The stronger assigned band supplies the colour.
        self.assertEqual(
            reaction.audio_color(0, reaction.levels["a"], 100.0),
            reaction.band_colors[0],
        )

    def test_solo_makes_every_bulb_follow_the_band(self):
        eq = [
            {"freq": 80, "gain": 0, "q": 4.0, "lamp": 0},
            {"freq": 2500, "gain": 0, "q": 4.0, "lamp": 1, "solo": True},
        ]
        reaction = m.Reaction("vu", 1.0, 0.45, eq=eq)
        ReactionModeTests.update(
            self,
            reaction,
            100.0,
            audio={"rms": -10.0, "bands": [-60.0, -8.0]},
            lights=("a", "b"),
            names=("all", "all"),
        )
        self.assertEqual(reaction.assignments, {"a": (1,), "b": (1,)})
        self.assertGreater(reaction.levels["a"], 0.5)
        self.assertEqual(reaction.levels["a"], reaction.levels["b"])
        self.assertEqual(
            reaction.audio_color(1, reaction.levels["a"], 100.0),
            reaction.band_colors[1],
        )

    def test_eq_gain_drives_a_band_harder(self):
        def level(gain):
            eq = [
                {"freq": 100, "gain": gain, "q": 6.0, "lamp": 0},
                {"freq": 4000, "gain": 0, "q": 6.0, "lamp": 1},
            ]
            reaction = m.Reaction("vu", 1.0, 0.45, eq=eq)
            ReactionModeTests.update(
                self,
                reaction,
                100.0,
                audio={"rms": -30.0, "bands": [-20.0, -60.0]},
                lights=("a", "b"),
                names=("all", "all"),
            )
            return reaction.levels["a"]

        self.assertGreater(level(12.0), level(0.0))
        self.assertEqual(level(0.0), 0.0)

    def test_active_bands_hold_quiet_bands_dark(self):
        eq = [
            {"freq": 100, "gain": 0, "q": 4.0, "lamp": 0},
            {"freq": 4000, "gain": 0, "q": 4.0, "lamp": 1},
        ]
        reaction = m.Reaction("vu", 1.0, 0.45, eq=eq, active_bands=True)
        # Band 1 sits above the gate but never moves, so it stays at its own
        # noise floor and is not "active"; band 0 jumps 22 dB and fires.
        ReactionModeTests.update(
            self,
            reaction,
            100.0,
            audio={"rms": -16.0, "bands": [-30.0, -16.0]},
            lights=("a", "b"),
            names=("all", "all"),
        )
        ReactionModeTests.update(
            self,
            reaction,
            100.1,
            audio={"rms": -16.0, "bands": [-8.0, -16.0]},
            lights=("a", "b"),
            names=("all", "all"),
        )
        self.assertEqual(reaction.band_levels[0] > 0.5, True)
        self.assertEqual(reaction.band_levels[1], 0.0)
        self.assertGreater(reaction.levels["a"], 0.0)
        self.assertEqual(reaction.levels["b"], 0.0)

    def test_auto_modes_shape_the_release(self):
        def release(mode):
            reaction = m.Reaction("vu", 1.0, 0.45, auto=mode)
            value = reaction.audio_release
            for _ in range(12):
                value = reaction._auto_release("a", 0.1, 1.0)
            return value

        fixed = release("off")
        self.assertEqual(fixed, m.Reaction("vu", 1.0, 0.45).audio_release)
        # SSL-style dual release grows with sustained program.
        self.assertGreater(release("ssl"), fixed)
        self.assertGreater(release("hybrid"), fixed)
        # API-style is a fixed longer release, and its soft knee lifts detail.
        self.assertAlmostEqual(release("api"), fixed * 1.35)
        api = m.Reaction("vu", 1.0, 0.45, auto="api")
        self.assertGreater(api._auto_level(0.5), 0.5)
        self.assertLessEqual(api._auto_level(1.0), 1.0)

    def test_auto_thrust_lowers_the_low_bands_only(self):
        self.assertEqual(m.eq_thrust_db(60.0), -3.0)
        self.assertEqual(m.eq_thrust_db(200.0), -1.5)
        self.assertEqual(m.eq_thrust_db(800.0), 0.0)

    def test_eq_defaults_match_the_panel(self):
        self.assertEqual(m.DEFAULT_EQ_BANDS, 8)
        self.assertEqual(m.MIN_BANDS, 2)
        self.assertEqual(m.MAX_BANDS, 16)
        self.assertEqual(len(m.BAND_COLOR_PALETTE), 16)
        self.assertEqual(m.BAND_COLOR_PALETTE[:5], m.DEFAULT_BAND_COLORS)
        freqs = m.default_eq_freqs(8)
        self.assertAlmostEqual(freqs[0], 32.0)
        self.assertAlmostEqual(freqs[-1], 16000.0)


class LuaAudioContractTests(unittest.TestCase):
    def test_lua_graph_builds_bands_from_the_configured_splits(self):
        source = (
            Path(__file__).resolve().parents[1] / "lua" / "wiz_ambilight.lua"
        ).read_text(encoding="utf-8")
        self.assertIn("@wizstats", source)
        self.assertIn("@wizbands", source)
        self.assertIn("@wiztail", source)
        # The graph is built at runtime: the panel and CLI pass the full band
        # plan, and the classic five-band crossover is only a fallback.
        self.assertIn("local DEFAULT_SPLITS = { 60, 250, 800, 2500 }", source)
        self.assertIn("local function sanitize_bands(value)", source)
        self.assertIn("local function bands_equal(first, second)", source)
        self.assertIn("local function sanitize_eq(value)", source)
        self.assertIn("local function eq_equal(first, second)", source)
        self.assertIn("local function band_chain(band)", source)
        self.assertIn("local function eq_filter(eq, astats)", source)
        self.assertIn("local function band_filter(astats)", source)
        self.assertIn('"acrossover=split="', source)
        self.assertIn('"amerge=inputs="', source)
        self.assertIn("asplit=2[main][mon]", source)
        self.assertIn('"bandreject=f="', source)
        self.assertIn('cut_chain("lowpass"', source)
        self.assertIn('cut_chain("highpass"', source)
        self.assertNotIn("acrossover=split=60 250 800 2500[b0]", source)
        self.assertIn("S.bands", source)
        self.assertIn("S.eq", source)
        # The band graph must measure only the two fields the meter reads.
        # Measuring every astats parameter on 2N+2 channels made a 16-band EQ
        # cost most of a core; the lean form is the fast path.
        self.assertIn("measure_perchannel=Peak_level+RMS_level", source)
        self.assertIn("measure_overall=none", source)
        self.assertIn("ASTATS_BANDS_LEGACY", source)
        # RMS and peak travel together, and the overall level can be rebuilt
        # from the band powers when wizstats is empty.
        self.assertIn('"bands":', source)
        self.assertIn('"band_peaks":', source)
        self.assertIn("sum_db(band_rms)", source)
        self.assertIn("sum_db(band_peaks)", source)
        self.assertIn("local function main_stat(suffix)", source)
        # Audio heartbeats at 30 Hz without raising the video capture rate.
        self.assertIn("local AUDIO_FPS = 30.0", source)
        self.assertIn("math.max(S.fps, AUDIO_FPS)", source)
        # The removal path must tear the whole analyser down, in any order.
        self.assertIn("{ \"@wizbands\", \"@wizstats\", \"@wiztail\" }", source)


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
