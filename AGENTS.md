# AGENTS.md

Project context and standing preferences for `wiz-ambilight`. Read this before
editing; it is the source of truth when a request and the existing files
disagree.

## Scope

DIY Philips Hue-style Ambilight: mpv decodes the video, a small Lua script
samples the frame, a Python process fades the colors and sends them to WiZ
bulbs over the local network with plain UDP. A local web panel does the same by
hand and can start or stop the sync.

- **The panel is the primary interface.** The README teaches the GUI first. The
  command line is a supported alternative for scripts and headless machines,
  documented in [`docs/cli.md`](docs/cli.md), and the README points there
  instead of repeating commands.
- Python **3.9+**, standard library only. One Lua script inside mpv, one web
  panel with no build step.
- Linux and macOS are the supported targets. Windows is roadmap work (see the
  README), so do not document it as working yet.
- `VERSION` in `mpv_ambilight.py` is the single version string: the panel
  footer, `--version` and the README banner chip all follow it.

## Language

Everything that ships stays in **English**: README, `SECURITY.md`, `AGENTS.md`,
CHANGELOG, code comments, panel copy, commit messages, image labels. A Spanish
mirror (`README.es.md`) is planned but does not exist yet; when it is added,
keep the same sections, order, anchors and images, translate the prose and the
headings, and leave interface names, option values and file paths untranslated.

## Hard constraints

- **Zero dependencies.** No `pip install`, no vendored library, no `pywizlight`
  or similar. The protocol is a few JSON datagrams; keep it that way. Pillow
  and numpy are allowed for `assets/banner.py` only, which never runs at
  playback time.
- **Local only.** The only traffic is UDP `38899` to bulb IPs, LAN broadcast
  for discovery, and loopback HTTP for the panel. No HTTP client, no DNS, no
  account, no telemetry, no update check.
- **Nothing downloads and runs.** `--install-script` copies a file from the
  checkout into mpv's scripts folder. Do not add a self-updater.
- **GUI first in the docs.** The README may show only the command that starts
  the panel (`./mpv_ambilight.py --gui`) and, as a name in a table, the flags
  that change how the panel starts (`--gui-port`, `--no-browser`, `--demo`).
  Every other flag, command, headless mode and automation recipe belongs in
  `docs/cli.md`; the README links it from **Getting Started** and **Command
  Line**, and may mention a flag inline as a name, never as a command block.
- **The Lua install is optional and attach-only.** A clone installs nothing
  into mpv. Launch mode passes `--script=<checkout>/lua/wiz_ambilight.lua` to
  the mpv it starts; attach mode needs a one-time copy in mpv's scripts folder
  because mpv is already running when the panel appears. The panel's **Install
  script** button and `--install-script` do that copy. Never imply
  **Getting Started** performs it, and never write "install the Lua script once"
  without saying that it is for attach mode.
- **Panel invariants.** Bind to `127.0.0.1`; check `Host` and `Origin`; require
  the per-run `X-Wiz-Token`; keep the CSP at `default-src 'none'` with only
  its own sources; never use a shell string or interpolate a path into a
  command; reject paths that start with `-`; only act on bulbs the panel knows;
  range-check every value; write config `0600` inside a `0700` directory.
- **Design tokens.** Amber `#FCBE11`, hairlines `#1F1F1F`, shadow `#33000000`,
  radius at most `2px`, Merriweather Bold 700 served from `web/fonts/`, and the
  numbered reading order `01`–`05`. `tests/test_design.py` is the contract: if
  a restyle breaks it, the restyle is wrong.
- **Panel ergonomics.** Direct control and Activity are `<details>` cards and
  start closed; Lights, Session and Look start open. Zones are explained by the
  preview on each bulb row, never only with the raw name; do not add a separate
  Zone map column. Each bulb row also has identify, inclusion and a two-step
  **Forget** action; forgetting removes the row and its room membership from
  `lights.json`, never the bulb itself, and a later scan may add it back.
  `--demo` uses only the three named fixtures and never merges them into the
  saved bulb list. The status dot is the hidden five-second crazy trigger; do
  not turn it back into a visible button or document the gesture.
- **Panel layout.** Session and Look share the left stack; Direct control gets
  its own right stack, so a short Session never stretches to match a tall card.
  Session is one compact row. Saved scenes are a small `<details>` submenu
  inside Direct control, not a card. **Look** is three equal hairline columns —
  Preset / Sample / Send — with flat key/value rows, never nested boxes.
  **Preset** leads with the Reaction group: the dropdown, with one
  `<optgroup>` per source (Video / Audio), then reaction strength. Audio modes
  add a full-width dynamics strip inside Look, below the three columns: a
  scrolling Signal timeline with a draggable amber threshold line, a Dynamics
  preset and four round knobs (Threshold, Attack, Release, Punch) over hidden
  range inputs. Video modes show the profile select instead. The strip is never
  a fourth column and never a second card. The Equalize target and the five
  band color swatches stay flat rows under the reaction group, shown only when
  they apply. The **Capture & fade preset** select
  follows the reaction group, then Brightness and the **Vibrance** slider;
  those three are always visible and flat.
- **Reactions and audio.** `react` is one of `color`, `equalize`, `cut`,
  `motion`, `duotone`, `beat`, `vu`; `color` stays the default. Every reaction
  is scaled by `react_amount`, so `0` is a no-op. Video reactive modes share
  `react_profile` (`soft` / `balanced` / `strong`); audio modes use the same
  profile as a starting bundle but are driven by explicit compressor-style
  `react_threshold`, `react_attack`, `react_release` and `react_punch`
  (`AUDIO_PRESETS` holds the four named points). Audio modes split the
  mix into five bands (`sub`, `low`, `low-mid`, `mid`, `high`) with one color
  each via `react_bands`; one bulb follows the overall volume, 2–5 bulbs spread
  the bands. Audio modes are `beat` and `vu` only: the Lua script adds a
  labelled `lavfi`/`acrossover`/`astats` analyser while one is selected,
  removes all its labels on exit and never touches a user's `af` chain. The
  graph keeps the mix's magnitude but adds an all-pass phase shift, so never
  describe it as bit-identical. No audio dependency, no separate process, no
  microphone. The `lux.json` sensor is design-only; do not add its flag until
  the hardware path is tested.
- **Performance chart.** Activity holds one frame with three unit lanes —
  CPU %, RAM MB, UDP KB/s — and a series each for mpv and the panel. CPU is a
  share of the whole processor, said so in the legend tooltip; never merge the
  lanes onto one axis. Video and capture resolution, read fps and the process
  count stay visible above the chart, not only in a tooltip. mpv is sampled by
  the pid the Lua script writes into its state file, so attach mode works
  without a parent link.
- **Rooms and saved colors.** A room is a named set of known bulbs and steers
  direct control only; clicking a room targets it and opens Direct control.
  `groups` and `colors` live in `lights.json`; changing either never restarts
  the sync. A saved color is `{hex, brightness}`; legacy bare hex loads at
  100 %. Power lives only in Direct control, never on a Light row.

## Terminology

- **bulb** — one physical WiZ device. **lights** — the set, or the panel
  section that lists them. Do not mix them in the same sentence.
- **sync** — the process that samples, fades and sends. **panel** — the local
  web UI. **daemon** only for the background sync started with `--attach`.
- **zone** — what one bulb shows; **layout** — the rule that assigns zones;
  **style** — a preset for capture/fade/send; **reaction** — how the bulbs
  react and to what (video or audio); **scene** — a saved look, or a WiZ scene
  id (say which); **room** — a named set of bulbs used as a direct control
  target. Never call a room a group in the UI.
- **Ambilight** is the effect, capitalised as a proper-style name; `wiz-hack`
  is the upstream project, `mpv-config` the design source.

## README structure

1. `# wiz-ambilight`, badges, hero banner, one-paragraph summary, the
   `mpv → Lua → Python → WiZ` line.
2. **Overview** → **Features** → **Requirements & Compatibility** →
   **Getting Started** (installation, first run, Launch vs Attach) →
   **Web Panel & Operating Modes** (with **Attach to your own mpv** under it)
   → **Configuration** (with **Capture, Fade & Send**, **Styles**,
   **Sampling**, **Layouts & Zones**, **Reactions**, **Audio Dynamics**,
   **Band Colors** and **Audio Processing** under it) → **Performance** →
   **Architecture** → **Privacy & Security** → **Environment** →
   **Command Line** → **Troubleshooting** → **Development** → **Roadmap** →
   **Credits & License** → **Related Projects**.

- The page follows the user's path: what it is, what it needs, how to start,
  how to use it from the panel, how to configure it, then how it works inside,
  what it costs, and what it guarantees. Environment has its own top-level
  table after the security section; it is not repeated under Configuration.
- **Getting Started** is one clone plus `--gui`. It must say that the clone
  does not copy the Lua script into mpv, that launch mode needs no install at
  all, and link **Attach to your own mpv** for the attach-only copy. Its
  **First run** subsection is a numbered panel walkthrough (scan, choose,
  launch), not a list of commands.
- **Web Panel & Operating Modes** explains the panel first and keeps **Launch
  a video**, **Attach to mpv**, direct control and one row pointing to
  **Command Line**. **Attach** explains why the Lua copy exists, uses the
  panel's **Install script** button and mentions reinstalling after an update.
  The systemd user service lives in `docs/cli.md`.
- **Command Line** is a short pointer to `docs/cli.md` with the `control.png`
  strip. No command blocks in the README except `--gui` (and `--gui-port`);
  everything else — discovery, launch and attach, `--set`, style, reaction and
  sampling flags, the systemd service and scripted looks — is in
  `docs/cli.md`. `docs/cli.md` must stay exhaustive: every flag, its default
  and its range, because the README no longer duplicates that catalogue.
- **Environment** is a single table for every environment variable; other
  sections refer to it instead of repeating paths.
- One strip per `##` heading, directly under it; Styles and Layouts keep their
  own strips under Configuration, and Attach keeps its strip under Operating
  Modes. The overview answers "what is this" before Features.
- Exactly **one** UI screenshot: `docs/gui.png`, under **Web Panel & Operating
  Modes**. Do not add more screenshots; a strip per heading replaces them.
- Tables over prose, bold lead-ins, no marketing tone, no repetition between
  the summary, Features, Performance, Architecture and Security.
- Keep capture fps, fade ms and send Hz distinct: they are explained once in
  **Capture, Fade & Send** and only referenced elsewhere.
- Aesthetic and layout detail lives in `docs/design.md`; repository structure,
  runtime files, config schemas and the audio path live in
  `docs/development.md`. The README links both and summarises only what a user
  needs.
- Emojis only as section markers, one per `##` heading, never in body text.
- The fork note lives in **Credits**, not in the intro: the summary says what
  the tool does, the credits say what came from where.
- **Related Projects** closes the page with one short pointer to `mpv-config`
  and its own `related.png` strip.

## Images

- `assets/banner.py` (Pillow + numpy) draws the 1600×470 hero
  (`banner.png`) and one 1200×158 strip per section, including
  `related.png`. The only other images are the reference crop described below
  and the architecture diagram. `design.png` is used by `docs/design.md`, not
  by the README.
- Type is Fira Sans Condensed from `assets/banner-fonts/` (SIL OFL). Those
  files belong to the generator; the panel serves `web/fonts/` and nothing
  else.
- Deterministic output: same input, same bytes. Never generate these with an
  image model — exact text matters more than style.
- `banner.png` carries the version chip; link it as
  `assets/banner.png?v=<version>` and bump the query when `VERSION` changes so
  GitHub's image proxy refetches. `--version` defaults to the current release.
- `assets/mpv-config.png` is a 1200×340 crop of `assets/keys.png` from
  `mfascioli/mpv-config`, kept for reference. The README now uses
  `assets/related.png`; if you switch back, re-crop the current `keys.png`
  instead of drawing a look-alike.
- `docs/gui.png` is a real screenshot of the panel. If the panel's layout
  changes, retake it — do not mock one up.
- `docs/architecture.mmd` is the Mermaid source; `docs/architecture.svg` is the
  committed render linked from **How it works** and `SECURITY.md`. Keep both in
  step, and keep the exposed-interface callout accurate.

## Privacy and security docs

`SECURITY.md` is the user-facing summary: trust model, what the code touches,
panel guarantees, provenance, what was reviewed and what was not, and the
limits. Keep it in step with the code.

- Never claim a scan, a vendor count or a clean result that did not happen.
  State the date and scope of any review.
- The README's **Privacy and security** section names only verified behaviour;
  the detail stays in `SECURITY.md`.
- The **How it was written** note records the workflow: generated with
  DeepSeek V4.1 Flash Free in OpenCode. Do not add other models unless they
  were actually used in this repository.
- If a change touches the network, process control, the file picker or a
  persisted file, update `SECURITY.md` in the same commit.

## Testing checklist

```bash
python -m unittest discover -s tests -v
python -m py_compile mpv_ambilight.py webui.py
lua5.4 -e 'assert(loadfile("lua/wiz_ambilight.lua"))'
```

Before calling a change done:

- the three commands above pass, on the oldest supported Python you have;
- `--demo` shows the panel and never sends UDP;
- `--set` rejects bad input with status `2` and an unreachable bulb with `1`;
- a config written by an older version still loads and is range-checked;
- `--install-script` is idempotent and needs `--force` to replace;
- the panel still refuses a foreign `Host`, a foreign `Origin` and a wrong
  token;
- the README shows only the panel start command and links `docs/cli.md` for the
  rest; installation never claims to install the Lua script, and `docs/cli.md`
  lists every flag with its default and range;
- `python assets/banner.py` reproduces the committed PNGs byte for byte.

## Git

- Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `ci:`,
  `release:`. Imperative subject, body explaining what and why, no emoji.
- Do not commit, tag or push unless the user asks. Report uncommitted changes.
- Bumping `VERSION`, tagging and publishing a release are separate decisions
  from a code change: ask first, then bump `VERSION`, regenerate the banners,
  move the `?v=` query, add the CHANGELOG entry and tag.
- Keep `AGENTS.md` current when a preference changes.

## File map

| Path | Purpose |
| --- | --- |
| `mpv_ambilight.py` | CLI, discovery, style/layout/reaction resolution, fade loop, UDP sender, `--discover`, `--set`, `--attach`, `--install-script` |
| `webui.py` | panel server, session control, bulb control, scenes, config, file picker |
| `web/index.html` `web/style.css` `web/app.js` | panel UI, no build step |
| `web/fonts/` | Merriweather Bold + SIL OFL licence, served to the panel |
| `lua/wiz_ambilight.lua` | runs inside mpv, samples the frame, manages the optional audio analyser and writes the state file, including mpv's pid |
| `tests/test_design.py` | pins the design tokens, the numbered order, the two stacks, the scenes submenu, the chart and the room controls |
| `tests/test_security.py` | pins loopback, process and architecture-doc invariants |
| `tests/test_mpv_ambilight.py` | CLI, parsing, colors, discovery helpers |
| `tests/test_webui.py` | config shape, panel handlers, ranges, token |
| `assets/banner.py` | generator for the README banners |
| `assets/banner-fonts/` | Fira Sans Condensed + OFL, generator only, never served |
| `assets/*.png` | hero, one strip per section, `mpv-config.png` reference crop |
| `docs/architecture.mmd` | architecture source, kept next to the render |
| `docs/architecture.svg` | architecture diagram linked from README and SECURITY |
| `docs/cli.md` | user-facing command line reference: discovery, launch/attach, `--set`, flags, service, scripts |
| `docs/design.md` | panel design language, layout and chart contract |
| `docs/development.md` | repository layout, runtime/config files, reactions and audio internals |
| `docs/gui.png` | the one panel screenshot in the README |
| `contrib/` | optional systemd user service and its env example |
| `upstream/` | original wiz-hack toolkit, reference only, never imported |
| `SECURITY.md` | trust model, guarantees, review status, limits |
| `CHANGELOG.md` | one entry per release, grouped by feature |
| `README.md` | user-facing documentation |
