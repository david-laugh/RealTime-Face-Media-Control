// smart_media — XIAO ESP32S3 Sense firmware (Mock detection demo)
//
// Boot -> Wi-Fi -> MQTT -> publish mock face detection (true/false alternating)
// right after MQTT connects, then every PUBLISH_INTERVAL_MS.
//
// Board: XIAO_ESP32S3 (esp32 by Espressif Systems)
// Library: PubSubClient (Nick O'Leary)
//
// Setup: copy config.example.h to config.h and edit it.

#include <WiFi.h>

#include "config.h"
#include "MockDetectionProvider.h"
#include "MqttPublisher.h"

#ifndef PUBLISH_INTERVAL_MS
#define PUBLISH_INTERVAL_MS 10000
#endif

static const uint32_t kWifiRetryIntervalMs = 10000;

// Replace with a real provider (e.g. EdgeImpulseDetectionProvider) later.
static MockDetectionProvider detector;
static MqttPublisher publisher;

static uint32_t seq = 0;
static uint32_t lastPublishMs = 0;
static uint32_t lastWifiAttemptMs = 0;
static bool wifiWasConnected = false;

static void startWifi() {
  Serial.printf("[WiFi] Connecting to '%s' ...\n", WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptMs = millis();
}

// Non-blocking Wi-Fi maintenance: never waits for the connection to complete.
static void maintainWifi() {
  const bool connected = WiFi.status() == WL_CONNECTED;

  if (connected && !wifiWasConnected) {
    Serial.printf("[WiFi] Connected, IP=%s RSSI=%d dBm\n", WiFi.localIP().toString().c_str(),
                  WiFi.RSSI());
  } else if (!connected && wifiWasConnected) {
    Serial.println("[WiFi] Disconnected");
  }
  wifiWasConnected = connected;

  if (!connected && millis() - lastWifiAttemptMs >= kWifiRetryIntervalMs) {
    startWifi();
  }
}

static void publishDetection() {
  const DetectionResult result = detector.detect();
  seq++;
  const uint32_t uptimeMs = millis();

  Serial.printf("[DETECT] seq=%lu source=%s face_detected=%s\n", (unsigned long)seq,
                detector.source(), result.faceDetected ? "true" : "false");

  publisher.publishDetection(seq, uptimeMs, detector.modelId(), result);
  lastPublishMs = uptimeMs;
}

void setup() {
  Serial.begin(115200);
  delay(500);  // let USB CDC settle; boot only
  Serial.println();
  Serial.println("=== smart_media (mock detection) ===");
  Serial.printf("device_id=%s broker=%s:%d interval=%d ms\n", DEVICE_ID, MQTT_HOST, MQTT_PORT,
                PUBLISH_INTERVAL_MS);

  detector.begin();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  startWifi();

  publisher.begin(MQTT_HOST, MQTT_PORT, DEVICE_ID, detector.source());
}

void loop() {
  maintainWifi();
  publisher.loop();

  if (!publisher.connected()) {
    return;
  }

  // First detection right after (re)connecting, then every PUBLISH_INTERVAL_MS.
  if (publisher.consumeConnectedEvent() || millis() - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    publishDetection();
  }
}
