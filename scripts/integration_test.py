#!/usr/bin/env python3
"""End-to-end test: MQTT broker -> control-gateway -> WebSocket (T01-T10).

Prerequisite:
    docker compose up -d mqtt-broker control-gateway
    pip install -r services/control-gateway/requirements-dev.txt

Run:
    python scripts/integration_test.py                    # T01-T08, T10, LWT
    python scripts/integration_test.py --broker-restart   # + T09 (restarts mqtt-broker container)

Connects to the same WebSocket path as web-ui (/ws).
Uses its own device id (default it-xiao-01) so it does not disturb a real xiao-01.
Prints PASS/FAIL per test and exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt
from websockets.sync.client import connect as ws_connect

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, str, str]] = []


class Ctx:
    def __init__(self, args):
        self.args = args
        self.dev = args.device_id
        self.prefix = f"smart-media/{self.dev}"
        self.seq = 0
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{self.dev}-it")
        self.mqtt.connect(args.mqtt_host, args.mqtt_port, keepalive=15)
        self.mqtt.loop_start()

    # ---- helpers ------------------------------------------------------
    def http(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.args.gateway}{path}", timeout=3) as r:
            return json.loads(r.read())

    def publish_detection(self, face: bool) -> None:
        self.seq += 1
        payload = {
            "schema_version": "1.0", "device_id": self.dev, "seq": self.seq,
            "uptime_ms": self.seq * 10000, "source": "mock", "model_id": "mock-v1",
            "raw_face_detected": face,
        }
        self.mqtt.publish(f"{self.prefix}/detection", json.dumps(payload), qos=0, retain=False).wait_for_publish()

    def publish_raw(self, kind: str, payload: str | bytes, retain: bool = False) -> None:
        self.mqtt.publish(f"{self.prefix}/{kind}", payload, qos=1, retain=retain).wait_for_publish()

    def status(self, online: bool) -> str:
        return json.dumps({"schema_version": "1.0", "device_id": self.dev, "source": "mock", "online": online})


class WsListener:
    """Background reader; keeps only messages for our device id."""

    def __init__(self, url: str, dev: str):
        self.dev = dev
        self.q: "queue.Queue[dict]" = queue.Queue()
        self.ws = ws_connect(url, open_timeout=5)
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            for raw in self.ws:
                msg = json.loads(raw)
                if msg.get("device_id") == self.dev:
                    self.q.put((time.monotonic(), msg))
        except Exception:
            pass

    def get(self, timeout: float):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None, None

    def expect_none(self, wait: float) -> bool:
        _, msg = self.get(wait)
        return msg is None

    def drain(self):
        while not self.q.empty():
            self.q.get_nowait()

    def close(self):
        self.ws.close()


def record(test_id: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((test_id, status, detail))
    print(f"[{status}] {test_id}: {detail}", flush=True)


# web-ui display reason for each gateway detail (contracts/websocket/media-control.schema.json)
UI_REASON = {
    "FACE_PRESENT": "FRONT_FACE_PRESENT",
    "FACE_ABSENT": "FACE_ABSENT",
    "DEVICE_TIMEOUT": "DEVICE_TIMEOUT",
    "DEVICE_OFFLINE": "DEVICE_TIMEOUT",
    "BROKER_DISCONNECTED": "UNKNOWN",
    "SYSTEM_STARTUP": "UNKNOWN",
}


def expect_cmd(ws: WsListener, command: str, detail: str, timeout: float = 3.0):
    t0 = time.monotonic()
    ts, msg = ws.get(timeout)
    if msg is None:
        return False, f"no message within {timeout}s", None
    ok = msg["command"] == command and msg["detail"] == detail and msg["reason"] == UI_REASON[detail]
    return ok, (
        f"got {msg['command']} reason={msg['reason']} detail={msg['detail']} "
        f"source={msg['source']} face={msg['face_detected']} after {ts - t0:.3f}s"
    ), msg


# ---- tests -------------------------------------------------------------

def test_broker(ctx: Ctx):
    got: "queue.Queue[tuple[str, dict]]" = queue.Queue()
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{ctx.dev}-it-sub")
    sub.on_message = lambda c, u, m: got.put((m.topic, json.loads(m.payload)))
    sub.connect(ctx.args.mqtt_host, ctx.args.mqtt_port)
    sub.subscribe(f"{ctx.prefix}/detection")
    sub.loop_start()
    time.sleep(0.5)
    ctx.publish_detection(False)
    try:
        topic, payload = got.get(timeout=3)
        record("B01 MQTT pub/sub", payload["seq"] == ctx.seq, f"received JSON on {topic}: seq={payload['seq']}")
    except queue.Empty:
        record("B01 MQTT pub/sub", False, "no message received within 3s")
    sub.loop_stop()
    sub.disconnect()


def run(args) -> int:
    ctx = Ctx(args)

    health = ctx.http("/health")
    record("H01 /health", health["status"] == "ok" and health["mqtt_connected"], json.dumps(health))

    test_broker(ctx)

    # Ensure known baseline: device paused, no retained offline status.
    ctx.publish_raw("status", b"", retain=True)
    ws = WsListener(args.ws, ctx.dev)
    time.sleep(0.5)
    ws.drain()

    ctx.publish_detection(True)
    ok, d, _ = expect_cmd(ws, "PLAY", "FACE_PRESENT")
    record("T01 true -> PLAY", ok, d)

    ctx.publish_detection(True)
    record("T03 true->true no duplicate", ws.expect_none(2.0), "no WebSocket message within 2s")

    ctx.publish_detection(False)
    ok, d, _ = expect_cmd(ws, "PAUSE", "FACE_ABSENT")
    record("T02 false -> PAUSE", ok, d)

    ctx.publish_detection(False)
    record("T04 false->false no duplicate", ws.expect_none(2.0), "no WebSocket message within 2s")

    before = ctx.http("/health")["invalid_messages"]
    ctx.publish_raw("detection", b"{this is not json")
    ctx.publish_raw("detection", json.dumps({"schema_version": "1.0", "device_id": ctx.dev}))
    no_msg = ws.expect_none(1.5)
    after = ctx.http("/health")
    record(
        "T07 invalid JSON / missing fields",
        no_msg and after["status"] == "ok" and after["invalid_messages"] == before + 2,
        f"invalid_messages {before} -> {after['invalid_messages']}, gateway status={after['status']}",
    )

    ctx.publish_detection(True)
    expect_cmd(ws, "PLAY", "FACE_PRESENT")
    ws2 = WsListener(args.ws, ctx.dev)
    _, snap = ws2.get(3)
    ws2.close()
    record(
        "T08 WebSocket reconnect sync",
        bool(snap) and snap["command"] == "PLAY" and snap["detail"] == "FACE_PRESENT",
        f"snapshot on connect: {snap}",
    )

    ctx.publish_raw("status", ctx.status(False), retain=True)
    ok, d, _ = expect_cmd(ws, "PAUSE", "DEVICE_OFFLINE")
    record("T06 status offline -> PAUSE", ok, d)
    ctx.publish_raw("status", ctx.status(True), retain=True)
    record("T06b status online alone -> no PLAY", ws.expect_none(2.0), "no WebSocket message within 2s")

    # LWT: a client that dies without DISCONNECT -> broker publishes the will.
    lwt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{ctx.dev}-it-lwt")
    lwt.will_set(f"{ctx.prefix}/status", ctx.status(False), qos=1, retain=True)
    lwt.connect(args.mqtt_host, args.mqtt_port, keepalive=2)
    lwt.loop_start()
    time.sleep(0.5)
    ctx.publish_detection(True)
    expect_cmd(ws, "PLAY", "FACE_PRESENT")
    lwt.loop_stop()       # stop keepalive pings
    lwt.socket().close()  # abrupt close, no DISCONNECT packet
    ok, d, _ = expect_cmd(ws, "PAUSE", "DEVICE_OFFLINE", timeout=8)
    record("T06c Last Will on abnormal disconnect", ok, d)
    ctx.publish_raw("status", ctx.status(True), retain=True)

    # T05: timeout
    timeout_s = ctx.http("/api/state")["device_timeout_ms"] / 1000
    ctx.publish_detection(True)
    _, _, play = expect_cmd(ws, "PLAY", "FACE_PRESENT")
    t0 = time.monotonic()
    ts, msg = ws.get(timeout_s + 5)
    elapsed = (ts - t0) if ts else None
    ok = bool(msg) and msg["detail"] == "DEVICE_TIMEOUT" and msg["command"] == "PAUSE" and timeout_s <= elapsed + 0.5 <= timeout_s + 3
    record("T05 no detection -> DEVICE_TIMEOUT", ok, f"{msg and msg['command']}/{msg and msg['detail']} after {elapsed and round(elapsed, 2)}s (timeout={timeout_s}s)")

    # T10: 10 s periodic alternating input, no timeout.
    seen = []
    for i in range(args.periodic_count):
        ctx.publish_detection(i % 2 == 0)
        deadline = time.monotonic() + args.interval
        while (remaining := deadline - time.monotonic()) > 0:
            _, msg = ws.get(remaining)
            if msg:
                seen.append(f"{msg['command']}/{msg['detail']}")
    expected = ["PLAY/FACE_PRESENT", "PAUSE/FACE_ABSENT"] * (args.periodic_count // 2)
    record(
        f"T10 {args.interval:.0f}s periodic x{args.periodic_count}, no timeout",
        seen == expected,
        f"messages={seen}",
    )

    if args.broker_restart:
        ctx.publish_detection(True)
        expect_cmd(ws, "PLAY", "FACE_PRESENT")
        subprocess.run(["docker", "compose", "restart", "mqtt-broker"], cwd=REPO_ROOT, check=True, capture_output=True)
        ok1, d1, _ = expect_cmd(ws, "PAUSE", "BROKER_DISCONNECTED", timeout=10)
        recovered = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < 30:
            try:
                if ctx.http("/health")["mqtt_connected"]:
                    recovered = time.monotonic() - t0
                    break
            except Exception:
                pass
            time.sleep(0.5)
        ok2 = False
        d2 = "gateway did not reconnect within 30s"
        if recovered is not None:
            # our own publisher also auto-reconnects (paho loop)
            time.sleep(2)
            ctx.publish_detection(True)
            ok2, d2, _ = expect_cmd(ws, "PLAY", "FACE_PRESENT", timeout=5)
            d2 = f"gateway mqtt_connected after {recovered:.1f}s; then {d2}"
        record("T09 broker restart -> fail-safe PAUSE + auto recovery", ok1 and ok2, f"{d1}; {d2}")
    else:
        RESULTS.append(("T09 broker restart", "NOT_RUN", "run with --broker-restart"))

    # Cleanup: leave the test device paused and remove retained status.
    ctx.publish_detection(False)
    ctx.publish_raw("status", b"", retain=True)
    ws.close()
    ctx.mqtt.loop_stop()
    ctx.mqtt.disconnect()

    print("\n=== SUMMARY ===")
    for tid, st, detail in RESULTS:
        print(f"{st:8} {tid}")
    return 0 if all(st != "FAIL" for _, st, _ in RESULTS) else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqtt-host", default="localhost")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--gateway", default="http://localhost:8000")
    ap.add_argument("--ws", default="ws://localhost:8000/ws", help="web-ui default path; /ws/media is an alias")
    ap.add_argument("--device-id", default="it-xiao-01")
    ap.add_argument("--interval", type=float, default=10.0, help="T10 publish interval (s)")
    ap.add_argument("--periodic-count", type=int, default=4)
    ap.add_argument("--broker-restart", action="store_true")
    sys.exit(run(ap.parse_args()))


if __name__ == "__main__":
    main()
