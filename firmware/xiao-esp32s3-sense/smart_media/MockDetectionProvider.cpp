#include "MockDetectionProvider.h"

bool MockDetectionProvider::begin() {
  nextValue_ = true;
  return true;
}

DetectionResult MockDetectionProvider::detect() {
  DetectionResult result;
  result.faceDetected = nextValue_;
  nextValue_ = !nextValue_;
  return result;
}
