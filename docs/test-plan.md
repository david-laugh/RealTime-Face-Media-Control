# Test Plan

> ⚠️ 테스트 계획 템플릿입니다. 테스트 코드는 아직 작성되지 않았습니다.

## 1. 범위

| 레벨 | 대상 | 담당 | 비고 |
|------|------|------|------|
| Unit | Control Gateway State Machine | Member B | `services/control-gateway/tests/` |
| Unit | Web UI 메시지 처리 | Member C | TBD |
| Contract | MQTT / WebSocket JSON Schema 검증 | Member D | `contracts/` |
| Device | Firmware 추론 / MQTT publish | Member A | 실기기 |
| Integration | XIAO → Broker → Gateway → Web UI → YouTube | Member D | Docker Compose |
| Performance | 모델 Benchmark | Member D | [`model-benchmark.md`](./model-benchmark.md) |

## 2. 테스트 케이스 (템플릿)

| ID | 시나리오 | 사전 조건 | 절차 | 기대 결과 | 결과 |
|----|----------|-----------|------|-----------|------|
| TC-01 | 정면 응시 시 재생 | 영상 일시정지 상태 | 카메라 정면 응시 | PLAY | |
| TC-02 | 시선 이탈 시 일시정지 | 영상 재생 상태 | 측면으로 회전 | PAUSE | |
| TC-03 | 자리 이탈 시 일시정지 | 영상 재생 상태 | 화면 앞에서 이탈 | PAUSE | |
| TC-04 | 디바이스 연결 끊김 | 영상 재생 상태 | XIAO 전원 차단 | PAUSE (DEVICE_TIMEOUT) | |
| TC-05 | Schema 위반 메시지 | – | 잘못된 JSON publish | Gateway가 무시/로그 | |
| TC-06 | Broker 재시작 | 정상 동작 중 | mqtt-broker 재시작 | 자동 재연결 | |

## 3. 합격 기준 (TBD)

- [ ] PLAY transition latency ≤ TBD ms
- [ ] PAUSE transition latency ≤ TBD ms
- [ ] Side / Back / Empty false positive rate ≤ TBD %
- [ ] State flicker count ≤ TBD 회 / 분
