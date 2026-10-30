"""Per-device media state machine.

Rules (face presence only):
    raw_face_detected=true  -> PLAY   (only if not already PLAY)
    raw_face_detected=false -> PAUSE  (only if not already PAUSE)
Optional debounce per direction (DebounceRule): a switch happens only after the
new value has been seen in min_count consecutive detections spanning at least
min_ms. A detection agreeing with the current command cancels the candidate.
The default rule (1 detection, 0 ms) switches immediately (mock demo behavior).
Fail-safe PAUSE on device timeout, device offline and broker disconnect is never
debounced and also discards any pending candidate.

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

# Gateway-internal causes, sent to the browser as "detail".
FACE_PRESENT = "FACE_PRESENT"
FACE_ABSENT = "FACE_ABSENT"
DEVICE_TIMEOUT = "DEVICE_TIMEOUT"
DEVICE_OFFLINE = "DEVICE_OFFLINE"
BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
SYSTEM_STARTUP = "SYSTEM_STARTUP"

# "reason" values understood by web-ui (services/web-ui/public/index.html).
UI_REASON = {
    FACE_PRESENT: "FRONT_FACE_PRESENT",
    FACE_ABSENT: "FACE_ABSENT",
    DEVICE_TIMEOUT: "DEVICE_TIMEOUT",
    DEVICE_OFFLINE: "DEVICE_TIMEOUT",  # web-ui: "카메라 끊김"
    BROKER_DISCONNECTED: "UNKNOWN",
    SYSTEM_STARTUP: "UNKNOWN",
}

SYSTEM_SOURCE = "system"


def wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


@dataclass(frozen=True)
class DebounceRule:
    """When a candidate command is confirmed. Default = immediately."""

    min_count: int = 1  # consecutive detections agreeing with the candidate
    min_ms: int = 0  # time from the first to the confirming detection (gateway clock)

    def __post_init__(self) -> None:
        if self.min_count < 1 or self.min_ms < 0:
            raise ValueError(f"invalid debounce rule {self}")

    @property
    def enabled(self) -> bool:
        return self.min_count > 1 or self.min_ms > 0


@dataclass
class DeviceState:
    device_id: str
    command: str = PAUSE
    reason: str = SYSTEM_STARTUP
    face_detected: Optional[bool] = None
    confidence: Optional[float] = None
    command_source: str = SYSTEM_SOURCE
    last_source: Optional[str] = None  # source of the last device message (e.g. "mock")
    online: Optional[bool] = None
    last_seq: Optional[int] = None
    last_detection_mono_ms: Optional[int] = None
    last_detection_ts_ms: Optional[int] = None
    timed_out: bool = False
    command_ts_ms: int = 0
    # Debounce candidate (a command different from `command`, not yet confirmed).
    pending_command: Optional[str] = None
    pending_count: int = 0
    pending_since_mono_ms: Optional[int] = None


class StateManager:
    def __init__(
        self,
        device_timeout_ms: int,
        default_device_id: Optional[str] = None,
        mono_ms: Callable[[], int] = monotonic_ms,
        wall_ms: Callable[[], int] = wall_clock_ms,
        play_debounce: DebounceRule = DebounceRule(),
        pause_debounce: DebounceRule = DebounceRule(),
    ) -> None:
        self.device_timeout_ms = device_timeout_ms
        self.play_debounce = play_debounce
        self.pause_debounce = pause_debounce
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

        now = self._mono_ms()
        dev.last_seq = det.seq
        dev.last_source = det.source
        dev.face_detected = det.raw_face_detected
        dev.confidence = det.confidence
        dev.last_detection_mono_ms = now
        dev.last_detection_ts_ms = self._wall_ms()
        dev.timed_out = False
        dev.online = True

        target = PLAY if det.raw_face_detected else PAUSE
        if target == dev.command:
            if dev.pending_command is not None:
                log.info("[%s] %s candidate cancelled after %d detection(s)",
                         dev.device_id, dev.pending_command, dev.pending_count)
            self._clear_pending(dev)
            return None  # no duplicate PLAY/PAUSE

        if dev.pending_command != target:
            dev.pending_command = target
            dev.pending_count = 0
            dev.pending_since_mono_ms = now
        dev.pending_count += 1

        rule = self.play_debounce if target == PLAY else self.pause_debounce
        held_ms = now - dev.pending_since_mono_ms
        if dev.pending_count < rule.min_count or held_ms < rule.min_ms:
            log.info("[%s] %s candidate %d/%d detection(s), %d/%d ms",
                     dev.device_id, target, dev.pending_count, rule.min_count, held_ms, rule.min_ms)
            return None
        reason = FACE_PRESENT if target == PLAY else FACE_ABSENT
        return self._transition(dev, target, reason, det.source)

    def handle_status(self, status: DeviceStatus) -> Optional[dict[str, Any]]:
        dev = self._device(status.device_id)
        dev.online = status.online
        dev.last_source = status.source
        if status.online:
            # online alone never triggers PLAY; a detection is required.
            return None
        dev.face_detected = None
        dev.confidence = None
        self._clear_pending(dev)
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
                dev.confidence = None
                self._clear_pending(dev)
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
            dev.confidence = None
            self._clear_pending(dev)
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
                "confidence": dev.confidence,
                "command_source": dev.command_source,
                "last_source": dev.last_source,
                "online": dev.online,
                "last_seq": dev.last_seq,
                "last_detection_ts_ms": dev.last_detection_ts_ms,
                "ms_since_last_detection": since,
                "timed_out": dev.timed_out,
                "command_ts_ms": dev.command_ts_ms,
                "pending_command": dev.pending_command,
                "pending_count": dev.pending_count,
            }
        return {
            "device_timeout_ms": self.device_timeout_ms,
            "debounce": {
                "play": {"min_count": self.play_debounce.min_count, "min_ms": self.play_debounce.min_ms},
                "pause": {"min_count": self.pause_debounce.min_count, "min_ms": self.pause_debounce.min_ms},
            },
            "devices": devices,
        }

    # ---- internals ----------------------------------------------------

    def _device(self, device_id: str) -> DeviceState:
        dev = self._devices.get(device_id)
        if dev is None:
            dev = DeviceState(device_id=device_id, command_ts_ms=self._wall_ms())
            self._devices[device_id] = dev
        return dev

    @staticmethod
    def _clear_pending(dev: DeviceState) -> None:
        dev.pending_command = None
        dev.pending_count = 0
        dev.pending_since_mono_ms = None

    def _transition(self, dev: DeviceState, command: str, reason: str, source: str) -> Optional[dict[str, Any]]:
        if dev.command == command:
            return None  # no duplicate PLAY/PAUSE
        self._clear_pending(dev)
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
            "reason": UI_REASON[dev.reason],
            "detail": dev.reason,
            "face_detected": dev.face_detected,
            "confidence": dev.confidence,
            "source": dev.command_source,
            "ts_server_ms": ts_ms,
        }
