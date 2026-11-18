# Changelog

Releases before 1.4.0 were never tagged; their history is in `git log`.

## Unreleased

- **Panel:** crazy mode now pauses an attach-mode sync, restores every bulb's
  previous `getPilot` state after the burst and then resumes the sync. If the
  state cannot be read, the burst still ends on a full-brightness amber frame
  instead of the dim end of the sweep. Launch mode still asks you to stop the
  player first.
- **Panel:** the hidden gesture is more forgiving — three clicks within three
  seconds, with a small tap animation on the status dot.
- **Panel:** compact Apple-like pass over the existing mpv-config tokens: the
  three-step intro strip is gone, the header and cards are shorter, light rows
  are dense lists, buttons and sliders are smaller, the active sync mode is a
  solid amber segment and Activity spans the full width.
- **Tests:** pin `restore_params`, the attach pause/resume path and the
  three-second gesture window.
- **Docs:** refresh `docs/gui.png`.

## 1.6.0 — 2026-11-18

- **Panel:** every card collapses. Direct control and Activity start closed,
  so the first screen is lights, session and look; the quick start is three
  short steps instead of three sentences.
- **Panel:** zones are explained with a miniature video frame that highlights
  the sampled region, in each bulb row and in the zone map. The misleading
  `t1/t2/t3 → top-left/top-centre/top-right` labels are gone: thirds are
  left, middle and right.
- **Panel:** Direct control is more compact — two-column fields, shorter
  sliders and the target pill in the collapsed header.
- **Panel:** crazy mode is now a hidden five-second burst on the grey status
  dot (three clicks), at the 20 updates/s ceiling, with brightness sweeping
  from 10% to 100% and back instead of only changing hue.
- **Security:** stopping a sync no longer calls `os.killpg` unconditionally;
  it uses the process group when available and falls back to
  `terminate()`/`kill()`. PID adoption now verifies `/proc/<pid>/cmdline` or
  `ps -p <pid> -o command=` and refuses to trust a stale `gui-daemon.json`.
- **Docs:** new architecture diagram (`docs/architecture.mmd` and
  `docs/architecture.svg`) covering components, data exchanged, dependencies,
  local vs internet, exposed interfaces and trust boundaries; `SECURITY.md`
  gets an exposed-interface table and a review-status update.
- **Docs:** the AI note now claims only DeepSeek V4.1 Flash Free in OpenCode,
  which is what was used in this repository.
- **Tests:** new `tests/test_security.py` pins loopback-only binding, no
  wildcard binds, portable process control, PID verification, the five-second
  crazy defaults and the architecture docs. `tests/test_design.py` now pins
  the collapsible layout, the concise quick start and the zone previews.
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
