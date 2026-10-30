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
    assert det["inference_ms"] == 152 and det["state"] == "FRONT_PRESENT"
    for t, m in pubs:
        assert common.validate(common.kind_of(t), m) == []


def test_no_detection_frame():
    _, pubs, _ = run([PRED, HEADER, PRED, HEADER])
    dets = detections(pubs)
    assert len(dets) == 2 and [d["seq"] for d in dets] == [0, 1]
    assert dets[0]["raw_face_detected"] is False
    assert dets[0]["confidence"] == 0 and dets[0]["bbox"] is None
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
