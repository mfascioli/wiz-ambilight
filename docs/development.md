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
| `$XDG_RUNTIME_DIR/wiz-ambilight/state-<pid>.json` | Lua | zone colors, capture rate, mpv pid |
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
python3 assets/banner.py --version v1.8.0
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
