import pytest

from conftest import detection_payload, ei_payload, status_payload
from messages import parse_detection, parse_status
from state_manager import DebounceRule, StateManager

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
    real = parse_detection(ei_payload(True, 0.84, 1, threshold=0.6, inference_ms=700), "xiao-01")
    msg = sm.handle_detection(real)
    assert msg["confidence"] == 0.84 and msg["source"] == "edge_impulse"


def test_confidence_zero_reaches_websocket_as_zero(clock):
    sm = make(clock)
    sm.handle_detection(parse_detection(ei_payload(True, 0.9, 1), "xiao-01"))
    msg = sm.handle_detection(parse_detection(ei_payload(False, 0, 2), "xiao-01"))
    assert msg["command"] == "PAUSE" and msg["confidence"] == 0 and msg["confidence"] is not None


# ---- debounce ---------------------------------------------------------

STEP = 2300  # ~2.3 s/frame reported by the benchmark owner (ESP-NN off); test input only
FLICKER = [True, False, True, False, True, False, True]


def ei(face, seq):
    return parse_detection(ei_payload(face, 0.8 if face else 0.1, seq), "xiao-01")


def feed(sm, clock, faces, step=STEP):
    out = []
    for i, face in enumerate(faces):
        if i:
            clock.advance(step)
        msg = sm.handle_detection(ei(face, i + 1))
        if msg:
            out.append(msg["command"])
    return out


def test_debounce_disabled_by_default_follows_every_flip(clock):
    sm = make(clock)
    assert not sm.play_debounce.enabled and not sm.pause_debounce.enabled
    assert feed(sm, clock, FLICKER) == ["PLAY", "PAUSE", "PLAY", "PAUSE", "PLAY", "PAUSE", "PLAY"]


def test_pause_hold_suppresses_flicker(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, pause_debounce=DebounceRule(min_ms=5000))
    assert feed(sm, clock, FLICKER) == ["PLAY"]
    assert sm.state_dict()["devices"]["xiao-01"]["command"] == "PLAY"


def test_pause_hold_still_pauses_on_sustained_absence(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, pause_debounce=DebounceRule(min_ms=5000))
    # false at +2.3 s starts the candidate; held 2.3 s, 4.6 s -> pending; 6.9 s >= 5 s -> PAUSE.
    assert feed(sm, clock, [True, False, False, False, False]) == ["PLAY", "PAUSE"]


def test_pause_count_suppresses_flicker(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, pause_debounce=DebounceRule(min_count=3))
    assert feed(sm, clock, FLICKER) == ["PLAY"]
    clock.advance(STEP)
    assert feed(sm, clock, [False, False, False]) == ["PAUSE"]


def test_play_and_pause_rules_are_independent(clock):
    sm = StateManager(
        TIMEOUT, "xiao-01", mono_ms=clock,
        play_debounce=DebounceRule(min_count=2), pause_debounce=DebounceRule(min_count=3),
    )
    assert feed(sm, clock, [True]) == []  # 1/2
    clock.advance(STEP)
    assert feed(sm, clock, [False, True, True]) == ["PLAY"]  # false resets the PLAY candidate
    clock.advance(STEP)
    assert feed(sm, clock, [False, False, True, False, False, False]) == ["PAUSE"]


def test_debounced_transition_has_no_duplicates(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, play_debounce=DebounceRule(min_count=2))
    assert feed(sm, clock, [True] * 6) == ["PLAY"]


def test_pending_state_exposed(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, pause_debounce=DebounceRule(min_count=3))
    feed(sm, clock, [True, False])
    state = sm.state_dict()
    assert state["debounce"]["pause"] == {"min_count": 3, "min_ms": 0}
    assert state["devices"]["xiao-01"]["pending_command"] == "PAUSE"
    assert state["devices"]["xiao-01"]["pending_count"] == 1


@pytest.mark.parametrize("rule", [{"min_count": 0}, {"min_ms": -1}])
def test_invalid_debounce_rule(rule):
    with pytest.raises(ValueError):
        DebounceRule(**rule)


# Fail-safe PAUSE must ignore the debounce rule (a very long PAUSE debounce here).
SLOW_PAUSE = DebounceRule(min_count=100, min_ms=600_000)


def playing(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, pause_debounce=SLOW_PAUSE)
    assert feed(sm, clock, [True, False]) == ["PLAY"]  # PAUSE candidate pending
    return sm


def test_failsafe_timeout_not_delayed_by_debounce(clock):
    sm = playing(clock)
    clock.advance(TIMEOUT - 1)
    assert sm.check_timeouts() == []
    clock.advance(1)
    [msg] = sm.check_timeouts()
    assert (msg["command"], msg["detail"]) == ("PAUSE", "DEVICE_TIMEOUT")
    assert sm.state_dict()["devices"]["xiao-01"]["pending_command"] is None


def test_failsafe_offline_not_delayed_by_debounce(clock):
    sm = playing(clock)
    msg = sm.handle_status(parse_status(status_payload(False), "xiao-01"))
    assert (msg["command"], msg["detail"]) == ("PAUSE", "DEVICE_OFFLINE")


def test_failsafe_broker_disconnect_not_delayed_by_debounce(clock):
    sm = playing(clock)
    [msg] = sm.handle_broker_disconnected()
    assert (msg["command"], msg["detail"]) == ("PAUSE", "BROKER_DISCONNECTED")


def test_failsafe_discards_pending_play(clock):
    sm = StateManager(TIMEOUT, "xiao-01", mono_ms=clock, play_debounce=DebounceRule(min_count=2))
    assert feed(sm, clock, [True]) == []  # PLAY candidate 1/2
    sm.handle_status(parse_status(status_payload(False), "xiao-01"))
    # The pre-offline detection must not count: one more true is still only 1/2.
    assert sm.handle_detection(ei(True, 2)) is None
    assert sm.handle_detection(ei(True, 3))["command"] == "PLAY"
