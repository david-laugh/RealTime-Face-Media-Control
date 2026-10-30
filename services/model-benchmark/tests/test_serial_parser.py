import json

import common
from serial_bridge import Bridge, SerialParser

PRED = "Predictions (DSP: 3 ms., Classification: 152 ms., Anomaly: 0 ms.): \r\n"
HEADER = "Object detection bounding boxes:\r\n"
FEATURES = "Features (9216):\r\n"
DUMP = " ".join(f"0x{i:06x}," for i in range(40)) + "\r\n"
SECRET = "SSID=home-wifi password=abc123\r\n"


def run(lines, t0=0.0, dt=0.2):
    logs, pubs = [], []
    parser = SerialParser(log=logs.append)
    bridge = Bridge(lambda t, m: pubs.append((t, m)), "xiao-bench-01", "ei-test", 96, 96, start=0.0)
    t = t0
    for line in lines:
        if line.startswith("Predictions"):
            t += dt
        frame = parser.feed(line, now=t)
        if frame:
            bridge.handle(frame)
    if frame := parser.flush():
        bridge.handle(frame)
    return parser, pubs, logs


def detections(pubs):
    return [m for t, m in pubs if t.endswith("/detection")]


def test_face_frame_normalized_and_valid():
    _, pubs, _ = run([PRED, HEADER,
                      "  face (0.578125) [ x: 24, y: 16, width: 8, height: 8 ]\r\n",
                      "  face (0.812500) [ x: 48, y: 32, width: 16, height: 8 ]\r\n"])
    det = detections(pubs)[0]
    assert det["raw_face_detected"] is True
    assert det["confidence"] == 0.8125
    assert det["bbox"] == {"x": 0.5, "y": 0.3333, "w": 0.1667, "h": 0.0833}
    assert det["inference_ms"] == 152 and det["source"] == "edge_impulse" and "state" not in det
    for t, m in pubs:
        assert common.validate(common.kind_of(t), m) == []


def test_no_detection_frame():
    _, pubs, _ = run([PRED, HEADER, PRED, HEADER])
    dets = detections(pubs)
    assert len(dets) == 2 and [d["seq"] for d in dets] == [0, 1]
    assert dets[0]["raw_face_detected"] is False
    assert dets[0]["confidence"] == 0 and "bbox" not in dets[0]
    tels = [m for t, m in pubs if t.endswith("/telemetry")]
    assert "fps" not in tels[0] and tels[1]["fps"] == 5.0
    assert tels[0]["preprocess_ms"] == 3


def test_malformed_allowlisted_line_logged_as_failure():
    parser, pubs, logs = run(["Predictions (DSP: x ms.)\n", PRED, HEADER, "  face (0.9) [ x: 1, y: 2 ]\n"])
    assert parser.parse_failures == 2 and len(logs) == 2
    assert detections(pubs)[0]["raw_face_detected"] is False


def test_privacy_dump_and_unlisted_lines_not_stored_or_published():
    long_line = "a" * 201 + "\n"
    parser, pubs, logs = run([FEATURES, DUMP, SECRET, long_line, "No objects found\n",
                              PRED, DUMP, HEADER, SECRET,
                              "  face (0.7) [ x: 8, y: 8, width: 8, height: 8 ]\n"])
    assert parser.suspicious == 3          # DUMP x2 + long_line
    assert parser.ignored == 4             # FEATURES, SECRET x2, "No objects found"
    assert any("debug_nn" in l for l in logs)
    blob = json.dumps(pubs) + "".join(logs) + repr({k: v for k, v in vars(parser).items() if k != "log"})
    for needle in ("0x000001", "password", "home-wifi", "aaaa", "Features", "No objects"):
        assert needle not in blob
    assert detections(pubs)[0]["raw_face_detected"] is True
    for t, m in pubs:   # 스키마 필드만
        assert set(m) <= common.schema_fields(common.kind_of(t))


def test_face_label_filter():
    parser = SerialParser(log=lambda m: None)
    pubs = []
    bridge = Bridge(lambda t, m: pubs.append(m), "d", "m", 96, 96, face_labels=["face"], start=0)
    for line in [PRED, HEADER, "  hand (0.9) [ x: 8, y: 8, width: 8, height: 8 ]\n"]:
        parser.feed(line, now=1)
    bridge.handle(parser.flush())
    assert pubs[0]["raw_face_detected"] is False


# 실기기 샘플 (XIAO ESP32S3, 115200 baud). 줄 끝 공백/빈 줄 포함
REAL_NO_FACE = ["Predictions (DSP: 4 ms., Classification: 2275 ms., Anomaly: 0 ms.): \r\n",
                "Object detection bounding boxes:\r\n", "\r\n", "   \r\n"]
REAL_FACE = ["Predictions (DSP: 4 ms., Classification: 2275 ms., Anomaly: 0 ms.): \r\n",
             "Object detection bounding boxes:  \r\n",
             "  face (0.804688) [ x: 40, y: 40, width: 8, height: 8 ]  \r\n", "\r\n"]


def test_real_sample():
    parser, pubs, logs = run(REAL_NO_FACE + REAL_FACE)
    no, yes = detections(pubs)
    assert (no["raw_face_detected"], no["confidence"], "bbox" in no) == (False, 0, False)
    assert yes["raw_face_detected"] is True and yes["confidence"] == 0.8047
    assert yes["bbox"] == {"x": 0.4167, "y": 0.4167, "w": 0.0833, "h": 0.0833}
    assert yes["inference_ms"] == 2275
    tel = [m for t, m in pubs if t.endswith("/telemetry")][0]
    assert tel["preprocess_ms"] == 4 and tel["inference_ms"] == 2275
    assert parser.ignored == parser.suspicious == parser.parse_failures == 0 and not logs


def test_below_threshold_keeps_confidence_for_sweep():
    _, pubs, _ = run([REAL_FACE[0], REAL_FACE[1],
                      "  face (0.312500) [ x: 8, y: 8, width: 8, height: 8 ]\n",
                      "  face (0.250000) [ x: 16, y: 8, width: 8, height: 8 ]\n"])
    det = detections(pubs)[0]
    assert det["raw_face_detected"] is False
    assert det["confidence"] == 0.3125 and "bbox" not in det
    assert common.validate("detection", det) == []


def test_default_threshold_is_model_original_06():
    _, pubs, _ = run([REAL_FACE[0], REAL_FACE[1], "  face (0.550000) [ x: 8, y: 8, width: 8, height: 8 ]\n"])
    det = detections(pubs)[0]
    assert det["raw_face_detected"] is False and det["confidence"] == 0.55


# ---- classification model (xiao_face_presence_example.ino) ----

CLS = ["Predictions (DSP: 4 ms., Classification: 310 ms., Anomaly: 0 ms.): \r\n", "Predictions:\r\n"]


def cls_frame(absent, present):
    top = ("face_present", present) if present > absent else ("face_absent", absent)
    return [*CLS, f"  face_absent: {absent:.5f}\r\n", f"  face_present: {present:.5f}\r\n",
            f"Face presence: {top[0]} ({top[1]:.5f})\r\n"]


def run_cls(lines, threshold=0.5):
    pubs = []
    parser = SerialParser(log=lambda m: None)
    bridge = Bridge(lambda t, m: pubs.append((t, m)), "xiao-bench-01", "ei-1152903-face-presence-binary",
                    96, 96, start=0.0, threshold=threshold)
    for i, line in enumerate(lines):
        if frame := parser.feed(line, now=float(i)):
            bridge.handle(frame)
    if frame := parser.flush():
        bridge.handle(frame)
    return parser, pubs


def test_classification_face_present_and_absent():
    parser, pubs = run_cls(cls_frame(0.08, 0.92) + cls_frame(0.7, 0.3))
    present, absent = detections(pubs)
    assert (present["raw_face_detected"], present["confidence"], present["threshold"]) == (True, 0.92, 0.5)
    assert (absent["raw_face_detected"], absent["confidence"]) == (False, 0.3)
    assert "bbox" not in present and "bbox" not in absent
    assert present["inference_ms"] == 310
    assert parser.parse_failures == 0
    for t, m in pubs:
        assert common.validate(common.kind_of(t), m) == []


def test_classification_below_threshold_keeps_score():
    _, pubs = run_cls(cls_frame(0.45, 0.55), threshold=0.6)
    assert detections(pubs)[0]["raw_face_detected"] is False  # 0.55 kept as confidence for the sweep
    assert detections(pubs)[0]["confidence"] == 0.55


def test_classification_without_face_label_scores_zero():
    _, pubs = run_cls([*CLS, "  something_else: 0.99000\r\n"])
    det = detections(pubs)[0]
    assert det["confidence"] == 0 and det["raw_face_detected"] is False
