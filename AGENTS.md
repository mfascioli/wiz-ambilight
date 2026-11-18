# AGENTS.md

Project context and standing preferences for `wiz-ambilight`. Read this before
editing; it is the source of truth when a request and the existing files
disagree.

## Scope

DIY Philips Hue-style Ambilight: mpv decodes the video, a small Lua script
samples the frame, a Python process fades the colors and sends them to WiZ
bulbs over the local network with plain UDP. A local web panel does the same by
hand and can start or stop the sync.

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
- **Panel invariants.** Bind to `127.0.0.1`; check `Host` and `Origin`; require
  the per-run `X-Wiz-Token`; keep the CSP at `default-src 'none'` with only
  its own sources; never use a shell string or interpolate a path into a
  command; reject paths that start with `-`; only act on bulbs the panel knows;
  range-check every value; write config `0600` inside a `0700` directory.
- **Design tokens.** Amber `#FCBE11`, hairlines `#1F1F1F`, shadow `#33000000`,
  radius at most `2px`, Merriweather Bold 700 served from `web/fonts/`, and the
  numbered reading order `01`–`06`. `tests/test_design.py` is the contract: if
  a restyle breaks it, the restyle is wrong.
- **Panel ergonomics.** Direct control and Activity are `<details>` cards and
  start closed; Lights, Session and Look start open. Zones are explained with
  the miniature frame preview, never only with the raw name. The status dot is
  the hidden five-second crazy trigger; do not turn it back into a visible
  button or document the gesture.

## Terminology

- **bulb** — one physical WiZ device. **lights** — the set, or the panel
  section that lists them. Do not mix them in the same sentence.
- **sync** — the process that samples, fades and sends. **panel** — the local
  web UI. **daemon** only for the background sync started with `--attach`.
- **zone** — what one bulb shows; **layout** — the rule that assigns zones;
  **style** — a preset for capture/fade/send; **scene** — a saved look, or a
  WiZ scene id (say which).
- **Ambilight** is the effect, capitalised as a proper-style name; `wiz-hack`
  is the upstream project, `mpv-config` the design source.

## README structure

1. `# wiz-ambilight`, badges, hero banner, one-paragraph summary, the
   `mpv → Lua → Python → WiZ` line.
2. **What you get** → **Requirements** → **Install** → **Quick start** →
   **Web panel** (with `Direct control from the CLI` under it) → **Design** →
   **Styles** → **Layouts and zones** → **Attach to a running mpv** (with the
   optional user service under it) → **How it works** → **Performance** →
   **Troubleshooting** → **Development** (with **Roadmap** under it) →
   **Privacy and security** → **Credits and license** → **Also check out**.

- One strip per `##` heading, directly under it. The overview comes first so
  the page answers "what do I get" before the detail.
- Exactly **one** UI screenshot: `docs/gui.png`, under **Web panel**. Do not
  add more screenshots; a strip per heading replaces them.
- Tables over prose, bold lead-ins, no marketing tone, no repetition between
  the summary and the sections that follow it.
- Emojis only as section markers, one per `##` heading, never in body text.
- The fork note lives in **Credits**, not in the intro: the summary says what
  the tool does, the credits say what came from where.
- **Also check out** closes the page with one short pointer to `mpv-config`
  and its cropped keyboard map.

## Images

- `assets/banner.py` (Pillow + numpy) draws the 1600×470 hero
  (`banner.png`) and one 1200×158 strip per section. The only other images are
  the crop described below and the architecture diagram.
- Type is Fira Sans Condensed from `assets/banner-fonts/` (SIL OFL). Those
  files belong to the generator; the panel serves `web/fonts/` and nothing
  else.
- Deterministic output: same input, same bytes. Never generate these with an
  image model — exact text matters more than style.
- `banner.png` carries the version chip; link it as
  `assets/banner.png?v=<version>` and bump the query when `VERSION` changes so
  GitHub's image proxy refetches. `--version` defaults to the current release.
- `assets/mpv-config.png` is a 1200×340 crop of `assets/keys.png` from
  `mfascioli/mpv-config`, used only by **Also check out**. Re-crop that file;
  do not draw a look-alike.
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
| `mpv_ambilight.py` | CLI, discovery, style/layout resolution, fade loop, UDP sender, `--discover`, `--set`, `--attach`, `--install-script` |
| `webui.py` | panel server, session control, bulb control, scenes, config, file picker |
| `web/index.html` `web/style.css` `web/app.js` | panel UI, no build step |
| `web/fonts/` | Merriweather Bold + SIL OFL licence, served to the panel |
| `lua/wiz_ambilight.lua` | runs inside mpv, samples the frame and writes the state file |
| `tests/test_design.py` | pins the design tokens and the numbered order |
| `tests/test_security.py` | pins loopback, process and architecture-doc invariants |
| `tests/test_mpv_ambilight.py` | CLI, parsing, colors, discovery helpers |
| `tests/test_webui.py` | config shape, panel handlers, ranges, token |
| `assets/banner.py` | generator for the README banners |
| `assets/banner-fonts/` | Fira Sans Condensed + OFL, generator only, never served |
| `assets/*.png` | hero, one strip per section, `mpv-config.png` crop |
| `docs/architecture.mmd` | architecture source, kept next to the render |
| `docs/architecture.svg` | architecture diagram linked from README and SECURITY |
| `docs/gui.png` | the one panel screenshot in the README |
| `contrib/` | optional systemd user service and its env example |
| `upstream/` | original wiz-hack toolkit, reference only, never imported |
| `SECURITY.md` | trust model, guarantees, review status, limits |
| `CHANGELOG.md` | one entry per release, grouped by feature |
| `README.md` | user-facing documentation |
