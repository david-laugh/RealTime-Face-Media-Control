# Team Roles

| Member | 역할 | 담당 영역 | 작업 디렉터리 |
|--------|------|-----------|---------------|
| A | Embedded / AI | XIAO ESP32S3 Sense, Arduino, Camera, Edge Impulse Model, Inference, MQTT Publisher | `firmware/xiao-esp32s3-sense/` |
| B | Backend / IoT | Mosquitto, MQTT Subscriber, Control Gateway, State Machine, WebSocket | `services/mqtt-broker/`, `services/control-gateway/` |
| C | Frontend | Web UI, YouTube IFrame API, PLAY / PAUSE, Face Status UI | `services/web-ui/` |
| D | Benchmark / Integration | Model comparison, Performance measurement, Docker Compose, Integration Test, Documentation | `services/model-benchmark/`, `docker-compose.yml`, `docs/`, `scripts/` |

## Member A — Embedded / AI

- XIAO ESP32S3 Sense
- Arduino
- Camera
- Edge Impulse Model
- Inference
- MQTT Publisher

## Member B — Backend / IoT

- Mosquitto
- MQTT Subscriber
- Control Gateway
- State Machine
- WebSocket

## Member C — Frontend

- Web UI
- YouTube IFrame API
- PLAY / PAUSE
- Face Status UI

## Member D — Benchmark / Integration

- Model comparison
- Performance measurement
- Docker Compose
- Integration Test
- Documentation

## 공동 소유

- `contracts/` : 변경 시 A(Publisher), B(Gateway), C(Frontend) 합의 필요
- `docs/communication.md` : Contract 변경과 함께 갱신
