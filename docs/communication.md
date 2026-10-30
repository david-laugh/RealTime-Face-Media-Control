# Communication Contract

> ⚠️ 통신 규약 템플릿입니다. Publisher / Subscriber / WebSocket Server는 아직 구현되지 않았습니다.
> JSON Schema 원본: [`contracts/`](../contracts/)

## 1. MQTT

### 1.1 Broker

| 항목 | 값 |
|------|----|
| Broker | Eclipse Mosquitto (`mqtt-broker`) |
| Port | `1883` (MQTT/TCP) |
| Reserved | `9001` (MQTT over WebSocket, 기본 비활성화) |
| Docker 내부 Host | `mqtt-broker` |

### 1.2 Topic 구조

| Topic | Publisher | Subscriber | QoS (안) | Retain (안) | Schema |
|-------|-----------|------------|----------|-------------|--------|
| `smart-media/{device_id}/detection` | XIAO ESP32S3 Sense | control-gateway | 0 | false | [`detection.schema.json`](../contracts/mqtt/detection.schema.json) |
| `smart-media/{device_id}/status` | XIAO ESP32S3 Sense (+ LWT) | control-gateway | 1 | true | [`status.schema.json`](../contracts/mqtt/status.schema.json) |
| `smart-media/{device_id}/telemetry` | XIAO ESP32S3 Sense | model-benchmark, control-gateway | 0 | false | [`telemetry.schema.json`](../contracts/mqtt/telemetry.schema.json) |

- `{device_id}` 예: `xiao-01`
- Wildcard 구독 예: `smart-media/+/detection`
- QoS / Retain 값은 초안이며 구현 시 확정합니다.

### 1.3 detection 메시지

```json
{
  "schema_version": "1.0",
  "device_id": "xiao-01",
  "seq": 152,
  "uptime_ms": 124552,
  "model_id": "ei-541658-fomo01-int8",
  "raw_face_detected": true,
  "confidence": 0.84,
  "bbox": {
    "x": 0.32,
    "y": 0.18,
    "w": 0.35,
    "h": 0.51
  },
  "inference_ms": 731,
  "state": "FRONT_PRESENT"
}
```

| Field | Type | Required | 설명 |
|-------|------|----------|------|
| `schema_version` | string | ✅ | `"1.0"` |
| `device_id` | string | ✅ | Topic의 `{device_id}`와 동일 |
| `seq` | integer | ✅ | 메시지 순번 |
| `uptime_ms` | integer | ✅ | 디바이스 부팅 후 경과 시간 |
| `model_id` | string | ✅ | Edge Impulse 모델 식별자 |
| `raw_face_detected` | boolean | ✅ | 필터링 전 모델 원시 검출 결과 |
| `confidence` | number (0–1) | ✅ | 검출 신뢰도 |
| `bbox` | object \| null | – | 정규화 좌표 (0–1), 미검출 시 `null` |
| `inference_ms` | integer | ✅ | 온디바이스 추론 시간 |
| `state` | enum | ✅ | 아래 State Enum 참고 |

### 1.4 State Enum

| 값 | 의미 |
|----|------|
| `FRONT_PRESENT` | 사용자가 화면을 정면으로 보고 있음 |
| `NOT_PRESENT` | 얼굴 미검출 또는 측면/뒤쪽을 바라봄 |
| `UNKNOWN` | 판단 불가 (초기화 중, 오류 등) |

> 실제 판단 알고리즘(threshold, debounce 등)은 아직 정의/구현되지 않았습니다.

### 1.5 status / telemetry 메시지

- **status**: `ONLINE` / `OFFLINE`. 연결 시 `ONLINE`을 retain publish하고, MQTT Last Will로 `OFFLINE`을 등록하는 것을 권장합니다.
- **telemetry**: capture / preprocess / inference 시간, FPS, heap/PSRAM, RSSI 등 성능 지표. Model Benchmark가 사용합니다.

세부 필드는 각 JSON Schema를 참고합니다.

## 2. WebSocket (Control Gateway → Browser)

| 항목 | 값 |
|------|----|
| Server | control-gateway |
| Endpoint (안) | `ws://<host>:8000/ws` |
| Direction | Gateway → Browser (단방향 push) |
| Schema | [`media-control.schema.json`](../contracts/websocket/media-control.schema.json) |

```json
{
  "type": "media_control",
  "device_id": "xiao-01",
  "command": "PLAY",
  "reason": "FRONT_FACE_PRESENT",
  "confidence": 0.84,
  "ts_server_ms": 1793320123456
}
```

### command

| 값 | 동작 |
|----|------|
| `PLAY` | YouTube 영상 재생 |
| `PAUSE` | YouTube 영상 일시정지 |

### reason

| 값 | 의미 |
|----|------|
| `FRONT_FACE_PRESENT` | 정면 얼굴 검출 |
| `FACE_ABSENT` | 얼굴 미검출 / 측면 / 뒤쪽 |
| `DEVICE_TIMEOUT` | 디바이스로부터 일정 시간 메시지 없음 |
| `UNKNOWN` | 기타 / 판단 불가 |

## 3. Versioning

- 모든 MQTT 메시지는 `schema_version`을 포함합니다.
- 하위 호환이 깨지는 변경 시 major version을 올리고 `contracts/`와 본 문서를 함께 갱신합니다.
