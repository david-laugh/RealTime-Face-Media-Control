# bench-sketch

Edge Impulse 프로젝트 541658(FOMO, int8, Grayscale) Arduino 라이브러리의 `esp32_camera` 예제를 수정해 측정합니다.
Edge Impulse 라이브러리는 커밋하지 않습니다 (`.gitignore`). 수정한 `.ino`는 이 폴더에 둡니다.

1. Edge Impulse Studio → Deployment → Arduino library (Quantized int8, EON 여부 기록) 다운로드
2. Arduino IDE → Sketch → Include Library → Add .ZIP Library
3. 보드: XIAO_ESP32S3, PSRAM: OPI PSRAM 활성화, Serial 115200 baud
4. 다운로드 날짜와 배포 옵션을 collector `--download-date`, `--deploy` 로 기록

## 원본 예제 대비 변경사항

| 항목 | 변경 | 이유 |
|------|------|------|
| 카메라 핀 | XIAO ESP32S3 Sense 핀맵 추가 (아래 표) | 원본 예제는 ESP-EYE / AI-Thinker 핀만 정의 |
| `ei_camera_get_data()` 색상 순서 | BGR→RGB 스왑 제거: `(snapshot_buf[pixel_ix] << 16) + (snapshot_buf[pixel_ix + 1] << 8) + snapshot_buf[pixel_ix + 2]` | 최신 esp32-camera 드라이버는 이미 RGB 순서로 변환하므로 원본의 스왑이 색을 다시 뒤집어 검출이 실패함 |
| ESP-NN | off: 라이브러리 `src/edge-impulse-sdk/classifier/ei_classifier_config.h`의 `#define EI_CLASSIFIER_TFLITE_ENABLE_ESP_NN 1` → `0` | ESP-NN on 상태에서 첫 추론 시 Guru Meditation (StoreProhibited) 크래시 발생 |
| 검출 출력 임계값 | 0.2: 라이브러리 `src/model-parameters/` (파일명: TBD) 의 threshold 값 | 낮은 confidence 박스도 출력해 analyzer 에서 임계값 스윕. 실제 판정 임계값은 serial_bridge `--threshold`(기본 0.5) |
| `debug_nn` | `false` 고정 | 아래 개인정보 보호 참고 |

## 모델 입력 영역

- 카메라 프레임 320x240 중 **가운데 240x240만 모델에 입력**되므로 좌우 가장자리(각 40px)는 인식 영역 밖입니다.
  FACE 측정은 얼굴을 화면 중앙에 두고 합니다 (`position: CENTER`).
- 모델 입력 해상도: TBD (`model_metadata.h`의 `EI_CLASSIFIER_INPUT_WIDTH/HEIGHT`) → serial_bridge `--input-width/--input-height`

## 빌드 환경

- ESP32 보드 패키지 (Boards Manager `esp32`) 버전: TBD

카메라 핀 (Seeed XIAO ESP32S3 Sense 공식 핀맵 기준, 스케치 값과 다르면 이 표를 수정):

| PWDN | RESET | XCLK | SIOD | SIOC | Y9 | Y8 | Y7 | Y6 | Y5 | Y4 | Y3 | Y2 | VSYNC | HREF | PCLK |
|------|-------|------|------|------|----|----|----|----|----|----|----|----|-------|------|------|
| -1 | -1 | 10 | 40 | 39 | 48 | 11 | 12 | 14 | 16 | 18 | 17 | 15 | 38 | 47 | 13 |

## 반드시 지킬 것 (개인정보 보호)

- **`debug_nn = false` 고정.** debug_nn을 켜면 픽셀 데이터(features)가 시리얼로 출력되므로 금지.
- Wi-Fi / 네트워크 코드 추가 금지. 기기 밖으로는 시리얼 텍스트 결과만 나갑니다.
- 이미지 캡처 저장·전송 코드 추가 금지.
