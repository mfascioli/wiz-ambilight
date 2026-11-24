# A measured light sensor

**Auto Lux** can hold the room at a **measured** brightness instead of guessing
it from the video, on top of any reaction. The path is deliberately small and
file-based:

```
sensor --I2C--> ESP32 --Wi-Fi POST--> lux-bridge.py --atomic write--> lux.json
                                                                          |
                                                     mpv_ambilight.py reads it
```

The sync never opens a socket for this and never imports an HTTP client. It
only reads `$XDG_RUNTIME_DIR/wiz-ambilight/lux.json` while Auto Lux is checked,
and drops the correction when the file is missing, malformed or older than 5 s
(Equalize then falls back to the video estimate; every other reaction keeps its
look). That means the sensor is optional at every step: unplug it, stop the
bridge, or kill the ESP32 mid-film and the look degrades to the current
behaviour.

## Supported sensors

The ESP32 sketch talks to the sensor over raw I2C, so it needs no Arduino
sensor library. Pick the model you can buy locally and set `SENSOR_MODEL` in
the sketch to the matching constant.

| Sensor | I2C address | Range | Resolution / notes | `SENSOR_MODEL` |
| --- | --- | --- | --- | --- |
| BH1750 (GY-302) | `0x23` (ADDR low) or `0x5C` (ADDR high) | 1–65,535 lx | 1 lx; the default and the cheapest | `SENSOR_BH1750` |
| VEML7700 | `0x10` | ~0–15,100 lx linear | 0.23 lx at gain 1/4, 100 ms; Vishay correction above 1,000 lx | `SENSOR_VEML7700` |
| MAX44009 (GY-49) | `0x4A` (ADDR low) or `0x4B` (ADDR high) | 0.045–188,000 lx | 0.045 lx; auto range | `SENSOR_MAX44009` |
| OPT3001 | `0x44` (ADDR low), `0x45`/`0x46`/`0x47` | 0.01–83,865 lx | 0.01 lx; auto range | `SENSOR_OPT3001` |
| TSL2591 | `0x29` | ~0–10,700 lx | ~0.16 lx at gain 25x, 100 ms; 88,000 lx at gain 1x | `SENSOR_TSL2591` |

The BH1750 is the default because it is the cheapest widely sold module, reads
1–65,535 lx at 1 lx resolution, and needs no library: the sketch talks to its
two registers directly. The other four are supported by the same sketch, each
with its own raw-I2C driver, so you do not need a sensor library for any of
them.

The bridge accepts `0`–`65,535` lx. Brighter sensors are clamped to that
ceiling by the sketch; Auto Lux targets at most `5,000` lx, so this is not a
practical limit.

## Bill of materials

| Part | Notes | Price |
| --- | --- | --- |
| ESP32 DevKit (any classic ESP32) | Wi-Fi, 3V3, two free pins | US$ 4–8 |
| One sensor from the table above | I2C, 3.3 V | US$ 1–7 |
| 4 jumper wires | no soldering if the module has headers | — |

## 1. Flash the ESP32

Open [`esp32-lux/esp32-lux.ino`](esp32-lux/esp32-lux.ino) in the Arduino IDE
(Arduino-ESP32 core 2.x or 3.x, no libraries) and set:

```cpp
#define SENSOR_MODEL SENSOR_BH1750  // or SENSOR_VEML7700, SENSOR_MAX44009,
                                    // SENSOR_OPT3001, SENSOR_TSL2591
WIFI_SSID, WIFI_PASS      // your 2.4 GHz network
BRIDGE_HOST               // fixed IP of the machine running the bridge
BRIDGE_PORT               // 8766 unless you change it
BRIDGE_TOKEN              // same value as WIZ_LUX_TOKEN, or empty
```

Wiring is the same for every model:

| Sensor | ESP32 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

Set the module's address pin as noted in the table above (`ADDR`/`A0` to GND
for the first address, to 3V3 for the second; the OPT3001 also offers `0x46`
and `0x47` by tying `ADDR` to SDA or SCL). All modules are 3.3 V; do not power
a 5 V-only breakout from 3V3 without checking its regulator, and do not put 5 V
on the ESP32 I2C pins.

The serial monitor at 115200 baud prints `sensor: ready at 0x…` once at boot
and `lux: 42.5 ok` once per second. Note the IP the router gives the ESP32 and
reserve it, so a DHCP change does not silently stop the readings.

## 2. Run the bridge

Run the bridge on the machine that runs the sync. It writes `lux.json` into
`$XDG_RUNTIME_DIR/wiz-ambilight/`, and the sync reads the file from its own
runtime directory, so both must be the same filesystem; a shared runtime
directory over the network would also work but is not the supported setup.

```bash
mkdir -p ~/.local/bin
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
- Tested against the bridge and the parser, not against a physical sensor in
  this repository. The sketch has a raw-I2C driver for each model, but none has
  been run on hardware here; if a module always reads `0` or `65535`, check the
  address pin, the wiring and the serial monitor.
- The bridge accepts `0`–`65,535` lx; brighter sensors are clamped by the
  sketch. Auto Lux targets at most `5,000` lx.
