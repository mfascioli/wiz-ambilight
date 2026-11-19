"""The panel must keep the mpv-config design language.

Tokens taken from https://github.com/mfascioli/mpv-config:

    fill    #FCBE11
    outline #1F1F1F at 1.5
    shadow  #33000000 at 1 px
    type    Merriweather Bold 700

These tests are the contract: if a future restyle turns the panel back into a
generic purple dashboard, CI fails.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CSS = (WEB / "style.css").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")
WEBUI = (ROOT / "webui.py").read_text(encoding="utf-8")
CORE = (ROOT / "mpv_ambilight.py").read_text(encoding="utf-8")


def root_tokens():
    block = re.search(r":root\s*\{(.*?)\}", CSS, re.S)
    if block is None:
        raise AssertionError("style.css has no :root token block")
    tokens = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1)):
        tokens[name] = value.strip()
    return tokens


TOKENS = root_tokens()


class PaletteTests(unittest.TestCase):
    def test_amber_is_the_mpv_config_amber(self):
        self.assertEqual(TOKENS["--amber"].lower(), "#fcbe11")

    def test_outline_is_the_mpv_config_outline(self):
        self.assertEqual(TOKENS["--line"].lower(), "#1f1f1f")

    def test_shadow_uses_the_mpv_config_argb(self):
        self.assertIn("33000000", TOKENS["--shadow"].lower())

    def test_old_purple_theme_is_gone(self):
        legacy = (
            "#ffb44d",
            "#ff7a59",
            "#0e0d12",
            "#1a1822",
            "#211f2b",
            "#2e2b3a",
            "#a39db4",
            "#6ee7a8",
            "#ff6b81",
        )
        for color in legacy:
            with self.subTest(color=color):
                self.assertNotIn(color, CSS.lower())

    def test_every_css_variable_is_defined(self):
        defined = set(TOKENS)
        used = set(re.findall(r"var\((--[\w-]+)", CSS))
        self.assertEqual(used - defined, set())


class TypographyTests(unittest.TestCase):
    def test_display_type_is_merriweather(self):
        self.assertIn("Merriweather", TOKENS["--font-display"])

    def test_font_is_declared_and_served_from_the_panel(self):
        self.assertIn('font-family: "Merriweather"', CSS)
        self.assertIn('url("fonts/Merriweather-Bold.ttf")', CSS)
        self.assertIn("/fonts/Merriweather-Bold.ttf", WEBUI)
        self.assertIn("font-src 'self'", WEBUI)

    def test_font_file_is_bundled_with_its_ofl_licence(self):
        font = WEB / "fonts" / "Merriweather-Bold.ttf"
        licence = WEB / "fonts" / "Merriweather-OFL.txt"
        self.assertTrue(font.is_file(), "Merriweather-Bold.ttf is not bundled")
        self.assertTrue(licence.is_file(), "the SIL OFL licence is missing")
        self.assertGreater(font.stat().st_size, 50_000)
        self.assertIn(font.read_bytes()[:4], (b"\x00\x01\x00\x00", b"true"))

    def test_ui_labels_use_tracked_uppercase(self):
        self.assertIn("text-transform: uppercase", CSS)
        self.assertIn("letter-spacing: .09em", CSS)


class HudTests(unittest.TestCase):
    def test_hud_is_square_not_rounded(self):
        radius = int(re.search(r"(-?\d+)px", TOKENS["--radius"]).group(1))
        self.assertLessEqual(radius, 2)
        self.assertNotIn("border-radius: 999px", CSS)

    def test_charcoal_hud_grid(self):
        self.assertIn("background-size: 72px 72px", CSS)
        self.assertGreaterEqual(CSS.count("linear-gradient"), 2)

    def test_cards_have_amber_bracket_corners(self):
        shared = re.search(r"\.card::before,\s*\.card::after\s*\{([^}]*)\}", CSS, re.S)
        self.assertIsNotNone(shared)
        self.assertIn("border-color: var(--amber)", shared.group(1))
        for corner in (
            ".card::before { top: -1px; left: -1px; border-width: 1px 0 0 1px; }",
            ".card::after { right: -1px; bottom: -1px; border-width: 0 1px 1px 0; }",
        ):
            with self.subTest(corner=corner):
                self.assertIn(corner, CSS)


class StructureTests(unittest.TestCase):
    def test_sections_are_numbered_in_reading_order(self):
        # The cards live in two independent columns (02/04 left, 03/05 right)
        # so opening Direct control cannot push Look down. The numbers still
        # match their headings, and each column holds its own stack.
        pairs = re.findall(
            r'<span class="step">(\d\d)</span>\s*<h2>([^<]+)</h2>', HTML
        )
        self.assertEqual(
            pairs,
            [
                ("01", "Lights"),
                ("02", "Session"),
                ("04", "Look"),
                ("03", "Direct control"),
                ("05", "My scenes"),
                ("06", "Activity"),
            ],
        )
        columns = HTML.split('<div class="pair-col">')[1:]
        self.assertEqual(len(columns), 2)
        self.assertIn("session-card", columns[0])
        self.assertIn("look-card", columns[0])
        self.assertNotIn("control-card", columns[0])
        self.assertIn("control-card", columns[1])
        self.assertIn("scenes-card", columns[1])
        self.assertNotIn("look-card", columns[1])
        self.assertIn(".pair-col", CSS)
        self.assertIn("align-content: start", CSS)

    def test_the_panel_opens_without_a_quick_start_strip(self):
        self.assertNotIn("quickstart", HTML)
        self.assertNotIn("quick-step", HTML)
        self.assertIn("Each bulb copies one", HTML)
        self.assertLess(HTML.index("lights-card"), HTML.index("session-card"))

    def test_sections_can_collapse(self):
        for card in ("lights-card", "session-card", "control-card", "log-card"):
            with self.subTest(card=card):
                self.assertRegex(HTML, r'<details class="card %s"' % card)
        # Direct control and the activity console are not the normal path.
        self.assertNotRegex(HTML, r'<details class="card control-card"[^>]* open')
        self.assertNotRegex(HTML, r'<details class="card log-card"[^>]* open')

    def test_zones_are_explained_visually(self):
        self.assertIn("What a zone samples", HTML)
        self.assertIn('class="zone-preview"', HTML)
        self.assertIn("zone-preview", CSS)
        self.assertIn("data-zone", CSS)
        for label in ("left edge", "right edge", "left third", "middle third", "right third"):
            with self.subTest(label=label):
                self.assertIn(label, (WEB / "app.js").read_text(encoding="utf-8"))
        self.assertNotIn("top-left", (WEB / "app.js").read_text(encoding="utf-8"))

    def test_crazy_is_a_short_hidden_burst(self):
        self.assertNotIn("crazyBtn", HTML)
        self.assertNotIn("Crazy 20", HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("crazyEasterEgg", js)
        self.assertIn("CRAZY_WINDOW = 3000", js)
        self.assertIn("CRAZY_SECONDS = 5.0", WEBUI)
        self.assertIn("dimming", WEBUI)

    def test_sampling_profiles_are_selectable(self):
        for control in (
            "samplingSelect",
            "samplingManual",
            "samplingFps",
            "samplingGrid",
            "samplingBlock",
            "samplingCapture",
        ):
            with self.subTest(control=control):
                self.assertIn(f'id="{control}"', HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        for label in ("Auto — follows the video size", "Lean", "Balanced", "Quality", "Manual"):
            with self.subTest(label=label):
                self.assertIn(label, js)
        self.assertIn("SAMPLING_PROFILES", CORE)
        self.assertIn("--sampling", CORE)

    def test_look_reads_as_a_signal_path(self):
        # Sample -> color -> send, with the preset that owns each stage named.
        # The numbers stay, but every one sits under a plain-language label.
        self.assertIn('class="signal span-2"', HTML)
        for stage in ("sampleStage", "colorStage", "sendStage"):
            with self.subTest(stage=stage):
                self.assertIn(f'id="{stage}"', HTML)
        self.assertIn("A sampling preset can only lower the read rate", HTML)
        self.assertIn('id="layoutHint"', HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("Edge band", js)
        self.assertIn("function renderStage", js)
        for label in ("Frame", "Columns", "Avg pixels", "Saturation", "Brightness"):
            with self.subTest(label=label):
                self.assertIn(f'["{label}"', js)
        for gone in (
            "styleHint",
            "samplingHint",
            "SAMPLING_HINTS",
            "styleSpec",
            "samplingSpec",
            "renderSpec",
        ):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, js)
                self.assertNotIn(gone, HTML)

    def test_resources_strip_has_cpu_ram_and_network(self):
        self.assertEqual(HTML.count('class="spark"'), 3)
        for control in ("resCpu", "resRam", "resNet", "sparkCpu", "sparkRam", "sparkNet"):
            with self.subTest(control=control):
                self.assertIn(f'id="{control}"', HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("sparkPath", js)
        self.assertIn("network_bps", WEBUI)
        self.assertIn("stats-", CORE)

    def test_panel_stays_local_only(self):
        self.assertIn("127.0.0.1", WEBUI)
        self.assertIn("default-src 'none'", WEBUI)


class HardwareIdTests(unittest.TestCase):
    def test_hardware_ids_are_hover_only(self):
        # The model string is data, not chrome: it lives in a tooltip on the IP.
        self.assertNotIn('<span class="model">', HTML)
        self.assertIn(".meta .model { display: none; }", CSS)
        self.assertIn("Hover an IP for its hardware id", HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("dataset.hw", js)
        self.assertIn('content: attr(data-hw);', CSS)


if __name__ == "__main__":
    unittest.main()
