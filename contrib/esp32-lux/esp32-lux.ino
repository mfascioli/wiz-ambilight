/*
 * wiz-ambilight lux sensor: ESP32 + one I2C ambient-light sensor.
 *
 * Supported sensors (raw I2C, no Arduino sensor library):
 *   BH1750    0x23 / 0x5C   1-65535 lx
 *   VEML7700  0x10          0-15100 lx linear, higher with correction
 *   MAX44009  0x4A / 0x4B   0.045-188000 lx
 *   OPT3001   0x44          0.01-83865 lx
 *   TSL2591   0x29          0-10700 lx at gain 25x, 100 ms
 *
 * Every model uses the same four wires:
 *   VCC -> 3V3, GND -> GND, SDA -> GPIO21, SCL -> GPIO22.
 * Set SENSOR_MODEL below and, if the module has an address pin, wire it as
 * noted in contrib/lux-sensor.md.
 *
 * The reading is posted once per second as `{"lux": 42.5}` to the bridge in
 * `contrib/lux-bridge.py`. Nothing here talks to the bulbs, mpv or the
 * internet beyond your LAN.
 *
 * Before flashing, set the Wi-Fi and bridge constants and pick SENSOR_MODEL.
 * Use Arduino-ESP32 2.x/3.x; no external library is required.
 */

#include <HTTPClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <math.h>

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
// older than 5 s as stale and Auto Lux falls back to the reaction's own look.
static const uint32_t INTERVAL_MS = 1000;

// ---- sensor selection ------------------------------------------------------
#define SENSOR_BH1750 1
#define SENSOR_VEML7700 2
#define SENSOR_MAX44009 3
#define SENSOR_OPT3001 4
#define SENSOR_TSL2591 5

// Pick one. The default matches the wiring guide and the cheapest module.
#ifndef SENSOR_MODEL
#define SENSOR_MODEL SENSOR_BH1750
#endif

static const uint8_t SDA_PIN = 21;
static const uint8_t SCL_PIN = 22;

// ---- sensor drivers --------------------------------------------------------
#if SENSOR_MODEL == SENSOR_BH1750

static const uint8_t SENSOR_ADDR = 0x23;  // 0x5C when ADDR is tied to 3V3
static const uint8_t BH1750_CONTINUOUS_HIGH = 0x10;

static bool sensor_begin() {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(BH1750_CONTINUOUS_HIGH);
  return Wire.endTransmission() == 0;
}

static bool sensor_read(float &lux) {
  if (Wire.requestFrom(SENSOR_ADDR, (uint8_t)2) != 2) {
    while (Wire.available()) {
      Wire.read();
    }
    return false;
  }
  uint8_t high = Wire.read();
  uint8_t low = Wire.read();
  uint16_t raw = (uint16_t(high) << 8) | low;
  lux = raw / 1.2f;
  return true;
}

#elif SENSOR_MODEL == SENSOR_VEML7700

static const uint8_t SENSOR_ADDR = 0x10;
static const uint8_t VEML7700_ALS_CONF = 0x00;
static const uint8_t VEML7700_ALS = 0x04;
// Gain 1/4, integration time 100 ms: 0.2304 lx/count, full scale ~15,100 lx.
// The two high bits of ALS_GAIN are 11 and ALS_IT 0000 is 100 ms.
static const uint16_t VEML7700_CONF = 0x1800;

static bool sensor_begin() {
  // VEML7700 registers are 16-bit little-endian: low byte first.
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(VEML7700_ALS_CONF);
  Wire.write(uint8_t(VEML7700_CONF & 0xFF));
  Wire.write(uint8_t(VEML7700_CONF >> 8));
  if (Wire.endTransmission() != 0) {
    return false;
  }
  delay(120);  // first 100 ms integration
  return true;
}

static bool sensor_read(float &lux) {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(VEML7700_ALS);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(SENSOR_ADDR, (uint8_t)2) != 2) {
    return false;
  }
  uint8_t low = Wire.read();
  uint8_t high = Wire.read();
  uint16_t raw = (uint16_t(high) << 8) | low;
  float value = raw * 0.2304f;
  if (value > 1000.0f) {
    // Vishay's correction for gain 1/4 and 1/8 above 1000 lx.
    float square = value * value;
    value = 6.0135e-13f * square * square
            - 9.3924e-9f * square * value
            + 8.1488e-5f * square
            + 1.0023f * value;
  }
  lux = value;
  return true;
}

#elif SENSOR_MODEL == SENSOR_MAX44009

static const uint8_t SENSOR_ADDR = 0x4A;  // 0x4B when ADDR is tied to 3V3
static const uint8_t MAX44009_CONFIG = 0x02;
static const uint8_t MAX44009_LUX_HIGH = 0x03;

static bool sensor_begin() {
  // Continuous mode, 100 ms integration, automatic range.
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(MAX44009_CONFIG);
  Wire.write(0x83);
  if (Wire.endTransmission() != 0) {
    return false;
  }
  delay(120);
  return true;
}

static bool sensor_read(float &lux) {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(MAX44009_LUX_HIGH);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(SENSOR_ADDR, (uint8_t)2) != 2) {
    return false;
  }
  uint8_t high = Wire.read();
  uint8_t low = Wire.read();
  uint8_t exponent = high >> 4;
  if (exponent == 0x0F) {
    lux = 65535.0f;  // overrange; clamp to the ceiling the bridge accepts
    return true;
  }
  uint16_t mantissa = ((high & 0x0F) << 4) | (low & 0x0F);
  lux = (1UL << exponent) * mantissa * 0.045f;
  return true;
}

#elif SENSOR_MODEL == SENSOR_OPT3001

static const uint8_t SENSOR_ADDR = 0x44;  // 0x45/0x46/0x47 with ADDR high/SDA/SCL
static const uint8_t OPT3001_RESULT = 0x00;
static const uint8_t OPT3001_CONFIG = 0x01;
// Automatic range, 100 ms conversion, continuous.
static const uint16_t OPT3001_CONF = 0xC000;

static bool sensor_begin() {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(OPT3001_CONFIG);
  Wire.write(uint8_t(OPT3001_CONF >> 8));
  Wire.write(uint8_t(OPT3001_CONF & 0xFF));
  if (Wire.endTransmission() != 0) {
    return false;
  }
  delay(120);
  return true;
}

static bool sensor_read(float &lux) {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(OPT3001_RESULT);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(SENSOR_ADDR, (uint8_t)2) != 2) {
    return false;
  }
  uint8_t high = Wire.read();
  uint8_t low = Wire.read();
  uint16_t raw = (uint16_t(high) << 8) | low;
  uint8_t exponent = raw >> 12;
  uint16_t mantissa = raw & 0x0FFF;
  lux = 0.01f * (1UL << exponent) * mantissa;
  return true;
}

#elif SENSOR_MODEL == SENSOR_TSL2591

static const uint8_t SENSOR_ADDR = 0x29;
static const uint8_t TSL2591_COMMAND = 0xA0;
static const uint8_t TSL2591_ENABLE = 0x00;
static const uint8_t TSL2591_CONTROL = 0x01;
static const uint8_t TSL2591_ALS = 0x14;
// Gain 25x, 100 ms integration: counts-per-lux = (100 * 25) / 408.
static const float TSL2591_CPL = (100.0f * 25.0f) / 408.0f;

static bool sensor_begin() {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(TSL2591_COMMAND | TSL2591_ENABLE);
  Wire.write(0x03);  // power on + ALS enable
  if (Wire.endTransmission() != 0) {
    return false;
  }
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(TSL2591_COMMAND | TSL2591_CONTROL);
  Wire.write(0x10);  // gain 25x, 100 ms
  if (Wire.endTransmission() != 0) {
    return false;
  }
  delay(120);
  return true;
}

static bool sensor_read(float &lux) {
  Wire.beginTransmission(SENSOR_ADDR);
  Wire.write(TSL2591_COMMAND | TSL2591_ALS);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(SENSOR_ADDR, (uint8_t)4) != 4) {
    return false;
  }
  uint8_t ch0_low = Wire.read();
  uint8_t ch0_high = Wire.read();
  uint8_t ch1_low = Wire.read();
  uint8_t ch1_high = Wire.read();
  uint16_t ch0 = uint16_t(ch0_low) | (uint16_t(ch0_high) << 8);
  uint16_t ch1 = uint16_t(ch1_low) | (uint16_t(ch1_high) << 8);
  if (ch0 == 0) {
    lux = 0.0f;
    return true;
  }
  if (ch1 >= ch0) {
    // Saturated or no visible/IR difference: skip the sample instead of
    // reporting a false zero that would make Auto Lux brighten the room.
    return false;
  }
  lux = (ch0 - ch1) * (1.0f - float(ch1) / float(ch0)) / TSL2591_CPL;
  return true;
}

#else
#error "Set SENSOR_MODEL to SENSOR_BH1750, SENSOR_VEML7700, SENSOR_MAX44009, SENSOR_OPT3001 or SENSOR_TSL2591"
#endif

// ---- Wi-Fi and HTTP --------------------------------------------------------
static uint32_t last_post = 0;
static uint32_t last_wifi_try = 0;

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
  if (lux < 0.0f) {
    lux = 0.0f;
  }
  if (lux > 65535.0f) {
    lux = 65535.0f;  // the bridge accepts 0-65535 lx
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
  if (!sensor_begin()) {
    Serial.printf("sensor: no answer at 0x%02X\n", SENSOR_ADDR);
  } else {
    Serial.printf("sensor: ready at 0x%02X\n", SENSOR_ADDR);
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
  if (!sensor_read(lux)) {
    Serial.println("sensor: read failed");
    return;
  }
  Serial.printf("lux: %.1f %s\n", lux, post_lux(lux) ? "ok" : "not sent");
}
