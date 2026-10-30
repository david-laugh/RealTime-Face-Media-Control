"""paho-mqtt wrapper that forwards events into an asyncio.Queue.

paho callbacks run on paho's network thread. They never touch gateway state
or WebSockets directly; they only enqueue events via call_soon_threadsafe.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import paho.mqtt.client as mqtt

from config import Settings

log = logging.getLogger("gateway.mqtt")


@dataclass(frozen=True)
class MqttEvent:
    kind: str  # "connected" | "disconnected" | "message"
    topic: str = ""
    payload: bytes = b""
    retain: bool = False


class MqttConsumer:
    def __init__(self, settings: Settings, loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[MqttEvent]") -> None:
        self._settings = settings
        self._loop = loop
        self._queue = queue
        self.connected = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
            clean_session=True,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_message = self._on_message

    def start(self) -> None:
        log.info("connecting to %s:%d", self._settings.mqtt_host, self._settings.mqtt_port)
        self._client.connect_async(self._settings.mqtt_host, self._settings.mqtt_port, self._settings.mqtt_keepalive_s)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    # ---- paho thread callbacks ----------------------------------------

    def _post(self, event: MqttEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("connect refused: %s", reason_code)
            return
        self.connected = True
        topics = [(self._settings.detection_topic, 0), (self._settings.status_topic, 1)]
        client.subscribe(topics)
        log.info("connected, subscribed to %s", [t for t, _ in topics])
        self._post(MqttEvent("connected"))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        was_connected = self.connected
        self.connected = False
        log.warning("disconnected: %s", reason_code)
        if was_connected:
            self._post(MqttEvent("disconnected"))

    def _on_connect_fail(self, client, userdata) -> None:
        log.warning("broker unreachable, retrying")

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        self._post(MqttEvent("message", topic=msg.topic, payload=bytes(msg.payload), retain=bool(msg.retain)))
