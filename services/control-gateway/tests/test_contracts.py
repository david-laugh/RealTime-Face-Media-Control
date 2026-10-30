"""Keep contracts/*.schema.json, the gateway parser and gateway output in sync."""

import json
import re
from pathlib import Path

import jsonschema
import pytest

from conftest import detection_payload, ei_payload, status_payload
from messages import parse_detection, parse_status
from state_manager import StateManager

SCHEMAS = [
    "mqtt/detection.schema.json",
    "mqtt/status.schema.json",
    "mqtt/telemetry.schema.json",
    "websocket/media-control.schema.json",
]


@pytest.mark.parametrize("rel", SCHEMAS)
def test_schema_valid_and_examples_conform(load_schema, rel):
    schema = load_schema(rel)
    jsonschema.Draft202012Validator.check_schema(schema)
    for example in schema.get("examples", []):
        jsonschema.Draft202012Validator(schema).validate(example)


def test_detection_examples_accepted_by_gateway(load_schema):
    for example in load_schema("mqtt/detection.schema.json")["examples"]:
        parse_detection(json.dumps(example).encode(), example["device_id"])


def test_status_examples_accepted_by_gateway(load_schema):
    for example in load_schema("mqtt/status.schema.json")["examples"]:
        parse_status(json.dumps(example).encode(), example["device_id"])


def _detection_validator(load_schema):
    return jsonschema.Draft202012Validator(load_schema("mqtt/detection.schema.json"))


def _ei(**overrides):
    """Edge Impulse payload; an override of ... removes the field."""
    data = json.loads(ei_payload(True, 0.84, threshold=0.6, inference_ms=2300,
                                 bbox={"x": 0.4167, "y": 0.4167, "w": 0.0833, "h": 0.0833}))
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not ...}


@pytest.mark.parametrize(
    "payload",
    [
        _ei(),
        _ei(raw_face_detected=False, confidence=0.35, bbox=...),  # below threshold: score kept
        _ei(raw_face_detected=False, confidence=0, bbox=...),  # no valid score
        _ei(raw_face_detected=False, confidence=0, threshold=..., bbox=..., inference_ms=...),
        _ei(threshold=...),  # threshold is optional
    ],
)
def test_schema_accepts_edge_impulse(load_schema, payload):
    _detection_validator(load_schema).validate(payload)
    parse_detection(json.dumps(payload).encode(), "xiao-01")


@pytest.mark.parametrize(
    "payload,why",
    [
        (_ei(confidence=...), "edge_impulse without confidence"),
        (_ei(confidence=None), "edge_impulse with null confidence"),
        (_ei(raw_face_detected=False, confidence=0.1), "bbox with raw_face_detected=false"),
        (_ei(threshold=1.2), "threshold out of range"),
        (_ei(state="FRONT_PRESENT"), "removed state field"),
        (_ei(source=...), "source missing"),
        (json.loads(detection_payload(True, confidence=0.84)), "mock with numeric confidence"),
        (json.loads(detection_payload(True, threshold=0.6)), "mock with threshold"),
    ],
)
def test_schema_rejects(load_schema, payload, why):
    assert not _detection_validator(load_schema).is_valid(payload), why


def test_schema_accepts_mock_with_or_without_null_confidence(load_schema):
    validator = _detection_validator(load_schema)
    validator.validate(json.loads(detection_payload(False)))
    validator.validate(json.loads(detection_payload(False, confidence=None)))


def test_schema_confidence_and_threshold_share_scale(load_schema):
    props = load_schema("mqtt/detection.schema.json")["properties"]
    for field in ("confidence", "threshold"):
        assert (props[field]["minimum"], props[field]["maximum"]) == (0, 1)


def test_firmware_shaped_payload_matches_schema(load_schema):
    # Same field order/shape the firmware builds with snprintf.
    payload = (
        '{"schema_version":"1.0","device_id":"xiao-01","seq":3,"uptime_ms":20412,'
        '"source":"mock","model_id":"mock-v1","raw_face_detected":true}'
    )
    jsonschema.validate(json.loads(payload), load_schema("mqtt/detection.schema.json"))
    # Edge Impulse shape the firmware builds when a provider sets confidence/threshold.
    for face, conf in (("true", "0.840"), ("false", "0.000")):
        payload = (
            '{"schema_version":"1.0","device_id":"xiao-01","seq":4,"uptime_ms":25400,'
            '"source":"edge_impulse","model_id":"ei-541658-fomo01-int8",'
            f'"raw_face_detected":{face},"confidence":{conf},"threshold":0.600,"inference_ms":2300}}'
        )
        jsonschema.validate(json.loads(payload), load_schema("mqtt/detection.schema.json"))
    will = '{"schema_version":"1.0","device_id":"xiao-01","source":"mock","online":false}'
    jsonschema.validate(json.loads(will), load_schema("mqtt/status.schema.json"))


def test_gateway_output_matches_ws_schema(load_schema, clock):
    validator = jsonschema.Draft202012Validator(load_schema("websocket/media-control.schema.json"))
    sm = StateManager(25000, "xiao-01", mono_ms=clock)
    out = list(sm.snapshot_messages())
    out.append(sm.handle_detection(parse_detection(detection_payload(True, 1), "xiao-01")))
    out.append(sm.handle_detection(parse_detection(detection_payload(False, 2), "xiao-01")))
    sm.handle_detection(parse_detection(detection_payload(True, 3), "xiao-01"))
    clock.advance(25000)
    out.extend(sm.check_timeouts())
    sm.handle_detection(parse_detection(detection_payload(True, 4), "xiao-01"))
    out.append(sm.handle_status(parse_status(status_payload(False), "xiao-01")))
    sm.handle_detection(parse_detection(detection_payload(True, 5), "xiao-01"))
    out.extend(sm.handle_broker_disconnected())

    pairs = [(m["detail"], m["reason"]) for m in out]
    assert pairs == [
        ("SYSTEM_STARTUP", "UNKNOWN"),
        ("FACE_PRESENT", "FRONT_FACE_PRESENT"),
        ("FACE_ABSENT", "FACE_ABSENT"),
        ("DEVICE_TIMEOUT", "DEVICE_TIMEOUT"),
        ("DEVICE_OFFLINE", "DEVICE_TIMEOUT"),
        ("BROKER_DISCONNECTED", "UNKNOWN"),
    ]
    for msg in out:
        validator.validate(msg)


# Reasons handled by services/web-ui/public/index.html (const REASON = {...}).
WEB_UI_INDEX = Path(__file__).resolve().parents[3] / "services" / "web-ui" / "public" / "index.html"


def test_ws_reasons_are_known_to_web_ui(load_schema):
    html = WEB_UI_INDEX.read_text(encoding="utf-8")
    block = re.search(r"const REASON = \{(.*?)\};", html, re.S).group(1)
    web_ui_reasons = set(re.findall(r"^\s*([A-Z_]+):", block, re.M))
    schema_reasons = set(load_schema("websocket/media-control.schema.json")["properties"]["reason"]["enum"])
    assert schema_reasons <= web_ui_reasons


def test_web_ui_default_ws_path_is_served():
    import main

    html = WEB_UI_INDEX.read_text(encoding="utf-8")
    path = re.search(r":8000(/[\w/]*)`", html).group(1)
    served = {r.path for r in main.app.routes}
    assert path in served, f"web-ui connects to {path}, gateway serves {served}"
