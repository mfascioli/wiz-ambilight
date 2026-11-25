# Development

Notes for working on `wiz-ambilight` itself: repository layout, the files the
runtime creates, the config schemas, the reaction and audio pipeline, and the
test setup. The user-facing command line lives in [`cli.md`](cli.md); the panel
design lives in [`design.md`](design.md).

## Repository layout

```text
.
├── mpv_ambilight.py        # CLI, discovery, fade loop, UDP sender
├── webui.py                # local web panel server and config
├── web/                    # panel HTML/CSS/JS (no build step)
│   └── fonts/              # bundled Merriweather Bold + SIL OFL licence
├── lua/wiz_ambilight.lua   # runs inside mpv, writes zone colors as JSON
├── tests/                  # dependency-free unit tests
│   ├── test_design.py      # the mpv-config design contract
│   ├── test_lux.py         # lux bridge, parser and lux.json writes
│   └── test_security.py    # loopback, process and docs invariants
├── assets/                 # README banners + their generator
│   └── banner-fonts/       # Fira Sans Condensed for banner.py only
├── docs/
│   ├── architecture.mmd    # architecture source (Mermaid)
│   ├── architecture.svg    # rendered architecture diagram
│   ├── cli.md              # user-facing command line reference
│   ├── design.md           # panel design language and layout
│   └── gui.png             # the one panel screenshot in the README
├── contrib/                # systemd units, lux bridge, ESP32 sensor sketch
└── upstream/               # original wiz-hack toolkit, kept for reference
```

There is no build step on either side: Python is standard library only, and the
panel is served as written. `mpv_ambilight.py` imports `webui.py` only when
`--gui` runs, so the panel and the CLI share discovery, styles and validation
without loading the server for normal playback.

## Files the runtime creates

| Path | Written by | Purpose |
| --- | --- | --- |
| `$XDG_RUNTIME_DIR/wiz-ambilight/state-<pid>.json` (launch) or `state.json` (attach) | Lua | zone colors, capture rate, mpv pid, and audio levels in audio modes |
| `$XDG_RUNTIME_DIR/wiz-ambilight/stats-<pid>.json` | sync | UDP throughput, rewritten once a second |
| `$XDG_RUNTIME_DIR/wiz-ambilight/control.json` | sync | makes the Lua script wake up in attach mode |
| `$XDG_RUNTIME_DIR/wiz-ambilight/lux.json` | lux bridge (optional) | the latest measured illuminance, `0600` |
| `$XDG_RUNTIME_DIR/wiz-ambilight/gui-daemon.json` | panel | the sync PID it started, for adoption |
| `~/.config/wiz-ambilight/lights.json` | panel | bulbs, names, zones, rooms, saved colors |
| `~/.config/wiz-ambilight/scenes.json` | panel | saved looks |
| mpv's `scripts/wiz_ambilight.lua` | panel **Install script** / `--install-script` | a copy of the Lua script for attach mode; launch mode passes the checkout copy directly |

The runtime directory is `0700`; the two config files are written `0600`. When
`XDG_RUNTIME_DIR` is unset the runtime files go to `/tmp/wiz-ambilight`.

## Config format

`lights.json` is validated on load and on save, so it is safe to edit by hand
or generate from a script:

```json
{
  "layout": "auto",
  "style": "hue",
  "react": "color",
  "react_amount": 0.8,
  "react_target": 0.45,
  "react_profile": "balanced",
  "react_eq_bands": 8,
  "react_eq": [
    {"freq": 32, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 77.75, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 188.92, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 459.04, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 1115.37, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 2710.1, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 6584.96, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false},
    {"freq": 16000, "type": "bell", "slope": 24, "gain": 0, "q": 1.4, "lamp": -1, "solo": false}
  ],
  "react_auto": "off",
  "react_active_bands": false,
  "react_bands": ["#ff5a3c", "#fcbe11", "#7ad66b", "#38bdf8",
                  "#a78bfa", "#f472b6", "#2dd4bf", "#fb923c"],
  "brightness": 100,
  "white_leds": false,
  "mode": "attach",
  "media": "",
  "dry_run": false,
  "sampling": "auto",
  "sampling_fps": 15,
  "sampling_grid": 80,
  "sampling_block": 1,
  "sampling_capture": "auto",
  "groups": {
    "Living room": ["192.168.1.5", "192.168.1.7"]
  },
  "colors": [
    {"hex": "#fcbe11", "brightness": 80},
    {"hex": "#78c8ff", "brightness": 55}
  ],
  "lights": {
    "192.168.1.5": {
      "name": "Left wall",
      "enabled": true,
      "zone": "t1",
      "model": "ESP24_SHRGBC_01",
      "mac": "d8a01154f818",
      "firmware": "1.38.0"
    }
  }
}
```

Rooms are named lists of IPs the panel already knows; saved colors pair a
`#rrggbb` string with the brightness it was saved at. A legacy bare string
loads at 100 %. Changing either never restarts a running sync. Point the panel
at another file with `WIZ_AMBILIGHT_GUI_CONFIG` and
`WIZ_AMBILIGHT_SCENES_CONFIG`.

`white_leds` is opt-in and applies to the sync and to Direct control: the grey
part of each color (`min(r, g, b)`) is sent on the bulb's `c` and `w` channels
and subtracted from RGB, following `cB-Sigma/wiz` (Apache-2.0). Saturated colors
are unchanged. The panel keeps storing the original RGB in `lights.json` and in
its live state; `pilot_rgb()` folds `c`/`w` back into the swatch and saved scene,
so the file never depends on the mapping. `--white-leds` is the CLI equivalent.

`scenes.json` maps a scene name to per-bulb state. Only known bulbs are applied
and every value is range-checked:

```json
{
  "Movie night": {
    "192.168.1.5": {"state": true, "r": 255, "g": 80, "b": 20, "dimming": 40},
    "192.168.1.7": {"state": true, "sceneId": 4, "speed": 80}
  }
}
```

## Reactions and audio

`react` has seven values. `color` is the classic Ambilight; the rest add one
layer and are scaled by `react_amount` (`0` is a no-op). Spans below are at
`react_amount = 1`; the default `0.8` scales them, timings do not change:

| value | group | source | notes |
| --- | --- | --- | --- |
| `color` | video | `zones.all` / per-zone | default |
| `equalize` | video | `zones.all` luma | slow EMA (`EQUALIZE_TAU = 4 s`), target `react_target`, `±35 %`, 35 % floor |
| `cut` | video | frame-to-frame distance | one hard edit, 120 ms flash, 1.5 s cooldown, 6 per minute, 22 % headroom |
| `motion` | video | per-zone distance | 0.35 s release, brightness and saturation |
| `duotone` | video | per-zone colour | odd bulbs get `hue_shift(rgb, 180° × amount)` |
| `beat` | audio | per-band RMS + peak transient | each band must clear the `react_threshold` gate and jump 3 dB over a fast running average; 0.12 s minimum gap, 1 ms attack / 55 ms release, 75 % flash span; a hit reaches full scale |
| `vu` | audio | per-band RMS + sample peak | −18…−6 dBFS window per band, 1 ms attack / 55 ms release, punch 3.0; one bulb uses the overall level |

`react_profile` (`soft`, `balanced`, `strong`) selects a row from
`REACTION_PROFILES`. Video modes use it for `equalize`, `cut` and `motion`;
audio modes use it as a starting bundle for the gate, ceiling, envelope and
punch. `react_amount` still scales the spans, so the two compose. `color` and
`duotone` have no profile. An unknown profile falls back to `balanced`.

Audio modes expose the same dynamics as explicit controls. `AUDIO_PRESETS`
holds four named starting points, served to the panel as `dynamics`:

| preset | threshold | attack | release | punch |
| --- | --- | --- | --- | --- |
| `mellow` | −28 dBFS | 12 ms | 200 ms | 1.4 |
| `glue` | −24 dBFS | 6 ms | 120 ms | 2.0 |
| `punch` | −18 dBFS | 1 ms | 55 ms | 3.0 |
| `strobe` | −14 dBFS | 0 ms | 30 ms | 4.0 |

`react_threshold` is the gate in dBFS (−36…0), `react_attack` and
`react_release` are milliseconds (0…200 and 20…1000) and `react_punch` is
1…4. The panel writes all four; `--react-threshold`, `--react-attack`,
`--react-release` and `--react-punch` are the CLI equivalents. When they are
absent, the values come from the profile, which keeps `--react-profile`
meaningful for old configs. The ceiling comes from the profile's `high` value
(−6 dBFS by default), and `pulse_level` keeps at least `AUDIO_WINDOW_DB`
(12 dB) of range above the gate so a high threshold stays usable.

`react_eq_bands` is the analysis band count, **2–16** (default 8).
`react_eq` is a list of `{freq, type, slope, gain, q, lamp, solo}` objects kept
in frequency order. `freq` is the band centre in Hz (20–20000), `type` is one of
`bell`, `bandpass`, `lowpass`, `highpass`, `notch` or `flat`, `slope` snaps to
12, 24 or 48 dB/oct, `gain` is the detection boost in dB (−18…+18), `q` is the
width (0.4–8), `lamp` is a 0-based index into the enabled bulbs in panel order
or `-1` for auto, and `solo` makes every bulb follow the soloed bands. Unknown
types become `bell` and a missing `slope` becomes 24, so old configs keep
working. `normalize_eq_bands` clamps every value, fills a missing slot with the
log-spaced default for that position and sorts the list, so a malformed band
never shifts the rest of the curve. The panel always writes an explicit list; a
`Reaction` built directly without one keeps the classic 5-band layout for
compatibility.

The default centres are `(16000/32) ** (1/(N-1))` apart, starting at 32 Hz;
for N=8 that is 32, 78, 189, 459, 1.1k, 2.7k, 6.6k and 16k Hz. `eq_splits`
turns adjacent centres and Q values into the legacy crossover boundaries: each
band's Q-derived edges are `f * 2**(±0.5/Q)`, the split is the geometric mean of
the neighbouring edges and is nudged to stay strictly increasing. The shaped
analyser does not need them; the list still travels as `bands` so old Lua copies
and the panel labels keep working. `eq_thrust_db` returns the API-style low-end
de-emphasis (−3 dB below 120 Hz, −1.5 dB below 250 Hz) used only by the `api`
and `hybrid` auto modes.

`react_bands` is one `#rrggbb` string per EQ band, low to high, and
`normalize_band_colors` cycles `BAND_COLOR_PALETTE` (16 colours; the first five
are the legacy `DEFAULT_BAND_COLORS`) so a 16-band EQ still has distinct
swatches. Missing or malformed entries fall back to the palette colour at their
own position. The CLI form is `--react-bands '#aabbcc,#…'` and its count must
match `--react-eq-bands`; `--react-eq` takes the JSON list.

`band_for(index, count, bands)` spreads the bands over the bulbs when no lamp
is assigned: one bulb follows the overall level, fewer bulbs than bands map
evenly from low to high, and more bulbs than bands repeat the cycle. An
explicit `lamp >= 0` on any band switches to assignment mode: each bulb
averages every active band assigned to it, takes the colour of the strongest
of those bands, and bulbs with no assigned band follow the overall mix. A
`solo` on any band overrides both modes: every bulb follows the soloed bands
(and the overall view uses the loudest soloed band) until solo is cleared.

`react_auto` is `off`, `ssl`, `api` or `hybrid`. `Reaction._auto_release`
tracks how long a bulb has been driven (`sustain`): `ssl` and `hybrid` keep a
fast time constant for hits and stretch toward `release * 8` (up to 2 s) while
the program stays compressed, while `api` uses a fixed 1.35× release. `api` and
`hybrid` also run the level through `** 0.85` (`_auto_level`, a soft knee) and
apply `eq_thrust_db` to the low bands. `react_active_bands` enables the
per-band detector: each band keeps a slow floor (fast down, slow up), must sit
4 dB above it and stay there for 180 ms (`ACTIVE_MARGIN_DB`, `ACTIVE_HOLD`),
and an inactive band contributes zero even if it is above the gate.

`react_color_mode` picks where an audio bulb's colour comes from:
`bands` (the list above), `spectrum` (a fixed hue per band), `rainbow` (a hue
that rotates with time and is offset per band), `range` (a blend from
`react_color_a` to `react_color_b` across the bands), `level` (the same blend
driven by the bulb's live level) or `single` (`react_color_a` everywhere).
`Reaction.audio_color(band, level, now)` is the single decision point, so every
mode shares the band assignment and brightness path. Colour A and B default to
`#fcbe11` and `#38bdf8`; malformed hex falls back to the default. The CLI flags
are `--react-color-mode`, `--react-color-a` and `--react-color-b`.

The pure helpers are in `mpv_ambilight.py`: `scene_luma`, `rgb_distance`,
`hue_shift`, `hsv_rgb`, `blend_rgb`, `equalize_gain`, `pulse_level`,
`vu_level`, `hot_db`, `beat_pulse`, `cut_pulse`, `finite_float`, `band_for`,
`normalize_band_colors`, `parse_band_colors`, `normalize_audio_color` and the
`Reaction` state class. `Reaction.update()` runs when Lua writes a state frame;
`Reaction.dimming()` runs on every send tick so a 120 ms flash is not lost
between frames. Colour changes happen before saturation/gamma; brightness is
per bulb.

### Audio path

Audio modes use mpv's own `lavfi` bridge, so there is no new dependency and no
external process. On activation the Lua script appends:

```text
@wizstats:lavfi=[astats=metadata=1:reset=1],
@wizbands:lavfi=[aformat=channel_layouts=stereo,asplit=2[main][mon];
  [mon]asplit=N[m0]…[mN-1];
  [m0]<shape 0>[f0]; … [mN-1]<shape N-1>[fN-1];
  [f0]…[fN-1]amerge=inputs=N[filtered];
  [filtered][main]amerge=inputs=2[all];
  [all]astats=metadata=1:reset=1[stats];
  [stats]pan=stereo|c0=c2N|c1=c2N+1],
@wiztail:lavfi=[anull]
```

The band plan travels as `eq` in the Lua startup config. `sanitize_eq` keeps
`freq`, `type`, `q` and `slope` (the fields that change the graph) and rejects
non-numeric or out-of-range bands; `band_chain` maps a shape to a filter:
`bandpass=f=…:width_type=q:w=…` for a bell, `bandreject` for a notch, repeated
`lowpass`/`highpass` stages for the cuts and the band pass (`poles=2` per
stage, one stage per 12 dB/oct) and `anull` for flat. Changing the plan in a
running script removes and re-adds the chain (the plans are compared first).

`astats` injects `af-metadata/wizstats` with the overall levels. The band graph
splits a copy of the stereo mix, filters each copy with its band shape, merges
the N filtered pairs into 2N channels and merges the untouched `main` pair back
as channels 2N+1 and 2N+2. A second `astats` exposes `af-metadata/wizbands`,
one RMS and one peak pair per band, and `pan` selects only the main pair, so the
audio mpv plays is unchanged. That second `astats` runs with
`measure_perchannel=Peak_level+RMS_level` and `measure_overall=none`: only those
two fields feed the meter, and measuring the full statistics set on up to 34
channels makes a 16-band EQ burn most of a core. `ASTATS_BANDS_LEGACY` retries
the plain filter on builds without `measure_perchannel`. `anull` keeps the
chain valid while the labels are removed. The script installs the chain
`af set`-style only when `react` is `beat` or `vu`, putting the analyser
**ahead of any existing filters** so a compressor that follows sees the mix
after the EQ. It re-adds the chain after `file-loaded`, and an `af` observer
puts it back at the head when another script replaces the chain on a profile
switch. On a switch back to a video mode, on stop and on shutdown it removes
`@wizbands`, `@wizstats` and `@wiztail` in any order, leaving a user's own `af`
filters in place after it.

Configs without an `eq` plan fall back to the older crossover graph:
`acrossover=split=<s1> … <sN-1>[b0]…[bN-1]`, `amerge=inputs=N` into 2N
channels, `astats` and `pan` summing the pairs back into stereo. The split
points come from `eq_splits()` and the `bands` list; `sanitize_bands` rejects
non-numeric and out-of-range splits, and the classic `60 250 800 2500`
five-band plan is the last fallback. The crossover keeps the magnitude flat
(measured within 0.6 dB with white noise) but adds an all-pass phase shift, so
its output is not sample-identical.

Some mpv builds only expose the metadata of the last `astats` in a chain, so
`wizstats` can be empty while `wizbands` is live. The shaped graph reads the
overall level from its main pair (channels 2N+1 and 2N+2). The crossover
fallback has no such pair, so the Lua script rebuilds the overall RMS and peak
by summing every band's power. That also means audio still works on builds where
only the band graph is readable; the Python parser accepts either shape.

While an audio mode is active the state snapshot gains:

```json
"audio": {"rms": -24.1, "peak": -18.0, "crest": 6.1, "zcr": 0.12,
          "l": -24.1, "r": -25.0,
          "bands": [-41.2, -33.8, -27.0, -24.1, -21.0, -26.5, -31.0, -38.0],
          "band_peaks": [-36.0, -28.1, -21.4, -18.0, -15.5, -20.0, -24.2, -31.0]}
```

Levels are dBFS; `crest` is peak minus RMS in dB and `zcr` is the
zero-crossing rate. The louder channel of each stereo band pair is used, so a
one-sided mix still registers. Digital silence (`-inf`) and NaN become
`null`; Python treats `null` as silence. The signal view uses
`hot_db(rms, peak)`: the hotter of RMS and peak minus 8 dB, so a kick is
visible on the first update without a mastered track sitting at full scale.
`pulse_level(db, threshold, ceiling, punch)` then gates everything below the
threshold to zero, maps the window up to the ceiling onto 0…1 and raises the
result to `1 / punch`. The window never shrinks below `AUDIO_WINDOW_DB`
(12 dB): `high = max(threshold + 12, ceiling)`, so a gate close to the ceiling
does not collapse into a switch. A punch above 1 lifts the middle of the
window, so a solid hit lands near full instead of halfway; that is what turns
a level meter into a pulse. The beat detector runs on the same combined level,
ignores anything below the threshold, and compares it with a fast running
baseline.

`Reaction.dimming()` is called only when the send loop builds a datagram, so
`run_sync()` passes the time since the previous send, not the 3–6 ms polling
step. The dynamics attack/release values are therefore wall-clock seconds;
using the polling delta would stretch a 55 ms release into almost a second.

The panel's **Signal** view is a local readout over that meter. `GET
/api/meter` reads the newest fresh Lua state file, applies `hot_db` to its
`audio` object and returns `active`, `db`, `ceiling`, `window`, `rms`, `peak`
and up to 16 band levels. `ceiling` is the selected profile's `high` value and
`window` is `AUDIO_WINDOW_DB`, so the client can reproduce `pulse_level`
without duplicating the profile table. The browser polls it every 40 ms only
while an audio reaction is selected and keeps a five-second history on the
canvas: an amber input trace, a red light-drive curtain attached to the top
border and descending by the drive amount, and the live **LIGHT n %** and dBFS
values in the header. The threshold knob's outer ring reuses the same poll on a
−60…0 dB scale: a dot walks toward 0 dB as the input rises, turns red above the
gate and crosses an amber tick at the threshold. The amber threshold line is
drawn from `react_threshold` and dragging it writes that config value, so the
meter follows the song without restarting the sync or adding a second
analyser.

The Lua timer beats at 30 Hz (`AUDIO_FPS`) even when the sampling profile caps
video analysis lower. `analyze()` is still gated by `fps_now`, so the extra
ticks only reuse the cached zones and re-read `af-metadata`. `run_sync()`
likewise raises the send rate to 30 Hz for audio modes. On an audio-only file
the Lua script keeps emitting a heartbeat with `audio` and no `zones`; the sync
holds a warm base color and drives only the brightness.

## Auto Lux (light sensor)

`--auto-lux` and the **Auto Lux** checkbox add measured-light brightness on top
of any reaction. The hook stays file-based, so the sync adds no port, daemon or
dependency: a bridge writes

```json
{"lux": 42.5}
```

to `$XDG_RUNTIME_DIR/wiz-ambilight/lux.json` and the sync reads it only while
Auto Lux is enabled. `contrib/lux-bridge.py` (stdlib only) accepts `POST /lux`
from an ESP32 and writes the file atomically at `0600`;
`contrib/esp32-lux/` holds the sketch (BH1750, VEML7700, MAX44009, OPT3001 or
TSL2591, selected with `SENSOR_MODEL`) and `contrib/lux-sensor.md` the wiring
and service setup.

- `read_lux()` rejects a missing file, a malformed body, a boolean, a
  non-finite or negative value, and anything above `LUX_MAX` (65535, the
  ceiling the bridge and parser accept; the sketch clamps brighter sensors). A
  reading older than `LUX_STALE_SECONDS` (5 s) counts as missing, so a stopped
  bridge stops correcting without a restart.
- `Reaction.update()` computes `ambient_gain` once per frame and `dimming()`
  multiplies every mode by it, so color, cut, motion, duotone, beat and vu keep
  their own colors and pulses. It always uses the **Equalize** profile's
  `span` / `tau` / `floor`, even when another reaction is selected, so
  switching reactions never changes the ambient controller.
- Equalize is the one exception: while Auto Lux has a fresh reading its luma
  gain is held at `1.0` and Auto Lux owns brightness. Without a reading,
  Equalize falls back to scene luma and `--react-target`.
- `lux_gain()` mirrors `equalize_gain()`: `target / lux`, capped by `span` and
  `floor`, then scaled by `react_amount`. The reading is smoothed with the
  profile's `tau` before the ratio is taken, because the bulbs add light to the
  room the sensor sees.
- `--lux-target` is in lux (default 50, 1–5000) and is not a reused luma
  value. The panel shows **Auto Lux**, **Target lux**, the current reading and
  its age, and never writes the file itself.
- The bridge binds `0.0.0.0:8766`; `WIZ_LUX_TOKEN` / `--token` adds an
  `X-Lux-Token` check. It can only change brightness, never drive the bulbs or
  run code.

The parser, freshness window, gain, the per-mode layer and the Equalize
fallback are covered by unit tests. The physical sensor path is not tested in
CI.

## Power metering

Power is a readout, never a control. Newer firmware puts `pc` (milliwatts) in
the `getPilot` answer the panel already polls; older metering devices answer a
separate `getPower` with `{"power": milliwatts}`; most bulbs support neither
and return error `-32601` (method not found), following `cB-Sigma/wiz`
(Apache-2.0). `_milliwatts_to_watts()` converts and rejects booleans, negatives
and non-finite values.

`maybe_power()` runs on `/api/state`, at most every `POWER_REFRESH` (30 s), and
only for bulbs whose `getPilot` had no `pc`. It asks in a daemon thread so a
slow or absent device never stalls the request, keeps a reading for
`POWER_STALE` (90 s), and stops asking a device after `POWER_ATTEMPTS` (3)
silent answers until a manual scan clears the list. Watts reach the snapshot
as `power` on each light row and the panel shows them only in **Direct control**
— the target's total, with `(n/m)` when only some bulbs meter — never on a
Light row.

## Tests and CI

```bash
python -m unittest discover -s tests -v
python -m py_compile mpv_ambilight.py webui.py
lua5.4 -e 'assert(loadfile("lua/wiz_ambilight.lua"))'
```

The workflow runs the unit tests on Python 3.9, 3.11 and 3.13 and checks that
the Lua script compiles. Tests never touch a real bulb: discovery, the fade
loop and the panel are exercised in-process, and `--demo` keeps the panel and
the sender off the network.

## Documentation assets

```bash
python3 assets/banner.py            # rewrite the hero and the section strips
python3 assets/banner.py --version v1.12.0
```

`assets/banner.py` needs Pillow and numpy; neither is imported at playback
time. It is deterministic, and the committed PNGs should reproduce byte for
byte. The hero carries the version chip, so bump the `?v=` query in the README
when `VERSION` changes. The architecture source and render live next to each
other in `docs/`; edit the `.mmd`, re-render the `.svg` and update the
exposed-interface callout together.

## Design contract

The panel's tokens, layout and chart are documented in
[`design.md`](design.md) and pinned by `tests/test_design.py`. `SECURITY.md`
holds the trust model and the panel guarantees; if a change touches the
network, process control, the file picker or a persisted file, update it in the
same commit.
