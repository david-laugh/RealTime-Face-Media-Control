#pragma once

#include <Arduino.h>
#include "DetectionResult.h"

// Mock face detector: alternates true / false on every detect() call.
// No camera, no inference. Does NOT fabricate confidence or latency.
//
// To integrate a real model, write a class with the same public methods
// (begin / detect / source / modelId), e.g. EdgeImpulseDetectionProvider,
// and change the provider type in smart_media.ino.
class MockDetectionProvider {
 public:
  bool begin();
  DetectionResult detect();

  const char* source() const { return "mock"; }
  const char* modelId() const { return "mock-v1"; }

 private:
  bool nextValue_ = true;  // first published value is true
};
