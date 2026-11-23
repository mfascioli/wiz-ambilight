# Changelog

Releases before 1.4.0 were never tagged; their history is in `git log`.

## Unreleased

- **Audio:** `beat` and `vu` now share a compressor-style level stage.
  `pulse_level` gates levels below a dBFS threshold, maps the window up to a
  ceiling onto 0…1 and applies a punch curve, so a solid hit reaches full
  brightness instead of drifting halfway. The default window is −22…−10 dBFS
  with a 1 ms attack, 55 ms release and punch 3.0; `beat` covers 75 % of the
  range with the flash and `vu` uses the full swing. Quiet ticks no longer
  trigger beats, and a hit scales with its band level but any solid hit reaches
  full scale.
- **Panel:** a full-width dynamics strip under the three Look columns — not a
  fourth column and not a second card — shows a scrolling five-second **Signal**
  timeline with dBFS grid, amber trace and red peaks above the threshold. The
  amber threshold line is draggable and writes `react_threshold`. A **Dynamics
  preset** select and four round knobs — Threshold, Attack, Release and Punch —
  replace the old sliders; each knob is a vertical drag (Shift for fine) over a
  hidden, keyboard-accessible range input. Four presets ship: **Mellow**,
  **Glue**, **Punch** (default) and **Strobe**. Audio modes show the strip
  instead of the profile select; video modes keep the profile. Both the timeline
  and the readouts use `GET /api/meter`, which samples the live Lua state at
  40 ms without restarting the sync.
- **CLI:** `--react-threshold`, `--react-attack`, `--react-release` and
  `--react-punch` expose the same four values; `--react-profile` still works as
  a starting bundle for audio modes.
- **Docs:** README, `docs/development.md`, `docs/design.md` and `AGENTS.md`
  describe the dynamics stage, the timeline and the knobs. The roadmap now
  includes the UI/UX redesign as item 5.
- **Docs:** the README follows one reading path and teaches the panel first.
  **Getting Started** absorbs the old Installation and Quick Start: one clone
  plus `--gui`, and cloning never copies the Lua script into mpv — only attach
  mode needs that one-time copy because mpv is already running. **Web Panel &
  Operating Modes** absorbs Attach, and **Configuration** groups
  Capture/Fade/Send, Styles, Sampling, Layouts & Zones, Reactions, Audio
  Dynamics, Band Colors and Audio Processing. Environment is a single
  top-level table and now includes `XDG_CONFIG_HOME`. The panel table documents
  **Quit**, **Identify** and the sync dry-run switch. The terminal reference —
  discovery, launch and attach, `--set`, style, reaction and sampling flags,
  the systemd service and scripted looks — moved to `docs/cli.md`, linked from
  **Getting Started** and **Command Line**; it gains the exhaustive flag,
  default, range and exit-code tables, so the README no longer duplicates the
  catalogue. `AGENTS.md` records the GUI-first and attach-only install rules.

## 1.10.0 — 2026-11-22

- **Audio:** `beat` and `vu` now react on the first transient instead of
  waiting for a smoothed RMS window. Beats have an instant attack, a 3 dB
  threshold over a fast baseline and twice the headroom, so the flash is a
  visible jump rather than a tremble. The VU meter follows RMS plus sample
  peaks with an 8 ms attack and a 110 ms release, raises the level to the 1.4
  power to darken quiet passages, and uses the full brightness range. The
  envelope is now timed by the send tick instead of the polling loop, which
  was stretching its release by roughly six times. The Lua analyser exposes
  per-band peaks, and audio state updates and sends run at 30 Hz even when
  video capture stays at 12–20 fps. Some mpv builds only expose the last
  `astats`; the Lua script rebuilds the overall level from the band powers
  instead of going silent.
- **Panel:** **Preset** now leads with the reaction group; the style bundle is
  called **Capture & fade preset** and explains what it sets. A new
  **Vibrance** slider multiplies the style's saturation from 50 % to 200 %
  (`--vibrance` on the CLI). It composes with the style and every reaction
  without changing fade, edge or send rate.

## 1.9.0 — 2026-11-22

- **Reactions:** `equalize`, `cut`, `motion`, `beat` and `vu` now share three
  profiles — `soft`, `balanced` and `strong` — exposed as **Reaction profile**
  in **Look → Preset** and `--react-profile` on the CLI. A profile moves span,
  speed, threshold and rate limit together, and still composes with **Reaction
  strength** (`react_amount`), which the panel now exposes as a slider.
- **Reactions:** every mode has a plain-language description in the panel and
  the README. `cut` now explains that it reacts to one hard edit, not camera
  motion, and what the dimmed interval between flashes is for.
- **Audio:** `beat` and `vu` split the mix into five bands — `sub`, `low`,
  `low-mid`, `mid`, `high` — each with its own color picker in **Look →
  Preset** or `--react-bands '#…,#…,#…,#…,#…'`. One bulb follows the overall
  volume (0–100 %); 2–5 bulbs spread the bands from sub to high, and more than
  five repeat. The Lua analyser now uses a labelled
  `acrossover`/`amerge`/`astats` graph that recombines the slices before
  output: magnitude is preserved, with an all-pass phase shift.
- **Panel:** Reaction strength, profile, Equalize target and the five band
  color swatches live inside **Preset** as flat rows; the three-column Look
  contract is unchanged. Controls appear only for the reactions that use them.
- **Docs:** README Reactions, `docs/development.md`, `docs/design.md` and
  `SECURITY.md` describe the profiles, bands and the corrected audio path.
- **Tests:** cover band assignment for 1–7 bulbs, profile parameter changes,
  reaction descriptions, the Lua band graph, config normalization, command
  flags and snapshot metadata.

## 1.8.0 — 2026-11-22

- **Reactions:** six new modes on top of plain color — `equalize`, `cut`,
  `motion` and `duotone` follow the video; `beat` and `vu` follow the audio.
  One **Reaction** dropdown in **Look → Preset** groups Video and Audio, and
  `--react`, `--react-amount` and `--react-target` expose the same choice on the
  CLI. Audio modes add a labelled `astats` pass-through filter to mpv only
  while selected and remove it when they end; no dependency is added. The
  light-sensor `lux.json` path is documented for a future real-lux Equalize.
- **Panel:** each light row has a two-step **Forget** action. It removes the
  row from `lights.json` and from every room; **Scan network** can add a
  reachable bulb back, so deleting is for stale addresses and duplicates,
  while the inclusion switch keeps a bulb out of the sync.
- **Panel:** demo mode now replaces the saved bulb list with three named
  fixtures instead of merging into it. Real and demo addresses no longer
  appear twice, once unnamed, when a real config exists.
- **Panel:** Session and Look share the left stack, Direct control gets its own
  right stack, so a short Session no longer stretches to match a tall card.
  Below 1000 px the stacks flatten to 02 → 03 → 04.
- **Panel:** Session is one compact row — mode, start and stop — and only shows
  its start time while a sync runs. Lights and Activity are renumbered 01 and
  05; the separate Zone map column and its legend are gone.
- **Panel:** Look is flat and modular — Preset, Sample and Send in three equal
  hairline columns with key/value rows instead of nested boxes.
- **Panel:** one performance chart in Activity replaces the strip under the
  cards, with three unit lanes (CPU %, RAM MB, UDP KB/s) and a line each for
  mpv and for the panel; CPU is a share of the whole processor, stated in the
  legend tooltip. Video and capture resolution, read fps and the process count
  are now visible above the chart instead of hidden in a tooltip.
- **Panel:** power lives only in Direct control; Lights keeps naming, zones and
  inclusion. Rooms are direct-control targets: clicking a room selects it,
  opens the card and leaves editing to its own pencil button. Saved scenes are
  a small disclosure inside Direct control.
- **Panel:** a saved color now stores its brightness too. Clicking a chip
  reapplies both; legacy bare-hex entries load at 100 %. Changing **White**
  maps the Kelvin value to an approximate hex and updates the field live.
- **Panel:** rooms group bulbs, Direct control uses a power switch, and a
  saved-colors row reapplies or deletes a color in one click. Rooms and colors
  live in `lights.json` and never restart the sync; RGB and white temperature
  are kept mutually exclusive.
- **Lua:** the state file carries mpv's pid, so the panel can sample a player
  it did not launch in attach mode.
- **Panel:** hardware ids stay in an IP tooltip, a name/IP/model filter trims
  long lists, and the dry-run checkbox now says it applies to the sync.
- **Discovery:** a deep scan sweeps the local /24 before starting its listen
  window, so the ARP delay no longer expires the timeout and drops one of two
  live bulbs.
- **Panel:** capture size and video resolution are reported separately, and a
  stale mpv state file no longer leaves the last movie's size on screen.
- **Tests:** pin the two-column stacks, the slim Session, the integrated scenes
  menu, the room targets, the saved-color brightness schema and the chart
  payload.
- **Docs:** the README now follows the user's path — overview, features,
  requirements, installation, quick start, panel, operating modes,
  configuration, direct control, architecture, performance, security,
  troubleshooting, development, roadmap, credits and related projects.
  Aesthetic and layout detail moved to `docs/design.md`; repository layout,
  runtime files, config schemas and scripted recipes moved to
  `docs/development.md`. Capture fps, fade ms and send Hz are explained
  separately, and the duplicated passages between Features, Performance,
  Architecture and Security are gone.
- **Docs:** refresh `docs/gui.png`, add the new section strips and update the
  banner generator.

## 1.7.0 — 2026-11-18

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
- **Performance:** sampling is now separate from the style preset and
  resolution-aware. `auto` (default) uses `scaled` capture and picks 80/96/112
  columns, 1×1 or 2×2 blocks and the style rate / 12 / 8 fps from the captured
  height; `lean`, `balanced` and `quality` are fixed trade-offs; `manual`
  exposes `--fps`, `--sample-grid`, `--sample-block` and `--capture`. An
  explicit `--fps` or `--capture` still wins over the profile, so `--style`
  keeps controlling fade, edge, saturation and send rate independently.
- **Capture:** `screenshot-raw scaled` copies the window-size frame instead of
  the decoded source (a 4K movie in a 720p window copies one ninth of the
  pixels) and falls back to `video` once if the output refuses the flag.
- **Panel:** the Look card gets a **Sampling** menu with the same profiles and
  manual controls; values are saved in `lights.json` and applied on start.
- **Panel:** a thin resource strip under the cards graphs CPU, RAM and WiZ UDP
  for the panel and its sync child. CPU/RSS come from `/proc` (graceful `n/a`
  elsewhere); UDP counts real datagrams from the new `stats-<pid>.json`, so
  dry runs and demo mode stay at zero.
- **Tests:** cover sampling normalization and `build_command`, the profile
  resolver, sender byte/packet counters, the resources payload and the new UI
  contracts.
- **Docs:** refresh `docs/gui.png` and document the profiles and the resource
  strip in the README; `SECURITY.md` lists `stats-<pid>.json`.

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
