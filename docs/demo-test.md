# Demo Test Report (A/B Mock Demo)

실행일: 2026-10-30 (1차 KST 11:06–11:10, web-ui 연동 2차 KST 11:20–11:30, Benchmark 피드백 3차 KST 13:00–13:20)

> 원칙: 실제로 실행한 항목만 PASS/FAIL로 기록합니다. 실행하지 않은 항목은 `NOT_RUN`입니다.

## 1. 테스트 환경

| 항목 | 값 |
|------|----|
| OS | Windows 11 Home 10.0.26200 |
| Docker | Docker Desktop, Engine 29.1.2 |
| Mosquitto | `eclipse-mosquitto:2` → 실제 2.1.2 |
| Gateway | Python 3.12-slim, fastapi 0.115.6, uvicorn 0.32.1, paho-mqtt 2.1.0 |
| Host 테스트 도구 | Python 3.12.10, pytest 8.3.4, websockets 14.1, jsonschema 4.23.0 |
| Arduino | arduino-cli 1.5.1 (Arduino IDE 번들), esp32 core 3.3.12 (1·2차) / **2.0.17 (3차, 로컬 설치 버전이 바뀌어 있었음)**, PubSubClient 2.8.0 |
| ESP32 보드 | 1·2차: **연결되지 않음**. 3차: 사용자 보드가 `xiao-01`로 broker에 접속해 있는 것을 관찰 (3.7) |

## 2. 실행 명령어

```bash
# Docker
docker compose config -q
docker compose build mqtt-broker control-gateway
docker compose up -d mqtt-broker control-gateway
docker compose ps
docker compose logs --tail=100 mqtt-broker
docker compose logs --tail=100 control-gateway

# Gateway unit/app/contract tests
cd services/control-gateway && pip install -r requirements-dev.txt && pytest -q

# E2E (Docker 실행 중)
python scripts/integration_test.py --broker-restart

# 전체 파이프라인 (benchmark 포함, 보드 없이)
docker compose --profile benchmark up -d --build
python scripts/pipeline_e2e_test.py

# PC mock device로 xiao-01 흐름 확인
python scripts/mock_publisher.py --count 3 --interval 10

# Firmware compile
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 --warnings all \
  --build-path D:/Arduino/ArduinoBuild/smart_media-cli smart_media
```

## 3. 결과 요약

### 3.1 Docker / MQTT Broker

| ID | 항목 | 결과 | 근거 |
|----|------|------|------|
| D01 | `docker compose config` | PASS | 오류 없음, 기본 서비스 `mqtt-broker, control-gateway, web-ui` |
| D02 | `docker compose build` (broker, gateway) | PASS | 두 이미지 Built |
| D03 | Container 실행 | PASS | `mqtt-broker Up (healthy) 0.0.0.0:1883`, `control-gateway Up (healthy) 0.0.0.0:8000` |
| D04 | Port 1883 Host 접근 | PASS | Host의 Python paho client가 `localhost:1883` 접속 |
| B01 | MQTT Publish/Subscribe + JSON 수신 | PASS | `received JSON on smart-media/it-xiao-01/detection: seq=1` |
| D05 | Container 로그 | PASS | broker: `New client connected ... as control-gateway (p4, c1, k15)` / gateway: `connected, subscribed to ['smart-media/+/detection', 'smart-media/+/status']` |
| H01 | `GET /health` | PASS | `{"status":"ok","mqtt_connected":true,"mqtt_broker":"mqtt-broker:1883",...}` |
| H02 | `GET /api/state` | PASS | 시작 직후 `xiao-01: PAUSE / SYSTEM_STARTUP` |

### 3.2 Gateway 시나리오 (E2E: MQTT → Gateway → WebSocket, `scripts/integration_test.py`)

테스트 device_id는 `it-xiao-01` (실제 `xiao-01`과 분리).

| ID | 입력 | 기대 | 실제 | 결과 |
|----|------|------|------|------|
| T01 | `true` | PLAY | `PLAY/FACE_PRESENT source=mock face=True` | PASS |
| T02 | `false` | PAUSE | `PAUSE/FACE_ABSENT source=mock face=False` | PASS |
| T03 | `true → true` | 중복 없음 | 2초간 WS 메시지 없음 | PASS |
| T04 | `false → false` | 중복 없음 | 2초간 WS 메시지 없음 | PASS |
| T05 | 25초 이상 detection 없음 | PAUSE/DEVICE_TIMEOUT | `PAUSE/DEVICE_TIMEOUT after 25.17s` (gateway 로그 `no detection for 25169 ms`) | PASS |
| T06 | status offline | PAUSE/DEVICE_OFFLINE | `PAUSE/DEVICE_OFFLINE source=system face=None` | PASS |
| T06b | status online만 | PLAY 안 함 | 2초간 WS 메시지 없음 | PASS |
| T06c | LWT (TCP 비정상 종료) | PAUSE/DEVICE_OFFLINE | broker가 will 발행 → `PAUSE/DEVICE_OFFLINE` 0.016s 내 수신 | PASS |
| T07 | 잘못된 JSON, 필수 필드 누락 | 오류 로그, 서버 유지 | `invalid_messages 0 → 2`, `/health status=ok`, WS 메시지 없음 | PASS |
| T08 | WebSocket 재접속 | 현재 상태 동기화 | 새 연결 첫 메시지 `PLAY/FACE_PRESENT` | PASS |
| T09 | Broker 재시작 | fail-safe PAUSE, 자동 복구 | `PAUSE/BROKER_DISCONNECTED` → 1.0초 후 `mqtt_connected=true` → `true` 입력 시 PLAY | PASS |
| T10 | 10초 주기 정상 입력 ×4 (40초) | timeout 없음 | `PLAY, PAUSE, PLAY, PAUSE` (FACE_PRESENT/ABSENT만, DEVICE_TIMEOUT 없음) | PASS |

T07 Gateway 로그:

```
ERROR gateway: invalid message on smart-media/it-xiao-01/detection: invalid JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1) | payload=b'{this is not json'
ERROR gateway: invalid message on smart-media/it-xiao-01/detection: missing required field 'source' | payload=b'{"schema_version": "1.0", "device_id": "it-xiao-01"}'
```

T09 Gateway 로그:

```
02:08:25,370 WARNING gateway.mqtt: disconnected: Unspecified error
02:08:25,370 WARNING gateway: MQTT broker disconnected -> fail-safe PAUSE
02:08:25,370 INFO gateway.state: [it-xiao-01] PAUSE (reason=BROKER_DISCONNECTED, source=system, last_source=mock)
02:08:26,372 INFO gateway.mqtt: connected, subscribed to ['smart-media/+/detection', 'smart-media/+/status']
```

> 참고: T09 스크립트 출력의 `after -0.375s`는 측정 시작 시점(`docker compose restart` 완료 후)보다 메시지가 먼저 도착해서 생긴 표시상 값입니다. 판정에는 영향 없습니다.

### 3.3 xiao-01 기본 장치 흐름 (PC Mock Publisher, 10초 주기)

`scripts/mock_publisher.py`가 Firmware와 동일한 방식(status online retain + LWT, detection 10초 교차)으로 발행.

| 순서 | MQTT 입력 | WebSocket 수신 (`ts_server_ms`) |
|------|-----------|-------------------------------|
| 연결 | – | `PAUSE/SYSTEM_STARTUP` (snapshot) |
| seq 1 | `true` | `PLAY/FACE_PRESENT` 1793326122828 |
| seq 2 | `false` | `PAUSE/FACE_ABSENT` 1793326132830 (+10.002 s) |
| seq 3 | `true` | `PLAY/FACE_PRESENT` 1793326142829 (+9.999 s) |
| 종료 | status `online:false` | `PAUSE/DEVICE_OFFLINE` 1793326152829 |

결과: PASS (Gateway 로그 `detection xiao-01 seq=N source=mock face=...` → `broadcast ... to 1 client(s)`)

### 3.4 자동화 테스트 (pytest, broker 불필요)

`services/control-gateway/tests/` — 1차 **50 passed**, web-ui 연동 수정 후 2차 **54 passed** (0.37s), 3차 **96 passed** (3.7)

| 파일 | 내용 |
|------|------|
| `test_state_manager.py` | T01–T06, T10을 가짜 시계로 검증, broker disconnect, 장치 독립성 |
| `test_messages.py` | T07: 깨진 JSON, 타입 불일치, 필수 필드 누락, topic/device_id 불일치 |
| `test_contracts.py` | 4개 Schema Draft 2020-12 유효성 + example 검증, Gateway 출력이 WS Schema와 일치, **WS reason이 web-ui `REASON` 표에 모두 존재 / web-ui 기본 WS 경로를 Gateway가 제공** (web-ui 파일을 읽기만 함) |
| `test_app.py` | FastAPI + WebSocket 다중 client broadcast, 재접속 snapshot, retained detection 무시 |

### 3.5 Arduino Firmware

| ID | 항목 | 결과 | 근거 / 사유 |
|----|------|------|------------|
| A01 | arduino-cli 컴파일 (XIAO_ESP32S3) | PASS | 1차(core 3.3.12): exit 0, 경고 0, `Sketch uses 859304 bytes (25%)`, `Global variables use 46336 bytes (14%)`. 3차(core 2.0.17, threshold 추가 후): exit 0, 경고 0, `674081 bytes (20%)`, `44328 bytes (13%)` |
| A02 | Arduino IDE GUI 빌드 | NOT_RUN | GUI 미사용 (동일 core/library로 CLI 빌드만 수행) |
| A03 | 보드 업로드 | NOT_RUN | XIAO ESP32S3 미연결 |
| A04 | Wi-Fi 연결 | NOT_RUN | 실기기 없음 |
| A05 | MQTT 연결 / status online / LWT | NOT_RUN | 실기기 없음 (LWT 메커니즘 자체는 T06c에서 PC client로 검증) |
| A06 | 10초 주기 발행, true/false 교차 | NOT_RUN | 실기기 없음 (동일 동작의 PC mock은 3.3에서 검증) |
| A07 | Serial Monitor 로그 | NOT_RUN | 실기기 없음 |
| A08 | Wi-Fi/MQTT 끊김 후 재연결 | NOT_RUN | 실기기 없음 |

#### 수동 확인 절차 (보드 연결 후)

1. `docker compose up -d mqtt-broker control-gateway`
2. PC LAN IP 확인 (`ipconfig`) → `config.h`의 `MQTT_HOST`에 입력, Wi-Fi 정보 입력
3. Windows 방화벽에서 TCP 1883 인바운드 허용
4. 업로드 → Serial Monitor 115200: `[WiFi] Connected`, `[MQTT] Connected`, `[DETECT] seq=1 ... true` 확인 (A04, A05, A07)
5. 다른 터미널: `docker compose exec mqtt-broker mosquitto_sub -t 'smart-media/#' -v` → 10초 간격 true/false 교차, seq 증가 확인 (A06)
6. `curl localhost:8000/api/state` → `xiao-01` `last_source: "mock"`, command가 10초마다 PLAY/PAUSE 전환
7. 보드 USB 분리 → 최대 keepalive×1.5(약 22초) 내 LWT로 `PAUSE/DEVICE_OFFLINE`, 또는 25초 timeout으로 `DEVICE_TIMEOUT` 확인
8. 공유기 Wi-Fi 끄기/켜기 또는 `docker compose restart mqtt-broker` → Serial에 재연결 로그, 재연결 직후 detection 즉시 발행 확인 (A08)

### 3.6 Web UI(C) 연동 테스트 (2차)

C 담당 web-ui(PR #1, `services/web-ui/public/index.html`)를 **수정 없이** 검토·실행했습니다.

#### 검토 결과 (수정 전 Gateway와의 불일치)

| # | 불일치 | 수정 전 실제 결과 | 조치 (Gateway 쪽만 수정) |
|---|--------|-------------------|--------------------------|
| 1 | web-ui 기본 WS 경로 `/ws`, Gateway는 `/ws/media`만 제공 | `ws://localhost:8000/ws` → **HTTP 403** (연결 불가, 화면 "게이트웨이 끊김") | `/ws` 추가, `/ws/media`는 별칭 유지 |
| 2 | Gateway reason `FACE_PRESENT` ↔ web-ui `FRONT_FACE_PRESENT` | (코드 검토) 재생은 되지만 화면이 "판단 불가" | `reason`을 web-ui enum으로 출력 |
| 3 | `DEVICE_OFFLINE`, `BROKER_DISCONNECTED`, `SYSTEM_STARTUP`은 web-ui에 없음 | (코드 검토) 모두 "판단 불가" | OFFLINE → `DEVICE_TIMEOUT`(카메라 끊김), 나머지 → `UNKNOWN`. 세부 원인은 `detail` 필드 |
| 4 | web-ui가 `confidence` 표시 | 필드 없음 → "-" (문제 없음) | `confidence` 항상 포함 (Mock은 null) |

#### 실제 브라우저 테스트 (`scripts/webui_e2e_test.py`)

환경: Google Chrome headless(DevTools Protocol), `--autoplay-policy=no-user-gesture-required`, web-ui 컨테이너(nginx) `http://localhost:8080/`, 실제 YouTube IFrame Player(기본 영상 `M7lc1UVf-VE`).
흐름: Python이 MQTT로 `xiao-01` mock payload 발행 → mqtt-broker → control-gateway → `ws://localhost:8000/ws` → web-ui → YouTube.
페이지 로드 후 "시작하기" 버튼을 1회 클릭(자동재생 정책)하고 DOM 문구와 `player.getPlayerState()`를 읽어 판정했습니다.

| ID | 입력 | 기대 화면 / 플레이어 | 실제 | 결과 |
|----|------|----------------------|------|------|
| W0 | 페이지 로드 | 게이트웨이 연결됨 | `게이트웨이 연결됨`, 로그 `연결됨: ws://localhost:8000/ws`, 첫 snapshot "판단 불가"(SYSTEM_STARTUP) | PASS |
| W1 | detection `true` | 보고 있어요 / PLAYING | `보고 있어요`, PLAYING, `전달 1ms` | PASS |
| W2 | detection `false` | 자리 비움 / PAUSED | `자리 비움`, PAUSED, 자동 정지 1 | PASS |
| W3 | detection `true` | 보고 있어요 / PLAYING | 동일 | PASS |
| W4 | status `online:false` | 카메라 끊김 / PAUSED | `카메라 끊김`, PAUSED, 로그 `PAUSE (DEVICE_TIMEOUT)` | PASS |
| W5 | 25초 detection 없음 | 카메라 끊김 / PAUSED | 25초 후 `카메라 끊김`, PAUSED | PASS |
| W6 | `docker compose restart mqtt-broker` | 판단 불가 / PAUSED | `판단 불가`, PAUSED, 로그 `PAUSE (UNKNOWN)` | PASS |
| W7 | broker 복구 후 `true` | 보고 있어요 / PLAYING | 동일 (web-ui WebSocket은 끊기지 않음) | PASS |
| W8 | 페이지 새로고침 | 현재 상태 동기화 | 새 연결 직후 `보고 있어요` 표시, 영상은 "시작하기" 대기(CUED) | PASS |

Gateway → 브라우저 전달 지연(web-ui 표시 `전달 Nms`, 같은 PC): 0–35 ms.

#### 회귀 테스트

`scripts/integration_test.py --broker-restart`를 web-ui와 같은 `/ws` 경로로 재실행 → **14/14 PASS**
(예: `T01 got PLAY reason=FRONT_FACE_PRESENT detail=FACE_PRESENT`, `T06c got PAUSE reason=DEVICE_TIMEOUT detail=DEVICE_OFFLINE`, `T05 DEVICE_TIMEOUT after 25.56s`).

#### 검토 의견 (web-ui는 수정하지 않음, C 담당 참고)

- web-ui는 `device_id`를 필터링하지 않습니다. 같은 Gateway에 다른 장치 메시지(예: `integration_test.py`의 `it-xiao-01`)가 오면 화면이 그 장치를 따라갑니다.
  → 시연 중에는 `integration_test.py`를 실행하지 말고, 실행했다면 `docker compose restart control-gateway`로 테스트 장치 상태를 지우세요.
- 화면 문구 "정면 얼굴이 보여서 재생합니다."는 이번 버전(얼굴 존재 여부만 판단)에서는 "얼굴이 보여서"의 의미입니다.

### 3.7 Benchmark 피드백 반영 (3차)

변경: detection 계약(`confidence` 규칙, `threshold`), Firmware `DetectionResult.threshold`, Gateway debounce 구조(기본 꺼짐).

#### pytest — **96 passed** (0.45s)

| 구분 | 검증 내용 | 결과 |
|------|-----------|------|
| Schema/Contract | `edge_impulse`에 `confidence` 없음/`null` → 거부 | PASS |
| | `confidence: 0` (`0`, `0.0`, `0.000`) → `0.0`으로 유지, WebSocket에도 `0` (null 아님) | PASS |
| | threshold 미만 점수(`false`, 0.35, threshold 0.6) 유지 | PASS |
| | `threshold` 있음/없음 모두 허용, 범위 밖·문자열·bool 거부, `confidence`와 같은 0–1 척도 | PASS |
| | `raw_face_detected:false` + `bbox` → Schema 거부, 미검출 시 `bbox` 생략 payload 허용 | PASS |
| | Mock payload(필드 생략 / `confidence:null`) 허용, Mock + 숫자 `confidence`·`threshold` 거부 | PASS |
| | `state` 필드 재등장, `source` 누락 → 거부 | PASS |
| | Firmware 형태 payload(`"confidence":0.000`, `"threshold":0.600`) Schema 통과 | PASS |
| Gateway | 기존 T01–T10 상태 머신, 중복 명령 방지, WS snapshot/broadcast (기존 테스트 전부) | PASS |
| | debounce 기본값 = 꺼짐: `T,F,T,F,T,F,T` → 7번 모두 전환 (기존 동작 동일) | PASS |
| | `PAUSE_CONFIRM_MS=5000`(2.3 s 간격 입력): 깜빡임 → PLAY 1회만, 지속 false → PAUSE | PASS |
| | `PAUSE_CONFIRM_COUNT=3`: 깜빡임 억제, 연속 3회 false → PAUSE | PASS |
| | PLAY/PAUSE 규칙 독립 (`PLAY 2회`, `PAUSE 3회`) | PASS |
| | Fail-safe: PAUSE debounce를 매우 길게(100회/600 s) 해도 timeout(정확히 25 s)·offline·broker 끊김 즉시 PAUSE, 후보 폐기 | PASS |
| | offline 후 이전 PLAY 후보가 재사용되지 않음 | PASS |
| | 환경변수 → `/api/state.debounce` 반영, WebSocket 실제 전송이 `PLAY, PAUSE` 2건뿐 | PASS |

(테스트 수치는 동작 검증용 입력이며 권장값이 아닙니다.)

#### Docker 실측

| ID | 항목 | 결과 | 근거 |
|----|------|------|------|
| R1 | `integration_test.py --broker-restart` (기본 설정, debounce 꺼짐) | **14/14 PASS** | `T05 DEVICE_TIMEOUT after 25.83s`, `T10` 4회 전환 |
| L1 | `PAUSE_CONFIRM_COUNT=3`으로 재시작, edge_impulse `T,F,T,F,T,F` 발행 | PASS | WebSocket `PLAY` 1건만 (`confidence 0.82`), 로그 `PAUSE candidate cancelled` |
| L2 | `edge_impulse` + `confidence` 누락 | PASS | `invalid_messages 0→1`, 상태 변화 없음 |
| L3 | 연속 false 3회 (마지막 `confidence:0`) | PASS | `PAUSE / FACE_ABSENT`, `confidence 0.0` |
| L4 | PAUSE 후보 대기 중 status offline | PASS | 즉시 `PAUSE / DEVICE_OFFLINE` (0.000 s) |
| – | 확인 후 기본 설정으로 Gateway 재시작 | 완료 | `/api/state.debounce` = 1/0, 장치 `xiao-01`만 |

#### web-ui 브라우저 회귀 (`scripts/webui_e2e_test.py`)

| 결과 | 내용 |
|------|------|
| W1–W4, W7, W8 PASS | 표시 문구 / YouTube 상태 기존과 동일 |
| **W5, W6 FAIL (외부 간섭)** | 테스트 중 **사용자의 실제 보드가 같은 `xiao-01`로 10초마다 발행**하고 있었음. W5(25초 무발행 기대) 구간에 보드의 `PLAY`가 들어왔고, W6 broker 재시작 직후에는 보드의 이전 상태 때문에 기대와 다른 문구가 표시됨. Gateway 코드 문제 아님. 보드를 끈 뒤 재실행 필요 → **NOT_RUN(재실행 필요)** |

#### 실기기 관찰 (사용자 보드, 직접 조작하지 않음)

`mosquitto_sub -t 'smart-media/#'` 및 broker 로그에서 관찰한 내용입니다. 보드 업로드·Serial Monitor는 이 테스트에서 하지 않았습니다.

- client id `xiao-01`, keepalive 15 s (`p4, c1, k15`) — Firmware 설정과 일치 (PC mock은 `xiao-01-pc-mock`)
- `status {"online":true}` retained, detection `seq 98 → 99`, `uptime_ms 967763 → 977763` (정확히 10초 간격), `source:"mock"`, true/false 교차
- broker 재시작(W6) 후 같은 client id로 재접속 기록 (`04:12:03`, `04:12:07`)

### 3.8 model-benchmark(#4) 포함 전체 파이프라인 (4차)

`main`(#3 계약/debounce + #4 model-benchmark) 기준, `docker compose --profile benchmark up -d --build`로 4개 컨테이너 실행.
보드 없이 `scripts/pipeline_e2e_test.py`로 확인했습니다 (P2는 serial_bridge의 파서·Bridge 코드를 그대로 쓰고 시리얼 포트만 재생 입력으로 대체).

| ID | 흐름 | debounce 꺼짐 (기본) | `PAUSE_CONFIRM_MS=7500` (Benchmark 후보) |
|----|------|----------------------|------------------------------------------|
| P1a | benchmark `mock_publisher`(alternate 3 s) → Gateway | PASS `PLAY,PAUSE,PLAY,PAUSE` | PASS `PLAY` (3 s 교차는 7.5 s hold 안이라 유지) |
| P1b | WebSocket `source:mock`, `confidence:null` | PASS | PASS |
| P1c/d | collector 저장(10 detection 모두 valid) → analyzer `summary.md` | PASS | PASS |
| P2a | serial replay(2.3 s/프레임, 12프레임) → bridge payload 전부 Gateway 수용 | PASS (invalid 0) | PASS |
| P2b | 깜빡이는 검출 `T F T F T F T F F F F T` | PASS 9회 전환 | PASS **3회** `PLAY,PAUSE,PLAY` |
| P2c | WebSocket `source:edge_impulse`, `confidence` 숫자(0 포함) | PASS | PASS |
| P2d/e | collector: 12프레임 valid, `confidence:0` 5건 유지, `threshold:0.6` 기록, `bbox`는 검출 시에만 | PASS | PASS |
| P2f | analyzer `summary.md` | PASS | PASS |
| P3 | replay 중단 → fail-safe `PAUSE/DEVICE_TIMEOUT` | PASS 25.1 s | PASS 26.1 s (debounce로 지연 없음) |

기대 PLAY/PAUSE는 Gateway의 `StateManager`에 collector가 기록한 수신 시각을 넣어 계산합니다 (debounce 설정과 무관하게 같은 스크립트로 판정).
테스트 결과는 컨테이너 안 `/tmp/e2e-*`에 저장되어 실제 측정 결과(`services/model-benchmark/results/`)와 섞이지 않습니다.

회귀: pytest Gateway **98 passed**, model-benchmark **24 passed**, `integration_test.py --broker-restart` **14/14**,
`webui_e2e_test.py` **W1–W8 8/8 PASS** (보드 offline 상태에서 재실행 — 3차의 W5/W6 FAIL은 보드 간섭이었음을 확인).

수정 사항:
- `PAUSE_CONFIRM_MS` 시간 기준을 "첫 미검출부터" → "**마지막 검출부터**"로 변경. Benchmark analyzer의 hold 정의와 같아져 FINDINGS의 hold 7.5 s를 그대로 설정 가능 (이전 정의로는 7500을 넣으면 실제 약 9.8 s 후 PAUSE)
- `.gitattributes`: 계약 JSON을 LF로 고정. Windows `core.autocrlf=true`에서 `schemas/` 사본이 CRLF로 체크아웃되어 model-benchmark `test_schemas_sync.py` 3건이 실패하던 문제 (내용은 동일했음)

## 4. 발견된 문제

| # | 문제 | 해결 |
|---|------|------|
| 1 | arduino-cli 기본 빌드 경로가 Windows 사용자 폴더(한글 이름)라 링커가 `.elf`를 열지 못함 | `--build-path`를 ASCII 경로로 지정해 해결. Firmware README에 기록 |
| 2 | `.env`에 값 뒤 인라인 주석(`25000  # ...`)이 있으면 파서에 따라 값 일부로 읽힐 위험 | `.env.example`에서 주석을 별도 줄로 이동 |
| 3 | 테스트 정리 시 retained status를 빈 payload로 삭제하면 Gateway가 invalid message로 기록 | 빈 payload는 조용히 무시하도록 수정 |
| 4 | Docker Desktop 데몬이 초기에 꺼져 있었음 | Docker Desktop 실행 후 진행 |
| 5 | web-ui(`/ws`, reason 4종)와 Gateway(`/ws/media`, reason 6종) 규약 불일치 → web-ui 연결 불가 (HTTP 403) | Gateway를 web-ui 규약에 맞춤 (3.6) |
| 6 | Claude in Chrome 확장 미연결 | 설치된 Chrome을 headless + DevTools Protocol로 직접 구동해 대체 |
| 7 | 실제 보드가 `xiao-01`로 발행 중이라 `webui_e2e_test.py` W5/W6가 간섭받음 | 브라우저 E2E는 보드 전원을 끄고 실행 (web-ui가 device_id를 필터링하지 않음) |
| 8 | 로컬 esp32 core가 3.3.12 → 2.0.17로 바뀌어 있었음 | 2.0.17로 컴파일 확인. 공용 Arduino 폴더라 3.3.12를 재설치하지 않음 |
| 9 | `services/model-benchmark/schemas/detection.schema.json`(D 사본)이 새 계약과 달라짐 | D 담당이 #4에서 다시 복사함 (해결) |
| 10 | Windows autocrlf로 schemas 사본이 CRLF → `test_schemas_sync.py` 바이트 비교 실패 | `.gitattributes`로 LF 고정 (3.8) |
| 11 | `PAUSE_CONFIRM_MS` 시간 기준이 Benchmark hold 정의와 달랐음 | 마지막 검출 기준으로 변경 (3.8) |

## 5. 남은 작업

- 실기기 테스트 A02–A08 (3차에서 보드 발행·재접속은 관찰됨, 직접 수행한 테스트는 아님)
- 실제 보드 + Edge Impulse 모델(serial_bridge 또는 펌웨어 Provider)로 debounce 후보값 시연 검증
- Benchmark 결과를 받은 뒤 debounce 수치 결정 및 실기기 검증
- 사람이 직접 보는 브라우저(헤드리스 아님)에서 실기기 ESP32와 함께 최종 시연 확인
- Broker 인증, 실제 모델 연동 (`docs/model-integration-guide.md`)
- healthcheck 요청이 10초마다 broker/gateway 로그에 남음 — 필요 시 로그 레벨 조정
