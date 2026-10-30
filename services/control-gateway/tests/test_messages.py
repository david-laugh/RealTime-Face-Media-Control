import json

import pytest

from conftest import detection_payload, ei_payload
from messages import MessageError, parse_detection, parse_status, split_topic


def test_valid_mock_detection():
    d = parse_detection(detection_payload(True, 7), "xiao-01")
    assert d.raw_face_detected is True and d.seq == 7 and d.source == "mock"
    assert d.confidence is None and d.inference_ms is None


def test_optional_model_fields_accepted():
    d = parse_detection(ei_payload(True, 0.84, threshold=0.6, inference_ms=731), "xiao-01")
    assert d.confidence == 0.84 and d.threshold == 0.6 and d.inference_ms == 731
    assert d.source == "edge_impulse"


@pytest.mark.parametrize("raw", [b"0", b"0.0", b"0.000"])
def test_edge_impulse_confidence_zero_is_kept(raw):
    # 0 means "no valid face score" and must not turn into None/null.
    payload = ei_payload(False, 0.5).replace(b"0.5", raw)
    d = parse_detection(payload, "xiao-01")
    assert d.confidence == 0.0 and d.confidence is not None
    assert d.raw_face_detected is False


def test_edge_impulse_below_threshold_score_is_kept():
    d = parse_detection(ei_payload(False, 0.35, threshold=0.6), "xiao-01")
    assert (d.raw_face_detected, d.confidence, d.threshold) == (False, 0.35, 0.6)


@pytest.mark.parametrize("confidence", ["missing", None])
def test_edge_impulse_requires_confidence(confidence):
    data = json.loads(ei_payload(True, 0.9))
    if confidence == "missing":
        del data["confidence"]
    else:
        data["confidence"] = None
    with pytest.raises(MessageError):
        parse_detection(json.dumps(data).encode(), "xiao-01")


def test_threshold_is_optional():
    assert parse_detection(ei_payload(True, 0.9), "xiao-01").threshold is None
    assert parse_detection(detection_payload(True), "xiao-01").threshold is None


def test_mock_confidence_null_accepted_number_rejected():
    assert parse_detection(detection_payload(True, confidence=None), "xiao-01").confidence is None
    with pytest.raises(MessageError):
        parse_detection(detection_payload(True, confidence=0.84), "xiao-01")


@pytest.mark.parametrize(
    "payload",
    [
        b"{not json",
        b"\xff\xfe",
        b"[]",
        b'"true"',
        json.dumps({"device_id": "xiao-01"}).encode(),
    ],
)
def test_t07_invalid_json_or_shape(payload):
    with pytest.raises(MessageError):
        parse_detection(payload, "xiao-01")


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_face_detected", "true"),
        ("raw_face_detected", 1),
        ("seq", "1"),
        ("seq", True),
        ("seq", -1),
        ("schema_version", "2.0"),
        ("source", "camera"),
        ("device_id", "xiao-99"),
        ("confidence", 1.5),
        ("threshold", 1.5),
        ("threshold", "0.6"),
        ("threshold", True),
        ("inference_ms", 1.5),
    ],
)
def test_t07_wrong_types(field, value):
    data = json.loads(detection_payload(True))
    data[field] = value
    with pytest.raises(MessageError):
        parse_detection(json.dumps(data).encode(), "xiao-01")


@pytest.mark.parametrize("field", ["seq", "uptime_ms", "source", "model_id", "raw_face_detected"])
def test_t07_missing_required(field):
    data = json.loads(detection_payload(True))
    del data[field]
    with pytest.raises(MessageError):
        parse_detection(json.dumps(data).encode(), "xiao-01")


def test_status_requires_bool_online():
    ok = {"schema_version": "1.0", "device_id": "xiao-01", "source": "mock", "online": False}
    assert parse_status(json.dumps(ok).encode(), "xiao-01").online is False
    with pytest.raises(MessageError):
        parse_status(json.dumps({**ok, "online": "false"}).encode(), "xiao-01")


def test_split_topic():
    assert split_topic("smart-media/xiao-01/detection", "smart-media") == ("xiao-01", "detection")
    with pytest.raises(MessageError):
        split_topic("other/xiao-01/detection", "smart-media")
