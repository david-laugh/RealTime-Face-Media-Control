# Model Benchmark (compose profile: benchmark)
# 상주 컨테이너. 실행: docker compose exec model-benchmark python src/<script>.py ...
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY schemas/ ./schemas/
COPY test-cases/ ./test-cases/

ENV PYTHONUNBUFFERED=1 \
    MQTT_HOST=mqtt-broker \
    MQTT_PORT=1883 \
    BENCHMARK_RESULTS_DIR=/app/results

CMD ["sh", "-c", "echo \"[model-benchmark] ready (MQTT ${MQTT_HOST}:${MQTT_PORT}, results ${BENCHMARK_RESULTS_DIR})\" && sleep infinity"]
