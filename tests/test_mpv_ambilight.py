"""Unit tests for the parts that do not need bulbs or a running mpv."""

import contextlib
import io
import json
import os
import socket
import sys
import threading
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

    def test_vu_level_maps_dbfs(self):
        self.assertEqual(m.vu_level(-60), 0.0)
        self.assertEqual(m.vu_level(-45), 0.0)
        self.assertEqual(m.vu_level(-12), 1.0)
        self.assertEqual(m.vu_level(0), 1.0)
        self.assertAlmostEqual(m.vu_level(-28.5), 0.5)
        self.assertEqual(m.vu_level(None), 0.0)

    def test_beat_pulse_attacks_then_releases(self):
        self.assertEqual(m.beat_pulse(-0.1), 0.0)
        self.assertEqual(m.beat_pulse(0.0), 0.0)
        self.assertAlmostEqual(m.beat_pulse(m.BEAT_ATTACK / 2), 0.5)
        self.assertAlmostEqual(m.beat_pulse(m.BEAT_ATTACK), 1.0)
        self.assertAlmostEqual(
            m.beat_pulse(m.BEAT_ATTACK + m.BEAT_RELEASE / 2), 0.5
        )
        self.assertEqual(m.beat_pulse(m.BEAT_ATTACK + m.BEAT_RELEASE + 1), 0.0)

    def test_cut_pulse_is_a_short_square(self):
        self.assertEqual(m.cut_pulse(0.0), 1.0)
        self.assertEqual(m.cut_pulse(m.CUT_SECONDS - 0.001), 1.0)
        self.assertEqual(m.cut_pulse(m.CUT_SECONDS), 0.0)


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
        self.update(reaction, 100.4, audio={"rms": -25.0})
        self.assertEqual(reaction.beat_at, 100.4)
        self.assertEqual(
            reaction.dimming("a", 100, 100.4 + m.BEAT_ATTACK, 0.05), 100
        )
        self.assertEqual(reaction.dimming("a", 100, 101.2, 0.05), 75)

    def test_vu_follows_the_left_and_right_channels(self):
        reaction = m.Reaction("vu", 1.0, 0.45)
        audio = {"rms": -20.0, "l": -12.0, "r": -45.0}
        now = 100.0
        for _ in range(40):
            self.update(
                reaction,
                now,
                audio=audio,
                lights=("left-bulb", "right-bulb"),
                names=("left", "right"),
            )
            now += 0.05
        self.assertAlmostEqual(reaction.levels["left-bulb"], 1.0)
        self.assertAlmostEqual(reaction.levels["right-bulb"], 0.0)
        left = reaction.dimming("left-bulb", 100, now, 0.05)
        right = reaction.dimming("right-bulb", 100, now, 0.05)
        self.assertGreater(left, right)
        self.assertEqual(right, 25)


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
