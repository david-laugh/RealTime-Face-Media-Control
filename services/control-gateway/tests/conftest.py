import json
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_DIR.parents[1]
sys.path.insert(0, str(SERVICE_DIR / "src"))


class FakeClock:
    def __init__(self, start_ms: int = 1_000_000) -> None:
        self.now = start_ms

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def load_schema():
    def _load(rel: str) -> dict:
        return json.loads((REPO_ROOT / "contracts" / rel).read_text(encoding="utf-8"))

    return _load


def detection_payload(face: bool, seq: int = 1, device_id: str = "xiao-01", **extra) -> bytes:
    data = {
        "schema_version": "1.0",
        "device_id": device_id,
        "seq": seq,
        "uptime_ms": seq * 10000,
        "source": "mock",
        "model_id": "mock-v1",
        "raw_face_detected": face,
        **extra,
    }
    return json.dumps(data).encode()


def status_payload(online: bool, device_id: str = "xiao-01") -> bytes:
    return json.dumps(
        {"schema_version": "1.0", "device_id": device_id, "source": "mock", "online": online}
    ).encode()
