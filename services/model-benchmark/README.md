# model-benchmark

Edge Impulse 얼굴 검출 모델을 XIAO ESP32S3 Sense에서 측정합니다 (compose profile `benchmark`).
측정 계획: [`docs/model-benchmark.md`](../../docs/model-benchmark.md)

| 파일 | 역할 |
|------|------|
| `src/serial_bridge.py` | 예제 스케치 시리얼 출력 → MQTT (호스트에서 실행) |
| `src/mock_publisher.py` | 가짜 디바이스 (기기 없이 테스트) |
| `src/collector.py` | 세션 수집 → `results/{model_id}/{YYYYMMDD}/{session}/` |
| `src/analyzer.py` | `summary.csv`, `summary.md` 생성 |
| `test-cases/cases.yaml` | 측정 케이스 (행 추가로 확장) |
| `schemas/` | `contracts/mqtt` 사본 (`tests/test_schemas_sync.py`로 동기화 확인) |

## 실행 순서 (실기기)

```bash
docker compose --profile benchmark up -d --build          # broker + benchmark
# 호스트: 스케치 업로드 후 (bench-sketch/README.md)
pip install -r services/model-benchmark/requirements.txt  # Python 3.12 권장
python services/model-benchmark/src/serial_bridge.py --port COM5 --baud 115200 \
    --input-width 96 --input-height 96 --threshold 0.6
# 케이스별 수집 (10초 카운트다운 후 120초, 카운트다운 중 메시지는 저장 안 함. --start-delay 로 변경)
docker compose exec model-benchmark python src/collector.py --case face-50-normal --operator NM \
    --download-date 2026-10-30 --camera-height 110cm --camera-position "모니터 상단"
docker compose exec model-benchmark python src/analyzer.py --date 20261030
```

`--operator`는 이니셜/별칭만 사용하세요. 측정 조건 기본값: `--esp-nn off --color grayscale
--device-threshold 0.2 --bridge-threshold 0.6` (바꿨으면 명시).
기기 출력 임계값은 모델 원래 기본값 0.6을 임계값 스윕을 위해 0.2로 낮춘 값이고, 판정 임계값은 원래 기준 0.6을 유지합니다.
빌드 환경: ESP32 보드 패키지 3.3.12. ESP-NN은 첫 추론 크래시로 off (3.x 호환 문제일 수 있어 2.0.x 재검증 필요).

### 측정 조건 정의

- FACE = 정면 응시 + **얼굴을 카메라 화면 중앙에 둠** (`position: CENTER`, 기본값).
- 모델에는 320x240 중 가운데 240x240만 입력되므로 화면 좌우 가장자리는 인식 영역 밖입니다.

### 판정/지표 규칙

- `source`: serial_bridge = `edge_impulse`, mock = `mock` (mock은 confidence/inference_ms/bbox 미전송).
- 프레임마다 최고 confidence 박스 사용. 박스 없음 → `confidence=0`, `bbox` 필드 생략.
- `raw_face_detected` = confidence ≥ bridge `--threshold`. 기기는 출력 임계값(`--device-threshold`) 이상 박스를 모두 출력하므로
  analyzer 임계값 스윕(0.3~0.9)은 저장된 confidence로 계산합니다.
- `bbox`: FOMO는 중심점 검출 모델이라 width/height는 얼굴 크기가 아니라 **출력 격자 셀 크기**입니다.
  x, y(셀 위치)만 의미가 있습니다.
- DSP 시간 → telemetry `preprocess_ms`, Classification 시간 → `inference_ms`.
 케이스 목록: `test-cases/cases.yaml` (`--case` 대신 `--label/--distance/--env` 직접 지정 가능).

## Mock 단독 실행 (기기 없이)

```bash
docker compose --profile benchmark up -d --build
docker compose exec -d model-benchmark python src/mock_publisher.py --mode alternate --period 5
docker compose exec model-benchmark python src/collector.py --model-id mock-v1 --label FACE --distance 50cm --env NORMAL --duration 20  # mock은 짧게
docker compose exec model-benchmark python src/analyzer.py --model-id mock-v1
```

gateway/web-ui 테스트용으로만 쓰려면 mock_publisher만 실행하면 됩니다
(`--mode face|no_face|alternate|random`, `--fps`, `--drop`, 토픽 `smart-media/mock-xiao-01/*`).

## 테스트

```bash
cd services/model-benchmark && python -m pytest -q tests
```

## 개인정보 보호

- 카메라 이미지는 ESP32 내부 메모리에서 추론에만 쓰이고, 기기 밖으로는 **텍스트 추론 결과만** 시리얼로 나갑니다.
- `serial_bridge`는 allowlist 파싱: Predictions 줄, `Object detection bounding boxes:` 줄, 바운딩 박스 줄만 처리합니다.
  나머지 줄은 저장/로그/publish 없이 개수만 셉니다. 200자 초과·숫자 나열 줄은 내용 없이 경고 카운트만 남깁니다.
- MQTT와 `results/`에는 contracts 스키마 필드만 저장합니다 (원본 시리얼 줄 저장 안 함, collector가 스키마 밖 필드 제거).
- 이미지·바이너리 파일은 `.gitignore`로 차단됩니다.
- **금지:** `debug_nn = true` (픽셀 데이터가 시리얼로 출력됨), Edge Impulse data acquisition /
  live classification / `edge-impulse-daemon` 연결 (카메라 이미지가 외부로 전송됨),
  스케치에 Wi-Fi/네트워크 코드 추가, 이미지 캡처 저장·전송 코드 작성.
