# control-gateway

> ⚠️ 아직 구현되지 않았습니다. 현재 Container는 placeholder(`sleep infinity`)로만 실행됩니다.
> Owner: Member B (Backend / IoT)

## 역할 (예정)

MQTT Broker로부터 디바이스 메시지를 구독하고, 상태를 판단하여 Browser(Web UI)에 WebSocket으로 PLAY / PAUSE 명령을 전달합니다.

```
mqtt-broker ──(smart-media/+/detection, status)──▶ control-gateway ──(WebSocket media_control)──▶ web-ui
```

## 구현 후보

- **Python FastAPI** (+ MQTT client, WebSocket endpoint)
- **Node.js** (+ MQTT client, WebSocket server)

구현 언어 확정 후 `Dockerfile`의 base image와 `CMD`를 교체합니다.

## 예정 구성 요소

- MQTT Subscriber
- State Machine (FRONT_PRESENT / NOT_PRESENT / UNKNOWN → PLAY / PAUSE)
- Device timeout 감지 (`DEVICE_TIMEOUT`)
- WebSocket Server (`ws://<host>:8000/ws` 안)

## Contract

- Input: [`contracts/mqtt/`](../../contracts/mqtt/)
- Output: [`contracts/websocket/media-control.schema.json`](../../contracts/websocket/media-control.schema.json)

## 디렉터리

| Path | 용도 |
|------|------|
| `src/` | Application source |
| `tests/` | Unit tests (State Machine 등) |
