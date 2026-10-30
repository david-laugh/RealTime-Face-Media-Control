#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "DetectionResult.h"

// Publishes detection / status messages to the MQTT broker.
// Independent of the detection provider: it only receives a DetectionResult
// plus source / model_id strings.
//
// Topics:
//   smart-media/{device_id}/detection  (QoS 0, retain=false)
//   smart-media/{device_id}/status     (retain=true, Last Will = offline)
class MqttPublisher {
 public:
  void begin(const char* host, uint16_t port, const char* deviceId, const char* source);

  // Call every loop(). Non-blocking except for a single bounded connect attempt
  // (socket timeout) at most once per reconnect interval.
  void loop();

  bool connected();

  // True exactly once after each successful (re)connection.
  bool consumeConnectedEvent();

  bool publishDetection(uint32_t seq, uint32_t uptimeMs, const char* modelId,
                        const DetectionResult& result);

 private:
  bool tryConnect();
  bool publishStatus(bool online);
  void buildStatusPayload(bool online, char* out, size_t outLen) const;

  WiFiClient wifiClient_;
  PubSubClient client_{wifiClient_};

  const char* deviceId_ = nullptr;
  const char* source_ = nullptr;

  char detectionTopic_[64] = {0};
  char statusTopic_[64] = {0};
  char willPayload_[128] = {0};

  uint32_t lastAttemptMs_ = 0;
  bool attemptedOnce_ = false;
  bool wasConnected_ = false;
  bool connectedEvent_ = false;

  static const uint32_t kReconnectIntervalMs = 5000;
};
