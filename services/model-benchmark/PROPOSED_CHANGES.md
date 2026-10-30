# Proposed changes outside services/model-benchmark/

이 서비스 담당 범위 밖이라 직접 수정하지 않았습니다. 리뷰 후 반영 부탁드립니다.

## docker-compose.yml

1. **mqtt-broker 포트를 localhost 에만 바인딩** (개인정보/보안: 같은 네트워크의 다른 기기 접근 차단)
   ```yaml
   ports:
     - "127.0.0.1:${MQTT_PORT:-1883}:1883"
   ```
   단, 실기기가 Wi-Fi로 직접 broker에 붙는 단계에서는 재검토 필요.
   (serial_bridge는 호스트에서 실행하므로 localhost 바인딩으로 충분)

2. **model-benchmark에 계약 스키마 mount 및 결과 경로 환경변수** (현재는 `schemas/` 사본 + 동기화 테스트로 대응)
   ```yaml
   environment:
     BENCHMARK_RESULTS_DIR: /app/results
     BENCHMARK_SCHEMA_DIR: /app/contracts
   volumes:
     - ./contracts/mqtt:/app/contracts:ro
   ```

## docs/model-benchmark.md

- 결과 경로가 `results/{model_id}/{YYYYMMDD}/{session}/{messages.jsonl,meta.json}` + `summary.{csv,md}` 로 확정됨을 반영.
- 시리얼 브리지 측정 시 `seq`/`uptime_ms`는 호스트 생성값, `state`는 raw 매핑임을 명시.
