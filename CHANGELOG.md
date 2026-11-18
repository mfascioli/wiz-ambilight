# Changelog

Releases before 1.4.0 were never tagged; their history is in `git log`.

## Unreleased

- **Docs:** the README is restructured around the mpv-config layout — hero
  banner, one strip per section, and a single panel screenshot instead of
  three. The fork note moves from the intro to **Credits**, which now names
  mpv, `wiz-hack`, `mpv-config` and Merriweather.
- **Docs:** new **Privacy and security** section (local UDP, no cloud, panel
  guarantees, how the code was written) and a **Roadmap** that lists the
  Windows gaps and the pending transport measurement.
- **Docs:** new **Also check out** closing pointer to
  [`mpv-config`](https://github.com/mfascioli/mpv-config), with a crop of its
  keyboard map.
- **Repository:** `SECURITY.md` (trust model, what the code touches, review
  status, limits) and `AGENTS.md` (context for future agents), plus
  `assets/banner.py` and its bundled Fira Sans Condensed for the README images.
- **Repository:** `docs/gui-launch.png` and `docs/gui-control.png` are removed;
  `docs/gui.png` is the only screenshot left.

## 1.5.0 — 2026-11-17

- **Panel:** inherits the mpv-config design language — amber `#FCBE11`,
  charcoal HUD grid, `1px` `#1F1F1F` hairlines, square corners, bracket
  corners on cards and Merriweather Bold for headings, served from
  `web/fonts/`.
- **Panel:** sections are numbered in reading order (`01` Lights → `06`
  Activity) with a three-step quick start at the top.
- **Tests:** `tests/test_design.py` pins the palette, the type, the HUD and the
  numbering, so a generic restyle fails CI.

## 1.4.0 — 2026-11-17

- **Panel:** first release of the local web UI — bulb scanning and naming,
  zone map, layout, style and brightness, attach or launch mode, and the
  activity log, all served from `127.0.0.1` with a per-run token and a strict
  CSP.
- **Panel:** **Direct control** for one bulb or all — power, brightness, white
  temperature, color picker and hex field, WiZ scenes with speed — plus saved
  scenes and a hex chip to resend a color.
- **Panel:** manual commands wait for the bulb's reply, and a silent bulb is
  greyed out and named instead of failing quietly, with **Panel network**
  explaining a bulb that sits outside the computer's subnet.
- **Panel:** **Crazy 20 s**, capped at 20 updates/s and refused while the sync
  owns the bulbs.
- **Discovery:** a manual scan probes the broadcast three times and then every
  address on the local `/24`, which finds bulbs that ignore broadcast.
- **Control:** quicker cuts — a large color jump snaps on the next frame while
  gentle camera moves still fade.
- **CLI:** `--set` for the same controls without a browser, `--dry-run` to
  print the payloads, and `--demo` for a panel that never sends UDP.
