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

The flow is numbered on screen: **01 Lights → 02 Session → 03 Direct control →
04 Look → 05 My scenes → 06 Activity**. The numbers are part of the design, not
decoration: they explain the path from choosing bulbs to watching the effect.

## Layout

- **01 Lights** spans the full width and keeps its own **Zone map** column, so
  the miniature frame and the zone legend sit beside the bulb list.
- **02–05** share one 2×2 grid with two equal rows. The four modules keep the
  same width and height, in reading order: 02 Session and 04 Look on the left,
  03 Direct control and 05 My scenes on the right. A collapsed card keeps only
  its header inside its cell.
- **06 Activity** is a full-width card below the grid and holds the performance
  chart.
- **Look** is three equal hairline columns — **Preset / Sample / Send** — with
  flat key/value rows, never nested boxes.
- Below `1000px` the grid falls back to a single column in 01 → 06 order.
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
when the card opens or the window resizes.

## Contract

[`tests/test_design.py`](../tests/test_design.py) pins the tokens, the square
corners, the bundled font and licence, the numbered order, the 2×2 grid, the
three Look columns and the chart IDs. A restyle that drifts back to a generic
dashboard fails CI; change the test only when the design decision changes.

`docs/gui.png` is a real screenshot of the panel in `--demo` mode. Retake it
when the layout changes instead of mocking one up.
