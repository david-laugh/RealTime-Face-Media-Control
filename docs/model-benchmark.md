# Model Benchmark

> ⚠️ 측정 계획 템플릿입니다. Benchmark 코드와 측정 결과는 아직 없습니다.
> 결과 저장 위치: `services/model-benchmark/results/`

## 1. 목적

여러 Edge Impulse Face Detection 모델(해상도, 양자화, 아키텍처)을 비교하여
XIAO ESP32S3 Sense에서 **정면 얼굴만 안정적으로 PLAY 신호로 변환**할 수 있는 모델을 선정합니다.

## 2. 측정 항목

### 2.1 모델 정보

| Model ID | Edge Impulse Project ID | Model architecture | Quantization | Input resolution | Validation accuracy | Test accuracy |
|----------|-------------------------|--------------------|--------------|------------------|---------------------|---------------|
| ei-541658-fomo01-int8 | 541658 | FOMO | int8 | TBD | TBD | TBD |
| | | | | | | |

### 2.2 디바이스 성능

| Model ID | Inference latency (ms) | Peak RAM (KB) | Flash usage (KB) |
|----------|------------------------|---------------|------------------|
| | | | |

### 2.3 검출 품질

| Model ID | Front detection rate | Side false positive rate | Back false positive rate | Empty false positive rate |
|----------|----------------------|--------------------------|--------------------------|---------------------------|
| | | | | |

### 2.4 End-to-End 제어 품질

| Model ID | PLAY transition latency (ms) | PAUSE transition latency (ms) | State flicker count |
|----------|------------------------------|-------------------------------|---------------------|
| | | | |

### 2.5 지표 정의 (초안)

| 지표 | 정의 |
|------|------|
| Front detection rate | `FRONT` 시나리오에서 `FRONT_PRESENT`로 판단된 비율 |
| Side false positive rate | `LEFT_*`, `RIGHT_*` 시나리오에서 `FRONT_PRESENT`로 잘못 판단된 비율 |
| Back false positive rate | `BACK` 시나리오에서 `FRONT_PRESENT`로 잘못 판단된 비율 |
| Empty false positive rate | `EMPTY` 시나리오에서 `FRONT_PRESENT`로 잘못 판단된 비율 |
| PLAY transition latency | 사용자가 정면을 본 시점 → 브라우저 PLAY 실행 시점 |
| PAUSE transition latency | 사용자가 시선을 돌린 시점 → 브라우저 PAUSE 실행 시점 |
| State flicker count | 고정 자세 유지 중 불필요한 상태 전환 횟수 |

## 3. 테스트 조건

### 3.1 Pose

| Pose | 설명 | 기대 state |
|------|------|------------|
| FRONT | 카메라 정면 응시 | FRONT_PRESENT |
| LEFT_45 | 왼쪽 45° 회전 | NOT_PRESENT |
| LEFT_90 | 왼쪽 90° 회전 (측면) | NOT_PRESENT |
| RIGHT_45 | 오른쪽 45° 회전 | NOT_PRESENT |
| RIGHT_90 | 오른쪽 90° 회전 (측면) | NOT_PRESENT |
| BACK | 뒤돌아 있음 | NOT_PRESENT |
| EMPTY | 사람 없음 | NOT_PRESENT |

> LEFT_45 / RIGHT_45의 기대값은 팀 합의 후 확정합니다.

### 3.2 Distance

| Distance |
|----------|
| 50cm |
| 80cm |
| 120cm |

### 3.3 Environment

| Environment | 설명 |
|-------------|------|
| BRIGHT | 밝은 조명 |
| NORMAL | 일반 실내 조명 |
| LOW_LIGHT | 저조도 |

### 3.4 테스트 매트릭스

Pose(7) × Distance(3) × Environment(3) = **63 조합** / 모델

| Pose \ Distance | 50cm | 80cm | 120cm |
|-----------------|------|------|-------|
| FRONT | | | |
| LEFT_45 | | | |
| LEFT_90 | | | |
| RIGHT_45 | | | |
| RIGHT_90 | | | |
| BACK | | | |
| EMPTY | | | |

(Environment별로 위 표를 반복 작성: BRIGHT / NORMAL / LOW_LIGHT)

## 4. 결과 파일 규칙 (안)

- `services/model-benchmark/test-cases/` : 테스트 케이스 정의
- `services/model-benchmark/results/{model_id}/{YYYYMMDD}/` : 측정 결과
