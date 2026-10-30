import json
from pathlib import Path

import analyzer
import common
from collector import build_record

FIXTURES = Path(__file__).parent / "fixtures"


def mock_det(seq, face, up=None):
    """mock 계약: confidence / inference_ms / bbox 없음."""
    return {"schema_version": "1.0", "device_id": "d1", "seq": seq, "uptime_ms": seq * 200 if up is None else up,
            "source": "mock", "model_id": "mock-v1", "raw_face_detected": face}


def records(payloads, kind="detection", label="FACE"):
    ctx = {"label": label, "position": "CENTER", "distance": "50cm", "env": "NORMAL"}
    out = []
    for i, p in enumerate(payloads):
        r = build_record(f"smart-media/d1/{kind}", json.dumps(p).encode(), ctx)
        r["received_at"] = i
        out.append(r)
    return out


def meta(label="FACE", expected=True):
    return {"model_id": "m", "label": label, "distance": "50cm", "env": "NORMAL", "expected_face": expected}


def test_fixture_payloads_match_contract():
    [(_, recs)] = analyzer.load_sessions(FIXTURES / "edge_impulse_session")
    for r in recs:
        assert common.validate("detection", r["payload"]) == []


def test_edge_impulse_fixture_metrics():
    # seq 0,1,2,4,5 (3 유실) / conf .9 .5 0 .7 .35 / raw(≥0.6) T F F T F
    [row] = analyzer.aggregate(analyzer.load_sessions(FIXTURES / "edge_impulse_session"))
    assert row["frames"] == 5 and row["metric"] == "detection_rate" and row["position"] == "CENTER"
    assert row["face_rate"] == 0.4
    # 스윕은 저장된 confidence 기준 (raw 와 무관)
    assert row["rate@0.3"] == 0.8 and row["rate@0.5"] == 0.6 and row["rate@0.8"] == 0.2
    assert row["rate@0.9"] == 0.2
    assert row["transitions"] == 3
    assert abs(row["seq_loss_rate"] - 1 / 6) < 1e-9
    assert row["inference_ms_mean"] == 300 and row["inference_ms_p50"] == 300
    assert row["inference_ms_p95"] == 480
    assert row["debounce1_transitions"] == 3 and row["debounce2_transitions"] == 1  # T→F(연속 2)
    assert row["debounce3_transitions"] == 0


def test_mock_without_optional_fields():
    rs = records([mock_det(0, False), mock_det(1, True)], label="NO_FACE") + records([{"bad": 1}], label="NO_FACE")
    [row] = analyzer.aggregate([(meta("NO_FACE", False), rs)])
    assert row["metric"] == "false_positive_rate"
    assert row["face_rate"] == 0.5 and row["invalid_msgs"] == 1 and row["frames"] == 2
    assert row["rate@0.5"] is None and row["inference_ms_mean"] is None


def test_fps_from_telemetry_else_uptime():
    tel = {"schema_version": "1.0", "device_id": "d1", "seq": 0, "uptime_ms": 0, "model_id": "m", "fps": 4.0}
    [row] = analyzer.aggregate([(meta(), records([mock_det(0, True), mock_det(1, True)]) + records([tel], "telemetry"))])
    assert row["fps"] == 4.0
    [row] = analyzer.aggregate([(meta(), records([mock_det(0, True, up=0), mock_det(1, True, up=250)]))])
    assert row["fps"] == 4.0


def test_seq_reset_and_debounce():
    assert analyzer.seq_stats([5, 6, 8, 0, 1]) == (5, 6)
    assert analyzer.debounce([1, 0, 1, 1, 0, 0, 0], 2) == [1, 1, 1, 1, 1, 0, 0]


def test_collector_strips_non_schema_fields():
    p = mock_det(0, True) | {"image": "base64...", "state": "FRONT_PRESENT"}
    [r] = records([p])
    assert r["valid"] is False and "image" not in r["payload"] and "state" not in r["payload"]
    r = build_record("smart-media/d1/detection", b"not json", {})
    assert r["payload"] is None and r["valid"] is False
