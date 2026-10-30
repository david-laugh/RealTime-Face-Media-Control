"""공통 유틸: 환경변수, 스키마 검증, MQTT 클라이언트, 토픽 규칙."""
import json
import os
from pathlib import Path

import paho.mqtt.client as mqtt
from jsonschema import Draft202012Validator

SERVICE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = Path(os.environ.get("BENCHMARK_SCHEMA_DIR", SERVICE_DIR / "schemas"))
RESULTS_DIR = Path(os.environ.get("BENCHMARK_RESULTS_DIR", SERVICE_DIR / "results"))
CASES_FILE = Path(os.environ.get("BENCHMARK_CASES_FILE", SERVICE_DIR / "test-cases" / "cases.yaml"))
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

SCHEMA_VERSION = "1.0"
KINDS = ("detection", "telemetry")
DEFAULT_MODEL_ID = "ei-541658-fomo01-int8"


def topic(device_id: str, kind: str) -> str:
    return f"smart-media/{device_id}/{kind}"


def kind_of(topic_str: str) -> str | None:
    parts = topic_str.split("/")
    if len(parts) == 3 and parts[0] == "smart-media" and parts[2] in KINDS:
        return parts[2]
    return None


_validators: dict[str, Draft202012Validator] = {}


def validator(kind: str) -> Draft202012Validator:
    if kind not in _validators:
        schema = json.loads((SCHEMA_DIR / f"{kind}.schema.json").read_text(encoding="utf-8"))
        _validators[kind] = Draft202012Validator(schema)
    return _validators[kind]


def schema_fields(kind: str) -> set[str]:
    return set(validator(kind).schema["properties"])


def validate(kind: str, payload) -> list[str]:
    """에러 위치/종류만 반환 (값은 담지 않음)."""
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}:{e.validator}"
        for e in validator(kind).iter_errors(payload)
    ]


def mqtt_client(client_id: str = "") -> mqtt.Client:
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    return [{**defaults, **c} for c in data["cases"]]
