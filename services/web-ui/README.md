# web-ui

> ⚠️ 아직 구현되지 않았습니다. 현재 Container는 nginx로 빈 `public/` 디렉터리만 서빙합니다.
> Owner: Member C (Frontend)

## 역할 (예정)

- YouTube IFrame API 기반 Player 임베드
- Control Gateway WebSocket 연결 및 `media_control` 메시지 수신
- `PLAY` / `PAUSE` 명령에 따라 Player 제어
- Face Status UI (현재 상태, confidence, device 연결 상태 표시)

## Contract

- Input: [`contracts/websocket/media-control.schema.json`](../../contracts/websocket/media-control.schema.json)

## 디렉터리

| Path | 용도 |
|------|------|
| `src/` | Frontend source (React/Vite 등, 미정) |
| `public/` | Static assets |

프레임워크 확정 후 `Dockerfile`을 multi-stage build(빌드 → nginx 서빙)로 교체합니다.
