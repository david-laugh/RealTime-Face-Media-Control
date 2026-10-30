"""Keep contracts/*.schema.json, the gateway parser and gateway output in sync."""

import json

import jsonschema
import pytest

from conftest import detection_payload, status_payload
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


def test_firmware_shaped_payload_matches_schema(load_schema):
    # Same field order/shape the firmware builds with snprintf.
    payload = (
        '{"schema_version":"1.0","device_id":"xiao-01","seq":3,"uptime_ms":20412,'
        '"source":"mock","model_id":"mock-v1","raw_face_detected":true}'
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

    reasons = [m["reason"] for m in out]
    assert reasons == [
        "SYSTEM_STARTUP", "FACE_PRESENT", "FACE_ABSENT",
        "DEVICE_TIMEOUT", "DEVICE_OFFLINE", "BROKER_DISCONNECTED",
    ]
    for msg in out:
        validator.validate(msg)
