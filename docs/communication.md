# Communication Contract (v1.0 — Face Presence Demo)

> JSON Schema 원본 (Draft 2020-12): [`contracts/`](../contracts/)
> Gateway 파서와 Schema의 일치 여부는 `services/control-gateway/tests/test_contracts.py`가 자동 검증합니다.

## 0. 이전 Skeleton Contract 대비 변경 사항 (C/D 담당 필독)

| 항목 | 이전 (skeleton) | 현재 (v1.0 demo) |
|------|-----------------|------------------|
| 판단 기준 | 정면/비정면 (`FRONT_PRESENT` / `NOT_PRESENT`) | **얼굴 존재 여부만** |
| MQTT detection `state` | 필수 | **삭제** — 상태 판단은 Gateway가 `raw_face_detected`로 수행 |
| MQTT detection `source` | 없음 | **필수** (`mock` \| `edge_impulse`) |
| MQTT detection `confidence` | 필수 | **`edge_impulse`는 필수(숫자, 미검출이어도 최고 점수, 없으면 `0`)**, Mock은 생략 또는 `null` |
| MQTT detection `threshold` | 없음 | **추가 (선택)**: 기기가 판정에 쓴 임계값, `confidence`와 같은 0–1 척도 |
| MQTT detection `inference_ms`, `bbox` | 필수/– | **선택** (실제 모델만). `bbox`는 `raw_face_detected:true`일 때만 |
| MQTT status | `status: ONLINE/OFFLINE` | **`online: true/false`** + `source` |
| WebSocket endpoint | `/ws` | **`/ws` 유지** (web-ui 기본값) + 별칭 `/ws/media` |
| WebSocket `reason` | `FRONT_FACE_PRESENT`, `FACE_ABSENT`, `DEVICE_TIMEOUT`, `UNKNOWN` | **유지** (web-ui 4개 값). `FRONT_FACE_PRESENT` = 이번 버전에서는 "얼굴 있음" |
| WebSocket `detail` | – | **추가**: Gateway 세부 원인 6종 (`FACE_PRESENT`, `FACE_ABSENT`, `DEVICE_TIMEOUT`, `DEVICE_OFFLINE`, `BROKER_DISCONNECTED`, `SYSTEM_STARTUP`) |
| WebSocket 추가 필드 | – | `schema_version`, `face_detected`(bool\|null), `source` |
| WebSocket `confidence` | 선택 | **항상 포함, number\|null** (Mock은 null, `0`은 `0` 그대로) |
| Gateway PLAY/PAUSE 전환 | 즉시 | 방향별 debounce 설정 추가 (**기본 꺼짐** = 즉시, §3.1) |
| telemetry schema | – | 변경 없음 (D 담당, 향후 확장용) |

> web-ui(C, PR #1)가 skeleton 규약(`/ws`, reason 4종, `confidence`)으로 구현되어 있어 Gateway 출력을 그에 맞췄습니다.
> web-ui는 모르는 필드(`detail`, `face_detected`, `source`, `schema_version`)를 무시하므로 web-ui 수정은 필요 없습니다.
> `confidence`/`threshold` 규칙은 D 담당(Benchmark) 피드백으로 2026-10-30 추가되었습니다.

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
| `raw_face_detected` | boolean | ✅ | 기기가 판정한 얼굴 존재 여부. **PLAY/PAUSE는 이 값만 사용** |
| `confidence` | number 0–1 | `edge_impulse`: ✅ / `mock`: 생략 또는 `null` | 프레임의 얼굴 점수 최고값. 미검출·threshold 미만이어도 전송, 유효 점수가 없으면 `0` |
| `threshold` | number 0–1 | – | 판정에 쓴 임계값 (`confidence`와 같은 척도). Mock은 보내지 않음 |
| `inference_ms` | integer ≥ 0 | – | 실제 모델만 (측정값) |
| `bbox` | `{x,y,w,h}` 0–1 | – | 실제 모델만, `raw_face_detected:true`일 때만 |

- `threshold`를 보낼 때는 `raw_face_detected == (confidence >= threshold)`가 성립해야 합니다.
- 제거된 `state` 필드는 다시 쓰지 않습니다 (`additionalProperties:false`).
- Schema가 강제하는 조건: `edge_impulse` → `confidence` 숫자 필수 / `mock` → `confidence`는 `null`만, `threshold`·`inference_ms`·`bbox` 금지 / `raw_face_detected:false` → `bbox` 금지.
- Gateway도 `edge_impulse`의 `confidence` 누락·`null`, Mock의 숫자 `confidence`를 잘못된 메시지로 무시합니다.

```json
{"schema_version":"1.0","device_id":"xiao-01","seq":1,"uptime_ms":10000,"source":"mock","model_id":"mock-v1","raw_face_detected":true}
{"schema_version":"1.0","device_id":"xiao-01","seq":4,"uptime_ms":25400,"source":"edge_impulse","model_id":"ei-541658-fomo01-int8","raw_face_detected":false,"confidence":0.35,"threshold":0.6,"inference_ms":2300}
{"schema_version":"1.0","device_id":"xiao-01","seq":5,"uptime_ms":27700,"source":"edge_impulse","model_id":"ei-541658-fomo01-int8","raw_face_detected":false,"confidence":0}
```

상세 규칙과 실기기 관찰 사항: [`model-integration-guide.md`](model-integration-guide.md) §2–3

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
| Endpoint | `ws://<host>:8000/ws` (web-ui 기본값) — 별칭 `ws://<host>:8000/ws/media` |
| 방향 | Gateway → Browser push (client가 보내는 텍스트는 무시) |
| 연결 직후 | 장치별 **현재 상태**를 1회 전송 (재접속 동기화) |
| 이후 | **상태가 바뀔 때만** 전송 (중복 PLAY/PAUSE 없음) |
| Schema | [`media-control.schema.json`](../contracts/websocket/media-control.schema.json) |

| Field | Type | 설명 |
|-------|------|------|
| `schema_version` | `"1.0"` | |
| `type` | `"media_control"` | |
| `device_id` | string | 현재 `xiao-01` |
| `command` | `"PLAY"` \| `"PAUSE"` | web-ui가 그대로 실행 |
| `reason` | `FRONT_FACE_PRESENT` \| `FACE_ABSENT` \| `DEVICE_TIMEOUT` \| `UNKNOWN` | web-ui 화면 문구 결정 |
| `detail` | enum (아래) | Gateway 세부 원인 (로그/디버깅용) |
| `face_detected` | boolean \| null | 알 수 없으면 null |
| `confidence` | number 0–1 \| null | 실제 모델 신뢰도. Mock/시스템 이벤트는 null (web-ui "신뢰도" 칸 `-`) |
| `source` | `"mock"` \| `"edge_impulse"` \| `"system"` | system = Gateway fail-safe |
| `ts_server_ms` | integer | Gateway Unix epoch ms (web-ui "전달 Nms" 계산에 사용) |

| detail | reason | command | source | web-ui 표시 | 발생 조건 |
|--------|--------|---------|--------|-------------|-----------|
| `SYSTEM_STARTUP` | `UNKNOWN` | PAUSE | system | 판단 불가 | Gateway 시작 후 detection 전 (연결 직후 snapshot) |
| `FACE_PRESENT` | `FRONT_FACE_PRESENT` | PLAY | mock/edge_impulse | 보고 있어요 | `raw_face_detected=true` & 이전 PAUSE |
| `FACE_ABSENT` | `FACE_ABSENT` | PAUSE | mock/edge_impulse | 자리 비움 | `raw_face_detected=false` & 이전 PLAY |
| `DEVICE_TIMEOUT` | `DEVICE_TIMEOUT` | PAUSE | system | 카메라 끊김 | 마지막 detection 이후 `DEVICE_TIMEOUT_MS` 경과 |
| `DEVICE_OFFLINE` | `DEVICE_TIMEOUT` | PAUSE | system | 카메라 끊김 | status `online:false` (LWT 포함) |
| `BROKER_DISCONNECTED` | `UNKNOWN` | PAUSE | system | 판단 불가 | Gateway ↔ Broker 연결 끊김 |

```json
{"schema_version":"1.0","type":"media_control","device_id":"xiao-01","command":"PLAY","reason":"FRONT_FACE_PRESENT","detail":"FACE_PRESENT","face_detected":true,"confidence":null,"source":"mock","ts_server_ms":1793320123456}
{"schema_version":"1.0","type":"media_control","device_id":"xiao-01","command":"PAUSE","reason":"FACE_ABSENT","detail":"FACE_ABSENT","face_detected":false,"confidence":null,"source":"mock","ts_server_ms":1793320133456}
{"schema_version":"1.0","type":"media_control","device_id":"xiao-01","command":"PAUSE","reason":"DEVICE_TIMEOUT","detail":"DEVICE_TIMEOUT","face_detected":null,"confidence":null,"source":"system","ts_server_ms":1793320163456}
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
- 위 표는 debounce가 꺼진 기본 설정입니다.

### 3.1 Debounce (선택, 기본 꺼짐)

| 환경변수 | 기본값 | 의미 |
|----------|--------|------|
| `PLAY_CONFIRM_COUNT` / `PLAY_CONFIRM_MS` | `1` / `0` | PAUSE→PLAY: 연속 `true` 횟수 **그리고** 첫 `true`부터의 시간 |
| `PAUSE_CONFIRM_COUNT` / `PAUSE_CONFIRM_MS` | `1` / `0` | PLAY→PAUSE: 연속 `false` 횟수 **그리고** 첫 `false`부터의 시간 |

- 조건이 충족된 detection을 받는 순간 전환합니다. 현재 명령과 같은 값이 오면 후보는 취소됩니다.
- **timeout / offline / broker 끊김 PAUSE는 debounce 없이 즉시** 발생하고 대기 중인 후보를 버립니다.
- 수치는 Benchmark 측정 후 결정합니다. 그 전까지 기본값(꺼짐)을 유지합니다. 상세: [`model-integration-guide.md`](model-integration-guide.md) §4

## 4. Timeout 정책

| 값 | 설정 |
|----|------|
| Firmware 발행 주기 | `PUBLISH_INTERVAL_MS = 10000` |
| Gateway timeout | `DEVICE_TIMEOUT_MS = 25000` (환경변수) — 발행 주기의 2.5배, 1회 유실까지 허용 |
| 검사 주기 | 1초 |

Timeout 후 새 `true` detection이 오면 다시 PLAY합니다.

## 5. 담당자별 요약

**C (Web UI)**: 현재 web-ui(`ws://<host>:8000/ws`, reason 4종, `confidence`)를 **수정 없이** 사용하도록 Gateway를 맞췄습니다 (실제 브라우저 테스트 W1–W8 PASS, `docs/demo-test.md`). 선택 개선 제안:
- `detail`로 "카메라 끊김"(DEVICE_TIMEOUT / DEVICE_OFFLINE), "판단 불가"(SYSTEM_STARTUP / BROKER_DISCONNECTED)를 더 구체적으로 표시 가능
- web-ui가 `device_id`를 필터링하지 않아, 다른 장치(예: 테스트용 `it-xiao-01`) 메시지에도 화면이 반응함 → `?device=xiao-01` 같은 필터 권장

**D (Benchmark)**: Docker 내부에서 `mqtt-broker:1883`, `smart-media/+/detection` 구독. 실제 모델 결과는 `source:"edge_impulse"`, **필수** `confidence`(미검출 시에도 최고 점수, 없으면 0), 선택 `threshold`, `inference_ms`, `bbox`를 사용합니다. telemetry topic/schema는 그대로 예약되어 있습니다.
- `contracts/mqtt/detection.schema.json`이 바뀌었으므로 `services/model-benchmark/schemas/detection.schema.json` 사본을 다시 복사해야 `test_schemas_sync.py`가 통과합니다.
