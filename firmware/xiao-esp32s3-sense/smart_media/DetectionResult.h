#pragma once

// Output of any detection provider (Mock now, Edge Impulse later).
// Optional fields are only published when their has* flag is true,
// so the MQTT payload contract stays the same across providers.
//
// Contract (contracts/mqtt/detection.schema.json):
//   mock:          has* all false -> no confidence / threshold / inference_ms.
//   edge_impulse:  hasConfidence MUST be true on every frame. confidence = highest
//                  face score of the frame (0..1), also when no face passes the
//                  threshold; 0 when the model produced no valid face score.
//                  threshold (same 0..1 scale) = value used to decide faceDetected,
//                  i.e. faceDetected == (confidence >= threshold).
struct DetectionResult {
  bool faceDetected = false;

  bool hasConfidence = false;
  float confidence = 0.0f;

  bool hasThreshold = false;
  float threshold = 0.0f;

  bool hasInferenceMs = false;
  uint32_t inferenceMs = 0;
};
