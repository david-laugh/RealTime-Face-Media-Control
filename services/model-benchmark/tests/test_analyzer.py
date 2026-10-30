import json

import analyzer
from collector import build_record


def det(seq, face, conf, inf=100, up=None, dev="d1"):
    return {"schema_version": "1.0", "device_id": dev, "seq": seq, "uptime_ms": up if up is not None else seq * 200,
            "model_id": "m", "raw_face_detected": face, "confidence": conf,
            "bbox": {"x": 0, "y": 0, "w": 0.1, "h": 0.1} if face else None,
            "inference_ms": inf, "state": "FRONT_PRESENT" if face else "NOT_PRESENT"}


def records(payloads, kind="detection", label="FACE"):
    ctx = {"label": label, "distance": "50cm", "env": "NORMAL"}
    out = []
    for i, p in enumerate(payloads):
        r = build_record(f"smart-media/d1/{kind}", json.dumps(p).encode(), ctx)
        r["received_at"] = i
        out.append(r)
    return out


def meta(label="FACE", expected=True):
    return {"model_id": "m", "label": label, "distance": "50cm", "env": "NORMAL", "expected_face": expected}


def test_rates_thresholds_transitions_seq_loss():
    # seq 0,1,2,4,5 (3 유실) / 판정 T T F T T / conf .9 .5 0 .7 .35
    ps = [det(0, True, .9, 100), det(1, True, .5, 200), det(2, False, 0, 300),
          det(4, True, .7, 400), det(5, True, .35, 500)]
    [row] = analyzer.aggregate([(meta(), records(ps))])
    assert row["frames"] == 5 and row["metric"] == "detection_rate"
    assert row["face_rate"] == 0.8
    assert row["rate@0.3"] == 0.8 and row["rate@0.5"] == 0.6 and row["rate@0.8"] == 0.2
    assert row["rate@0.9"] == 0.2
    assert row["transitions"] == 2
    assert abs(row["seq_loss_rate"] - 1 / 6) < 1e-9
    assert row["inference_ms_mean"] == 300 and row["inference_ms_p50"] == 300
    assert row["inference_ms_p95"] == 480
    assert row["debounce1_transitions"] == 2 and row["debounce2_transitions"] == 0


def test_false_positive_and_invalid_excluded():
    rs = records([det(0, False, 0), det(1, True, .6)], label="NO_FACE")
    rs += records([{"bad": 1}], label="NO_FACE")
    [row] = analyzer.aggregate([(meta("NO_FACE", False), rs)])
    assert row["metric"] == "false_positive_rate"
    assert row["face_rate"] == 0.5 and row["invalid_msgs"] == 1 and row["frames"] == 2


def test_fps_from_telemetry_else_uptime():
    tel = {"schema_version": "1.0", "device_id": "d1", "seq": 0, "uptime_ms": 0, "model_id": "m", "fps": 4.0}
    [row] = analyzer.aggregate([(meta(), records([det(0, True, .9), det(1, True, .9)]) + records([tel], "telemetry"))])
    assert row["fps"] == 4.0
    [row] = analyzer.aggregate([(meta(), records([det(0, True, .9, up=0), det(1, True, .9, up=250)]))])
    assert row["fps"] == 4.0


def test_seq_reset_and_debounce():
    assert analyzer.seq_stats([5, 6, 8, 0, 1]) == (5, 6)
    assert analyzer.debounce([1, 0, 1, 1, 0, 0, 0], 2) == [1, 1, 1, 1, 1, 0, 0]


def test_collector_strips_non_schema_fields():
    p = det(0, True, .9) | {"image": "base64..."}
    [r] = records([p])
    assert r["valid"] is False and "image" not in r["payload"]
    r = build_record("smart-media/d1/detection", b"not json", {})
    assert r["payload"] is None and r["valid"] is False


def test_threshold_sweep_uses_stored_confidence():
    # raw=False 이지만 confidence 0.4 (bridge 임계값 0.5 미만) → rate@0.3 에는 포함
    ps = [det(0, False, .4), det(1, True, .6)]
    [row] = analyzer.aggregate([(meta(), records(ps))])
    assert row["face_rate"] == 0.5 and row["rate@0.3"] == 1.0 and row["rate@0.5"] == 0.5
