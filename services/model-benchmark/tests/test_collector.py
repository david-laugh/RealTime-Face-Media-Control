import io
import json

from collector import Recorder, countdown

DET = json.dumps({"schema_version": "1.0", "device_id": "d1", "seq": 0, "uptime_ms": 0,
                  "source": "mock", "model_id": "mock-v1", "raw_face_detected": True}).encode()
TOPIC = "smart-media/d1/detection"


def test_messages_before_start_are_not_saved():
    fh = io.StringIO()
    rec = Recorder(fh, {"label": "FACE"})
    assert rec.handle(TOPIC, DET) is False and rec.handle(TOPIC, DET) is False
    assert fh.getvalue() == ""
    rec.start()
    assert rec.handle(TOPIC, DET) is True
    rec.stop()
    assert rec.handle(TOPIC, DET) is False
    assert len(fh.getvalue().splitlines()) == 1
    assert rec.counts["detection"] == 1 and rec.counts["dropped_before_start"] == 3


def test_countdown_prints_each_second():
    sleeps, lines = [], []
    countdown(3, sleep=sleeps.append, out=lines.append)
    assert sleeps == [1, 1, 1] and len(lines) == 3
    assert "3초" in lines[0] and "1초" in lines[-1]
    sleeps.clear()
    countdown(0, sleep=sleeps.append, out=lines.append)
    assert sleeps == []
