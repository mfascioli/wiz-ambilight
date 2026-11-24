# Panel design

The local panel borrows its visual language from
[mpv-config](https://github.com/mfascioli/mpv-config): an amber-on-charcoal HUD
with square corners, hairlines and condensed type. This file records that
language and the layout rules; the product documentation lives in the
[README](../README.md).

![Design strip: amber, not white](../assets/design.png)

## Tokens

| Token | Value | Used for |
| --- | --- | --- |
| Accent | `#FCBE11` | titles, active keys, focus, the version chip |
| Hairline | `#1F1F1F` | card borders and table rules |
| Shadow | `#33000000` | 20 % black behind floating surfaces (ARGB) |
| Background | charcoal gradient with a faint grid | page and strips |
| Radius | at most `2px` | every control, never pills or bubbles |

Headings are **Merriweather Bold 700**, served from `web/fonts/` under the SIL
OFL, so the panel needs no network and no installed fonts. Body copy and
labels use the system sans stack. The type scale is small and consistent:
section titles, card titles, key/value rows, captions.

The same palette and frame are used by `assets/banner.py` for the README
strips, which is why the screenshots and the documentation look like one
product.

## Reading order

The flow is numbered on screen: **01 Lights → 02 Session → 03 Look →
04 Direct control → 05 Activity**. The numbers are part of the design, not
decoration: they explain the path from choosing bulbs to watching the effect.

## Layout

- **01 Lights** spans the full width. Rooms sit directly above the bulb list;
  the separate Zone map column and its legend are gone, and each row keeps the
  small zone preview where its zone is chosen. Each row also has identify, an
  inclusion switch and a two-step **Forget** action; forgetting removes the
  row and its room membership, never the bulb itself.
- **02–04** use two independent stacks: **02 Session** and **03 Look** on the
  left, **04 Direct control** on the right. Each column grows at its own pace,
  so a short Session never stretches to match a tall Direct control. A
  collapsed card keeps only its header.
- **Session** is one compact row — mode, start, stop — and only adds its start
  time while a sync is running.
- **Direct control** owns power: one switch for the selected bulb, room or all
  bulbs. **Saved colors** reapply a hex and its brightness, and **Saved
  scenes** live in a small `<details>` submenu inside the card, not as a card of
  their own.
- **05 Activity** is a full-width card below the stacks and holds the
  performance chart, with video and capture resolution, read fps and process
  count visible above it.
- **Look** is three equal hairline columns — **Preset / Sample / Send** — with
  flat key/value rows, never nested boxes. **Preset** leads with the Reaction
  group: the dropdown (with a **Video** / **Audio** optgroup each and one hint
  line for the selected mode), then Reaction strength and the **Auto Lux**
  checkbox that layers the light sensor over any reaction. The Equalize target
  luma slider and the **Audio colors** block appear only for the reactions that
  use them; the target lux field and its sensor readout appear only while Auto
  Lux is checked. **Audio colors** is a mode select plus the controls that mode
  needs: one swatch per EQ band for `bands`, a two-color Low/High row for
  `range`, a Soft/Loud row for `level`, one swatch for `single`, and no swatches
  for `spectrum` or `rainbow`. A one-line hint names the current mode. The
  **Capture & fade preset** select follows the reaction group, with a
  hint naming what it bundles, then Brightness and the **Vibrance** slider that
  multiplies the style's saturation. The capture preset, Brightness and
  Vibrance are always visible; the swatches are a hairline grid of equal
  `input[type="color"]` cells labelled with each band's frequency, up to eight
  per row. Reactions never add a fourth column or a second card.
- **Audio dynamics** are one full-width strip inside Look, below the three
  columns: not a fourth column and not a second card. The left side is a
  scrolling five-second **Signal** timeline on a canvas — a −36…0 dBFS grid in
  6 dB steps, an amber input trace, a red light-drive curtain attached to the
  top border and descending by the same `pulse_level` percentage the bulbs
  receive (not another level), and an amber threshold line with a drag handle.
  Dragging anywhere on it writes `react_threshold`. The header pairs the live
  dBFS value with a **LIGHT n %** readout, red once the drive is above zero.
  The right side is **Preset** — four starting points for the knobs — and four
  small round knobs in compressor order: Threshold, Punch, Attack and Release.
  Each knob is an invisible range input over a conic dial. Vertical drag
  changes the value; `Shift` is fine, arrows work when the input has focus, and
  the amber value sits above a tracked uppercase label. The threshold knob is a
  miniature side-chain meter: its outer ring covers **−60…0 dB**, the live dot
  walks toward 0 as the input rises, turns red above the gate and crosses an
  amber tick at the threshold, while the amber dial inside shows the threshold
  value itself. A permanent note explains that Punch sets how hard hits above
  the threshold drive the bulbs. Audio modes show the strip instead of the
  profile select; video modes keep the profile.
- **Below the dynamics strip** a second full-width **EQ** strip carries the
  graphic EQ, again inside Look and never a fourth column or a second card. Its
  header holds **Bands** (2–16), **Auto release** (off / SSL / API 2500 /
  Hybrid), **Detect active bands** and a summary of how many bands are
  assigned. A canvas draws the response from 20 Hz to 20 kHz on a −18…+18 dB
  scale with one draggable node per band. Below it, one vertical fader per band
  shows gain with the frequency and a lamp select; the selected band is
  outlined amber and its frequency, Q, gain and lamp are editable in a flat
  detail row. The frequency control is logarithmic so the low end is not
  squeezed into a few pixels. The strip stays generic: it takes its minimum,
  maximum, gain limit and auto modes from the snapshot, not from hard-coded
  band names.
- Below `1000px` both stacks flatten to a single column in 01 → 05 order.
  `prefers-reduced-motion` disables transitions.

The content is capped at 1080px, so the desktop layout is what the screenshot
and the tests describe; narrower windows reflow. There is no build step: the
panel is plain HTML, CSS and JavaScript under `web/`.

## Performance chart

**Activity** holds one frame with three unit lanes — CPU %, RAM MB, UDP KB/s —
and a line for mpv and for the panel in each lane they share. CPU is a share of
the whole processor and the legend says so in a tooltip. Series colors are
chalk-style and deliberately muted:

| Series | Color |
| --- | --- |
| mpv CPU | `#e08c82` |
| panel CPU | `#9fcf9f` |
| mpv RAM | `#fcbe11` |
| panel RAM | `#8fb6db` |
| WiZ UDP | `#b9a0d8` |

The lanes are never merged onto one axis: percent, megabytes and kilobytes per
second cannot share a scale honestly. The time axis is relative and re-renders
when the card opens or the window resizes. Above the chart, one line shows the
video size, the capture size, the read rate and the process count, so the
resolution is readable without hovering a tooltip.

## Contract

[`tests/test_design.py`](../tests/test_design.py) pins the tokens, the square
corners, the bundled font and licence, the numbered order, the two independent
stacks, the integrated scenes submenu, the three Look columns and the chart
IDs. A restyle that drifts back to a generic dashboard fails CI; change the
test only when the design decision changes.

`docs/gui.png` is a real screenshot of the panel in `--demo` mode. Retake it
when the layout changes instead of mocking one up.
