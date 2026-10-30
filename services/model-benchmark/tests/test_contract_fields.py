"""main #3 계약: edge_impulse 는 confidence 필수 + threshold, mock 은 confidence 미전송."""
import common
from mock_publisher import make_detection
from test_serial_parser import REAL_FACE, REAL_NO_FACE, detections, run


def test_edge_impulse_sends_threshold_and_confidence():
    _, pubs, _ = run(REAL_NO_FACE + REAL_FACE + [REAL_FACE[0], REAL_FACE[1],
                     "  face (0.599960) [ x: 8, y: 8, width: 8, height: 8 ]\n"])
    dets = detections(pubs)
    assert len(dets) == 3
    for d in dets:
        assert d["source"] == "edge_impulse" and d["threshold"] == 0.6
        assert "confidence" in d
        assert d["raw_face_detected"] == (d["confidence"] >= d["threshold"])
        assert common.validate("detection", d) == []
    assert dets[0]["confidence"] == 0
    # 반올림 후 0.6 → 판정도 반올림 값 기준
    assert dets[2]["confidence"] == 0.6 and dets[2]["raw_face_detected"] is True


def test_mock_omits_model_fields():
    for face in (True, False):
        d = make_detection("mock-xiao-01", "mock-v1", 0, 0, face)
        assert d["source"] == "mock"
        assert not {"confidence", "threshold", "inference_ms", "bbox"} & set(d)
        assert common.validate("detection", d) == []
