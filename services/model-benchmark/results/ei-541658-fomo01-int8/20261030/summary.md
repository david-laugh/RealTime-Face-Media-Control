# Model Benchmark Summary

판정 기준: `raw_face_detected`. FACE 계열은 검출률, NO_FACE 계열은 오탐률.
board_pkg / esp_nn 이 기록되지 않은 세션은 3.3.12 / off 으로 간주.

## 측정 조건

| session_id | label | position | distance | env | operator | started_at | board_pkg | deploy | esp_nn | color | device_threshold | bridge_threshold | download_date | lighting | camera_height | camera_position | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 041413_FACE_CENTER_50cm_NORMAL | FACE | CENTER | 50cm | NORMAL | NY | 2026-10-30T04:14:23 | 3.3.12 | int8 | off | grayscale | 0.200 | 0.600 | 2026-10-30 |  | 40 | 모니터 상단 중앙 |  |
| 041701_FACE_CENTER_80cm_NORMAL | FACE | CENTER | 80cm | NORMAL | NY | 2026-10-30T04:17:11 | 3.3.12 | int8 | off | grayscale | 0.200 | 0.600 | 2026-10-30 |  | 40 | 모니터 상단 중앙 |  |
| 041833_FACE_CENTER_120cm_NORMAL | FACE | CENTER | 120cm | NORMAL | NY | 2026-10-30T04:18:43 | 3.3.12 | int8 | off | grayscale | 0.200 | 0.600 | 2026-10-30 |  | 40 | 모니터 상단 중앙 |  |
| 042011_NO_FACE_-_-_NORMAL | NO_FACE | - | - | NORMAL | NY | 2026-10-30T04:20:21 | 3.3.12 | int8 | off | grayscale | 0.200 | 0.600 | 2026-10-30 |  | 40 | 모니터 상단 중앙 |  |
| 045053_LEFT_45_CENTER_50cm_NORMAL | LEFT_45 | CENTER | 50cm | NORMAL | NY | 2026-10-30T04:51:03 | 3.3.12 | int8+EON | off | grayscale | 0.200 | 0.600 | 2026-10-30 | 실내 천장등 | 40cm | 모니터 상단 중앙 |  |
| 045227_RIGHT_45_CENTER_50cm_NORMAL | RIGHT_45 | CENTER | 50cm | NORMAL | NY | 2026-10-30T04:52:37 | 3.3.12 | int8+EON | off | grayscale | 0.200 | 0.600 | 2026-10-30 | 실내 천장등 | 40cm | 모니터 상단 중앙 |  |
| 061728_FACE_CENTER_50cm_NORMAL | FACE | CENTER | 50cm | NORMAL | NY | 2026-10-30T06:17:38 | 2.0.17 | int8+EON | on | grayscale | 0.200 | 0.600 | 2026-10-30 | 실내 천장등 | 40cm | 모니터 상단 중앙 |  |
| 061813_NO_FACE_-_-_NORMAL | NO_FACE | - | - | NORMAL | NY | 2026-10-30T06:18:23 | 2.0.17 | int8+EON | on | grayscale | 0.200 | 0.600 | 2026-10-30 | 실내 천장등 | 40cm | 모니터 상단 중앙 |  |

# 환경: esp32 2.0.17 / ESP-NN on

## 검출률 / 오탐률

| model_id | label | position | distance | env | metric | sessions | frames | invalid_msgs | face_rate |
|---|---|---|---|---|---|---|---|---|---|
| ei-541658-fomo01-int8 | FACE | CENTER | 50cm | NORMAL | detection_rate | 1 | 137 | 0 | 0.219 |
| ei-541658-fomo01-int8 | NO_FACE | - | - | NORMAL | false_positive_rate | 1 | 141 | 0 | 0.000 |

## confidence 임계값별 비율 (저장된 confidence ≥ t, raw_face_detected 와 무관)

기기 출력 임계값(측정 조건 표 device_threshold) 미만 박스는 기기가 출력하지 않으므로 그보다 낮은 t 는 의미 없음.

| label | position | distance | env | rate@0.3 | rate@0.4 | rate@0.5 | rate@0.6 | rate@0.7 | rate@0.8 | rate@0.9 |
|---|---|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 0.672 | 0.431 | 0.343 | 0.219 | 0.088 | 0.007 | 0.000 |
| NO_FACE | - | - | NORMAL | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## 성능 / 안정성

| label | position | distance | env | inference_ms_mean | inference_ms_p50 | inference_ms_p95 | fps | transitions | seq_loss_rate |
|---|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 119.000 | 119.000 | 119.000 | 4.568 | 22 | 0.000 |
| NO_FACE | - | - | NORMAL | 119.000 | 119.000 | 119.000 | 4.701 | 0 | 0.000 |

## Debounce 시뮬레이션 (N 프레임 연속 시 전환)

`added_ms` = (N-1) × 평균 프레임 간격: 실제 전환이 늦어지는 추정 시간.

| label | position | distance | env | debounce1_transitions | debounce1_added_ms | debounce2_transitions | debounce2_added_ms | debounce3_transitions | debounce3_added_ms | debounce4_transitions | debounce4_added_ms | debounce5_transitions | debounce5_added_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 22 | 0.000 | 16 | 219.088 | 10 | 438.176 | 6 | 657.265 | 2 | 876.353 |
| NO_FACE | - | - | NORMAL | 0 | 0.000 | 0 | 213.064 | 0 | 426.129 | 0 | 639.193 | 0 | 852.257 |

## 비대칭 Debounce 시뮬레이션 (추정)

저장된 confidence ≥ t 를 검출로 보고, PLAY 는 검출 1회 즉시, PAUSE 는 마지막 검출 후 hold 초 경과 시.
시간은 실제 프레임 수신 간격(uptime_ms) 기준. **실측이 아닌 시뮬레이션 결과**이며,
`pause_latency_s_est` 는 hold 값 그대로인 추정치(실제 반응 지연은 미측정).
한 번도 검출되지 않은 세션은 PAUSE 오류 0 / 재생 비율 0 이므로 debounce 로 해결할 수 없다.

### FACE 세션: 잘못된 PAUSE (정면인데 멈춤), 재생 상태 시간 비율

| label | position | distance | env | t | hold_s | wrong_pause | play_ratio | pause_latency_s_est |
|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 0.400 | 2.500 | 3 | 0.909 | 2.500 |
| FACE | CENTER | 50cm | NORMAL | 0.400 | 5 | 0 | 0.979 | 5 |
| FACE | CENTER | 50cm | NORMAL | 0.400 | 7.500 | 0 | 0.979 | 7.500 |
| FACE | CENTER | 50cm | NORMAL | 0.400 | 10 | 0 | 0.979 | 10 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 2.500 | 3 | 0.733 | 2.500 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 5 | 2 | 0.919 | 5 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 7.500 | 0 | 0.979 | 7.500 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 10 | 0 | 0.979 | 10 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 2.500 | 3 | 0.703 | 2.500 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 5 | 2 | 0.890 | 5 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 7.500 | 0 | 0.971 | 7.500 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 10 | 0 | 0.971 | 10 |

### NO_FACE 계열 세션 (빈 화면, 측면 등): 잘못된 PLAY 횟수, 재생 상태 시간 비율

| label | position | distance | env | t | hold_s | wrong_play | play_ratio | pause_latency_s_est |
|---|---|---|---|---|---|---|---|---|
| NO_FACE | - | - | NORMAL | 0.400 | 2.500 | 0 | 0.000 | 2.500 |
| NO_FACE | - | - | NORMAL | 0.400 | 5 | 0 | 0.000 | 5 |
| NO_FACE | - | - | NORMAL | 0.400 | 7.500 | 0 | 0.000 | 7.500 |
| NO_FACE | - | - | NORMAL | 0.400 | 10 | 0 | 0.000 | 10 |
| NO_FACE | - | - | NORMAL | 0.500 | 2.500 | 0 | 0.000 | 2.500 |
| NO_FACE | - | - | NORMAL | 0.500 | 5 | 0 | 0.000 | 5 |
| NO_FACE | - | - | NORMAL | 0.500 | 7.500 | 0 | 0.000 | 7.500 |
| NO_FACE | - | - | NORMAL | 0.500 | 10 | 0 | 0.000 | 10 |
| NO_FACE | - | - | NORMAL | 0.600 | 2.500 | 0 | 0.000 | 2.500 |
| NO_FACE | - | - | NORMAL | 0.600 | 5 | 0 | 0.000 | 5 |
| NO_FACE | - | - | NORMAL | 0.600 | 7.500 | 0 | 0.000 | 7.500 |
| NO_FACE | - | - | NORMAL | 0.600 | 10 | 0 | 0.000 | 10 |

# 환경: esp32 3.3.12 / ESP-NN off

## 검출률 / 오탐률

| model_id | label | position | distance | env | metric | sessions | frames | invalid_msgs | face_rate |
|---|---|---|---|---|---|---|---|---|---|
| ei-541658-fomo01-int8 | FACE | CENTER | 50cm | NORMAL | detection_rate | 1 | 25 | 0 | 0.600 |
| ei-541658-fomo01-int8 | FACE | CENTER | 80cm | NORMAL | detection_rate | 1 | 25 | 0 | 0.000 |
| ei-541658-fomo01-int8 | FACE | CENTER | 120cm | NORMAL | detection_rate | 1 | 26 | 0 | 0.000 |
| ei-541658-fomo01-int8 | LEFT_45 | CENTER | 50cm | NORMAL | false_positive_rate | 1 | 25 | 0 | 0.200 |
| ei-541658-fomo01-int8 | NO_FACE | - | - | NORMAL | false_positive_rate | 1 | 25 | 0 | 0.000 |
| ei-541658-fomo01-int8 | RIGHT_45 | CENTER | 50cm | NORMAL | false_positive_rate | 1 | 25 | 0 | 0.320 |

## confidence 임계값별 비율 (저장된 confidence ≥ t, raw_face_detected 와 무관)

기기 출력 임계값(측정 조건 표 device_threshold) 미만 박스는 기기가 출력하지 않으므로 그보다 낮은 t 는 의미 없음.

| label | position | distance | env | rate@0.3 | rate@0.4 | rate@0.5 | rate@0.6 | rate@0.7 | rate@0.8 | rate@0.9 |
|---|---|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 0.920 | 0.880 | 0.800 | 0.600 | 0.480 | 0.320 | 0.120 |
| FACE | CENTER | 80cm | NORMAL | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| FACE | CENTER | 120cm | NORMAL | 0.038 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.720 | 0.600 | 0.320 | 0.200 | 0.040 | 0.040 | 0.000 |
| NO_FACE | - | - | NORMAL | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.760 | 0.480 | 0.400 | 0.320 | 0.160 | 0.000 | 0.000 |

## 성능 / 안정성

| label | position | distance | env | inference_ms_mean | inference_ms_p50 | inference_ms_p95 | fps | transitions | seq_loss_rate |
|---|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 2275.000 | 2275.000 | 2275.000 | 0.420 | 8 | 0.000 |
| FACE | CENTER | 80cm | NORMAL | 2275.000 | 2275.000 | 2275.000 | 0.420 | 0 | 0.000 |
| FACE | CENTER | 120cm | NORMAL | 2275.000 | 2275.000 | 2275.000 | 0.420 | 0 | 0.000 |
| LEFT_45 | CENTER | 50cm | NORMAL | 2275.000 | 2275.000 | 2275.000 | 0.419 | 8 | 0.000 |
| NO_FACE | - | - | NORMAL | 2275.000 | 2275.000 | 2275.000 | 0.420 | 0 | 0.000 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 2275.000 | 2275.000 | 2275.000 | 0.419 | 6 | 0.000 |

## Debounce 시뮬레이션 (N 프레임 연속 시 전환)

`added_ms` = (N-1) × 평균 프레임 간격: 실제 전환이 늦어지는 추정 시간.

| label | position | distance | env | debounce1_transitions | debounce1_added_ms | debounce2_transitions | debounce2_added_ms | debounce3_transitions | debounce3_added_ms | debounce4_transitions | debounce4_added_ms | debounce5_transitions | debounce5_added_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 8 | 0.000 | 6 | 2381.542 | 2 | 4763.083 | 2 | 7144.625 | 2 | 9526.167 |
| FACE | CENTER | 80cm | NORMAL | 0 | 0.000 | 0 | 2378.917 | 0 | 4757.833 | 0 | 7136.750 | 0 | 9515.667 |
| FACE | CENTER | 120cm | NORMAL | 0 | 0.000 | 0 | 2378.120 | 0 | 4756.240 | 0 | 7134.360 | 0 | 9512.480 |
| LEFT_45 | CENTER | 50cm | NORMAL | 8 | 0.000 | 2 | 2384.167 | 0 | 4768.333 | 0 | 7152.500 | 0 | 9536.667 |
| NO_FACE | - | - | NORMAL | 0 | 0.000 | 0 | 2377.583 | 0 | 4755.167 | 0 | 7132.750 | 0 | 9510.333 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 6 | 0.000 | 4 | 2384.708 | 2 | 4769.417 | 2 | 7154.125 | 2 | 9538.833 |

## 비대칭 Debounce 시뮬레이션 (추정)

저장된 confidence ≥ t 를 검출로 보고, PLAY 는 검출 1회 즉시, PAUSE 는 마지막 검출 후 hold 초 경과 시.
시간은 실제 프레임 수신 간격(uptime_ms) 기준. **실측이 아닌 시뮬레이션 결과**이며,
`pause_latency_s_est` 는 hold 값 그대로인 추정치(실제 반응 지연은 미측정).
한 번도 검출되지 않은 세션은 PAUSE 오류 0 / 재생 비율 0 이므로 debounce 로 해결할 수 없다.

### FACE 세션: 잘못된 PAUSE (정면인데 멈춤), 재생 상태 시간 비율

| label | position | distance | env | t | hold_s | wrong_pause | play_ratio | pause_latency_s_est |
|---|---|---|---|---|---|---|---|---|
| FACE | CENTER | 50cm | NORMAL | 0.400 | 2.500 | 2 | 0.879 | 2.500 |
| FACE | CENTER | 50cm | NORMAL | 0.400 | 5 | 1 | 0.963 | 5 |
| FACE | CENTER | 50cm | NORMAL | 0.400 | 7.500 | 0 | 1.000 | 7.500 |
| FACE | CENTER | 50cm | NORMAL | 0.400 | 10 | 0 | 1.000 | 10 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 2.500 | 3 | 0.798 | 2.500 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 5 | 2 | 0.925 | 5 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 7.500 | 0 | 1.000 | 7.500 |
| FACE | CENTER | 50cm | NORMAL | 0.500 | 10 | 0 | 1.000 | 10 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 2.500 | 4 | 0.592 | 2.500 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 5 | 3 | 0.762 | 5 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 7.500 | 1 | 0.881 | 7.500 |
| FACE | CENTER | 50cm | NORMAL | 0.600 | 10 | 1 | 0.925 | 10 |
| FACE | CENTER | 80cm | NORMAL | 0.400 | 2.500 | 0 | 0.000 | 2.500 |
| FACE | CENTER | 80cm | NORMAL | 0.400 | 5 | 0 | 0.000 | 5 |
| FACE | CENTER | 80cm | NORMAL | 0.400 | 7.500 | 0 | 0.000 | 7.500 |
| FACE | CENTER | 80cm | NORMAL | 0.400 | 10 | 0 | 0.000 | 10 |
| FACE | CENTER | 80cm | NORMAL | 0.500 | 2.500 | 0 | 0.000 | 2.500 |
| FACE | CENTER | 80cm | NORMAL | 0.500 | 5 | 0 | 0.000 | 5 |
| FACE | CENTER | 80cm | NORMAL | 0.500 | 7.500 | 0 | 0.000 | 7.500 |
| FACE | CENTER | 80cm | NORMAL | 0.500 | 10 | 0 | 0.000 | 10 |
| FACE | CENTER | 80cm | NORMAL | 0.600 | 2.500 | 0 | 0.000 | 2.500 |
| FACE | CENTER | 80cm | NORMAL | 0.600 | 5 | 0 | 0.000 | 5 |
| FACE | CENTER | 80cm | NORMAL | 0.600 | 7.500 | 0 | 0.000 | 7.500 |
| FACE | CENTER | 80cm | NORMAL | 0.600 | 10 | 0 | 0.000 | 10 |
| FACE | CENTER | 120cm | NORMAL | 0.400 | 2.500 | 0 | 0.000 | 2.500 |
| FACE | CENTER | 120cm | NORMAL | 0.400 | 5 | 0 | 0.000 | 5 |
| FACE | CENTER | 120cm | NORMAL | 0.400 | 7.500 | 0 | 0.000 | 7.500 |
| FACE | CENTER | 120cm | NORMAL | 0.400 | 10 | 0 | 0.000 | 10 |
| FACE | CENTER | 120cm | NORMAL | 0.500 | 2.500 | 0 | 0.000 | 2.500 |
| FACE | CENTER | 120cm | NORMAL | 0.500 | 5 | 0 | 0.000 | 5 |
| FACE | CENTER | 120cm | NORMAL | 0.500 | 7.500 | 0 | 0.000 | 7.500 |
| FACE | CENTER | 120cm | NORMAL | 0.500 | 10 | 0 | 0.000 | 10 |
| FACE | CENTER | 120cm | NORMAL | 0.600 | 2.500 | 0 | 0.000 | 2.500 |
| FACE | CENTER | 120cm | NORMAL | 0.600 | 5 | 0 | 0.000 | 5 |
| FACE | CENTER | 120cm | NORMAL | 0.600 | 7.500 | 0 | 0.000 | 7.500 |
| FACE | CENTER | 120cm | NORMAL | 0.600 | 10 | 0 | 0.000 | 10 |

### NO_FACE 계열 세션 (빈 화면, 측면 등): 잘못된 PLAY 횟수, 재생 상태 시간 비율

| label | position | distance | env | t | hold_s | wrong_play | play_ratio | pause_latency_s_est |
|---|---|---|---|---|---|---|---|---|
| LEFT_45 | CENTER | 50cm | NORMAL | 0.400 | 2.500 | 4 | 0.589 | 2.500 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.400 | 5 | 3 | 0.717 | 5 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.400 | 7.500 | 2 | 0.798 | 7.500 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.400 | 10 | 1 | 0.833 | 10 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.500 | 2.500 | 2 | 0.338 | 2.500 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.500 | 5 | 2 | 0.421 | 5 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.500 | 7.500 | 2 | 0.465 | 7.500 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.500 | 10 | 2 | 0.508 | 10 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.600 | 2.500 | 4 | 0.217 | 2.500 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.600 | 5 | 2 | 0.379 | 5 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.600 | 7.500 | 2 | 0.423 | 7.500 |
| LEFT_45 | CENTER | 50cm | NORMAL | 0.600 | 10 | 2 | 0.466 | 10 |
| NO_FACE | - | - | NORMAL | 0.400 | 2.500 | 0 | 0.000 | 2.500 |
| NO_FACE | - | - | NORMAL | 0.400 | 5 | 0 | 0.000 | 5 |
| NO_FACE | - | - | NORMAL | 0.400 | 7.500 | 0 | 0.000 | 7.500 |
| NO_FACE | - | - | NORMAL | 0.400 | 10 | 0 | 0.000 | 10 |
| NO_FACE | - | - | NORMAL | 0.500 | 2.500 | 0 | 0.000 | 2.500 |
| NO_FACE | - | - | NORMAL | 0.500 | 5 | 0 | 0.000 | 5 |
| NO_FACE | - | - | NORMAL | 0.500 | 7.500 | 0 | 0.000 | 7.500 |
| NO_FACE | - | - | NORMAL | 0.500 | 10 | 0 | 0.000 | 10 |
| NO_FACE | - | - | NORMAL | 0.600 | 2.500 | 0 | 0.000 | 2.500 |
| NO_FACE | - | - | NORMAL | 0.600 | 5 | 0 | 0.000 | 5 |
| NO_FACE | - | - | NORMAL | 0.600 | 7.500 | 0 | 0.000 | 7.500 |
| NO_FACE | - | - | NORMAL | 0.600 | 10 | 0 | 0.000 | 10 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.400 | 2.500 | 6 | 0.512 | 2.500 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.400 | 5 | 3 | 0.762 | 5 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.400 | 7.500 | 2 | 0.881 | 7.500 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.400 | 10 | 1 | 0.916 | 10 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.500 | 2.500 | 5 | 0.427 | 2.500 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.500 | 5 | 3 | 0.637 | 5 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.500 | 7.500 | 1 | 0.756 | 7.500 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.500 | 10 | 1 | 0.800 | 10 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.600 | 2.500 | 3 | 0.339 | 2.500 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.600 | 5 | 3 | 0.470 | 5 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.600 | 7.500 | 2 | 0.595 | 7.500 |
| RIGHT_45 | CENTER | 50cm | NORMAL | 0.600 | 10 | 2 | 0.683 | 10 |
