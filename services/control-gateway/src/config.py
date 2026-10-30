"""Environment-based configuration for the Control Gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    mqtt_host: str = "mqtt-broker"
    mqtt_port: int = 1883
    mqtt_client_id: str = "control-gateway"
    mqtt_topic_prefix: str = "smart-media"
    mqtt_keepalive_s: int = 15

    default_device_id: str = "xiao-01"
    device_timeout_ms: int = 25000
    timeout_check_interval_ms: int = 1000

    log_level: str = "INFO"

    @property
    def detection_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/+/detection"

    @property
    def status_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/+/status"


def load_settings() -> Settings:
    return Settings(
        mqtt_host=os.getenv("MQTT_HOST", "mqtt-broker"),
        mqtt_port=_env_int("MQTT_PORT", 1883),
        mqtt_client_id=os.getenv("MQTT_CLIENT_ID", "control-gateway"),
        mqtt_topic_prefix=os.getenv("MQTT_TOPIC_PREFIX", "smart-media"),
        mqtt_keepalive_s=_env_int("MQTT_KEEPALIVE_S", 15),
        default_device_id=os.getenv("DEFAULT_DEVICE_ID", "xiao-01"),
        device_timeout_ms=_env_int("DEVICE_TIMEOUT_MS", 25000),
        timeout_check_interval_ms=_env_int("TIMEOUT_CHECK_INTERVAL_MS", 1000),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
