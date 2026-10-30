#pragma once

// Output of any detection provider (Mock now, Edge Impulse later).
// Optional fields are only published when their has* flag is true,
// so the MQTT payload contract stays the same across providers.
struct DetectionResult {
  bool faceDetected = false;

  bool hasConfidence = false;
  float confidence = 0.0f;

  bool hasInferenceMs = false;
  uint32_t inferenceMs = 0;
};
