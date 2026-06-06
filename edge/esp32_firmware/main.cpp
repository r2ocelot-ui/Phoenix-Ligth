/*
 * Phoenix-Light edge firmware (reference sketch).
 *
 * Reads instantaneous V/I/P/PF from a PZEM-004T (UART) and publishes a JSON
 * telemetry payload over MQTT every TELEMETRY_INTERVAL_MS. Subscribes to
 *   phoenix/cabinets/<ID>/cmd/relay  -> {"state":"on"|"off"}
 *   phoenix/cabinets/<ID>/cmd/dim    -> {"level":0..100}
 * to actuate the lamp contactor and a 0-10 V dimming output (PWM + RC filter).
 *
 * Hardware: ESP32-WROOM-32, PZEM-004T v3 (UART2), SSR/relay on GPIO 26,
 *           PWM dimming on GPIO 25.
 *
 * Build with PlatformIO (env:esp32dev), libraries: PubSubClient, ArduinoJson,
 * PZEM004Tv30.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <PZEM004Tv30.h>

static const char* WIFI_SSID = "your-ssid";
static const char* WIFI_PASS = "your-pass";
static const char* MQTT_HOST = "broker.local";
static const uint16_t MQTT_PORT = 1883;
static const char* CABINET_ID = "CAB-001";
static const uint32_t TELEMETRY_INTERVAL_MS = 5000;

static const uint8_t RELAY_PIN = 26;
static const uint8_t DIM_PIN = 25;
static const uint8_t DIM_PWM_CH = 0;

PZEM004Tv30 pzem(Serial2, 16, 17);
WiFiClient wifi;
PubSubClient mqtt(wifi);

static String topicTelemetry, topicStatus, topicCmdRelay, topicCmdDim;
static uint32_t lastSent = 0;

static void onMessage(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, payload, len)) return;

  if (topicCmdRelay.equals(topic)) {
    const char* state = doc["state"] | "off";
    digitalWrite(RELAY_PIN, strcmp(state, "on") == 0 ? HIGH : LOW);
  } else if (topicCmdDim.equals(topic)) {
    int level = doc["level"] | 0;
    level = constrain(level, 0, 100);
    ledcWrite(DIM_PWM_CH, map(level, 0, 100, 0, 255));
  }
}

static void connectMqtt() {
  while (!mqtt.connected()) {
    String clientId = String("phoenix-") + CABINET_ID;
    if (mqtt.connect(clientId.c_str(), nullptr, nullptr,
                     topicStatus.c_str(), 1, true, "{\"online\":false}")) {
      mqtt.publish(topicStatus.c_str(), "{\"online\":true}", true);
      mqtt.subscribe(topicCmdRelay.c_str(), 1);
      mqtt.subscribe(topicCmdDim.c_str(), 1);
    } else {
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  ledcSetup(DIM_PWM_CH, 5000, 8);
  ledcAttachPin(DIM_PIN, DIM_PWM_CH);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);

  String base = String("phoenix/cabinets/") + CABINET_ID;
  topicTelemetry = base + "/telemetry";
  topicStatus    = base + "/status";
  topicCmdRelay  = base + "/cmd/relay";
  topicCmdDim    = base + "/cmd/dim";

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  uint32_t now = millis();
  if (now - lastSent < TELEMETRY_INTERVAL_MS) return;
  lastSent = now;

  float v  = pzem.voltage();
  float i  = pzem.current();
  float p  = pzem.power();
  float pf = pzem.pf();
  if (isnan(v) || isnan(i)) return;

  StaticJsonDocument<256> doc;
  doc["cabinet_id"]     = CABINET_ID;
  // timestamp omitted on purpose: the backend stamps server receive time.
  // For audit-grade timestamps, sync NTP on the edge and set an ISO-8601 string here.
  doc["voltage_v"]      = v;
  doc["current_a"]      = i;
  doc["active_power_w"] = p;
  doc["power_factor"]   = pf;
  doc["lamp_circuit"]   = "L1";

  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(topicTelemetry.c_str(), buf, n);
}
