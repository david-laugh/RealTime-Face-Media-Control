# web-ui

> Owner: Member C (Frontend)

`public/index.html` 한 파일로 된 정적 페이지입니다. 빌드 단계가 없어서 현재 `Dockerfile`(nginx가 `public/`을 그대로 서빙)을 바꾸지 않고 사용합니다.

## 하는 일

- YouTube IFrame API로 영상을 띄우고, Control Gateway WebSocket의 `media_control` 메시지를 받아 `PLAY` / `PAUSE`를 그대로 실행합니다.
- PLAY/PAUSE 판단(debounce, device timeout)은 게이트웨이 담당이라 web-ui는 판단하지 않습니다.
- Face Status UI: 현재 상태(`reason`), 신뢰도(`confidence`), 게이트웨이 연결 상태, 전달 지연(`ts_server_ms` 기준), 최근 60초 상태 타임라인, 시청 시간과 자동 정지 횟수를 보여 줍니다.
- 게이트웨이 연결이 끊기면 영상을 멈추고 자동으로 다시 연결합니다(최대 5초 간격).
- 규약과 다른 메시지는 무시하고 화면 아래 "동작 기록"에 남깁니다.

## Contract

- Input: [`contracts/websocket/media-control.schema.json`](../../contracts/websocket/media-control.schema.json)

| reason | 화면 표시 |
|--------|-----------|
| `FRONT_FACE_PRESENT` | 보고 있어요 |
| `FACE_ABSENT` | 자리 비움 |
| `DEVICE_TIMEOUT` | 카메라 끊김 |
| `UNKNOWN` | 판단 불가 |

## 실행

```bash
docker compose up -d --build web-ui   # http://localhost:8080
```

처음 한 번은 화면의 **시작하기**를 눌러야 합니다. 브라우저 자동재생 정책 때문에 사용자가 한 번 클릭한 뒤에만 스크립트로 재생할 수 있습니다.

## 설정

정적 페이지라 `.env` 값을 직접 읽지 못해서 주소 뒤 쿼리로 바꿉니다.

| 쿼리 | 기본값 | 의미 |
|------|--------|------|
| `ws` | `ws://<페이지 호스트>:8000/ws` | Gateway WebSocket 주소 (`.env`의 `GATEWAY_WS_URL`) |
| `v` | `M7lc1UVf-VE` | YouTube 영상 ID (`.env`의 `YOUTUBE_VIDEO_ID`) |
| `test` | 없음 | `1`이면 "게이트웨이 없이 시험하기" 버튼을 보여 줌 |

예: `http://localhost:8080/?ws=ws://192.168.0.23:8000/ws&v=dQw4w9WgXcQ`

## 게이트웨이 없이 시험하기

실제 동작에서는 카메라(ESP32)가 얼굴을 판단하므로 버튼이 필요 없고, 평소 화면에는 보이지 않습니다.
`http://localhost:8080/?test=1` 로 열 때만 **얼굴 있음 / 얼굴 없음** 버튼이 나타납니다. 용도는 세 가지입니다.

- 펌웨어·게이트웨이가 준비되기 전에 web-ui 화면과 YouTube 제어만 따로 확인
- 통합 중 문제가 생겼을 때 web-ui 문제인지 앞단 문제인지 구분 (버튼으로는 되는데 카메라로 안 되면 web-ui는 정상)
- 발표 시연 중 ESP32가 동작하지 않을 때 비상용

버튼은 페이지 안에서만 가짜 명령을 만들며, 켜 두는 동안에는 실제 게이트웨이 명령을 무시합니다. 같은 버튼을 다시 누르면 꺼집니다.

## 디렉터리

| Path | 용도 |
|------|------|
| `public/index.html` | Web UI 전체 (HTML, CSS, JS 한 파일) |
| `src/` | 사용하지 않음 (빌드 도구 도입 시 사용) |
