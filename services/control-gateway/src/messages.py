"""MQTT payload parsing/validation (contracts/mqtt/*.schema.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

SCHEMA_VERSION = "1.0"
SOURCES = ("mock", "edge_impulse")


class MessageError(ValueError):
    """Raised for invalid JSON, missing required fields or wrong types."""


@dataclass(frozen=True)
class Detection:
    device_id: str
    seq: int
    uptime_ms: int
    source: str
    model_id: str
    raw_face_detected: bool
    confidence: Optional[float] = None
    inference_ms: Optional[int] = None


@dataclass(frozen=True)
class DeviceStatus:
    device_id: str
    source: str
    online: bool


def _load_object(payload: bytes) -> dict[str, Any]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MessageError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MessageError("payload must be a JSON object")
    return data


def _require(data: dict[str, Any], field: str, kind: type | tuple[type, ...]) -> Any:
    if field not in data:
        raise MessageError(f"missing required field '{field}'")
    value = data[field]
    # bool is a subclass of int: reject it where an integer is expected.
    if kind is int and isinstance(value, bool):
        raise MessageError(f"field '{field}' must be integer")
    if not isinstance(value, kind):
        raise MessageError(f"field '{field}' has unsupported type {type(value).__name__}")
    return value


def _check_common(data: dict[str, Any], topic_device_id: str) -> tuple[str, str]:
    version = _require(data, "schema_version", str)
    if version != SCHEMA_VERSION:
        raise MessageError(f"unsupported schema_version '{version}'")
    device_id = _require(data, "device_id", str)
    if not device_id:
        raise MessageError("device_id must not be empty")
    if device_id != topic_device_id:
        raise MessageError(f"device_id '{device_id}' does not match topic '{topic_device_id}'")
    source = _require(data, "source", str)
    if source not in SOURCES:
        raise MessageError(f"unsupported source '{source}'")
    return device_id, source


def parse_detection(payload: bytes, topic_device_id: str) -> Detection:
    data = _load_object(payload)
    device_id, source = _check_common(data, topic_device_id)

    seq = _require(data, "seq", int)
    uptime_ms = _require(data, "uptime_ms", int)
    if seq < 0 or uptime_ms < 0:
        raise MessageError("seq and uptime_ms must be >= 0")
    model_id = _require(data, "model_id", str)
    raw = _require(data, "raw_face_detected", bool)

    confidence = data.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise MessageError("field 'confidence' must be a number")
        if not 0.0 <= confidence <= 1.0:
            raise MessageError("field 'confidence' must be within 0..1")
    inference_ms = data.get("inference_ms")
    if inference_ms is not None and (isinstance(inference_ms, bool) or not isinstance(inference_ms, int)):
        raise MessageError("field 'inference_ms' must be integer")

    return Detection(
        device_id=device_id,
        seq=seq,
        uptime_ms=uptime_ms,
        source=source,
        model_id=model_id,
        raw_face_detected=raw,
        confidence=float(confidence) if confidence is not None else None,
        inference_ms=inference_ms,
    )


def parse_status(payload: bytes, topic_device_id: str) -> DeviceStatus:
    data = _load_object(payload)
    device_id, source = _check_common(data, topic_device_id)
    online = _require(data, "online", bool)
    return DeviceStatus(device_id=device_id, source=source, online=online)


def split_topic(topic: str, prefix: str) -> tuple[str, str]:
    """'smart-media/xiao-01/detection' -> ('xiao-01', 'detection')."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != prefix or not parts[1]:
        raise MessageError(f"unexpected topic '{topic}'")
    return parts[1], parts[2]
