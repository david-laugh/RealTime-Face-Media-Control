"""FastAPI app tests with the MQTT client replaced by a fake (no broker needed)."""

import pytest
from fastapi.testclient import TestClient

import main
from conftest import detection_payload, status_payload
from mqtt_client import MqttEvent


class FakeMqtt:
    def __init__(self, settings, loop, queue):
        self.connected = True

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "MqttConsumer", FakeMqtt)
    with TestClient(main.app) as c:
        yield c


def inject(client, event: MqttEvent):
    """Run the gateway event handler on the app's event loop (as the consumer task would)."""
    gw = client.app.state.gateway
    client.portal.call(gw.handle_event, event)


def detection(face, seq):
    return MqttEvent("message", "smart-media/xiao-01/detection", detection_payload(face, seq))


def test_health_and_state(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["mqtt_connected"] is True
    state = client.get("/api/state").json()
    assert state["device_timeout_ms"] == 25000
    assert state["devices"]["xiao-01"]["command"] == "PAUSE"


def test_ws_snapshot_and_broadcast_to_multiple_clients(client):
    with client.websocket_connect("/ws/media") as ws1, client.websocket_connect("/ws/media") as ws2:
        assert ws1.receive_json()["detail"] == "SYSTEM_STARTUP"
        assert ws2.receive_json()["detail"] == "SYSTEM_STARTUP"
        inject(client, detection(True, 1))
        for ws in (ws1, ws2):
            msg = ws.receive_json()
            assert (msg["command"], msg["detail"], msg["source"]) == ("PLAY", "FACE_PRESENT", "mock")
        assert client.get("/health").json()["websocket_clients"] == 2
    assert client.get("/health").json()["websocket_clients"] == 0


def test_t07_invalid_message_keeps_server_alive(client):
    inject(client, MqttEvent("message", "smart-media/xiao-01/detection", b"{broken"))
    assert client.get("/health").json()["invalid_messages"] == 1
    inject(client, detection(True, 1))
    assert client.get("/api/state").json()["devices"]["xiao-01"]["command"] == "PLAY"


def test_retained_detection_ignored(client):
    inject(client, MqttEvent("message", "smart-media/xiao-01/detection", detection_payload(True, 1), retain=True))
    assert client.get("/api/state").json()["devices"]["xiao-01"]["command"] == "PAUSE"


def test_t08_reconnect_gets_current_state(client):
    inject(client, detection(True, 1))
    with client.websocket_connect("/ws/media") as ws:
        msg = ws.receive_json()
        assert (msg["command"], msg["detail"]) == ("PLAY", "FACE_PRESENT")


def test_offline_status_and_broker_disconnect(client):
    inject(client, detection(True, 1))
    with client.websocket_connect("/ws/media") as ws:
        ws.receive_json()
        inject(client, MqttEvent("message", "smart-media/xiao-01/status", status_payload(False)))
        assert ws.receive_json()["detail"] == "DEVICE_OFFLINE"
        inject(client, detection(True, 2))
        assert ws.receive_json()["command"] == "PLAY"
        inject(client, MqttEvent("disconnected"))
        assert ws.receive_json()["detail"] == "BROKER_DISCONNECTED"


def test_web_ui_path_ws_alias(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert (msg["command"], msg["reason"], msg["detail"]) == ("PAUSE", "UNKNOWN", "SYSTEM_STARTUP")


def test_debounce_defaults_off(client):
    debounce = client.get("/api/state").json()["debounce"]
    assert debounce == {"play": {"min_count": 1, "min_ms": 0}, "pause": {"min_count": 1, "min_ms": 0}}


def test_debounce_from_env_suppresses_flicker_over_ws(monkeypatch):
    monkeypatch.setattr(main, "MqttConsumer", FakeMqtt)
    monkeypatch.setenv("PAUSE_CONFIRM_COUNT", "3")
    with TestClient(main.app) as c:
        assert c.get("/api/state").json()["debounce"]["pause"] == {"min_count": 3, "min_ms": 0}
        gw = c.app.state.gateway
        sent = []
        broadcast = gw.ws.broadcast

        async def record(msg):
            sent.append(msg["command"])
            await broadcast(msg)

        gw.ws.broadcast = record
        with c.websocket_connect("/ws") as ws:
            assert ws.receive_json()["detail"] == "SYSTEM_STARTUP"
            for seq, face in enumerate([True, False, True, False, False, False], start=1):
                inject(c, detection(face, seq))
            assert ws.receive_json()["command"] == "PLAY"
            assert ws.receive_json()["command"] == "PAUSE"
        # The single falses between trues are suppressed; the 3rd consecutive false pauses.
        assert sent == ["PLAY", "PAUSE"]
