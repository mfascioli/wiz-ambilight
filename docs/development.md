# Development

Notes for working on `wiz-ambilight` itself: repository layout, the files the
runtime creates, the test setup and the scripted recipes that do not belong in
the user-facing README.

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
│   └── test_security.py    # loopback, process and docs invariants
├── assets/                 # README banners + their generator
│   └── banner-fonts/       # Fira Sans Condensed for banner.py only
├── docs/
│   ├── architecture.mmd    # architecture source (Mermaid)
│   ├── architecture.svg    # rendered architecture diagram
│   ├── design.md           # panel design language and layout
│   └── gui.png             # the one panel screenshot in the README
├── contrib/                # optional systemd user service
└── upstream/               # original wiz-hack toolkit, kept for reference
```

There is no build step on either side: Python is standard library only, and the
panel is served as written. `mpv_ambilight.py` imports `webui.py` only when
`--gui` runs, so the panel and the CLI share discovery, styles and validation
without loading the server for normal playback.

## Files the runtime creates

| Path | Written by | Purpose |
| --- | --- | --- |
| `$XDG_RUNTIME_DIR/wiz-ambilight/state-<pid>.json` | Lua | zone colors, capture rate, mpv pid, and audio levels in audio modes |
| `$XDG_RUNTIME_DIR/wiz-ambilight/stats-<pid>.json` | sync | UDP throughput, rewritten once a second |
| `$XDG_RUNTIME_DIR/wiz-ambilight/control.json` | sync | makes the Lua script wake up in attach mode |
| `$XDG_RUNTIME_DIR/wiz-ambilight/gui-daemon.json` | panel | the sync PID it started, for adoption |
| `~/.config/wiz-ambilight/lights.json` | panel | bulbs, names, zones, rooms, saved colors |
| `~/.config/wiz-ambilight/scenes.json` | panel | saved looks |
| mpv's `scripts/wiz_ambilight.lua` | `--install-script` | a copy of the Lua script |

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
  "react_bands": ["#ff5a3c", "#fcbe11", "#7ad66b", "#38bdf8", "#a78bfa"],
  "brightness": 100,
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
| `vu` | audio | per-band RMS + sample peak | −22…−10 dBFS window per band, 1 ms attack / 55 ms release, punch 3.0; one bulb uses the overall level |

`react_profile` (`soft`, `balanced`, `strong`) selects a row from
`REACTION_PROFILES`. Video modes use it for `equalize`, `cut` and `motion`;
audio modes use it as a starting bundle for the gate, ceiling, envelope and
punch. `react_amount` still scales the spans, so the two compose. `color` and
`duotone` have no profile. An unknown profile falls back to `balanced`.

Audio modes expose the same dynamics as explicit controls. `AUDIO_PRESETS`
holds four named starting points, served to the panel as `dynamics`:

| preset | threshold | attack | release | punch |
| --- | --- | --- | --- | --- |
| `mellow` | −30 dBFS | 12 ms | 200 ms | 1.4 |
| `glue` | −26 dBFS | 6 ms | 120 ms | 2.0 |
| `punch` | −22 dBFS | 1 ms | 55 ms | 3.0 |
| `strobe` | −18 dBFS | 0 ms | 30 ms | 4.0 |

`react_threshold` is the gate in dBFS (−60…0), `react_attack` and
`react_release` are milliseconds (0…200 and 20…1000) and `react_punch` is
1…4. The panel writes all four; `--react-threshold`, `--react-attack`,
`--react-release` and `--react-punch` are the CLI equivalents. When they are
absent, the values come from the profile, which keeps `--react-profile`
meaningful for old configs. The ceiling comes from the profile's `high` value
(−10 dBFS by default).

`react_bands` is five `#rrggbb` strings in `sub`, `low`, `low-mid`, `mid`,
`high` order. The crossover splits at 60, 250, 800 and 2500 Hz. Missing or
malformed entries fall back to `DEFAULT_BAND_COLORS` at their own position, so
the rest of the list never shifts. The CLI form is
`--react-bands '#aabbcc,#…'`; the panel stores the same list in `lights.json`.
`band_for(index, count)` spreads the bands over the bulbs: one bulb follows the
overall level, 2–5 map to `[0,4]`, `[0,2,4]`, `[0,1,3,4]` and `[0,1,2,3,4]`,
and more than five repeat. With one bulb the colour is the loudest band's.

The pure helpers are in `mpv_ambilight.py`: `scene_luma`, `rgb_distance`,
`hue_shift`, `equalize_gain`, `pulse_level`, `vu_level`, `hot_db`,
`beat_pulse`, `cut_pulse`, `finite_float`, `band_for`,
`normalize_band_colors`, `parse_band_colors` and the `Reaction` state class. `Reaction.update()` runs when Lua writes a state frame;
`Reaction.dimming()` runs on every send tick so a 120 ms flash is not lost
between frames. Colour changes happen before saturation/gamma; brightness is
per bulb.

### Audio path

Audio modes use mpv's own `lavfi` bridge, so there is no new dependency and no
external process. On activation the Lua script appends:

```text
@wizstats:lavfi=[astats=metadata=1:reset=1],
@wizbands:lavfi=[aformat=channel_layouts=stereo,
  acrossover=split=60 250 800 2500[b0][b1][b2][b3][b4];
  [b0][b1][b2][b3][b4]amerge=inputs=5,astats=metadata=1:reset=1,
  pan=stereo|c0=c0+c2+c4+c6+c8|c1=c1+c3+c5+c7+c9],
@wiztail:lavfi=[anull]
```

`astats` injects `af-metadata/wizstats` with the overall levels. `acrossover`
splits the stereo downmix into five bands, `amerge` stacks them into ten
channels and a second `astats` exposes `af-metadata/wizbands`, one RMS and one
peak pair per band. `pan` recombines the ten channels into the stereo output.
The crossover keeps the magnitude flat (measured within 0.6 dB with white
noise) but adds an all-pass phase shift, so the output is not sample-identical;
it is not a pass-through. `anull` keeps the chain valid while the labels are
removed. The script adds the chain only when `react` is `beat` or `vu`,
re-adds it after `file-loaded`, and removes `@wizbands`, `@wizstats` and
`@wiztail` in any order on a switch back to a video mode, on stop and on
shutdown. A user's own `af` chain is left in place.

Some mpv builds only expose the metadata of the last `astats` in a chain, so
`wizstats` can be empty while `wizbands` is live. In that case the Lua script
rebuilds the overall RMS and peak by summing the five band powers. That also
means audio still works on builds where only the band graph is readable; the
Python parser accepts either shape.

While an audio mode is active the state snapshot gains:

```json
"audio": {"rms": -24.1, "peak": -18.0, "crest": 6.1, "zcr": 0.12,
          "l": -24.1, "r": -25.0,
          "bands": [-41.2, -33.8, -27.0, -24.1, -30.5],
          "band_peaks": [-36.0, -28.1, -21.4, -18.0, -24.2]}
```

Levels are dBFS; `crest` is peak minus RMS in dB and `zcr` is the
zero-crossing rate. The louder channel of each stereo band pair is used, so a
one-sided mix still registers. Digital silence (`-inf`) and NaN become
`null`; Python treats `null` as silence. The signal view uses
`hot_db(rms, peak)`: the hotter of RMS and peak minus 8 dB, so a kick is
visible on the first update without a mastered track sitting at full scale.
`pulse_level(db, threshold, ceiling, punch)` then gates everything below the
threshold to zero, maps the window up to the ceiling onto 0…1 and raises the
result to `1 / punch`. A punch above 1 lifts the middle of the window, so a
solid hit lands near full instead of halfway; that is what turns a level meter
into a pulse. The beat detector runs on the same combined level, ignores
anything below the threshold, and compares it with a fast running baseline.

`Reaction.dimming()` is called only when the send loop builds a datagram, so
`run_sync()` passes the time since the previous send, not the 3–6 ms polling
step. The dynamics attack/release values are therefore wall-clock seconds;
using the polling delta would stretch a 55 ms release into almost a second.

The panel's **Signal** view is a local readout over that meter. `GET
/api/meter` reads the newest fresh Lua state file, applies `hot_db` to its
`audio` object and returns `active`, `db`, `rms`, `peak` and the five band
levels. The browser polls it every 40 ms only while an audio reaction is
selected and keeps a five-second history on the canvas: amber trace, red
segments above the threshold, and the same values in the header. The amber
threshold line is drawn from `react_threshold` and dragging it writes that
config value, so the meter follows the song without restarting the sync or
adding a second analyser.

The Lua timer beats at 30 Hz (`AUDIO_FPS`) even when the sampling profile caps
video analysis lower. `analyze()` is still gated by `fps_now`, so the extra
ticks only reuse the cached zones and re-read `af-metadata`. `run_sync()`
likewise raises the send rate to 30 Hz for audio modes. On an audio-only file
the Lua script keeps emitting a heartbeat with `audio` and no `zones`; the sync
holds a warm base color and drives only the brightness.

## Light sensor design

Not implemented yet. The planned hook is deliberately file-based, so it adds
no port, daemon or dependency: a BH1750 (or any sensor) writes

```json
{"lux": 42.5}
```

to `$XDG_RUNTIME_DIR/wiz-ambilight/lux.json`. A future `--lux-file` would read
it, reject a stale file, and make Equalize target measured lux instead of scene
luma; without a fresh file it falls back to `zones.all` as today. The panel
would show the reading next to the reaction hint. Do not add the flag until the
hardware path exists and has a test.

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
python3 assets/banner.py --version v1.10.0
```

`assets/banner.py` needs Pillow and numpy; neither is imported at playback
time. It is deterministic, and the committed PNGs should reproduce byte for
byte. The hero carries the version chip, so bump the `?v=` query in the README
when `VERSION` changes. The architecture source and render live next to each
other in `docs/`; edit the `.mmd`, re-render the `.svg` and update the
exposed-interface callout together.

## Scripted control recipes

`--set` is a normal command, so it composes with cron, systemd timers, desktop
shortcuts and media-server hooks without a dependency or a cloud account. For
example, a two-step look:

```sh
#!/bin/sh
# sunset.sh — warm the room, then settle into a scene
LIGHTS=192.168.1.5,192.168.1.7
cd /path/to/wiz-ambilight
./mpv_ambilight.py --set --lights "$LIGHTS" --hex '#ff8a3d' --brightness 70
sleep 3
./mpv_ambilight.py --set --lights "$LIGHTS" --scene 3 --speed 60
```

A systemd user timer for the same command:

```ini
# ~/.config/systemd/user/wiz-sunset.service
[Unit]
Description=Warm the room with WiZ

[Service]
Type=oneshot
ExecStart=%h/.local/bin/mpv-ambilight --set --lights 192.168.1.5,192.168.1.7 --scene 3 --speed 60
```

```ini
# ~/.config/systemd/user/wiz-sunset.timer
[Unit]
Description=Daily sunset look

[Timer]
OnCalendar=*-*-* 18:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

`systemctl --user enable --now wiz-sunset.timer` schedules it. On systems
without user timers, the same command works from `crontab`:

```cron
30 18 * * * /home/you/.local/bin/mpv-ambilight --set --lights 192.168.1.5,192.168.1.7 --hex '#ff8a3d' --brightness 70
```

Both run at a fixed local time. A true sunset lookup needs its own scheduler
or an external helper; the project does not add one.

## Design contract

The panel's tokens, layout and chart are documented in
[`design.md`](design.md) and pinned by `tests/test_design.py`. `SECURITY.md`
holds the trust model and the panel guarantees; if a change touches the
network, process control, the file picker or a persisted file, update it in the
same commit.
