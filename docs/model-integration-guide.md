# Model Integration Guide (Mock → Edge Impulse)

> 실제 Edge Impulse 모델 통합은 **아직 하지 않았습니다**. 이 문서는 A 담당이 Provider를 교체할 때 따를 계약과 작업 목록입니다.
> 2026-10-30: D(Benchmark) 담당 피드백 반영 — `confidence` 전송 규칙, `threshold` 필드, 실기기 관찰 사항, Gateway debounce 구조.

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
MQTT Contract(`contracts/mqtt/detection.schema.json`)는 `source:"edge_impulse"`와 `confidence`, `threshold`, `inference_ms`, `bbox`를 허용합니다 → **Gateway 수정 불필요**.

## 2. Detection 필드 규칙 (Edge Impulse)

### 2.1 `confidence` — 항상 전송

| source | `confidence` |
|--------|--------------|
| `mock` | 보내지 않음 (또는 `null`). Gateway → WebSocket에서는 `null` |
| `edge_impulse` | **필수, 숫자.** 매 프레임 전송 |

- 값 = 그 프레임에서 모델이 출력한 **얼굴 검출 점수의 최고값** (FOMO bounding box `value`, 0–1).
- 얼굴이 검출되지 않았거나 threshold 미만이어도 **최고 점수를 그대로** 보냅니다 (예: `raw_face_detected:false, confidence:0.35`).
- 유효한 점수가 없으면(박스 0개) **`0`**을 보냅니다. `null`이나 필드 생략은 계약 위반입니다.
  - 주의: 기기는 라이브러리 출력 임계값(`model_variables.h`의 `threshold`) 이상인 박스만 받습니다.
    D 담당 환경은 이 값을 0.2로 낮춰 두었으므로, 그 환경에서 `0`은 "0.2 이상 박스 없음"을 뜻합니다.
- 목적: Benchmark가 threshold별 검출률 / 오탐률을 계산 (D 담당 요청).
- Firmware `MqttPublisher`는 `source != mock`인데 `hasConfidence=false`이면 발행하지 않고 Serial에 계약 위반을 출력합니다. Gateway도 같은 payload를 무시합니다.

### 2.2 `threshold` — 선택

- 기기가 `raw_face_detected`를 판정할 때 실제 사용한 임계값. **`confidence`와 같은 0–1 점수 척도.**
- 같은 `model_id`라도 threshold에 따라 `raw_face_detected`가 달라지므로 Benchmark 기록용으로 보냅니다.
- 없어도 Gateway와 Mock은 정상 동작합니다 (Gateway는 로그에만 남김). Mock은 보내지 않습니다.

### 2.3 `confidence`와 `raw_face_detected`의 관계

```
raw_face_detected == (confidence >= threshold)      # threshold를 보낼 때 항상 성립해야 함
```

- **PLAY/PAUSE 판단은 Gateway가 `raw_face_detected`만으로** 합니다. `confidence`/`threshold`는 표시(web-ui "신뢰도")와 Benchmark 분석용입니다.
- `bbox`는 `raw_face_detected:true`일 때만 보냅니다 (최고 점수 박스, 0–1 정규화). 미검출이면 생략.

```json
{"schema_version":"1.0","device_id":"xiao-01","seq":3,"uptime_ms":23100,"source":"edge_impulse","model_id":"ei-541658-fomo01-int8","raw_face_detected":true,"confidence":0.84,"threshold":0.6,"inference_ms":2300,"bbox":{"x":0.4167,"y":0.4167,"w":0.0833,"h":0.0833}}
{"schema_version":"1.0","device_id":"xiao-01","seq":4,"uptime_ms":25400,"source":"edge_impulse","model_id":"ei-541658-fomo01-int8","raw_face_detected":false,"confidence":0.35,"threshold":0.6,"inference_ms":2300}
{"schema_version":"1.0","device_id":"xiao-01","seq":5,"uptime_ms":27700,"source":"edge_impulse","model_id":"ei-541658-fomo01-int8","raw_face_detected":false,"confidence":0,"threshold":0.6,"inference_ms":2300}
```

(위 숫자는 형식 예시입니다. `inference_ms`는 실제 측정값만 보냅니다.)

## 3. 실기기 관찰 사항 (D 담당 보고)

> **D 담당의 특정 테스트 환경**에서 관찰된 결과입니다. 모든 보드/라이브러리 버전에서 똑같이 발생한다고 단정하지 않습니다. A 담당 통합 시 재확인이 필요합니다.
> 환경: XIAO ESP32S3 Sense, Edge Impulse 프로젝트 541658 (FOMO, int8, Grayscale, 입력 96x96), Arduino ESP32 보드 패키지 3.3.12.
> 상세: `feature/model-benchmark` 브랜치 `services/model-benchmark/bench-sketch/README.md`

| # | 관찰 | 해당 환경에서의 조치 / 결과 |
|---|------|-----------------------------|
| 1 | Edge Impulse `esp32_camera` 예제의 **BGR→RGB 색상 스왑**을 그대로 쓰면 얼굴이 검출되지 않음 | `ei_camera_get_data()`에서 스왑을 제거하자 검출됨. D 담당 추정: 사용한 esp32-camera 드라이버가 이미 RGB 순서로 변환하므로 스왑이 색을 다시 뒤집음 |
| 2 | **ESP-NN 활성화** 시 첫 추론에서 크래시 (Guru Meditation, StoreProhibited) | `ei_classifier_config.h`의 `EI_CLASSIFIER_TFLITE_ENABLE_ESP_NN`을 `0`으로 해 비활성화. 보드 패키지 3.x 호환 문제일 수 있음 → 2.0.x에서 재검증 필요 (미확인) |
| 3 | ESP-NN 비활성화 시 추론 **약 2.3초/프레임** | 발행 주기와 Gateway timeout 설계에 반영 필요 (§5.3) |
| 4 | 얼굴이 화면 **중앙**일 때 상대적으로 잘 검출. 카메라 320x240 중 가운데 240x240만 모델 입력 | 좌우 가장자리 각 40px는 인식 영역 밖 |
| 5 | **정면 얼굴도 프레임마다 검출이 끊김** (예: `true → false → true → false → true`) | 메시지마다 즉시 PLAY/PAUSE하면 재생이 반복 전환됨 → Gateway debounce 필요 (§4) |

통합 시 할 일:
- 색상 스왑은 A 담당 보드/드라이버 조합에서 **스왑 유무 둘 다** 시험해 검출되는 쪽을 선택하고, 사용한 esp32-camera / 보드 패키지 버전을 기록합니다.
- ESP-NN은 기본 비활성화로 시작하고, 활성화는 크래시 없음이 확인된 보드 패키지 버전에서만 합니다.
- 보드 패키지 버전을 바꾸면 Mock 펌웨어도 다시 컴파일해 확인합니다.

## 4. Gateway Debounce (불연속 검출 대응)

### 4.1 방식

- PLAY / PAUSE 방향별로 **독립된 확정 규칙**(`DebounceRule`)을 둡니다.
- 현재 명령과 반대 값이 나오면 "후보"가 되고, 아래 두 조건을 **모두** 만족하는 detection이 오면 전환합니다.
  - `COUNT`: 후보 값이 연속으로 온 횟수 ≥ `*_CONFIRM_COUNT`
  - `MS`: 현재 명령을 **마지막으로 뒷받침한 detection**부터 지금까지의 시간(Gateway 시계) ≥ `*_CONFIRM_MS`
    (PLAY 중이면 "마지막 얼굴 검출 이후 시간". 시작 직후·fail-safe 직후처럼 그런 detection이 없으면 첫 후보부터)
    → model-benchmark analyzer의 비대칭 hold 시뮬레이션("마지막 검출 후 hold초 경과 시 PAUSE")과 같은 정의라
    Benchmark의 hold 값을 그대로 `PAUSE_CONFIRM_MS`에 넣으면 됩니다.
- 현재 명령과 같은 값이 한 번이라도 오면 후보는 취소됩니다 (hysteresis).
- 평가는 **detection 수신 시점에만** 합니다. 메시지 없이 시간만 흘러 PLAY가 확정되는 일은 없습니다.

| 환경변수 | 기본값 | 의미 |
|----------|--------|------|
| `PLAY_CONFIRM_COUNT` | `1` | PLAY 확정에 필요한 연속 `true` 수 |
| `PLAY_CONFIRM_MS` | `0` | 마지막 `false` 이후 경과해야 PLAY 확정 |
| `PAUSE_CONFIRM_COUNT` | `1` | PAUSE 확정에 필요한 연속 `false` 수 |
| `PAUSE_CONFIRM_MS` | `0` | 마지막 `true`(얼굴 검출) 이후 경과해야 PAUSE 확정 (= Benchmark hold) |

**기본값 = debounce 꺼짐** (detection마다 즉시 전환, 기존 Mock 데모와 동일). 현재 상태는 `GET /api/state`의 `debounce`, `pending_command`, `pending_count`로 확인합니다.

### 4.2 방식 선택 근거

- **시간 기준(`*_CONFIRM_MS`)을 주 기준으로 권장**: 프레임 주기가 환경마다 다릅니다 (Mock 10 s, ESP-NN off 약 2.3 s, ESP-NN on이면 더 빠를 수 있음). "N회"는 주기가 바뀌면 의미가 바뀌지만 "N ms"는 유지됩니다.
- **횟수 기준(`*_CONFIRM_COUNT`)은 보조 하한**: 프레임이 빠를 때 짧은 시간에 몇 프레임만으로 전환되는 것을 막습니다.
- 비대칭 설정이 자연스럽습니다: "잠깐 끊긴 검출"을 무시하려면 PAUSE를 느리게(예: PAUSE에만 시간 기준), PLAY는 빠르게 둡니다.

### 4.3 수치: Benchmark 후보값 (기본값은 아직 꺼짐)

D 담당 Benchmark 결과(`services/model-benchmark/FINDINGS.md`, 50cm·조건당 60초 1회 측정의 **[추정]** 값)의 시연 설정 후보:

| 항목 | 후보 | 설정 위치 |
|------|------|-----------|
| 판정 임계값 t | `0.5` | 기기/브리지 쪽 (`serial_bridge --threshold 0.5`, 향후 펌웨어 `kFaceThreshold`). Gateway는 `raw_face_detected`만 사용 |
| PLAY | 검출 1회면 즉시 | `PLAY_CONFIRM_COUNT=1`, `PLAY_CONFIRM_MS=0` (기본값) |
| PAUSE | 마지막 검출 후 7.5초 | `PAUSE_CONFIRM_MS=7500` |

- Benchmark 추정: 정면 50cm에서 잘못된 PAUSE 0회. 대신 45도 시선 이탈 때도 재생이 유지되는 쪽으로 작용하고, PAUSE 반응이 약 7.5초(+프레임 간격) 늦어집니다.
  → 시연 시나리오는 "자리를 떠났다 돌아오기"가 적합합니다 (FINDINGS.md "시연 권장").
- 측정 표본이 작아(조건당 약 25프레임) **기본값은 꺼짐으로 유지**하고, 시연할 때 `.env`로 켭니다.
- 테스트 코드의 값(예: `PAUSE_CONFIRM_MS=5000`, `COUNT=3`)은 동작 검증용 입력일 뿐 권장값이 아닙니다.
- 활성화 방법: `.env`에 값 설정 → `docker compose up -d control-gateway` (시작 로그에 `PAUSE debounce enabled ...` WARNING 출력).
  일회성: `PAUSE_CONFIRM_MS=7500 docker compose up -d control-gateway`

### 4.4 Fail-safe PAUSE는 debounce와 분리

| 상황 | 동작 |
|------|------|
| `DEVICE_TIMEOUT_MS` 동안 detection 없음 | **즉시** PAUSE (`DEVICE_TIMEOUT`) |
| status `online:false` (LWT 포함) | **즉시** PAUSE (`DEVICE_OFFLINE`) |
| Gateway ↔ Broker 연결 끊김 | **즉시** PAUSE (`BROKER_DISCONNECTED`) |

- 세 경우 모두 debounce 규칙을 거치지 않고, 대기 중이던 후보도 버립니다. 끊기기 전의 detection이 복구 후 PLAY 확정에 쓰이지 않습니다.
- `PAUSE_CONFIRM_MS ≥ DEVICE_TIMEOUT_MS`로 설정하면 Gateway가 시작 시 WARNING을 출력합니다 (그 경우 얼굴 없음 PAUSE보다 timeout PAUSE가 먼저 발생).

## 5. 통합 작업 목록 (A 담당)

### 5.1 Edge Impulse Arduino Library 설치
1. Edge Impulse Studio → Deployment → **Arduino library** → (Quantized int8 권장) Build → ZIP 다운로드
2. Arduino IDE → Sketch → Include Library → **Add .ZIP Library...**
3. ZIP 파일은 `firmware/xiao-esp32s3-sense/models/`에 보관 가능 (git-ignored, 커밋 금지)

### 5.2 Arduino IDE 설정
- Tools → **PSRAM: OPI PSRAM** (카메라 frame buffer 필요)
- Partition Scheme: 모델 크기에 따라 `Huge APP` 등 검토
- ESP-NN: §3 #2 참고 (기본 비활성화로 시작)

### 5.3 카메라 / 전처리
- `esp_camera.h`, XIAO ESP32S3 Sense 핀맵 (`CAMERA_MODEL_XIAO_ESP32S3`, D 담당 bench-sketch README에 Seeed 핀맵과 대조한 표 있음)
- D 담당 환경: `PIXFORMAT_JPEG`, `FRAMESIZE_QVGA` → `fmt2rgb888` → 중앙 crop/resize → 96x96
- 색상 스왑: §3 #1

### 5.4 추론 결과 → `DetectionResult`

```cpp
// FOMO: result.bounding_boxes[] 중 label "face"
float best = 0.0f;                       // 박스가 없으면 0
for (size_t i = 0; i < result.bounding_boxes_count; i++) {
  const auto& bb = result.bounding_boxes[i];
  if (bb.value > 0 && strcmp(bb.label, "face") == 0 && bb.value > best) best = bb.value;
}
DetectionResult r;
r.hasConfidence = true;  r.confidence = best;          // 미검출이어도 항상
r.hasThreshold  = true;  r.threshold  = kFaceThreshold; // 판정에 쓴 값
r.faceDetected  = best >= kFaceThreshold;
r.hasInferenceMs = true; r.inferenceMs = result.timing.dsp + result.timing.classification;
```

- `kFaceThreshold`는 D 담당 Benchmark 결과로 결정 (D 담당 bridge 기본값은 모델 원래 기준 0.6).
- `inference_ms`에 DSP 시간을 포함할지는 D 담당 측정 방식과 맞춥니다 (같은 `model_id`끼리 비교 가능해야 함).
- `bbox`가 필요하면 `DetectionResult`/`MqttPublisher`에 `has*` 플래그 방식으로 추가하고, `faceDetected`일 때만 설정합니다.

### 5.5 Provider 교체

```cpp
// EdgeImpulseDetectionProvider.h — MockDetectionProvider와 같은 public 메서드
class EdgeImpulseDetectionProvider {
 public:
  bool begin();                  // camera init
  DetectionResult detect();      // capture + inference
  const char* source() const { return "edge_impulse"; }
  const char* modelId() const { return "ei-541658-fomo01-int8"; }
};
```

`smart_media.ino`에서 `static EdgeImpulseDetectionProvider detector;`로 교체. `begin()` 실패(카메라 오류) 시 detection을 발행하지 않고 Serial에 오류 출력 → Gateway가 timeout으로 PAUSE.

### 5.6 발행 주기 / Timeout
- 추론이 약 2.3 s/프레임(§3 #3)이면 `PUBLISH_INTERVAL_MS`는 추론 1회마다 발행하는 구조로 바꾸고,
  Gateway `DEVICE_TIMEOUT_MS`는 실제 프레임 주기의 약 2.5–3배로 재설정합니다 (수치는 측정 후 결정).
- 추론(약 2.3 s) 동안 `loop()`가 막히면 MQTT keepalive(15 s)·Wi-Fi 재연결이 늦어집니다. 프레임마다 `publisher.loop()`를 호출하는지 확인합니다.

## 6. 향후 테스트 계획

| 항목 | 방법 |
|------|------|
| 컴파일 / Flash / RAM | arduino-cli compile 출력 (보드 패키지 버전 기록) |
| 추론 latency | `inference_ms` 필드, Serial 로그 |
| Peak RAM | `ESP.getMinFreeHeap()`, `ESP.getFreePsram()` → telemetry |
| 검출 품질 / threshold 스윕 | D 담당 analyzer (`confidence`, `threshold` 사용) |
| Debounce 수치 결정 | Benchmark의 연속 미검출 구간 길이 → `PAUSE_CONFIRM_MS` 등 결정 후 `pytest` + 실기기 재검증 |
| E2E PLAY/PAUSE latency | 사람 동작 시각 → WebSocket `ts_server_ms` → 브라우저 재생 시각 |
| 회귀 | `pytest`, `scripts/integration_test.py` (Gateway 계약 불변 확인) |
