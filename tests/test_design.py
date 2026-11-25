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
LUA = (ROOT / "lua" / "wiz_ambilight.lua").read_text(encoding="utf-8")


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
        # Two independent stacks: Session and Look on the left, Direct control
        # on the right. The DOM order is the reading order, and a short Session
        # never stretches to match a tall Direct control.
        pairs = re.findall(
            r'<span class="step">(\d\d)</span>\s*<h2>([^<]+)</h2>', HTML
        )
        self.assertEqual(
            pairs,
            [
                ("01", "Lights"),
                ("02", "Session"),
                ("03", "Look"),
                ("04", "Direct control"),
                ("05", "Activity"),
            ],
        )
        self.assertIn('<div class="pair">', HTML)
        self.assertEqual(HTML.count('class="pair-col"'), 2)
        self.assertIn("align-content: start", CSS)
        for area in (".session-card", ".control-card", ".look-card", ".scenes-card"):
            with self.subTest(gone=area):
                self.assertNotIn(f"{area} {{ grid-area:", CSS)
        self.assertNotIn("grid-template-rows: repeat(2, minmax(0, 1fr))", CSS)
        # A collapsed card keeps its natural height instead of a tall shell.
        self.assertIn("align-items: start", CSS)

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
        # The separate Zone map column is gone; the per-light preview remains
        # where the zone is actually chosen.
        self.assertNotIn("What a zone samples", HTML)
        self.assertNotIn("zone-panel", HTML)
        self.assertNotIn("zone-panel", CSS)
        self.assertNotIn("renderMapping", (WEB / "app.js").read_text(encoding="utf-8"))
        self.assertIn("zone-preview", CSS)
        self.assertIn("data-zone", CSS)
        self.assertIn('"zone-preview"', (WEB / "app.js").read_text(encoding="utf-8"))
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

    def test_reactions_are_grouped_by_source(self):
        self.assertIn('id="reactSelect"', HTML)
        self.assertIn('id="reactHint"', HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("fillReactionSelect", js)
        self.assertIn('"optgroup"', js)
        self.assertIn("reactSelect", js)
        self.assertIn("reaction_groups", js)
        for mode in ("equalize", "cut", "motion", "duotone", "beat", "vu"):
            with self.subTest(mode=mode):
                self.assertIn(f'"{mode}"', CORE)
        self.assertIn("AUDIO_REACTIONS", CORE)
        self.assertIn("--react", CORE)
        # The Reaction control lives inside Preset; the three-column contract
        # itself must not grow a fourth column.
        preset = HTML.index('class="look-col"')
        self.assertLess(preset, HTML.index('id="reactSelect"'))
        self.assertLess(HTML.index('id="reactSelect"'), HTML.index("sampleStage"))
        self.assertEqual(HTML.count('class="look-col"'), 3)

    def test_reaction_leads_and_the_style_bundle_is_named_for_what_it_does(self):
        # The reaction (what the bulbs do) opens the column. The style bundle
        # follows the whole reaction group, and its label names capture/fade
        # instead of repeating the column title.
        self.assertLess(HTML.index('id="reactSelect"'), HTML.index('id="reactBands"'))
        self.assertLess(HTML.index('id="reactBands"'), HTML.index('id="styleSelect"'))
        self.assertLess(HTML.index('id="styleSelect"'), HTML.index('id="brightness"'))
        self.assertIn("Capture &amp; fade preset", HTML)
        self.assertIn(
            "One coherent starting point for capture, fade, edge, color and send.",
            HTML,
        )
        self.assertNotIn("Style preset", HTML)
        self.assertIn(
            '<span class="look-col-src">reaction + style</span>', HTML
        )

    def test_reaction_granularity_stays_inside_preset(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        # Strength, profile, target and the audio color source are Preset
        # fields, not new columns or cards.
        for control in (
            'id="reactAmount"',
            'id="reactProfile"',
            'id="reactTarget"',
            'id="reactBands"',
            'id="reactColorMode"',
            'id="reactColorA"',
            'id="reactColorB"',
        ):
            with self.subTest(control=control):
                self.assertIn(control, HTML)
        self.assertLess(HTML.index('id="reactSelect"'), HTML.index('id="reactAmount"'))
        self.assertLess(HTML.index('id="reactAmount"'), HTML.index("sampleStage"))
        self.assertLess(HTML.index('id="reactBands"'), HTML.index("sampleStage"))
        self.assertIn("syncReactionFields", js)
        self.assertIn("fillProfileSelect", js)
        self.assertIn("buildBandInputs", js)
        self.assertIn("buildColorModeSelect", js)
        self.assertIn("react_profile", js)
        self.assertIn("react_bands", js)
        self.assertIn("react_color_mode", js)
        self.assertIn("react_color_a", js)
        self.assertIn("react_color_b", js)
        self.assertEqual(HTML.count('class="look-col"'), 3)

    def test_audio_dynamics_strip_lives_below_the_look_columns(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        for control in (
            'id="dynamicsPanel"',
            'id="vuMeter"',
            'id="reactDynamics"',
            'id="reactThreshold"',
            'id="reactAttack"',
            'id="reactRelease"',
            'id="reactPunch"',
            'id="thresholdKnob"',
            'class="knob-meter"',
            'class="knob-gate"',
            'class="knob-dot"',
        ):
            with self.subTest(control=control):
                self.assertIn(control, HTML)
        # The strip is full-width, after the three columns and outside the
        # manual sampling grid: not a fourth column and not a second card.
        self.assertIn('class="dynamics-strip hidden" id="dynamicsPanel"', HTML)
        self.assertLess(HTML.index("sampleStage"), HTML.index('id="dynamicsPanel"'))
        self.assertLess(HTML.index('id="dynamicsPanel"'), HTML.index('id="samplingManual"'))
        self.assertLess(HTML.index('id="vuMeter"'), HTML.index('id="samplingManual"'))
        # Dynamics controls are round knobs over hidden range inputs, not the
        # old column of sliders.
        for control in ("reactThreshold", "reactAttack", "reactRelease", "reactPunch"):
            with self.subTest(control=control):
                self.assertRegex(
                    HTML,
                    r'id="%s" class="knob-input" type="range"' % control,
                )
        self.assertNotIn('id="vuField"', HTML)
        self.assertNotIn('id="reactThresholdField"', HTML)
        # The threshold knob keeps Pro-C 2's −60…0 dB range so its outer ring
        # can show the live input walking up to 0 dB.
        self.assertIn('id="reactThreshold" class="knob-input" type="range" min="-60"', HTML)
        self.assertIn('value="-18"', HTML)
        # The live readout and the timeline are about light drive, not "over".
        self.assertIn("LIGHT 0%", HTML)
        self.assertIn("Red hangs from the top = light drive", HTML)
        self.assertIn("Punch: how hard hits above the threshold drive the bulbs.", HTML)
        self.assertNotIn("Dynamics preset", HTML)
        self.assertIn("syncDynamicsFields", js)
        self.assertIn("drawTimeline", js)
        self.assertIn("bindScope", js)
        self.assertIn("bindKnobs", js)
        self.assertIn("thresholdFromPointer", js)
        self.assertIn("activationLevel", js)
        self.assertIn("renderLightReadout", js)
        self.assertIn("updateThresholdRing", js)
        # A preset must write the prefixed config keys, not its short labels.
        self.assertIn("react_threshold: preset.threshold", js)
        self.assertIn("react_punch: preset.punch", js)
        self.assertIn("LIGHT ${percent}%", js)
        self.assertIn('SCOPE_MIN_DB = -36', js)
        self.assertIn('KNOB_MIN_DB = -60', js)
        self.assertIn("AUDIO_WINDOW_DB", CORE)
        self.assertIn('"ceiling"', WEBUI)
        self.assertIn('"window"', WEBUI)
        self.assertIn("/api/meter", js)
        self.assertIn("/api/meter", WEBUI)
        self.assertIn("AUDIO_PRESETS", CORE)
        self.assertIn(".dynamics-strip", CSS)
        self.assertIn(".knob-dial", CSS)
        self.assertIn(".knob-input", CSS)
        self.assertIn(".knob-meter", CSS)
        self.assertIn(".knob-gate", CSS)
        self.assertIn(".knob-dot", CSS)
        self.assertIn(".knob.hot .knob-meter", CSS)
        self.assertIn("#vuMeter", CSS)
        self.assertEqual(HTML.count('class="look-col"'), 3)

    def test_eq_strip_lives_below_the_dynamics_strip(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        for control in (
            'id="eqPanel"',
            'id="eqBandCount"',
            'id="eqCanvas"',
            'id="eqFaders"',
            'id="eqSummary"',
            'id="reactAuto"',
            'id="reactActiveBands"',
            'id="eqFreq"',
            'id="eqQ"',
            'id="eqGain"',
            'id="eqLamp"',
            'id="eqType"',
            'id="eqSlope"',
            'id="eqSolo"',
        ):
            with self.subTest(control=control):
                self.assertIn(control, HTML)
        # A second full-width strip, after dynamics and outside the columns.
        self.assertIn('class="eq-strip hidden" id="eqPanel"', HTML)
        self.assertLess(HTML.index('id="dynamicsPanel"'), HTML.index('id="eqPanel"'))
        self.assertLess(HTML.index('id="eqPanel"'), HTML.index('id="samplingManual"'))
        self.assertEqual(HTML.count('class="look-col"'), 3)
        # The frequency slider is logarithmic: 0…1000 maps onto 20 Hz…20 kHz.
        self.assertIn('id="eqFreq" type="range" min="0" max="1000"', HTML)
        for name in (
            "drawEq",
            "buildEqFaders",
            "syncEqFields",
            "eqCurveGain",
            "eqBandGain",
            "buildEqAuto",
            "buildEqType",
            "buildEqSlope",
            "eqTypeShort",
            "eqUsesSlope",
            "eqFreqToLog",
            "eqLogToFreq",
        ):
            with self.subTest(name=name):
                self.assertIn(name, js)
        self.assertIn("react_eq", js)
        self.assertIn("react_eq_bands", js)
        self.assertIn("react_auto", js)
        self.assertIn("react_active_bands", js)
        self.assertIn("requestAnimationFrame", js)
        self.assertIn(".eq-strip", CSS)
        self.assertIn(".eq-faders", CSS)
        self.assertIn(".eq-detail", CSS)
        self.assertIn(".eq-band-solo", CSS)
        self.assertIn(".eq-band-shape", CSS)
        self.assertIn("#eqCanvas", CSS)
        for constant in (
            "MAX_BANDS",
            "MIN_BANDS",
            "DEFAULT_EQ_BANDS",
            "BAND_COLOR_PALETTE",
            "AUTO_MODES",
            "ACTIVE_MARGIN_DB",
            "EQ_BAND_TYPES",
            "EQ_SLOPES",
            "EQ_DEFAULT_SLOPE",
        ):
            with self.subTest(constant=constant):
                self.assertIn(constant, CORE)
        self.assertIn("eq_splits", CORE)
        self.assertIn('"eq_limits"', WEBUI)
        self.assertIn('"auto_modes"', WEBUI)
        self.assertIn('"lamps"', WEBUI)

    def test_vibrance_stays_inside_preset(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="vibrance"', HTML)
        self.assertIn('id="vibranceOut"', HTML)
        self.assertLess(HTML.index('id="brightness"'), HTML.index('id="vibrance"'))
        self.assertLess(HTML.index('id="vibrance"'), HTML.index("sampleStage"))
        self.assertIn("config.vibrance", js)
        self.assertIn("vibrance: value", js)
        self.assertIn('"vibrance"', WEBUI)
        self.assertIn("--vibrance", CORE)
        self.assertEqual(HTML.count('class="look-col"'), 3)

    def test_white_leds_switch_sits_with_the_send_controls(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="whiteLeds"', HTML)
        self.assertLess(HTML.index('id="sendStage"'), HTML.index('id="whiteLeds"'))
        self.assertLess(HTML.index('id="whiteLeds"'), HTML.index('id="dryRun"'))
        self.assertIn("white_leds", js)
        self.assertIn('"white_leds"', WEBUI)
        self.assertIn("--white-leds", CORE)
        self.assertIn("white_led_params", CORE)

    def test_band_color_swatches_keep_the_hairline_language(self):
        self.assertIn(".band-colors", CSS)
        self.assertIn(".band-color", CSS)
        # Five equal slots, a real color input, and no new radius token.
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", CSS)
        self.assertIn('input[type="color"]', CSS)

    def test_lights_can_be_forgotten(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/light/delete", js)
        self.assertIn("Forget this light", js)
        self.assertIn("def delete_light", WEBUI)

    def test_look_reads_as_three_flat_columns(self):
        # Preset, sample and send share the width in three equal columns.
        # Values are flat key/value rows, not nested boxes.
        self.assertIn('class="look-cols"', HTML)
        self.assertEqual(HTML.count('class="look-col"'), 3)
        for stage in ("sampleStage", "colorStage", "sendStage"):
            with self.subTest(stage=stage):
                self.assertIn(f'id="{stage}"', HTML)
                self.assertRegex(HTML, r'class="kv" id="%s"' % stage)
        self.assertIn("A sampling preset can only lower the read rate", HTML)
        self.assertIn('id="layoutHint"', HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("Edge band", js)
        self.assertIn("function renderStage", js)
        self.assertIn('"kv-row"', js)
        for label in ("Frame", "Columns", "Avg pixels", "Saturation", "Brightness"):
            with self.subTest(label=label):
                self.assertIn(f'["{label}"', js)
        for gone in ("stage-row", "stage-list", "class=\"signal", "span-2", "look-grid"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, HTML)
                self.assertNotIn(gone, js)
        for gone in ("styleHint", "samplingHint", "SAMPLING_HINTS", "styleSpec", "samplingSpec", "renderSpec"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, js)
                self.assertNotIn(gone, HTML)

    def test_activity_has_one_performance_chart(self):
        # One frame, three unit lanes and five colored series: mpv and the
        # panel each get a CPU and a RAM line, plus the WiZ UDP rate.
        self.assertIn('id="perfSvg"', HTML)
        self.assertIn('id="perfLegend"', HTML)
        self.assertIn('id="perfMeta"', HTML)
        self.assertIn('class="perf"', HTML)
        self.assertNotIn('class="spark"', HTML)
        self.assertNotIn('class="resources"', HTML)
        js = (WEB / "app.js").read_text(encoding="utf-8")
        for series in ("mpvCpu", "wizCpu", "mpvRam", "wizRam", "udp"):
            with self.subTest(series=series):
                self.assertIn(series, js)
        self.assertIn("PERF_LANES", js)
        self.assertIn("renderPerfChart", js)
        # Idle UDP is a dash and a running dry run says so instead of showing a
        # zero as if datagrams were flowing.
        self.assertIn("dry run", js)
        for key in ("cpu_mpv", "ram_mpv", "cpu_wiz", "ram_wiz", "udp_kbps", "cores"):
            with self.subTest(key=key):
                self.assertIn(key, WEBUI)
        # The Lua state file carries mpv's pid so attach mode can sample it.
        self.assertIn('get_property_native("pid")', LUA)
        self.assertIn("stats-", CORE)

    def test_power_is_a_direct_control_switch_and_rooms_target_lights(self):
        for control in (
            "rooms",
            "newRoomBtn",
            "roomList",
            "roomEditor",
            "roomMembers",
            "powerToggle",
            "powerState",
            "colorChips",
            "saveColorBtn",
            "scenesMenu",
        ):
            with self.subTest(control=control):
                self.assertIn(f'id="{control}"', HTML)
        self.assertNotIn('id="powerOnBtn"', HTML)
        self.assertNotIn('id="powerOffBtn"', HTML)
        # Per-bulb power is gone: power lives in Direct control only.
        js = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("Toggle light power", js)
        self.assertIn("Target this room in Direct control", js)
        self.assertIn('class="submenu" id="scenesMenu"', HTML)
        self.assertIn("kelvinToHex", js)
        for needle in ("group:", "/api/group", "/api/color", "openRoomEditor", "renderRooms"):
            with self.subTest(needle=needle):
                self.assertIn(needle, js)
        self.assertIn('"groups"', WEBUI)
        self.assertIn('"colors"', WEBUI)
        self.assertIn("def set_group", WEBUI)
        self.assertIn("def save_color", WEBUI)
        self.assertIn('"brightness"', WEBUI)

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
