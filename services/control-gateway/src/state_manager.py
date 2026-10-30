"""Per-device media state machine.

Rules (face presence only, no temporal filtering):
    raw_face_detected=true  -> PLAY   (only if not already PLAY)
    raw_face_detected=false -> PAUSE  (only if not already PAUSE)
Fail-safe PAUSE on device timeout, device offline and broker disconnect.

Not thread-safe by design: all calls must come from the asyncio event loop.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from messages import Detection, DeviceStatus

log = logging.getLogger("gateway.state")

PLAY = "PLAY"
PAUSE = "PAUSE"

FACE_PRESENT = "FACE_PRESENT"
FACE_ABSENT = "FACE_ABSENT"
DEVICE_TIMEOUT = "DEVICE_TIMEOUT"
DEVICE_OFFLINE = "DEVICE_OFFLINE"
BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
SYSTEM_STARTUP = "SYSTEM_STARTUP"

SYSTEM_SOURCE = "system"


def wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


@dataclass
class DeviceState:
    device_id: str
    command: str = PAUSE
    reason: str = SYSTEM_STARTUP
    face_detected: Optional[bool] = None
    command_source: str = SYSTEM_SOURCE
    last_source: Optional[str] = None  # source of the last device message (e.g. "mock")
    online: Optional[bool] = None
    last_seq: Optional[int] = None
    last_detection_mono_ms: Optional[int] = None
    last_detection_ts_ms: Optional[int] = None
    timed_out: bool = False
    command_ts_ms: int = 0


class StateManager:
    def __init__(
        self,
        device_timeout_ms: int,
        default_device_id: Optional[str] = None,
        mono_ms: Callable[[], int] = monotonic_ms,
        wall_ms: Callable[[], int] = wall_clock_ms,
    ) -> None:
        self.device_timeout_ms = device_timeout_ms
        self._mono_ms = mono_ms
        self._wall_ms = wall_ms
        self._devices: dict[str, DeviceState] = {}
        if default_device_id:
            self._device(default_device_id)

    # ---- inputs -------------------------------------------------------

    def handle_detection(self, det: Detection) -> Optional[dict[str, Any]]:
        dev = self._device(det.device_id)
        if dev.last_seq is not None and det.seq <= dev.last_seq:
            # Device reboot resets seq; accept, but make it visible in logs.
            log.info("[%s] seq %d <= previous %d (device restart?)", dev.device_id, det.seq, dev.last_seq)

        dev.last_seq = det.seq
        dev.last_source = det.source
        dev.face_detected = det.raw_face_detected
        dev.last_detection_mono_ms = self._mono_ms()
        dev.last_detection_ts_ms = self._wall_ms()
        dev.timed_out = False
        dev.online = True

        if det.raw_face_detected:
            return self._transition(dev, PLAY, FACE_PRESENT, det.source)
        return self._transition(dev, PAUSE, FACE_ABSENT, det.source)

    def handle_status(self, status: DeviceStatus) -> Optional[dict[str, Any]]:
        dev = self._device(status.device_id)
        dev.online = status.online
        dev.last_source = status.source
        if status.online:
            # online alone never triggers PLAY; a detection is required.
            return None
        dev.face_detected = None
        return self._transition(dev, PAUSE, DEVICE_OFFLINE, SYSTEM_SOURCE)

    def check_timeouts(self) -> list[dict[str, Any]]:
        now = self._mono_ms()
        out: list[dict[str, Any]] = []
        for dev in self._devices.values():
            if dev.timed_out or dev.last_detection_mono_ms is None:
                continue
            if now - dev.last_detection_mono_ms >= self.device_timeout_ms:
                dev.timed_out = True
                dev.face_detected = None
                log.warning(
                    "[%s] no detection for %d ms (last source=%s)",
                    dev.device_id, now - dev.last_detection_mono_ms, dev.last_source,
                )
                msg = self._transition(dev, PAUSE, DEVICE_TIMEOUT, SYSTEM_SOURCE)
                if msg:
                    out.append(msg)
        return out

    def handle_broker_disconnected(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for dev in self._devices.values():
            dev.face_detected = None
            msg = self._transition(dev, PAUSE, BROKER_DISCONNECTED, SYSTEM_SOURCE)
            if msg:
                out.append(msg)
        return out

    # ---- outputs ------------------------------------------------------

    def snapshot_messages(self) -> list[dict[str, Any]]:
        """Current command per device, sent once to a newly connected client."""
        return [self._message(dev, self._wall_ms()) for dev in self._devices.values()]

    def state_dict(self) -> dict[str, Any]:
        now = self._mono_ms()
        devices = {}
        for dev in self._devices.values():
            since = None if dev.last_detection_mono_ms is None else now - dev.last_detection_mono_ms
            devices[dev.device_id] = {
                "command": dev.command,
                "reason": dev.reason,
                "face_detected": dev.face_detected,
                "command_source": dev.command_source,
                "last_source": dev.last_source,
                "online": dev.online,
                "last_seq": dev.last_seq,
                "last_detection_ts_ms": dev.last_detection_ts_ms,
                "ms_since_last_detection": since,
                "timed_out": dev.timed_out,
                "command_ts_ms": dev.command_ts_ms,
            }
        return {"device_timeout_ms": self.device_timeout_ms, "devices": devices}

    # ---- internals ----------------------------------------------------

    def _device(self, device_id: str) -> DeviceState:
        dev = self._devices.get(device_id)
        if dev is None:
            dev = DeviceState(device_id=device_id, command_ts_ms=self._wall_ms())
            self._devices[device_id] = dev
        return dev

    def _transition(self, dev: DeviceState, command: str, reason: str, source: str) -> Optional[dict[str, Any]]:
        if dev.command == command:
            return None  # no duplicate PLAY/PAUSE
        dev.command = command
        dev.reason = reason
        dev.command_source = source
        dev.command_ts_ms = self._wall_ms()
        log.info(
            "[%s] %s (reason=%s, source=%s, last_source=%s)",
            dev.device_id, command, reason, source, dev.last_source,
        )
        return self._message(dev, dev.command_ts_ms)

    @staticmethod
    def _message(dev: DeviceState, ts_ms: int) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "type": "media_control",
            "device_id": dev.device_id,
            "command": dev.command,
            "reason": dev.reason,
            "face_detected": dev.face_detected,
            "source": dev.command_source,
            "ts_server_ms": ts_ms,
        }
