# control-gateway

Owner: Member B (Backend / IoT) — Python 3.12 · FastAPI · Uvicorn · paho-mqtt 2.1

MQTT Detection/Status를 구독해 장치별 상태를 관리하고, 변경 시 WebSocket으로 PLAY/PAUSE를 Browser에 push합니다.

```
mqtt-broker ──smart-media/+/detection, +/status──▶ control-gateway ──ws /ws──▶ web-ui
```

## Endpoint

| Method | Path | 설명 |
|--------|------|------|
| WS | `/ws` (web-ui 기본값), `/ws/media` (별칭) | `media_control` push. 연결 직후 장치별 현재 상태 1회 전송. `reason` = web-ui enum, `detail` = 세부 원인 |
| GET | `/health` | Gateway 상태, `mqtt_connected`, WebSocket client 수, invalid message 수 |
| GET | `/api/state` | 장치별 command / reason / face_detected / 마지막 detection 경과시간 |

## 모듈

| File | 역할 |
|------|------|
| `src/main.py` | FastAPI app, lifespan, 이벤트 consumer task, timeout watcher task, endpoints |
| `src/mqtt_client.py` | paho-mqtt wrapper. 콜백(별도 thread)은 `call_soon_threadsafe`로 asyncio Queue에 이벤트만 넣음 |
| `src/messages.py` | MQTT payload 파싱/검증 (`contracts/mqtt/*.schema.json`과 동일 규칙) |
| `src/state_manager.py` | 장치별 상태 머신 (PLAY/PAUSE, timeout, offline, broker disconnect) |
| `src/websocket_manager.py` | WebSocket client 집합, broadcast, 끊긴 client 제거 |
| `src/config.py` | 환경변수 설정 |

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MQTT_HOST` | `mqtt-broker` | Compose에서는 고정 |
| `MQTT_PORT` | `1883` | |
| `MQTT_CLIENT_ID` | `control-gateway` | |
| `MQTT_TOPIC_PREFIX` | `smart-media` | |
| `DEFAULT_DEVICE_ID` | `xiao-01` | 시작 시 PAUSE/SYSTEM_STARTUP 상태로 생성 |
| `DEVICE_TIMEOUT_MS` | `25000` | 마지막 detection 이후 이 시간 경과 시 PAUSE |
| `TIMEOUT_CHECK_INTERVAL_MS` | `1000` | timeout 검사 주기 |
| `PLAY_CONFIRM_COUNT` | `1` | PAUSE→PLAY 확정에 필요한 연속 `true` 수 (1 = 즉시) |
| `PLAY_CONFIRM_MS` | `0` | PAUSE→PLAY: 마지막 `false` 이후 경과 시간 |
| `PAUSE_CONFIRM_COUNT` | `1` | PLAY→PAUSE 확정에 필요한 연속 `false` 수 (1 = 즉시) |
| `PAUSE_CONFIRM_MS` | `0` | PLAY→PAUSE: 마지막 `true` 이후 경과 시간 (Benchmark hold와 같은 정의, 후보값 7500) |

Debounce 4개 값은 기본이 "꺼짐"이며, 최종 수치는 Benchmark 측정 후 정합니다. timeout / offline / broker 끊김 PAUSE에는 적용되지 않습니다 (`docs/model-integration-guide.md` §4).
| `LOG_LEVEL` | `INFO` | |

## 실행

```bash
docker compose up -d --build mqtt-broker control-gateway
curl localhost:8000/health
```

## 테스트

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q                                          # unit + app + contract tests (broker 불필요)
python ../../scripts/integration_test.py --broker-restart   # Docker 실행 중일 때 E2E
python ../../scripts/webui_e2e_test.py                      # 실제 web-ui 페이지 + YouTube (headless Chrome)
python ../../scripts/pipeline_e2e_test.py                   # benchmark mock / serial replay → gateway (profile benchmark)
```

결과: [`docs/demo-test.md`](../../docs/demo-test.md)
