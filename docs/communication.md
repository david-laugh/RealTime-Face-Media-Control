# Communication Contract (v1.0 — Face Presence Demo)

> JSON Schema 원본 (Draft 2020-12): [`contracts/`](../contracts/)
> Gateway 파서와 Schema의 일치 여부는 `services/control-gateway/tests/test_contracts.py`가 자동 검증합니다.

## 0. 이전 Skeleton Contract 대비 변경 사항 (C/D 담당 필독)

| 항목 | 이전 (skeleton) | 현재 (v1.0 demo) |
|------|-----------------|------------------|
| 판단 기준 | 정면/비정면 (`FRONT_PRESENT` / `NOT_PRESENT`) | **얼굴 존재 여부만** |
| MQTT detection `state` | 필수 | **삭제** — 상태 판단은 Gateway가 `raw_face_detected`로 수행 |
| MQTT detection `source` | 없음 | **필수** (`mock` \| `edge_impulse`) |
| MQTT detection `confidence`, `inference_ms` | 필수 | **선택** (실제 모델만, Mock은 보내지 않음) |
| MQTT status | `status: ONLINE/OFFLINE` | **`online: true/false`** + `source` |
| WebSocket endpoint | `/ws` | **`/ws/media`** |
| WebSocket `reason` | `FRONT_FACE_PRESENT`, `FACE_ABSENT`, `DEVICE_TIMEOUT`, `UNKNOWN` | **`FACE_PRESENT`, `FACE_ABSENT`, `DEVICE_TIMEOUT`, `DEVICE_OFFLINE`, `BROKER_DISCONNECTED`, `SYSTEM_STARTUP`** |
| WebSocket 추가 필드 | – | `schema_version`, `face_detected`(bool\|null), `source` |
| WebSocket `confidence` | 선택 | **삭제** |
| telemetry schema | – | 변경 없음 (D 담당, 향후 확장용) |

## 1. MQTT

### 1.1 Broker 접속 정보

| Client | 주소 |
|--------|------|
| XIAO ESP32S3 Sense | `<Docker Host PC LAN IP>:1883` |
| control-gateway / model-benchmark (Docker 내부) | `mqtt-broker:1883` |
| Host PC 도구 (scripts, mosquitto_sub) | `localhost:1883` |

- 인증: 없음 (`allow_anonymous true`, **로컬 데모 전용**)
- MQTT over WebSocket(9001): 비활성 (예약)

### 1.2 Topic

| Topic | Publisher | Subscriber | QoS | Retain | Schema |
|-------|-----------|------------|-----|--------|--------|
| `smart-media/{device_id}/detection` | XIAO | control-gateway, (benchmark) | 0 | **false** | [`detection.schema.json`](../contracts/mqtt/detection.schema.json) |
| `smart-media/{device_id}/status` | XIAO (+ broker LWT) | control-gateway | 1 (LWT) | **true** | [`status.schema.json`](../contracts/mqtt/status.schema.json) |
| `smart-media/{device_id}/telemetry` | (향후) XIAO | (향후) model-benchmark | 0 | false | [`telemetry.schema.json`](../contracts/mqtt/telemetry.schema.json) |

Gateway 구독: `smart-media/+/detection`, `smart-media/+/status` (`+` = device_id). 현재 장치: `xiao-01`.

### 1.3 detection

| Field | Type | Required | 설명 |
|-------|------|----------|------|
| `schema_version` | string `"1.0"` | ✅ | |
| `device_id` | string | ✅ | topic의 `{device_id}`와 같아야 함 |
| `seq` | integer ≥ 0 | ✅ | 발행마다 +1, 재부팅 시 리셋 |
| `uptime_ms` | integer ≥ 0 | ✅ | 디바이스 `millis()` |
| `source` | `"mock"` \| `"edge_impulse"` | ✅ | |
| `model_id` | string | ✅ | Mock: `"mock-v1"` |
| `raw_face_detected` | boolean | ✅ | 얼굴 존재 여부 |
| `confidence` | number 0–1 | – | 실제 모델만 |
| `inference_ms` | integer ≥ 0 | – | 실제 모델만 |
| `bbox` | `{x,y,w,h}` 0–1 | – | 실제 모델만 |

```json
{"schema_version":"1.0","device_id":"xiao-01","seq":1,"uptime_ms":10000,"source":"mock","model_id":"mock-v1","raw_face_detected":true}
```

### 1.4 status

| Field | Type | Required |
|-------|------|----------|
| `schema_version` | string `"1.0"` | ✅ |
| `device_id` | string | ✅ |
| `source` | `"mock"` \| `"edge_impulse"` | ✅ |
| `online` | boolean | ✅ |

```json
{"schema_version":"1.0","device_id":"xiao-01","source":"mock","online":true}
```

- 연결 직후 `online:true`를 retain publish, Last Will로 `online:false`(retain, QoS 1) 등록.
- **`online:true`만으로는 PLAY하지 않습니다.** 실제 detection이 필요합니다.
- 빈 payload(retained 메시지 삭제)는 Gateway가 무시합니다.

## 2. WebSocket (Gateway → Browser)

| 항목 | 값 |
|------|----|
| Endpoint | `ws://<host>:8000/ws/media` |
| 방향 | Gateway → Browser push (client가 보내는 텍스트는 무시) |
| 연결 직후 | 장치별 **현재 상태**를 1회 전송 (재접속 동기화) |
| 이후 | **상태가 바뀔 때만** 전송 (중복 PLAY/PAUSE 없음) |
| Schema | [`media-control.schema.json`](../contracts/websocket/media-control.schema.json) |

| Field | Type | 설명 |
|-------|------|------|
| `schema_version` | `"1.0"` | |
| `type` | `"media_control"` | |
| `device_id` | string | 여러 장치 대비. 현재 `xiao-01` |
| `command` | `"PLAY"` \| `"PAUSE"` | |
| `reason` | enum (아래) | |
| `face_detected` | boolean \| null | 알 수 없으면 null |
| `source` | `"mock"` \| `"edge_impulse"` \| `"system"` | system = Gateway fail-safe |
| `ts_server_ms` | integer | Gateway Unix epoch ms (실제 시각) |

| reason | command | source | 발생 조건 |
|--------|---------|--------|-----------|
| `SYSTEM_STARTUP` | PAUSE | system | Gateway 시작 후 detection 전 (연결 직후 snapshot으로만 전달) |
| `FACE_PRESENT` | PLAY | mock/edge_impulse | `raw_face_detected=true` & 이전 PAUSE |
| `FACE_ABSENT` | PAUSE | mock/edge_impulse | `raw_face_detected=false` & 이전 PLAY |
| `DEVICE_TIMEOUT` | PAUSE | system | 마지막 유효 detection 이후 `DEVICE_TIMEOUT_MS` 경과 |
| `DEVICE_OFFLINE` | PAUSE | system | status `online:false` (LWT 포함) |
| `BROKER_DISCONNECTED` | PAUSE | system | Gateway ↔ Broker 연결 끊김 |

```json
{"schema_version":"1.0","type":"media_control","device_id":"xiao-01","command":"PLAY","reason":"FACE_PRESENT","face_detected":true,"source":"mock","ts_server_ms":1793320123456}
{"schema_version":"1.0","type":"media_control","device_id":"xiao-01","command":"PAUSE","reason":"FACE_ABSENT","face_detected":false,"source":"mock","ts_server_ms":1793320133456}
{"schema_version":"1.0","type":"media_control","device_id":"xiao-01","command":"PAUSE","reason":"DEVICE_TIMEOUT","face_detected":null,"source":"system","ts_server_ms":1793320163456}
```

## 3. 상태 변경 규칙

| 이전 상태 | 입력 | 출력 |
|-----------|------|------|
| PAUSE | detection `true` | PLAY / FACE_PRESENT |
| PLAY | detection `false` | PAUSE / FACE_ABSENT |
| PLAY | detection `true` | 없음 |
| PAUSE | detection `false` | 없음 |
| PLAY | timeout / offline / broker 끊김 | PAUSE / 해당 reason |
| PAUSE | timeout / offline / broker 끊김 | 없음 (상태 정보만 갱신) |

- Gateway 시작 시 기본 상태 PAUSE.
- 장치별 독립 상태 (`device_id` 기준).
- 잘못된 JSON / 필수 필드 누락 / 타입 불일치 / topic과 device_id 불일치 → ERROR 로그 후 무시, 상태 변화 없음.
- retain 플래그가 붙은 detection은 오래된 메시지로 간주해 무시.

## 4. Timeout 정책

| 값 | 설정 |
|----|------|
| Firmware 발행 주기 | `PUBLISH_INTERVAL_MS = 10000` |
| Gateway timeout | `DEVICE_TIMEOUT_MS = 25000` (환경변수) — 발행 주기의 2.5배, 1회 유실까지 허용 |
| 검사 주기 | 1초 |

Timeout 후 새 `true` detection이 오면 다시 PLAY합니다.

## 5. 담당자별 요약

**C (Web UI)**: `ws://<host>:8000/ws/media`에 연결 → 수신한 `command`대로 `player.playVideo()` / `pauseVideo()`. 연결 직후 오는 첫 메시지가 현재 상태입니다. 끊기면 재연결하세요 (재연결 시 상태 자동 동기화). `reason`, `face_detected`, `source`는 상태 UI 표시에 사용할 수 있습니다. 장치가 여러 대일 경우 `device_id`로 필터링하세요.

**D (Benchmark)**: Docker 내부에서 `mqtt-broker:1883`, `smart-media/+/detection` 구독. 실제 모델 결과는 `source:"edge_impulse"`, 그리고 선택 필드 `confidence`, `inference_ms`, `bbox`를 사용합니다. telemetry topic/schema는 그대로 예약되어 있습니다.
