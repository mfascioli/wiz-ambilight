# A measured light sensor

**Auto Lux** can hold the room at a **measured** brightness instead of guessing
it from the video, on top of any reaction. The path is deliberately small and
file-based:

```
BH1750 --I2C--> ESP32 --Wi-Fi POST--> lux-bridge.py --atomic write--> lux.json
                                                                          |
                                                     mpv_ambilight.py reads it
```

The sync never opens a socket for this and never imports an HTTP client. It
only reads `$XDG_RUNTIME_DIR/wiz-ambilight/lux.json` while Auto Lux is checked,
and drops the correction when the file is missing, malformed or older than 5 s
(Equalize then falls back to the video estimate). That means the sensor is
optional at every step: unplug it, stop the bridge, or kill the ESP32 mid-film
and the look degrades to the current behaviour.

## Bill of materials

| Part | Notes | Price |
| --- | --- | --- |
| ESP32 DevKit (any classic ESP32) | Wi-Fi, 3V3, two free pins | US$ 4–8 |
| BH1750 module (GY-302) | I2C, 3.3 V, address `0x23` or `0x5C` | US$ 1–3 |
| 4 jumper wires | no soldering if the module has headers | — |

A BH1750 is the default because it is the cheapest widely sold module, reads
1–65535 lx at 1 lx resolution, and needs no library: the sketch talks to its
two registers directly. VEML7700, MAX44009, OPT3001 and TSL2591 work too, but
each needs its own converter and none is cheaper or easier to find.

## 1. Flash the ESP32

Open [`esp32-bh1750/esp32-bh1750.ino`](esp32-bh1750/esp32-bh1750.ino) in the
Arduino IDE (Arduino-ESP32 core 2.x or 3.x, no libraries) and set:

```cpp
WIFI_SSID, WIFI_PASS      // your 2.4 GHz network
BRIDGE_HOST               // fixed IP of the machine running the bridge
BRIDGE_PORT               // 8766 unless you change it
BRIDGE_TOKEN              // same value as WIZ_LUX_TOKEN, or empty
```

Wiring, with the module's `ADDR` pin tied to GND (`0x23`):

| BH1750 | ESP32 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |
| ADDR | GND |

The serial monitor at 115200 baud prints `lux: 42.5 ok` once per second.
Note the IP the router gives the ESP32 and reserve it, so a DHCP change does
not silently stop the readings.

## 2. Run the bridge

On the machine that runs the sync — the same host is simplest, but any host on
the LAN works if both sides share `$XDG_RUNTIME_DIR`, which in practice means
the same machine:

```bash
install -m 755 contrib/lux-bridge.py ~/.local/bin/lux-bridge
mkdir -p ~/.config/wiz-ambilight
cp contrib/wiz-ambilight-lux.env.example ~/.config/wiz-ambilight/lux.env
cp contrib/wiz-ambilight-lux.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wiz-ambilight-lux
```

Check it without the ESP32:

```bash
curl -X POST http://127.0.0.1:8766/lux \
     -H 'X-Lux-Token: change-me' -d '{"lux": 42.5}'
cat "${XDG_RUNTIME_DIR:-/tmp}/wiz-ambilight/lux.json"
```

The file appears with mode `0600` and the sync picks it up within half a
second.

**Other bridges.** The contract is one file, not one protocol. If you already
run Home Assistant or Mosquitto, a subscriber can write the same
`{"lux": …}` atomically and the bridge is not needed. The project ships no MQTT
client and no broker integration on purpose: the sync reads a file and nothing
else.

## 3. Use it

Tick **Auto Lux** in **Look** or pass `--auto-lux`. It works with every
reaction; Equalize also shows **Target luma**, which it uses whenever no fresh
reading exists. The target lux field and the sensor readout appear as soon as
Auto Lux is checked, and the readout says "stale" when the bridge stops.

```bash
./mpv_ambilight.py --react color --auto-lux --lux-target 50 movie.mkv
```

| Flag | Default | Values | Effect |
| --- | --- | --- | --- |
| `--auto-lux` | off | flag | Use the sensor as a brightness layer over the selected reaction. |
| `--lux-file` | runtime directory | path | Where to read `{"lux": …}`. Rarely needed. |
| `--lux-target` | `50` | 1–5000 lx | Illuminance Auto Lux holds. 50 lx is a dim living room; 150–300 lx is a lit one. |

The correction uses the Equalize profile's ±35 % span, floor and 4 s smoothing
whatever reaction is selected, so a lamp switching on does not make the bulbs
jump and switching reactions never changes the ambient controller. Because the
bulbs themselves add light, keep the sensor pointed at the wall or the sofa,
not at a bulb, and do not mount it right beside one.

## Limits

- The bridge listens on `0.0.0.0:8766` so the ESP32 can reach it. Anyone on
  the LAN can post a reading; that can only change Auto Lux's brightness.
  Set `WIZ_LUX_TOKEN` to require the header, or bind `--host 127.0.0.1` when
  the sensor runs on the same machine.
- There is no TLS: the token crosses the LAN in clear text, like the WiZ UDP
  protocol itself. Keep the bridge on a trusted network.
- The reading is not a calibrated measurement. It is one sensor's view of one
  spot; adjust `--lux-target` by eye rather than trusting the number.
- Tested against the bridge and the parser, not against a physical BH1750 in
  this repository. If your module always reads `0` or `65535`, check `ADDR`,
  the wiring, and that the sketch found the sensor at `0x23`.
