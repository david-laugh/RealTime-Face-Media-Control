# Firmware — XIAO ESP32S3 Sense (Mock Detection Demo)

Owner: Member A (Embedded / AI)

> 현재 버전은 **Mock Detection**입니다. 카메라와 Edge Impulse 추론은 사용하지 않으며,
> MQTT 연결 직후 `raw_face_detected=true`를 발행하고 이후 10초마다 `true/false`를 번갈아 발행합니다.
> 메시지에는 `source:"mock"`, `model_id:"mock-v1"`이 표시되며 confidence / inference_ms는 생성하지 않습니다.

이 Firmware는 Docker Container가 아니며 XIAO ESP32S3 Sense에 직접 업로드합니다.

## 파일 구성

```
smart_media/                  # Arduino sketch folder (folder name == .ino name)
├── smart_media.ino           # setup/loop, Wi-Fi 유지, 10초 비차단 타이머
├── config.example.h          # 설정 템플릿 → config.h로 복사 (config.h는 git-ignored)
├── DetectionResult.h         # Provider 출력 구조체 (향후 confidence/inference_ms 선택 필드)
├── MockDetectionProvider.h/.cpp  # true/false 교차 Mock
└── MqttPublisher.h/.cpp      # MQTT 연결/재연결, LWT, detection/status publish
```

| Path | 용도 |
|------|------|
| `include/`, `src/` | (예약) 향후 공용 코드 |
| `models/` | Edge Impulse exported library (**Git에 커밋하지 않음**) |
| `config/` | (예약) |

## Arduino IDE 설정

1. Arduino IDE 2.x 설치
2. **File → Preferences → Additional boards manager URLs**
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. **Boards Manager** → `esp32 by Espressif Systems` 설치 (검증 버전: **3.3.12**)
4. **Library Manager** → `PubSubClient` by Nick O'Leary 설치 (검증 버전: **2.8.0**)
5. **Tools → Board → esp32 → XIAO_ESP32S3**
6. Tools → USB CDC On Boot: **Enabled** (Serial Monitor 출력용, 보드 기본값 확인)
7. `smart_media/config.example.h`를 `smart_media/config.h`로 복사 후 수정

```cpp
#define WIFI_SSID "실제 SSID"
#define WIFI_PASSWORD "실제 비밀번호"
#define MQTT_HOST "192.168.x.y"   // Docker를 실행하는 PC의 LAN IP (Windows: ipconfig)
#define MQTT_PORT 1883
#define DEVICE_ID "xiao-01"
#define PUBLISH_INTERVAL_MS 10000
```

> ⚠️ `MQTT_HOST`에 `localhost`나 `mqtt-broker`(Docker 서비스명)를 쓰면 안 됩니다. ESP32 입장에서
> localhost는 자기 자신이고, `mqtt-broker`는 Docker 내부 DNS에서만 해석됩니다.
> ESP32와 PC는 같은 2.4GHz 네트워크에 있어야 하며, PC 방화벽에서 TCP 1883 인바운드를 허용해야 합니다.

8. `smart_media/smart_media.ino` 열기 → Upload → Serial Monitor **115200 baud**

## arduino-cli 컴파일 (검증된 명령)

```bash
arduino-cli core install esp32:esp32
arduino-cli lib install PubSubClient
cp smart_media/config.example.h smart_media/config.h
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3 smart_media
```

Windows 사용자명에 한글 등 non-ASCII 문자가 있으면 링커가 기본 빌드 경로를 열지 못합니다.
이 경우 `--build-path D:/some/ascii/path`를 지정합니다.

## 예상 Serial Monitor 출력

```
=== smart_media (mock detection) ===
device_id=xiao-01 broker=192.168.0.100:1883 interval=10000 ms
[WiFi] Connecting to 'MySSID' ...
[WiFi] Connected, IP=192.168.0.57 RSSI=-55 dBm
[MQTT] Connecting as 'xiao-01' ...
[MQTT] Connected
[MQTT] Status online published -> smart-media/xiao-01/status
[DETECT] seq=1 source=mock face_detected=true
[MQTT] Published smart-media/xiao-01/detection {"schema_version":"1.0",...,"raw_face_detected":true}
[DETECT] seq=2 source=mock face_detected=false
...
```

(위 출력은 코드 기준 예상 형식이며 실제 보드에서는 아직 확인하지 않았습니다 — [`docs/demo-test.md`](../../docs/demo-test.md))

## 동작 요약

- `delay()` 없이 `millis()` 기반 타이머 사용 (부팅 시 Serial 안정화용 500ms 1회 제외)
- Wi-Fi 끊김: 10초마다 `WiFi.begin()` 재시도 (대기하지 않음)
- MQTT 끊김: 5초마다 1회 연결 시도, socket timeout 3초로 blocking 시간 제한
- MQTT (재)연결 직후 status `online`(retain) → detection 즉시 1회 → 이후 10초 주기
- Last Will: `smart-media/xiao-01/status` `{"online":false}` (QoS 1, retain)
- Detection: QoS 0, retain=false

실제 모델 연동 방법: [`docs/model-integration-guide.md`](../../docs/model-integration-guide.md)
