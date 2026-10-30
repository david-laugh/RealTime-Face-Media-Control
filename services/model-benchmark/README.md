# model-benchmark

> ⚠️ 아직 구현되지 않았습니다. 현재 Container는 placeholder(`sleep infinity`)로만 실행됩니다.
> Owner: Member D (Benchmark / Integration)

Production runtime 필수 Service가 아니며, Docker Compose profile `benchmark`로만 실행됩니다.

```bash
docker compose --profile benchmark up
```

## 역할 (예정)

- `smart-media/{device_id}/telemetry`, `detection` 메시지 수집
- 모델별 latency / 검출 품질 / 상태 전환 지표 산출
- 측정 계획: [`docs/model-benchmark.md`](../../docs/model-benchmark.md)

## 디렉터리

| Path | 용도 |
|------|------|
| `src/` | Benchmark source (Python 예정) |
| `test-cases/` | Pose / Distance / Environment 테스트 케이스 정의 |
| `results/` | 측정 결과 (Container에 volume mount) |
