from conftest import detection_payload, status_payload
from messages import parse_detection, parse_status
from state_manager import StateManager

TIMEOUT = 25000


def make(clock):
    return StateManager(TIMEOUT, "xiao-01", mono_ms=clock, wall_ms=lambda: 1793320123456)


def det(face, seq=1, device_id="xiao-01"):
    return parse_detection(detection_payload(face, seq, device_id), device_id)


def test_startup_is_pause(clock):
    sm = make(clock)
    [snap] = sm.snapshot_messages()
    assert snap["command"] == "PAUSE"
    assert snap["detail"] == "SYSTEM_STARTUP"
    assert snap["face_detected"] is None
    assert snap["source"] == "system"


def test_t01_true_plays(clock):
    msg = make(clock).handle_detection(det(True))
    assert msg["command"] == "PLAY"
    assert msg["detail"] == "FACE_PRESENT"
    assert msg["reason"] == "FRONT_FACE_PRESENT"  # web-ui enum
    assert msg["confidence"] is None
    assert msg["face_detected"] is True
    assert msg["source"] == "mock"
    assert msg["ts_server_ms"] == 1793320123456


def test_t02_false_pauses(clock):
    sm = make(clock)
    sm.handle_detection(det(True, 1))
    msg = sm.handle_detection(det(False, 2))
    assert msg["command"] == "PAUSE"
    assert msg["detail"] == "FACE_ABSENT"
    assert msg["face_detected"] is False


def test_t03_true_true_no_duplicate(clock):
    sm = make(clock)
    assert sm.handle_detection(det(True, 1))["command"] == "PLAY"
    assert sm.handle_detection(det(True, 2)) is None


def test_t04_false_false_no_duplicate(clock):
    sm = make(clock)
    # Startup is already PAUSE, so false never produces a command.
    assert sm.handle_detection(det(False, 1)) is None
    assert sm.handle_detection(det(False, 2)) is None
    sm.handle_detection(det(True, 3))
    assert sm.handle_detection(det(False, 4))["command"] == "PAUSE"
    assert sm.handle_detection(det(False, 5)) is None


def test_t05_timeout_pauses_once(clock):
    sm = make(clock)
    sm.handle_detection(det(True))
    clock.advance(TIMEOUT - 1)
    assert sm.check_timeouts() == []
    clock.advance(1)
    [msg] = sm.check_timeouts()
    assert msg["command"] == "PAUSE"
    assert msg["detail"] == "DEVICE_TIMEOUT"
    assert msg["face_detected"] is None
    assert msg["source"] == "system"
    clock.advance(10000)
    assert sm.check_timeouts() == []
    assert sm.state_dict()["devices"]["xiao-01"]["timed_out"] is True


def test_t05_true_after_timeout_plays_again(clock):
    sm = make(clock)
    sm.handle_detection(det(True, 1))
    clock.advance(TIMEOUT)
    sm.check_timeouts()
    msg = sm.handle_detection(det(True, 2))
    assert msg["command"] == "PLAY"
    assert sm.state_dict()["devices"]["xiao-01"]["timed_out"] is False


def test_t06_offline_pauses(clock):
    sm = make(clock)
    sm.handle_detection(det(True))
    msg = sm.handle_status(parse_status(status_payload(False), "xiao-01"))
    assert msg["command"] == "PAUSE"
    assert msg["detail"] == "DEVICE_OFFLINE"
    assert msg["reason"] == "DEVICE_TIMEOUT"  # web-ui: "카메라 끊김"
    assert msg["face_detected"] is None


def test_online_alone_does_not_play(clock):
    sm = make(clock)
    assert sm.handle_status(parse_status(status_payload(True), "xiao-01")) is None
    assert sm.snapshot_messages()[0]["command"] == "PAUSE"


def test_t10_periodic_10s_never_times_out(clock):
    sm = make(clock)
    commands = []
    for seq in range(1, 13):  # 2 minutes of alternating mock detections
        msg = sm.handle_detection(det(seq % 2 == 1, seq))
        commands.append(msg["command"] if msg else None)
        for _ in range(10):
            clock.advance(1000)
            assert sm.check_timeouts() == []
    assert commands == ["PLAY", "PAUSE"] * 6


def test_broker_disconnect_pauses(clock):
    sm = make(clock)
    sm.handle_detection(det(True))
    [msg] = sm.handle_broker_disconnected()
    assert msg["command"] == "PAUSE"
    assert msg["detail"] == "BROKER_DISCONNECTED"
    assert sm.handle_broker_disconnected() == []


def test_devices_are_independent(clock):
    sm = make(clock)
    sm.handle_detection(det(True, 1, "xiao-01"))
    msg = sm.handle_detection(det(True, 1, "xiao-02"))
    assert msg["device_id"] == "xiao-02" and msg["command"] == "PLAY"
    sm.handle_detection(det(False, 2, "xiao-02"))
    assert sm.state_dict()["devices"]["xiao-01"]["command"] == "PLAY"


def test_confidence_passed_through_from_real_model(clock):
    sm = make(clock)
    real = parse_detection(detection_payload(True, 1, confidence=0.84, inference_ms=700), "xiao-01")
    assert sm.handle_detection(real)["confidence"] == 0.84
