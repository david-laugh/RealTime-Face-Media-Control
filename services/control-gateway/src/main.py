"""Control Gateway: MQTT (device) -> state machine -> WebSocket (browser)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from config import Settings, load_settings
from messages import MessageError, parse_detection, parse_status, split_topic
from mqtt_client import MqttConsumer, MqttEvent
from state_manager import DebounceRule, StateManager, monotonic_ms
from websocket_manager import ConnectionManager

log = logging.getLogger("gateway")


class Gateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = StateManager(
            settings.device_timeout_ms,
            settings.default_device_id,
            play_debounce=DebounceRule(settings.play_confirm_count, settings.play_confirm_ms),
            pause_debounce=DebounceRule(settings.pause_confirm_count, settings.pause_confirm_ms),
        )
        self.ws = ConnectionManager()
        self.queue: "asyncio.Queue[MqttEvent]" = asyncio.Queue()
        self.mqtt: Optional[MqttConsumer] = None
        self.started_mono_ms = monotonic_ms()
        self.invalid_messages = 0

    async def handle_event(self, event: MqttEvent) -> None:
        if event.kind == "connected":
            log.info("MQTT broker connected")
            return
        if event.kind == "disconnected":
            log.warning("MQTT broker disconnected -> fail-safe PAUSE")
            for msg in self.state.handle_broker_disconnected():
                await self.ws.broadcast(msg)
            return

        if not event.payload:
            # Empty payload = retained message being cleared by a client; nothing to do.
            log.debug("ignoring empty payload on %s", event.topic)
            return

        try:
            device_id, kind = split_topic(event.topic, self.settings.mqtt_topic_prefix)
            if kind == "detection":
                if event.retain:
                    # A retained detection is stale by definition; never act on it.
                    log.warning("ignoring retained detection on %s", event.topic)
                    return
                det = parse_detection(event.payload, device_id)
                log.info(
                    "detection %s seq=%d source=%s face=%s confidence=%s threshold=%s",
                    det.device_id, det.seq, det.source, det.raw_face_detected, det.confidence, det.threshold,
                )
                msg = self.state.handle_detection(det)
            elif kind == "status":
                status = parse_status(event.payload, device_id)
                log.info("status %s online=%s source=%s", status.device_id, status.online, status.source)
                msg = self.state.handle_status(status)
            else:
                log.debug("ignoring topic %s", event.topic)
                return
        except MessageError as exc:
            self.invalid_messages += 1
            log.error("invalid message on %s: %s | payload=%r", event.topic, exc, event.payload[:200])
            return

        if msg:
            await self.ws.broadcast(msg)

    async def consume_events(self) -> None:
        while True:
            event = await self.queue.get()
            try:
                await self.handle_event(event)
            except Exception:  # never let one event kill the consumer
                log.exception("unexpected error while handling %s", event.kind)

    async def watch_timeouts(self) -> None:
        interval = self.settings.timeout_check_interval_ms / 1000
        while True:
            await asyncio.sleep(interval)
            for msg in self.state.check_timeouts():
                await self.ws.broadcast(msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    gw = Gateway(settings)
    app.state.gateway = gw
    log.info(
        "starting (broker=%s:%d, device_timeout_ms=%d, default_device=%s)",
        settings.mqtt_host, settings.mqtt_port, settings.device_timeout_ms, settings.default_device_id,
    )
    for name, rule in (("PLAY", gw.state.play_debounce), ("PAUSE", gw.state.pause_debounce)):
        if rule.enabled:
            log.warning("%s debounce enabled: min_count=%d, min_ms=%d", name, rule.min_count, rule.min_ms)
    if gw.state.pause_debounce.min_ms >= settings.device_timeout_ms:
        log.warning("PAUSE_CONFIRM_MS >= DEVICE_TIMEOUT_MS: face-absent PAUSE will be preceded by DEVICE_TIMEOUT")

    tasks = [asyncio.create_task(gw.consume_events()), asyncio.create_task(gw.watch_timeouts())]
    gw.mqtt = MqttConsumer(settings, asyncio.get_running_loop(), gw.queue)
    gw.mqtt.start()
    try:
        yield
    finally:
        gw.mqtt.stop()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="smart-media control-gateway", lifespan=lifespan)


def _gw(app_: FastAPI) -> Gateway:
    return app_.state.gateway


@app.get("/health")
async def health() -> dict[str, Any]:
    gw = _gw(app)
    return {
        "status": "ok",
        "mqtt_connected": bool(gw.mqtt and gw.mqtt.connected),
        "mqtt_broker": f"{gw.settings.mqtt_host}:{gw.settings.mqtt_port}",
        "websocket_clients": gw.ws.count,
        "invalid_messages": gw.invalid_messages,
        "uptime_ms": monotonic_ms() - gw.started_mono_ms,
    }


@app.get("/api/state")
async def api_state() -> dict[str, Any]:
    gw = _gw(app)
    return {"mqtt_connected": bool(gw.mqtt and gw.mqtt.connected), **gw.state.state_dict()}


# "/ws" is the web-ui default (services/web-ui); "/ws/media" kept as an alias.
@app.websocket("/ws")
@app.websocket("/ws/media")
async def ws_media(websocket: WebSocket) -> None:
    gw = _gw(app)
    await gw.ws.connect(websocket, gw.state.snapshot_messages())
    try:
        while True:
            # Server push only; incoming text is ignored but keeps disconnect detection working.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await gw.ws.disconnect(websocket)
