# Firmware — XIAO ESP32S3 Sense

> ⚠️ 아직 구현되지 않았습니다. 디렉터리 골격만 존재합니다.
> Owner: Member A (Embedded / AI)

이 Firmware는 Docker Container가 아니며, XIAO ESP32S3 Sense에 직접 업로드됩니다.

## 예정 기능

- Camera Capture
- Edge Impulse FOMO Face Detection inference
- Front Face / Face Absent 상태 판단 (`FRONT_PRESENT` / `NOT_PRESENT` / `UNKNOWN`)
- MQTT publish
  - `smart-media/{device_id}/detection`
  - `smart-media/{device_id}/status`
  - `smart-media/{device_id}/telemetry`

메시지 규격: [`contracts/mqtt/`](../../contracts/mqtt/), [`docs/communication.md`](../../docs/communication.md)

## 디렉터리

| Path | 용도 |
|------|------|
| `include/` | Header files |
| `src/` | Arduino sketch / source |
| `models/` | Edge Impulse exported library (**Git에 커밋하지 않음**, `.gitignore` 처리) |
| `config/` | Wi-Fi / MQTT 설정 템플릿 (실제 credential은 커밋 금지) |
