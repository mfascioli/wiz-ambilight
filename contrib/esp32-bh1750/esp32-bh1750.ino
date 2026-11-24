/*
 * wiz-ambilight lux sensor: BH1750 + ESP32, Wi-Fi POST to the host bridge.
 *
 * Wiring (classic ESP32 DevKit):
 *   BH1750 VCC -> 3V3
 *   BH1750 GND -> GND
 *   BH1750 SDA -> GPIO21
 *   BH1750 SCL -> GPIO22
 *   BH1750 ADDR -> GND (address 0x23) or 3V3 (address 0x5C)
 *
 * The sensor is read in continuous high-resolution mode (1 lx, ~120 ms) and
 * the value is posted once per second as `{"lux": 42.5}` to the bridge in
 * `contrib/lux-bridge.py`. Nothing here talks to the bulbs, mpv or the
 * internet beyond your LAN.
 *
 * Before flashing, set the five constants below. Use Arduino-ESP32 2.x/3.x;
 * no external library is required.
 */

#include <HTTPClient.h>
#include <WiFi.h>
#include <Wire.h>

// ---- configuration ---------------------------------------------------------
static const char *WIFI_SSID = "your-ssid";
static const char *WIFI_PASS = "your-password";

// Host that runs contrib/lux-bridge.py. A hostname such as "media-pc" works
// if your router resolves it; a fixed IP is more reliable for a device.
static const char *BRIDGE_HOST = "192.168.1.10";
static const uint16_t BRIDGE_PORT = 8766;

// Must match WIZ_LUX_TOKEN on the bridge. Leave empty to disable the check.
static const char *BRIDGE_TOKEN = "";

// How often to measure and post. 1 s is plenty: the bridge treats a reading
// older than 5 s as stale and Equalize falls back to video luma.
static const uint32_t INTERVAL_MS = 1000;

// ---- sensor ----------------------------------------------------------------
static const uint8_t BH1750_ADDR = 0x23;  // 0x5C when ADDR is tied to 3V3
static const uint8_t BH1750_CONTINUOUS_HIGH = 0x10;
static const uint8_t SDA_PIN = 21;
static const uint8_t SCL_PIN = 22;

static uint32_t last_post = 0;
static uint32_t last_wifi_try = 0;

static bool read_lux(float &lux) {
  if (Wire.requestFrom(BH1750_ADDR, (uint8_t)2) != 2) {
    while (Wire.available()) {
      Wire.read();
    }
    return false;
  }
  uint16_t raw = (uint16_t(Wire.read()) << 8) | Wire.read();
  lux = raw / 1.2f;
  return true;
}

static void connect_wifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (millis() - last_wifi_try < 5000) {
    return;
  }
  last_wifi_try = millis();
  Serial.printf("wifi: connecting to %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

static bool post_lux(float lux) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }
  HTTPClient http;
  String url = String("http://") + BRIDGE_HOST + ":" + String(BRIDGE_PORT) + "/lux";
  if (!http.begin(url)) {
    Serial.println("http: begin failed");
    return false;
  }
  http.setTimeout(3000);
  http.addHeader("Content-Type", "application/json");
  if (BRIDGE_TOKEN[0] != '\0') {
    http.addHeader("X-Lux-Token", BRIDGE_TOKEN);
  }
  char body[40];
  int length = snprintf(body, sizeof(body), "{\"lux\":%.1f}", lux);
  int code = http.POST((uint8_t *)body, (size_t)length);
  http.end();
  if (code < 200 || code >= 300) {
    Serial.printf("http: POST %s -> %d\n", url.c_str(), code);
    return false;
  }
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.beginTransmission(BH1750_ADDR);
  Wire.write(BH1750_CONTINUOUS_HIGH);
  if (Wire.endTransmission() != 0) {
    Serial.printf("bh1750: no answer at 0x%02X\n", BH1750_ADDR);
  } else {
    Serial.printf("bh1750: continuous high-res at 0x%02X\n", BH1750_ADDR);
    delay(180);  // first measurement in continuous high-res mode
  }
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void loop() {
  connect_wifi();
  if (millis() - last_post < INTERVAL_MS) {
    delay(20);
    return;
  }
  last_post = millis();

  float lux = 0.0f;
  if (!read_lux(lux)) {
    Serial.println("bh1750: read failed");
    return;
  }
  Serial.printf("lux: %.1f %s\n", lux, post_lux(lux) ? "ok" : "not sent");
}
