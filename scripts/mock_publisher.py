#!/usr/bin/env python3
"""PC-side mock device for testing the Gateway WITHOUT an ESP32.

This is a gateway verification tool, not a replacement for the firmware.
It mimics firmware behaviour: retained status online + Last Will offline,
then detection true/false alternating every --interval seconds.

    pip install paho-mqtt==2.1.0
    python scripts/mock_publisher.py --host localhost --device-id xiao-01
"""

from __future__ import annotations

import argparse
import json
import time

import paho.mqtt.client as mqtt


def status(device_id: str, online: bool) -> str:
    return json.dumps({"schema_version": "1.0", "device_id": device_id, "source": "mock", "online": online})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--device-id", default="xiao-01")
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--count", type=int, default=0, help="0 = run forever")
    args = ap.parse_args()

    prefix = f"smart-media/{args.device_id}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{args.device_id}-pc-mock")
    client.will_set(f"{prefix}/status", status(args.device_id, False), qos=1, retain=True)
    client.connect(args.host, args.port, keepalive=15)
    client.loop_start()
    client.publish(f"{prefix}/status", status(args.device_id, True), qos=1, retain=True).wait_for_publish()

    started = time.monotonic()
    seq, face = 0, True
    try:
        while args.count == 0 or seq < args.count:
            seq += 1
            payload = json.dumps({
                "schema_version": "1.0",
                "device_id": args.device_id,
                "seq": seq,
                "uptime_ms": int((time.monotonic() - started) * 1000),
                "source": "mock",
                "model_id": "mock-v1",
                "raw_face_detected": face,
            })
            client.publish(f"{prefix}/detection", payload, qos=0, retain=False)
            print(f"[{time.strftime('%H:%M:%S')}] published {payload}", flush=True)
            face = not face
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        # Graceful exit: publish offline ourselves (LWT only fires on abnormal disconnect).
        client.publish(f"{prefix}/status", status(args.device_id, False), qos=1, retain=True).wait_for_publish()
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
