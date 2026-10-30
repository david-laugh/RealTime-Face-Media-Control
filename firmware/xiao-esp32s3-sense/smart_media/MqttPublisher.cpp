#include "MqttPublisher.h"

void MqttPublisher::begin(const char* host, uint16_t port, const char* deviceId,
                          const char* source) {
  deviceId_ = deviceId;
  source_ = source;

  snprintf(detectionTopic_, sizeof(detectionTopic_), "smart-media/%s/detection", deviceId_);
  snprintf(statusTopic_, sizeof(statusTopic_), "smart-media/%s/status", deviceId_);
  buildStatusPayload(false, willPayload_, sizeof(willPayload_));

  client_.setServer(host, port);
  client_.setBufferSize(512);
  client_.setKeepAlive(15);
  // Bound the blocking time of a single connect attempt (seconds).
  client_.setSocketTimeout(3);
}

void MqttPublisher::loop() {
  if (client_.connected()) {
    client_.loop();
    return;
  }

  if (wasConnected_) {
    wasConnected_ = false;
    Serial.printf("[MQTT] Disconnected (state=%d)\n", client_.state());
  }

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  const uint32_t now = millis();
  if (attemptedOnce_ && now - lastAttemptMs_ < kReconnectIntervalMs) {
    return;
  }
  attemptedOnce_ = true;
  lastAttemptMs_ = now;

  if (tryConnect()) {
    wasConnected_ = true;
    connectedEvent_ = true;
  }
}

bool MqttPublisher::connected() {
  return client_.connected();
}

bool MqttPublisher::consumeConnectedEvent() {
  const bool event = connectedEvent_;
  connectedEvent_ = false;
  return event;
}

bool MqttPublisher::tryConnect() {
  Serial.printf("[MQTT] Connecting as '%s' ...\n", deviceId_);

  // Last Will: retained offline status, published by the broker on abnormal disconnect.
  const bool ok = client_.connect(deviceId_, statusTopic_, /*willQos=*/1,
                                  /*willRetain=*/true, willPayload_);
  if (!ok) {
    Serial.printf("[MQTT] Connect failed (state=%d), retry in %lu ms\n", client_.state(),
                  (unsigned long)kReconnectIntervalMs);
    return false;
  }

  Serial.println("[MQTT] Connected");
  if (publishStatus(true)) {
    Serial.printf("[MQTT] Status online published -> %s\n", statusTopic_);
  } else {
    Serial.println("[MQTT] Status online publish FAILED");
  }
  return true;
}

bool MqttPublisher::publishStatus(bool online) {
  char payload[128];
  buildStatusPayload(online, payload, sizeof(payload));
  return client_.publish(statusTopic_, payload, /*retained=*/true);
}

void MqttPublisher::buildStatusPayload(bool online, char* out, size_t outLen) const {
  snprintf(out, outLen,
           "{\"schema_version\":\"1.0\",\"device_id\":\"%s\",\"source\":\"%s\",\"online\":%s}",
           deviceId_, source_, online ? "true" : "false");
}

bool MqttPublisher::publishDetection(uint32_t seq, uint32_t uptimeMs, const char* modelId,
                                     const DetectionResult& result) {
  if (!client_.connected()) {
    return false;
  }

  char payload[320];
  int len = snprintf(payload, sizeof(payload),
                     "{\"schema_version\":\"1.0\",\"device_id\":\"%s\",\"seq\":%lu,"
                     "\"uptime_ms\":%lu,\"source\":\"%s\",\"model_id\":\"%s\","
                     "\"raw_face_detected\":%s",
                     deviceId_, (unsigned long)seq, (unsigned long)uptimeMs, source_, modelId,
                     result.faceDetected ? "true" : "false");

  // Optional fields: only present when the provider actually measured them.
  if (result.hasConfidence && len > 0 && len < (int)sizeof(payload)) {
    len += snprintf(payload + len, sizeof(payload) - len, ",\"confidence\":%.3f",
                    result.confidence);
  }
  if (result.hasInferenceMs && len > 0 && len < (int)sizeof(payload)) {
    len += snprintf(payload + len, sizeof(payload) - len, ",\"inference_ms\":%lu",
                    (unsigned long)result.inferenceMs);
  }
  if (len <= 0 || len >= (int)sizeof(payload) - 1) {
    Serial.println("[MQTT] Detection payload too large, dropped");
    return false;
  }
  payload[len++] = '}';
  payload[len] = '\0';

  // QoS 0, retain=false: stale detections must not be replayed on reconnect.
  const bool ok = client_.publish(detectionTopic_, payload, /*retained=*/false);
  Serial.printf("[MQTT] %s %s %s\n", ok ? "Published" : "Publish FAILED", detectionTopic_,
                payload);
  return ok;
}
