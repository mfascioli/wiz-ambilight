# Command line

The panel is the normal way to use `wiz-ambilight`, and the
[README](../README.md) documents it. This page is the terminal reference for
the same program: discovery, launch and attach modes, direct WiZ control,
styles, reactions, sampling and scripted looks. Nothing here needs a different
build or a separate install.

```bash
# the panel, if you landed here from a search
./mpv_ambilight.py --gui
```

## Run it from anywhere

The checkout is enough. A symlink lets you call it from any directory:

```bash
mkdir -p ~/.local/bin
ln -s "$PWD/mpv_ambilight.py" ~/.local/bin/mpv-ambilight
```

## Flags

`./mpv_ambilight.py --help` prints the same list. Values marked **style** come
from `--style`; the style table is in the [README](../README.md#-styles).

### Modes, panel and setup

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `media` | — | files, URLs, mpv arguments | Positional. Everything after a bare `--` goes to mpv. |
| `--version` | — | — | Print the version and exit. |
| `--gui` | off | flag | Start the local panel and open a browser. |
| `--gui-port` | `8765` | port | Panel port. |
| `--no-browser` | off | flag | With `--gui`: do not open a browser. |
| `--demo` | off | flag | With `--gui`: fake bulbs, never send UDP. |
| `--attach` | off | flag | Follow a running mpv (needs the installed Lua script). |
| `--install-script` | off | flag | Copy `lua/wiz_ambilight.lua` into mpv's scripts folder. |
| `--force` | off | flag | With `--install-script`: replace a different existing copy. |
| `--discover` | off | flag | List bulbs and exit. |
| `--json` | off | flag | With `--discover`: machine-readable output. |
| `--set` | off | flag | Send direct controls and exit; no mpv needed. |

### Bulbs, layouts and zones

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--lights` | `$WIZ_LIGHTS`, then `$WIZ_LIGHT_IPS`, then discovery | IPs separated by commas or spaces | Bulb set and order. Duplicates are removed; the order defines the zones. |
| `--layout` | `auto` | `auto`, `all`, `left-right`, `top-bottom`, `thirds`, `cycle` | How zones are spread over the bulbs. |
| `--zones` | from `--layout` | `all`, `left`, `right`, `top`, `bottom`, `t1`, `t2`, `t3` | Explicit zone per bulb. Repeats if there are fewer zones than bulbs; wins over `--layout`. |

`auto` means 1 bulb → `all`, 2 → `left-right`, 3 → `thirds`, 4 or more →
`cycle`. With exactly two bulbs, `thirds` uses the outer thirds (`t1`, `t3`).

### Look, styles and capture

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--style` | `hue` | `hue`, `cinema`, `fast`, `reactive`, `raw`, `custom` | Starting point for the knobs below. `custom` starts from the built-in values. |
| `--fps` | style (12–24) | 1–30 | Captures per second. A sampling profile caps it when `--fps` is not explicit. |
| `--edge` | style (0.12–0.20) | 0.02–0.45 | Edge band size. |
| `--smooth` | style (0–220) | 0–2000 ms | Fade constant; `0` disables interpolation. |
| `--saturation` | style (1.15–1.45) | 0–4 after vibrance | Base saturation. |
| `--vibrance` | `1.0` | 0–2 | Multiplies the style's saturation; `1` is unchanged. |
| `--white-leds` | off | flag | Send the grey part of each color (`min(r, g, b)`) on the bulb's `c` and `w` channels, following cB-Sigma/wiz. Saturated colors are unchanged. |
| `--gamma` | style (`1.0`) | 0.2–3 | Output gamma. |
| `--brightness` | style (80–100) | 10–100 | Bulb dimming. |
| `--send-hz` | style (15–30) | 1–30 | Maximum `setPilot` updates per second. Audio modes send at 30 Hz. |
| `--on-exit` | `leave` | `leave`, `off` | Keep the last color, or turn the bulbs off when mpv exits. |

### Reactions

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--react` | `color` | `color`, `equalize`, `cut`, `motion`, `duotone`, `beat`, `vu` | What the bulbs react to and how. |
| `--react-amount` | `0.8` | 0–1 | Reaction strength; `0` keeps the source color only. |
| `--react-target` | `0.45` | 0.05–0.95 | `equalize` only: target scene luma; the fallback when Auto Lux has no fresh reading. |
| `--auto-lux` | off | flag | Use the light sensor as a brightness layer over any reaction. |
| `--lux-file` | runtime `lux.json` | path | With `--auto-lux`: read measured lux from this file. See [the sensor guide](../contrib/lux-sensor.md). |
| `--lux-target` | `50` | 1–5000 lx | With `--auto-lux`: target illuminance. |
| `--react-profile` | `balanced` | `soft`, `balanced`, `strong` | Intensity profile. In audio modes it bundles gate, ceiling, envelope and punch. |
| `--react-bands` | [8 defaults](../README.md#-audio-colors) | exactly `--react-eq-bands` `#rrggbb` values | One color per EQ band, low to high (`bands` mode). |
| `--react-eq-bands` | `8` | 2–16 | Number of graphic-EQ bands. |
| `--react-eq` | log-spaced 32 Hz-16 kHz | JSON array | Per-band `{freq,type,slope,gain,q,lamp,solo}`; `type` is `bell`, `bandpass`, `lowpass`, `highpass`, `notch` or `flat`, `slope` is 12, 24 or 48 dB/oct, `lamp` is a 0-based enabled-bulb index or `-1` for auto, and `solo` makes every bulb follow that band. |
| `--react-auto` | `off` | `off`, `ssl`, `api`, `hybrid` | Light-envelope auto release; `ssl` uses dual program-dependent release, `api` adds a soft knee and low-end thrust. Lives in the Dynamics strip, not the EQ. |
| `--react-active-bands` | off | flag | Only bands above their own noise floor (4 dB, 180 ms hold) light a bulb. |
| `--react-color-mode` | `bands` | `bands`, `spectrum`, `rainbow`, `range`, `level`, `single` | Where audio bulb colors come from. |
| `--react-color-a` | `#fcbe11` | `#rrggbb` | Low color for `range`, soft color for `level`, only color for `single`. |
| `--react-color-b` | `#38bdf8` | `#rrggbb` | High color for `range`, loud color for `level`. |
| `--react-threshold` | profile (`-18` dBFS on `balanced`) | −36–0 dBFS | Audio gate where the bulbs start to open. |
| `--react-attack` | profile (`1` ms on `balanced`) | 0–200 ms | Envelope attack. |
| `--react-release` | profile (`55` ms on `balanced`) | 20–1000 ms | Envelope release. |
| `--react-punch` | profile (`3.0` on `balanced`) | 1–4 | How hard levels above the gate drive brightness. |

The audio profile values are `soft` −30 dBFS / 12 ms / 200 ms / 1.4, `balanced`
−18 / 1 / 55 / 3.0 and `strong` −14 / 0 / 30 / 4.0 (threshold / attack /
release / punch). The four named presets are in the
[README](../README.md#-audio-dynamics).

`--react-eq` is a JSON array in frequency order. A band missing from the array
keeps its log-spaced default at that position, and the array is sorted before
use. `type` defaults to `bell` and `slope` to `24`, so old arrays keep working.
For example, a high cut that follows the bass, a band pass on the mids and a
sparkle bell, with the bass soloed on every bulb:

```bash
./mpv_ambilight.py --react vu \
  --react-eq '[{"freq":60,"type":"lowpass","slope":24,"gain":-12,"lamp":0,"solo":true},{"freq":900,"type":"bandpass","slope":48,"q":2.4,"gain":4,"lamp":1},{"freq":9000,"type":"bell","q":5,"gain":6,"lamp":2}]' \
  song.flac
```

Gain only shapes detection, never mpv's output. Shapes change which part of the
mix the band hears: `lowpass` keeps everything below its frequency (the panel
calls it **High cut**), `highpass` everything above (**Low cut**), `bandpass` a
slice around it, `notch` cuts the centre out and `flat` hears the full mix.
Bands that share a lamp are averaged; lamps without an assignment follow the
overall mix. A soloed band overrides every lamp assignment until you clear it.

### Sampling

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--sampling` | `auto` | `auto`, `lean`, `balanced`, `quality`, `manual` | Capture budget. The profile table is in the [README](../README.md#-sampling). |
| `--sample-grid` | `auto`: Lua decides; `manual`: `80` | 24–240 | Sample columns. Profiles use 48 (`lean`), 80 (`balanced`) or 120 (`quality`). |
| `--sample-block` | `auto`: Lua decides; `manual`: `1` | 1–4 | Average an N×N block per cell. Profiles use 1, 2 or 3. |
| `--capture` | `scaled` (`quality`: `source`) | `auto`, `scaled`, `source` | `scaled` copies the window; `source` copies the decoded frame. An explicit value wins over the profile. |

### Direct control

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--hex` | — | `#rgb` or `#rrggbb` | RGB color. Mutually exclusive with `--temp`. |
| `--temp` | — | 2200–6500 K | White temperature. Mutually exclusive with `--hex`. |
| `--scene` | — | 1–999 | WiZ scene id. |
| `--speed` | — | 20–200 | Scene speed; requires `--scene`. |
| `--power` | — | `on`, `off`, `toggle` | Power state. `off` cannot be combined with any other control. |
| `--dry-run` | off | flag | Print the colors or payloads instead of sending them. Applies to the sync and to `--set`. |

The panel adds the target's metered draw to its power state (`On · 4.2 W`) when
the firmware reports it, reading `pc` from `getPilot` or asking `getPower` on
older metering models. Bulbs without metering just show `On`, and `--set` has no
power readout.

### Debugging

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--state` | launch: `state-<pid>.json`; attach: `state.json` (both under `$XDG_RUNTIME_DIR/wiz-ambilight/`) | path | Read and write an explicit state file. |
| `--no-bars` | off | flag | Disable automatic letterbox/pillarbox cropping. |
| `--mpv` | `mpv` | path | mpv binary to launch. |
| `--verbose`, `-v` | off | flag | Print the mpv command line. |

### Exit status

| Status | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | Missing Lua script, a different script already installed without `--force`, no bulbs found, or a discovery/network failure. |
| `2` | Invalid arguments, values out of range, an invalid `--set` combination or an invalid bulb address. |

## Discovery

```bash
./mpv_ambilight.py --discover
```

It prints each bulb's IP, model, firmware and state:

```text
192.168.1.5      ESP24_SHRGBC_01    fw=1.38.0   mac=d8a01154f818 state=on  dimming=100 rssi=-54
192.168.1.7      ESP24_SHRGBC_01    fw=1.38.0   mac=d8a01154fba8 state=on  dimming=100 rssi=-58
```

`--discover --json` gives the same data in machine-readable form. WiZ does not
expose the name you assigned in the app over the local UDP API, so the tool
identifies bulbs by IP and MAC; names live in the panel and `lights.json`.

## Launch a video

```bash
# auto-discover the bulbs, bulb 1 = left edge, bulb 2 = right edge
./mpv_ambilight.py movie.mkv

# choose the bulbs yourself
./mpv_ambilight.py --lights 192.168.1.5,192.168.1.7 movie.mkv

# both bulbs follow the whole picture (great when they sit above the TV)
./mpv_ambilight.py --layout all movie.mkv

# explicit zones, in bulb order
./mpv_ambilight.py --zones left,right,all movie.mkv

# pass normal mpv options after a bare "--"
./mpv_ambilight.py movie.mkv -- --fullscreen --sub-file=es.srt
```

Launch mode passes `--script=lua/wiz_ambilight.lua` to the mpv it starts, so it
needs no installed copy of the script.

When mpv exits, the bulbs keep their last color. `--on-exit off` turns them off
instead.

## Attach to a running mpv

Attach follows an mpv you started yourself, so mpv has to load the script at
startup. That is the only install this project needs, and it is a one-time
copy into mpv's scripts folder:

```bash
./mpv_ambilight.py --install-script
```

Start mpv the way you normally do — desktop launcher, file manager, shell — then
run:

```bash
./mpv_ambilight.py --attach
```

The installed script idles unless a live control file exists in
`$XDG_RUNTIME_DIR/wiz-ambilight/`, so installing it globally is safe. `Ctrl+C`
stops the daemon and the script goes back to sleep.

If you are already running a daemon, updating the checkout requires:

```bash
./mpv_ambilight.py --install-script --force
```

Then restart mpv so it loads the new copy. Only one mpv instance can be
followed; the control file is global. In the panel, the same install is the
**Install script** button and the same mode is **Attach to mpv** under
**Session**.

## Styles, reactions and sampling

A style is a starting point for capture, fade and send. The style and sampling
tables and the reaction descriptions live in the README under
[Configuration](../README.md#-configuration); the flags, defaults and ranges are
in [Flags](#flags). These are the flags in use:

```bash
# styles
./mpv_ambilight.py --style cinema movie.mkv
./mpv_ambilight.py --style fast --brightness 70 movie.mkv
./mpv_ambilight.py --smooth 150 --saturation 1.5 --send-hz 15 movie.mkv
./mpv_ambilight.py --style raw --vibrance 1.4 movie.mkv
```

```bash
# video reactions
./mpv_ambilight.py --react equalize movie.mkv
./mpv_ambilight.py --react cut --react-amount 0.5 movie.mkv
./mpv_ambilight.py --react motion --react-profile strong --react-amount 0.7 movie.mkv

# audio reactions (music, or any file with an audio track)
./mpv_ambilight.py --react vu concert.mkv
./mpv_ambilight.py --react beat --react-profile soft song.flac
./mpv_ambilight.py --react vu --react-threshold -24 --react-punch 4 \
  --react-release 30 concert.mkv
./mpv_ambilight.py --react vu \
  --react-bands '#ff3b30,#ff9500,#ffcc00,#34c759,#5ac8fa,#0a84ff,#bf5af2,#ff2d55' \
  concert.mkv
./mpv_ambilight.py --react vu --react-eq-bands 16 --react-auto hybrid concert.mkv
./mpv_ambilight.py --react vu --react-active-bands --react-auto ssl concert.mkv
./mpv_ambilight.py --react vu --react-color-mode rainbow concert.mkv
./mpv_ambilight.py --react vu --react-color-mode range \
  --react-color-a '#ff3b30' --react-color-b '#5ac8fa' concert.mkv
```

The four dynamics values also have flags: `--react-threshold`,
`--react-attack`, `--react-release` and `--react-punch`. `--react-amount`
scales every reaction (`0` disables it), `--react-profile` picks `soft`,
`balanced` or `strong`, and `--react-target` sets the luma Equalize aims for.
`--auto-lux` turns the optional light sensor into a brightness layer for any
reaction; `--lux-target` (and optionally `--lux-file`) configure it, and
Equalize keeps its luma target as the fallback when no reading is fresh. The
guide is in [`contrib/lux-sensor.md`](../contrib/lux-sensor.md).

```bash
# the default: adapt the sampling to the captured resolution
./mpv_ambilight.py movie.mkv

# explicit presets
./mpv_ambilight.py --sampling lean movie.mkv
./mpv_ambilight.py --sampling quality --style cinema movie.mkv

# every knob by hand
./mpv_ambilight.py --sampling manual --fps 12 --sample-grid 96 \
  --sample-block 2 --capture source movie.mkv
```

An explicit `--fps` or `--capture` wins over the profile, so
`--sampling lean --fps 15` keeps lean's 48 columns and raises its cap. The panel
starts from the same values and stores them in `lights.json`.

## Direct WiZ control

`--set` sends one command and exits; it does not start a sync or need mpv. It
uses `--lights`, then `WIZ_LIGHTS` / `WIZ_LIGHT_IPS`, then discovery.

```bash
# turn everything on/off (or one bulb with --lights)
./mpv_ambilight.py --set --power on
./mpv_ambilight.py --set --lights 192.168.1.5 --power off

# RGB as hex (3- or 6-digit), with optional brightness
./mpv_ambilight.py --set --lights 192.168.1.5,192.168.1.7 --hex '#ff8800' --brightness 60

# white temperature instead of color
./mpv_ambilight.py --set --temp 3000

# a WiZ scene, with optional speed
./mpv_ambilight.py --set --scene 4 --speed 120

# preview the UDP payloads without sending anything
./mpv_ambilight.py --set --hex '#00ff7f' --dry-run
```

`--hex` and `--temp` are mutually exclusive, `--speed` requires `--scene`, and
`--power off` cannot be combined with any other control (color, brightness,
temperature or scene). Invalid input exits with status `2`; a network/discovery
failure exits with `1`.

Common scene ids are `1` Ocean, `3` Sunset, `4` Party, `5` Fireplace, `10`
Bedtime, `12` Daylight, `16` Relax and `18` TV time; firmware may expose more.
The panel lists every scene it knows about.

## Run it as a user service

This needs the `~/.local/bin/mpv-ambilight` symlink from above. The service
starts with your session and waits for mpv on its own — no window or terminal is
needed.

```bash
mkdir -p ~/.config/wiz-ambilight
cp contrib/wiz-ambilight.env.example ~/.config/wiz-ambilight/env
$EDITOR ~/.config/wiz-ambilight/env

mkdir -p ~/.config/systemd/user
cp contrib/wiz-ambilight.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wiz-ambilight.service
```

## Scripted looks

`--set` is a normal command, so it composes with cron, systemd timers, desktop
shortcuts and media-server hooks without a dependency or a cloud account. A
two-step look:

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

Both run at a fixed local time. A true sunset lookup needs its own scheduler or
an external helper; the project does not add one.

## Configuration files

The panel writes `lights.json` and `scenes.json`; the CLI reads the same values
from flags and environment variables. Paths, overrides and the JSON schemas are
in [`development.md`](development.md#config-format). The panel's server flags
(`--gui`, `--gui-port`, `--no-browser`, `--demo`) are in the README under
[Web Panel & Operating Modes](../README.md#-web-panel--operating-modes).
