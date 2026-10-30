# bench-sketch

Edge Impulse 프로젝트 541658(FOMO, int8, Grayscale) Arduino 라이브러리(`Face_detection_for_AI_Bell_inferencing`)의
`esp32_camera` 예제를 수정한 `esp32_camera_xiao.ino`로 측정합니다.
Edge Impulse 라이브러리는 커밋하지 않습니다 (`.gitignore`). 아래 라이브러리 수정은 각자 로컬에 직접 적용합니다.

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
| 검출 출력 임계값 | 0.6 → **0.2**: 라이브러리 `src/model-parameters/model_variables.h`의 `ei_fill_result_fomo_i8_config_1152764_7.threshold` (114행). 2026-10-30 적용, 업로드 후 0.2대 박스 출력 확인 | 모델 원래 기본값은 0.6. 임계값 스윕을 위해 0.2로 낮춤. 실제 판정은 serial_bridge `--threshold`(기본 0.6, 모델 원래 기준과 동일) |
| `debug_nn` | `false` 고정 | 아래 개인정보 보호 참고 |

## 모델 입력 영역

- 카메라 프레임 320x240 중 **가운데 240x240만 모델에 입력**되므로 좌우 가장자리(각 40px)는 인식 영역 밖입니다.
  FACE 측정은 얼굴을 화면 중앙에 두고 합니다 (`position: CENTER`).
- 카메라 설정: `PIXFORMAT_JPEG`, `FRAMESIZE_QVGA`(320x240) → `fmt2rgb888` 변환 후 리사이즈/크롭
- 모델 입력 해상도: **96x96** (`model_metadata.h`의 `EI_CLASSIFIER_INPUT_WIDTH/HEIGHT`) → serial_bridge `--input-width 96 --input-height 96`
- FOMO 출력 격자: 12x12 (`model_variables.h`의 `out_width/out_height`) → 셀 1개 = 8px, bbox width/height는 항상 8의 배수

## 빌드 환경

- ESP32 보드 패키지 (Boards Manager `esp32`) 버전: **3.3.12**
- ESP-NN 크래시(Guru Meditation StoreProhibited)는 보드 패키지 3.x 호환 문제일 수 있음 → 2.0.x 에서 ESP-NN on 재검증 필요

카메라 핀 (`esp32_camera_xiao.ino`의 `CAMERA_MODEL_XIAO_ESP32S3` 값, Seeed 공식 핀맵과 일치 확인):

| PWDN | RESET | XCLK | SIOD | SIOC | Y9 | Y8 | Y7 | Y6 | Y5 | Y4 | Y3 | Y2 | VSYNC | HREF | PCLK |
|------|-------|------|------|------|----|----|----|----|----|----|----|----|-------|------|------|
| -1 | -1 | 10 | 40 | 39 | 48 | 11 | 12 | 14 | 16 | 18 | 17 | 15 | 38 | 47 | 13 |

## 반드시 지킬 것 (개인정보 보호)

- **`debug_nn = false` 고정.** debug_nn을 켜면 픽셀 데이터(features)가 시리얼로 출력되므로 금지.
- Wi-Fi / 네트워크 코드 추가 금지. 기기 밖으로는 시리얼 텍스트 결과만 나갑니다.
- 이미지 캡처 저장·전송 코드 추가 금지.
