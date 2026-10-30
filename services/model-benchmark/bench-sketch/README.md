# bench-sketch

Edge Impulse 프로젝트 541658(FOMO, int8) Arduino 라이브러리의 예제 스케치로 측정합니다.
라이브러리와 생성된 스케치는 커밋하지 않습니다 (`.gitignore`).

1. Edge Impulse Studio → Deployment → Arduino library (Quantized int8, EON 여부 기록) 다운로드
2. Arduino IDE → Sketch → Include Library → Add .ZIP Library
3. File → Examples → `<project>_inferencing` → `esp32` → `esp32_camera`를 이 폴더에 복사해 사용
4. 보드: XIAO_ESP32S3, PSRAM: OPI PSRAM 활성화
5. 다운로드 날짜와 배포 옵션을 collector `--download-date`, `--deploy` 로 기록

## 반드시 지킬 것 (개인정보 보호)

- **`debug_nn = false` 고정.** debug_nn을 켜면 픽셀 데이터(features)가 시리얼로 출력되므로 금지.
- Wi-Fi / 네트워크 코드 추가 금지. 기기 밖으로는 시리얼 텍스트 결과만 나갑니다.
- 이미지 캡처 저장·전송 코드 추가 금지.
