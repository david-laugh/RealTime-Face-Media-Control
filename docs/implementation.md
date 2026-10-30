# Implementation (A/B Mock Demo)

작성일: 2026-10-30

## 1. 이번에 구현한 기능

| Part | 기능 | 상태 |
|------|------|------|
| A | Mock Detection Firmware (10초 true/false 교차, `millis()` 비차단) | 구현, arduino-cli 컴파일 성공, **실기기 미검증** |
| A | Wi-Fi / MQTT 비차단 자동 재연결 | 구현, **실기기 미검증** |
| A | MQTT status online(retain) + Last Will offline | 구현, LWT 동작은 PC 클라이언트로 동일 방식 검증 |
| B | Mosquitto Broker (Docker, 1883) | 구현, 검증 |
| B | Control Gateway (FastAPI, MQTT 구독, 상태 관리, timeout, WebSocket, health) | 구현, 검증 |
| 공통 | MQTT / WebSocket JSON Schema (Draft 2020-12) | 갱신, 자동 검증 |
| 테스트 | 단위/앱/계약 테스트 96개, E2E 스크립트, 브라우저 E2E(web-ui), PC Mock Publisher | 구현, 실행 |
| B | web-ui(C) 연동: `/ws` 경로, web-ui reason enum, `detail`/`confidence` 필드 | 구현, 실제 브라우저 검증 |
| 공통 | Detection 계약: `edge_impulse`의 `confidence` 필수(0 허용), `threshold` 추가, `bbox`는 검출 시에만 | 구현, 계약/단위 테스트 (D 담당 피드백) |
| A | `DetectionResult.threshold`, Publisher 계약 위반 차단 | 구현, 컴파일 성공 (esp32 2.0.17) |
| B | 방향별 PLAY/PAUSE debounce 구조 (기본 꺼짐), fail-safe는 debounce 미적용 | 구현, 단위/앱 테스트 + Docker 실측 |

## 2. Arduino Firmware

경로: `firmware/xiao-esp32s3-sense/smart_media/`

| File | 내용 |
|------|------|
| `smart_media.ino` | `setup()`: Serial, Wi-Fi 시작, Publisher 초기화. `loop()`: Wi-Fi 유지 → `publisher.loop()` → (재)연결 직후 또는 10초 경과 시 detection 발행 |
| `config.example.h` | Wi-Fi, `MQTT_HOST`(PC LAN IP), `MQTT_PORT`, `DEVICE_ID`, `PUBLISH_INTERVAL_MS` 템플릿. `config.h`는 `.gitignore` |
| `DetectionResult.h` | `faceDetected` + 선택 필드(`hasConfidence/confidence`, `hasThreshold/threshold`, `hasInferenceMs/inferenceMs`). Provider별 계약을 주석으로 명시 |
| `MockDetectionProvider.*` | `detect()` 호출마다 true→false→true… 반환. `source()="mock"`, `modelId()="mock-v1"` |
| `MqttPublisher.*` | PubSubClient 래퍼. LWT 등록, 연결 직후 status online publish, detection JSON 생성/발행. Provider 타입에 의존하지 않음. 계약 위반(Mock이 모델 필드 보유 / 실제 모델이 confidence 없음)이면 발행하지 않고 Serial에 출력 |

핵심 설계:

- **비차단**: `delay(10000)` 없음. `millis() - lastPublishMs >= PUBLISH_INTERVAL_MS` (uint32 overflow-safe 비교).
- **재연결**: Wi-Fi는 10초마다 `WiFi.begin()`만 호출하고 기다리지 않음. MQTT는 5초마다 1회 시도, `setSocketTimeout(3)`으로 시도당 blocking 상한 3초.
- **첫 발행**: `consumeConnectedEvent()`로 MQTT (재)연결 직후 즉시 1회 발행.
- **가짜 값 금지**: Mock은 confidence/threshold/inference_ms를 만들지 않음 (`has*` 플래그 false → payload에 필드 없음 → Gateway/WebSocket에서 `confidence:null`).
- **confidence 0 보존**: 실제 모델 Provider는 `hasConfidence=true`, 점수가 없으면 `confidence=0` → payload `"confidence":0.000` (생략/`null` 아님).
- **Stale 방지**: detection은 retain=false, QoS 0.

빌드 결과 (XIAO_ESP32S3, `--warnings all`, 경고 0):

| 날짜 | esp32 core | Flash | RAM | 비고 |
|------|-----------|-------|-----|------|
| 2026-10-30 1차 | 3.3.12 | 859,304 B (25%) | 46,336 B (14%) | Mock 최초 구현 |
| 2026-10-30 2차 | 2.0.17 | 674,081 B (20%) | 44,328 B (13%) | threshold 필드 추가 후. 로컬에 설치된 core가 2.0.17로 바뀌어 있어 그 버전으로 확인 (3.3.12 재컴파일은 미실행) |

## 3. MQTT Broker

- Image: `eclipse-mosquitto:2` (검증 시 실제 버전 2.1.2)
- `services/mqtt-broker/config/mosquitto.conf`: `listener 1883`, `allow_anonymous true`, persistence `/mosquitto/data/`, `log_dest stdout`, connection 로그
- Compose healthcheck: `mosquitto_sub -t '$SYS/broker/uptime' -C 1 -W 3`
- 보안 개선 방향: `services/mqtt-broker/README.md`

## 4. Control Gateway

```
paho thread                     asyncio event loop
───────────                     ───────────────────────────────────────────
on_connect     ─┐               consume_events():  queue.get()
on_disconnect  ─┼─call_soon_──▶   ├─ split_topic / parse_detection / parse_status
on_message     ─┘ threadsafe      ├─ StateManager.handle_*()  → Optional[msg]
                  (asyncio.Queue) └─ ConnectionManager.broadcast(msg)
                                watch_timeouts(): 1 s 마다 StateManager.check_timeouts()
                                FastAPI: /health, /api/state, WS /ws (+ /ws/media)
```

- paho 콜백은 이벤트만 큐에 넣고, 상태 변경과 WebSocket 전송은 모두 이벤트 루프 한 곳에서 수행 → lock 없이 상태 일관성 유지.
- `ConnectionManager`는 asyncio Lock으로 "새 client 등록 + snapshot 전송"과 broadcast를 직렬화 → 새 client가 snapshot보다 broadcast를 먼저 받는 일이 없음. 전송 실패/2초 timeout client는 제거.
- 잘못된 메시지는 `MessageError`로 처리, 예상치 못한 예외도 consumer loop에서 잡아 서비스 유지.
- paho `reconnect_delay_set(1, 10)` + `loop_start()`로 자동 재연결, 재연결 시 재구독 (`on_connect`).
- **Debounce** (`state_manager.DebounceRule`): PLAY/PAUSE 방향별 `min_count`(연속 detection 수)와 `min_ms`(현재 명령을 마지막으로 뒷받침한 detection 이후 시간 = Benchmark hold 정의). 둘 다 만족하는 detection 수신 시 전환, 현재 명령과 같은 값이 오면 후보 취소. 기본 `1/0` = 꺼짐(즉시 전환).
  Fail-safe(timeout/offline/broker 끊김)는 `_transition()`을 직접 호출해 debounce를 거치지 않고 후보도 버림. 수치는 Benchmark 후 결정 (`docs/model-integration-guide.md` §4).
- `messages.parse_detection`: `edge_impulse`는 숫자 `confidence` 필수(0 허용), Mock은 `confidence` 숫자 금지, `threshold`는 선택 0–1.

환경변수: `services/control-gateway/README.md` 참고 (`DEVICE_TIMEOUT_MS=25000`, debounce `PLAY_/PAUSE_CONFIRM_COUNT=1`, `PLAY_/PAUSE_CONFIRM_MS=0` 기본).

## 5. 실행 방법

```bash
cp .env.example .env        # 선택
docker compose up -d --build mqtt-broker control-gateway
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/api/state

# ESP32 없이 Gateway 확인
pip install paho-mqtt==2.1.0
python scripts/mock_publisher.py --host localhost --device-id xiao-01
```

## 6. Arduino IDE 설정 및 업로드

`firmware/xiao-esp32s3-sense/README.md` 참고. 요약:

1. Boards Manager: `esp32 by Espressif Systems` (3.3.12 검증)
2. Library Manager: `PubSubClient` (2.8.0 검증)
3. Board: `XIAO_ESP32S3`
4. `config.example.h` → `config.h` 복사, Wi-Fi와 **PC LAN IP** 입력
5. Upload → Serial Monitor 115200

## 7. 아직 구현하지 않은 기능

- 카메라 초기화, Edge Impulse 추론 (→ `docs/model-integration-guide.md`)
- 정면/측면/후면 구분
- Debounce 수치 확정 및 활성화 (구조만 구현, Benchmark 결과 대기)
- telemetry 발행
- MQTT 인증/TLS
- Web UI (C 담당), Benchmark (D 담당)
