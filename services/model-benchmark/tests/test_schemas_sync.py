from pathlib import Path

import pytest

SERVICE = Path(__file__).resolve().parent.parent
CONTRACTS = SERVICE.parent.parent / "contracts" / "mqtt"


@pytest.mark.parametrize("name", ["detection.schema.json", "telemetry.schema.json", "status.schema.json"])
def test_schema_copy_matches_contract(name):
    if not CONTRACTS.exists():
        pytest.skip("contracts/ 없음 (컨테이너 내부 등)")
    assert (SERVICE / "schemas" / name).read_bytes() == (CONTRACTS / name).read_bytes(), \
        f"schemas/{name} 가 contracts 와 다름 → 다시 복사하세요"
