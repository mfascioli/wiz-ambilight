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

A style is a starting point for capture, fade and send. The tables, defaults
and reaction descriptions live in the README under
[Configuration](../README.md#-configuration); these are the flags.

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
  --react-bands '#ff3b30,#ff9500,#ffcc00,#34c759,#5ac8fa' concert.mkv
```

The four dynamics values also have flags: `--react-threshold`,
`--react-attack`, `--react-release` and `--react-punch`. `--react-amount`
scales every reaction (`0` disables it), `--react-profile` picks `soft`,
`balanced` or `strong`, and `--react-target` sets the luma Equalize aims for.

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
`--power off` cannot be combined with a color or brightness. Invalid input exits
with status `2`; a network/discovery failure exits with `1`.

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
[Web Panel](../README.md#-web-panel).
