# Security

What runs on your machine, what the code touches, what the panel guarantees,
and what none of it can promise. This is the user-facing summary; keep it in
step with the code. The [architecture diagram](docs/architecture.svg) shows
the same model visually, including the trust boundaries.

## Trust model

Three pieces run as you, none of them as root:

| Piece | Runs as | Reaches |
| --- | --- | --- |
| `mpv_ambilight.py` | a normal process | UDP `38899` to bulb IPs, LAN broadcast, loopback HTTP for the panel |
| `lua/wiz_ambilight.lua` | inside mpv | reads frames, writes one JSON state file |
| the web panel (`webui.py`) | a normal process | `127.0.0.1` only; spawns the sync as a child |

The only persistent install is `--install-script`, which **copies** the Lua
file into mpv's scripts folder (`~/.config/mpv/scripts/`), so it loads on every
mpv start. Nothing downloads code, and no installer fetches anything at all.

## What the code touches

- **Network.** UDP `38899` to the bulbs, broadcast on the LAN for discovery,
  an optional `/24` sweep when you press **Scan network**, and loopback HTTP
  for the panel. There is no HTTP client, no DNS lookup, no account, no
  telemetry and no update check — the Python standard library imports no
  outbound HTTP module. **The sync process never listens**: it creates an
  unbound UDP socket, which the kernel assigns an ephemeral local port, and
  only sends on it (discovery and direct control read replies with short
  timeouts). It does not call `bind`, `listen` or `accept`.
- **Optional lux bridge.** `contrib/lux-bridge.py` is separate from the sync
  and the panel: nothing imports it, starts it or enables it by default. When
  you run it, it is the only process here that listens beyond loopback, on
  `0.0.0.0:8766`, with a 512-byte body cap, no outbound requests, and one
  write: `lux.json` replaced atomically at `0600`. A reading can only change
  Auto Lux's brightness. The `contrib/esp32-lux/` sketch runs on the sensor
  board, not on the host, and only posts to the bridge. Set `WIZ_LUX_TOKEN` /
  `--token` to require the `X-Lux-Token` header, or `--host 127.0.0.1` to keep
  it local; there is no TLS.
- **Processes.** The panel starts the sync with `subprocess.Popen(argv, ...)`,
  no shell and no string interpolation, in its own session. Stopping it sends
  `SIGTERM` to the process group when `os.killpg` exists and falls back to
  `terminate()`/`kill()` where it does not, waiting 4 s before the hard stop.
  After a panel restart, a PID file is adopted only if `/proc/<pid>/cmdline`
  (Linux) or `ps -p <pid> -o command=` (macOS/BSD) contains both this script
  and `mpv_ambilight`; when neither source exists (Windows), the panel refuses
  to adopt. The file picker tries `osascript` (macOS), `zenity` and `kdialog`,
  always with an argument list and a 120 s timeout; when none of them exists
  it returns an empty path and the manual **Video file** field stays the way
  to choose a file.
- **Audio.** `beat` and `vu` analyse the audio mpv is already decoding. The
  Lua script appends three labelled `lavfi` stages to mpv's audio filter chain
  only while one of those modes is selected: `astats` for the overall levels,
  a per-band filter bank for the configured EQ, and `anull` as a removable
  tail. The bank filters a copy of the mix with each band's shape (bell, band
  pass, low/high pass, notch or flat), merges the untouched stereo pair back as
  the last two channels and reads every band with `astats`; `pan` then selects
  only the original pair. The audio mpv plays is therefore unchanged. Configs
  without an EQ keep the older `acrossover`/`amerge` graph, which recombines the
  slices and adds an all-pass phase shift. It reads the levels from
  `af-metadata` and removes all three labels on exit. It never opens a
  microphone, a capture device or a file and never adds a dependency. With any
  other reaction the audio chain is untouched.
- **Files written.** The state file (`state-<pid>.json` in launch mode,
  `state.json` in attach), `stats-<pid>.json` and `control.json` under
  `$XDG_RUNTIME_DIR/wiz-ambilight/` (`/tmp` fallback, `0700`), the optional
  `lux.json` written by the bridge beside them, the `gui-daemon.json` PID file,
  `lights.json` and `scenes.json` in `~/.config/wiz-ambilight/` (`0600`), and
  the Lua copy in mpv's scripts folder. Nothing else is created, renamed or
  deleted.

## Exposed interfaces

Every surface is listed here; if it is not in this table, it does not exist.

| Surface | When | Why it exists | Mitigation |
| --- | --- | --- | --- |
| `127.0.0.1:8765` TCP | only with `--gui` | serve the local panel | loopback bind, Host/Origin checks, per-run token, strict CSP |
| `0.0.0.0:8766` TCP | only while `contrib/lux-bridge.py` runs | receive a sensor reading from the ESP32 | 512-byte body cap, optional `X-Lux-Token`, writes only `lux.json`; `--host 127.0.0.1` keeps it local |
| ephemeral UDP source port | during sync, discovery and direct control | send `setPilot`/`getPilot`/`getPower` and read replies | not a service, no `listen`/`accept`, short timeouts, no `bind` to a public interface |
| the state file (`state-<pid>.json` launch, `state.json` attach), `control.json` | during sync | hand zone colors, mpv's pid and the optional audio levels from mpv to Python | runtime dir `0700` |
| `stats-<pid>.json` | during sync, once a second | let the panel graph capture rate and real UDP traffic | runtime dir `0700`, removed on exit, ignored when older than 6 s or owned by another PID |
| `lights.json`, `scenes.json` | panel | names, zones, rooms, saved colors and saved looks | files `0600`; values range-checked |

There is no inbound TCP service other than the optional panel, no UDP listener
started by design, and no internet endpoint.

## Panel guarantees

- **Loopback only.** `ThreadingHTTPServer` bound to `127.0.0.1`; it refuses to
  start if the port is taken instead of falling back to a public interface.
- **Host and Origin checked.** Requests whose `Host` is not
  `127.0.0.1`/`localhost`/`[::1]` are rejected, and a browser `Origin` that is
  not the panel itself is refused — both block DNS-rebinding tricks.
- **Per-run token.** `secrets.token_urlsafe(24)`, embedded in the page, sent
  as `X-Wiz-Token` and compared with `secrets.compare_digest`. Another site
  cannot read it, and JSON cross-origin POSTs need a preflight the panel does
  not allow.
- **Strict headers.** CSP `default-src 'none'` plus only its own script, style,
  font and connect sources, `base-uri 'none'`, `form-action 'none'`,
  `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, no referrer,
  `no-store`, and permissions for camera, microphone and geolocation denied.
- **No shell, no option smuggling.** A video path that starts with `-` is
  rejected, so it can never become an mpv option such as `--script=`.
- **Scoped actions.** Identify, power and direct control only accept bulbs the
  panel already knows about. Colors, temperatures, scene ids and speeds are
  range-checked, and saved scenes ignore unknown addresses.

## Provenance

`mpv_ambilight.py`, `webui.py`, `lua/wiz_ambilight.lua`, `web/`, `tests/` and
the `assets/` generators are ours. `upstream/` is
[wiz-hack](https://github.com/myselfshravan/wiz-hack) (MIT), kept for reference
and never imported. The white-LED mapping and the `getPower`/`pc` metering
follow [cB-Sigma/wiz](https://github.com/cB-Sigma/wiz) by Abhinav Gautam
(Apache-2.0); no code was copied, only the protocol behaviour. `web/fonts/Merriweather-Bold.ttf` is SIL OFL;
`assets/banner-fonts/` (Fira Sans Condensed, SIL OFL) is used by
`assets/banner.py` only and is never served by the panel. mpv is not bundled.

## How it was written

Most of the code was generated with **DeepSeek V4.1 Flash Free** in OpenCode.
No other model or tool is claimed for this repository.

## Review status (2026-11-18)

A static read of `mpv_ambilight.py`, `webui.py` and the Lua script for this
documentation pass confirmed the behaviour above: no outbound HTTP, no shell
string execution, Host/Origin/token checks present, private file modes, and
`--install-script` copying rather than executing. That is a code read, not an
audit.

Two weaknesses found in the 1.5.0 read were fixed in 1.6.0:

- **PID adoption without `/proc`.** The panel now verifies the process command
  line through `/proc` or `ps`; when neither exists it refuses to adopt. A
  stale `gui-daemon.json` can no longer make **Stop** signal a foreign PID.
- **`os.killpg` is POSIX-only.** The stop path uses `os.killpg` only when the
  function exists, then falls back to `terminate()`/`kill()`, so Windows no
  longer raises `AttributeError` instead of stopping the child.

What has **not** been done:

- no third-party or antivirus scan of a release archive yet;
- no fuzzing of the UDP parsers or of the panel's JSON bodies;
- no test against a physical sensor or ESP32: the bridge, the parser and the
  Auto Lux fallback are covered by unit tests, the sketch is not;
- no test on Windows, where the runtime directory, the Lua install path and
  the file picker still assume Unix — see the roadmap in the
  [README](README.md#-roadmap).

## Limits

- **The WiZ local API is unauthenticated.** Anyone on the same LAN can drive
  the bulbs, and a spoofed reply is indistinguishable from a real one. The
  panel's token protects the panel from other origins, not the bulbs from your
  network. Discovery and `getPilot` replies are keyed by source address but not
  restricted to the local subnet, so a host on the LAN can advertise a fake
  bulb entry; the next command to it is still just UDP.
- **Plain UDP, no encryption.** Colors are readable on the LAN by design; a
  VPN or a guest network with client isolation changes what is reachable, not
  what is protected.
- **The panel is a local service.** It trusts everything that can connect to
  `127.0.0.1` with the token; it is not hardened against a compromised local
  account.
- **The lux bridge is optional and unauthenticated by default.** It listens on
  `0.0.0.0:8766` only while you run it, and any LAN host that reaches the port
  can post a reading. That changes only Auto Lux's brightness. Set
  `WIZ_LUX_TOKEN` to require the header; the token itself is sent in clear
  text, so keep the bridge on a trusted network.

## Reporting

Open an issue at
[github.com/mfascioli/wiz-ambilight/issues](https://github.com/mfascioli/wiz-ambilight/issues)
with the version (`./mpv_ambilight.py --version`), the panel's **Activity**
log and the exact steps. There is no bounty.
