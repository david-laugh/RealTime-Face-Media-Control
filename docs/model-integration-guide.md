# Model Integration Guide (Mock → Edge Impulse)

> 이번 단계에서는 아래 작업을 **수행하지 않았습니다**. D 담당의 모델 선정 후 A 담당이 진행할 작업 목록입니다.

## 1. 현재 Mock 구조

```
smart_media.ino
  MockDetectionProvider detector;      ← 교체 지점 (1줄)
  detector.detect() → DetectionResult { faceDetected }
        ↓
  MqttPublisher::publishDetection(seq, uptime, detector.modelId(), result)
        ↓
  smart-media/xiao-01/detection  {"source":"mock","model_id":"mock-v1","raw_face_detected":...}
```

`MqttPublisher`는 `DetectionResult`와 문자열(`source`, `model_id`)만 받으므로 Provider 교체 시 수정이 필요 없습니다.
MQTT Contract(`contracts/mqtt/detection.schema.json`)는 이미 `source:"edge_impulse"`와 선택 필드 `confidence`, `inference_ms`, `bbox`를 허용합니다 → **Gateway 수정 불필요**.

## 2. 향후 흐름

```
Camera (OV2640/OV3660) → frame buffer → resize/crop to model input
  → run_classifier() → bounding boxes → max confidence ≥ threshold ?
  → DetectionResult { faceDetected, confidence, inferenceMs } → MqttPublisher
```

## 3. 작업 목록

### 3.1 Edge Impulse Arduino Library 설치
1. Edge Impulse Studio → Deployment → **Arduino library** → (Quantized int8 권장) Build → ZIP 다운로드
2. Arduino IDE → Sketch → Include Library → **Add .ZIP Library...**
3. ZIP 파일은 `firmware/xiao-esp32s3-sense/models/`에 보관 가능 (git-ignored, 커밋 금지)

### 3.2 Arduino IDE 설정
- Tools → **PSRAM: OPI PSRAM** (카메라 frame buffer 필요)
- Partition Scheme: 모델 크기에 따라 `Huge APP` 등 검토
- 빌드 시간이 길어짐 (EI 라이브러리 전체 컴파일)

### 3.3 카메라 초기화
- `esp_camera.h`, XIAO ESP32S3 Sense 핀맵 (`CAMERA_MODEL_XIAO_ESP32S3`)
- 권장: `PIXFORMAT_RGB565` 또는 `JPEG` + 디코딩, `FRAMESIZE_QVGA`, `fb_count=1~2`, `CAMERA_GRAB_LATEST`

### 3.4 이미지 전처리
- 모델 입력 해상도(예: 96x96)로 resize/crop, RGB888 변환
- `signal_t`의 `get_data` 콜백으로 전달 (Edge Impulse 예제 `esp32_camera` 참고)

### 3.5 추론 결과에서 Face 추출
- FOMO/Object detection: `result.bounding_boxes[]`에서 label `face`, `value >= threshold`
- `faceDetected = any(box)`; `confidence = max(value)`; `inferenceMs = result.timing.classification`
- threshold는 D의 Benchmark 결과로 결정

### 3.6 Provider 교체

```cpp
// EdgeImpulseDetectionProvider.h — MockDetectionProvider와 같은 public 메서드
class EdgeImpulseDetectionProvider {
 public:
  bool begin();                  // camera init
  DetectionResult detect();      // capture + inference
  const char* source() const { return "edge_impulse"; }
  const char* modelId() const { return "ei-<project>-<model>-int8"; }
};
```

`smart_media.ino`에서:

```cpp
#include "EdgeImpulseDetectionProvider.h"
static EdgeImpulseDetectionProvider detector;   // MockDetectionProvider 대체
```

`begin()` 실패(카메라 오류) 시 detection을 발행하지 않고 Serial에 오류를 출력 → Gateway가 timeout으로 PAUSE.

### 3.7 Payload 확장
`detect()`에서 `result.hasConfidence = true; result.confidence = ...; result.hasInferenceMs = true; result.inferenceMs = ...`
→ `MqttPublisher`가 자동으로 `confidence`, `inference_ms` 필드 추가. (`bbox` 필요 시 `DetectionResult`/`MqttPublisher`에 같은 방식으로 추가)

### 3.8 발행 주기 / Timeout 재설정
- 실제 추론은 연속 실행되므로 `PUBLISH_INTERVAL_MS`를 추론 주기(예: 500~1000 ms)로 줄이고,
- Gateway `DEVICE_TIMEOUT_MS`도 발행 주기의 약 2.5~3배로 조정 (예: 3000 ms)
- Flicker 방지를 위해 Gateway에 debounce/hysteresis 추가 검토

## 4. 향후 테스트 계획

| 항목 | 방법 |
|------|------|
| 컴파일 / Flash / RAM | arduino-cli compile 출력 |
| 추론 latency | `inference_ms` 필드, Serial 로그 |
| Peak RAM | `ESP.getMinFreeHeap()`, `ESP.getFreePsram()` → telemetry |
| 검출 품질 | `docs/model-benchmark.md`의 Pose × Distance × Environment 매트릭스 |
| E2E PLAY/PAUSE latency | 사람 동작 시각 → WebSocket `ts_server_ms` → 브라우저 재생 시각 |
| 회귀 | `scripts/integration_test.py` (Gateway 계약 불변 확인) |
