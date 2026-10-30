"""Full pipeline check without a board: model-benchmark -> MQTT -> control-gateway -> WebSocket.

Prerequisite:
    docker compose --profile benchmark up -d --build
    pip install paho-mqtt websockets jsonschema pyyaml

P1 mock:   model-benchmark mock_publisher (in container) -> gateway PLAY/PAUSE, collector, analyzer
P2 replay: Edge Impulse serial text (esp32_camera example format) -> serial_bridge parser/Bridge
           (same code as the real bridge, only the serial port is replaced) -> gateway, collector, analyzer.
           Frames are sent every --frame-interval s (default 2.3 s, the reported ESP-NN-off speed).
           --model fomo (bench-sketch, bounding boxes) or classification
           (xiao_face_presence_example.ino, labels face_absent / face_present, no bbox, threshold 0.5).
Expected PLAY/PAUSE sequences are computed with the gateway's own StateManager, the debounce settings
read from /api/state and the receive times recorded by the collector, so P1/P2 hold with debounce off or on.
P3 timeout: replay device stops -> gateway fail-safe PAUSE (DEVICE_TIMEOUT), not delayed by debounce.

Test devices (mock-xiao-01, e2e-bench-01) stay in the gateway state and web-ui follows any device:
run `docker compose restart control-gateway` afterwards before a demo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "model-benchmark" / "src"))
sys.path.insert(0, str(REPO / "services" / "control-gateway" / "src"))

import common  # noqa: E402  (model-benchmark)
from messages import parse_detection  # noqa: E402  (control-gateway)
from serial_bridge import Bridge, SerialParser  # noqa: E402
from state_manager import DebounceRule, StateManager  # noqa: E402

GATEWAY = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
MOCK_DEV = "mock-xiao-01"
REPLAY_DEV = "e2e-bench-01"
REPLAY_MODEL = "e2e-replay"
MODEL_KIND = "fomo"  # set from --model
THRESHOLD = 0.6  # 0.5 for --model classification
# Highest face score per frame (None = no box). Flickers like the real model, then a 4-frame absence.
REPLAY_SCORES = [0.82, 0.31, 0.77, None, 0.71, 0.45, 0.66, None, None, None, None, 0.9]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok, info))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {info}", flush=True)


def get_json(path: str) -> dict:
    with urllib.request.urlopen(GATEWAY + path, timeout=5) as r:
        return json.load(r)


def compose(*args: str, check_rc: bool = True) -> subprocess.CompletedProcess:
    # stdin=DEVNULL: concurrent `docker compose exec` calls sharing stdin block each other.
    return subprocess.run(["docker", "compose", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check_rc, stdin=subprocess.DEVNULL)


def bench(*args: str) -> subprocess.Popen:
    cmd = ["docker", "compose", "exec", "-T", "model-benchmark", "python", *args]
    return subprocess.Popen(cmd, cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def read_session(results_dir: str, model_id: str) -> list[dict]:
    out = compose("exec", "-T", "model-benchmark", "sh", "-c",
                  f"cat {results_dir}/{model_id}/*/*/messages.jsonl", check_rc=False).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def run_analyzer(results_dir: str, model_id: str) -> tuple[bool, str]:
    p = compose("exec", "-T", "model-benchmark", "python", "src/analyzer.py",
                "--results-dir", results_dir, "--model-id", model_id, check_rc=False)
    ls = compose("exec", "-T", "model-benchmark", "sh", "-c",
                 f"ls {results_dir}/{model_id}/summary.md", check_rc=False)
    return p.returncode == 0 and ls.returncode == 0, (p.stdout + p.stderr).strip().splitlines()[-1:]


async def wait_collecting(results_dir: str, model_id: str, timeout: float = 30) -> bool:
    """Wait until the collector created its session file (docker exec output is not streamed on
    every platform, so its start line cannot be used), then allow time to connect and subscribe."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ls = await asyncio.to_thread(compose, "exec", "-T", "model-benchmark", "sh", "-c",
                                     f"ls {results_dir}/{model_id}/*/*/messages.jsonl", check_rc=False)
        if ls.returncode == 0:
            await asyncio.sleep(2)
            return True
        await asyncio.sleep(0.5)
    return False


async def reset_device(device_id: str, source: str) -> None:
    """Earlier runs may leave a test device PLAYING; offline status puts it back to PAUSE."""
    if get_json("/api/state")["devices"].get(device_id, {}).get("command") != "PLAY":
        return
    client = common.mqtt_client()
    client.connect("localhost", common.MQTT_PORT)
    client.loop_start()
    client.publish(common.topic(device_id, "status"), json.dumps(
        {"schema_version": "1.0", "device_id": device_id, "source": source, "online": False})).wait_for_publish()
    client.loop_stop()
    client.disconnect()
    await asyncio.sleep(1)  # let the WebSocket recorder receive the PAUSE


def serial_lines(score: float | None) -> list[str]:
    """One frame of the Edge Impulse esp32_camera example serial output."""
    if MODEL_KIND == "classification":
        present = score or 0.0
        top = ("face_present", present) if present > 0.5 else ("face_absent", 1 - present)
        return ["Predictions (DSP: 9 ms., Classification: 310 ms., Anomaly: 0 ms.): ", "Predictions:",
                f"  face_absent: {1 - present:.5f}", f"  face_present: {present:.5f}",
                f"Face presence: {top[0]} ({top[1]:.5f})"]
    lines = ["Predictions (DSP: 9 ms., Classification: 2266 ms., Anomaly: 0 ms.): ",
             "Object detection bounding boxes:"]
    if score is not None:
        lines.append(f"  face ({score:.6f}) [ x: 40, y: 40, width: 8, height: 8 ]")
    return lines


def expected_commands(debounce: dict, rows: list[dict]) -> list[str]:
    """Replay the collected detections through the gateway StateManager at their receive times."""
    clock = [0]
    sm = StateManager(
        25000, None, mono_ms=lambda: clock[0],
        play_debounce=DebounceRule(**debounce["play"]), pause_debounce=DebounceRule(**debounce["pause"]),
    )
    out = []
    for row in rows:
        if row["kind"] != "detection":
            continue
        clock[0] = int(row["received_at"] * 1000)
        det = parse_detection(json.dumps(row["payload"]).encode(), row["payload"]["device_id"])
        msg = sm.handle_detection(det)
        if msg:
            out.append(msg["command"])
    return out


class WsRecorder:
    def __init__(self) -> None:
        self.msgs: list[dict] = []

    async def run(self, ws) -> None:
        async for raw in ws:
            self.msgs.append(json.loads(raw))

    def for_device(self, device_id: str) -> list[dict]:
        return [m for m in self.msgs if m["device_id"] == device_id]


async def phase_mock(rec: WsRecorder, results_dir: str) -> None:
    print("\n== P1 model-benchmark mock_publisher -> gateway / collector / analyzer ==", flush=True)
    debounce = get_json("/api/state")["debounce"]
    await reset_device(MOCK_DEV, "mock")
    before = len(rec.for_device(MOCK_DEV))
    collector = bench("src/collector.py", "--results-dir", results_dir, "--model-id", "mock-v1",
                      "--device-id", MOCK_DEV, "--label", "FACE", "--distance", "50cm", "--env", "NORMAL",
                      "--start-delay", "0", "--duration", "14")
    if not await wait_collecting(results_dir, "mock-v1"):
        check("P1 collector started", False, "no start line within 30 s")
        return
    mock = bench("src/mock_publisher.py", "--device-id", MOCK_DEV, "--mode", "alternate", "--period", "3",
                 "--fps", "1", "--duration", "10", "--seed", "1")
    await asyncio.to_thread(mock.wait, 60)
    await asyncio.to_thread(collector.wait, 60)
    await asyncio.sleep(0.5)

    got = rec.for_device(MOCK_DEV)[before:]
    cmds = [m["command"] for m in got]
    rows = read_session(results_dir, "mock-v1")
    dets = [r for r in rows if r["kind"] == "detection"]
    expected = expected_commands(debounce, rows)
    check("P1a gateway PLAY/PAUSE for benchmark mock matches debounce settings",
          bool(cmds) and cmds == expected and all(a != b for a, b in zip(cmds, cmds[1:])),
          f"got {cmds}, expected {expected} (debounce={debounce})")
    check("P1b mock -> WebSocket source=mock, confidence=null",
          bool(got) and all(m["source"] == "mock" and m["confidence"] is None for m in got), f"{len(got)} msg")
    check("P1c collector stored valid mock detections",
          len(dets) >= 5 and all(r["valid"] for r in rows), f"detections={len(dets)} rows={len(rows)}")
    ok, tail = run_analyzer(results_dir, "mock-v1")
    check("P1d analyzer summary for mock session", ok, str(tail))


async def phase_replay(rec: WsRecorder, results_dir: str, interval_s: float) -> None:
    print("\n== P2 Edge Impulse serial replay -> serial_bridge -> gateway / collector / analyzer ==", flush=True)
    debounce = get_json("/api/state")["debounce"]
    await reset_device(REPLAY_DEV, "edge_impulse")
    invalid_before = get_json("/health")["invalid_messages"]
    before = len(rec.for_device(REPLAY_DEV))

    collector = bench("src/collector.py", "--results-dir", results_dir, "--model-id", REPLAY_MODEL,
                      "--device-id", REPLAY_DEV, "--label", "FACE", "--distance", "50cm", "--env", "NORMAL",
                      "--start-delay", "0", "--bridge-threshold", str(THRESHOLD),
                      "--duration", str(int(len(REPLAY_SCORES) * interval_s + 4)))
    if not await wait_collecting(results_dir, REPLAY_MODEL):
        check("P2 collector started", False, "no start line within 30 s")
        return

    client = common.mqtt_client("e2e-serial-replay")
    client.connect("localhost", common.MQTT_PORT)
    client.loop_start()
    parser = SerialParser()
    bridge = Bridge(lambda t, m: client.publish(t, json.dumps(m)), REPLAY_DEV, REPLAY_MODEL, 96, 96,
                    threshold=THRESHOLD)
    for i, score in enumerate(REPLAY_SCORES):
        if i:
            await asyncio.sleep(interval_s)
        for line in serial_lines(score):
            frame = parser.feed(line)
            if frame:
                bridge.handle(frame)
        frame = parser.flush()  # what the bridge does on a serial read timeout
        if frame:
            bridge.handle(frame)
    await asyncio.sleep(1)
    client.loop_stop()
    client.disconnect()
    await asyncio.to_thread(collector.wait, 120)

    got = rec.for_device(REPLAY_DEV)[before:]
    cmds = [m["command"] for m in got]
    rows = read_session(results_dir, REPLAY_MODEL)
    expected = expected_commands(debounce, rows)
    print(f"gateway debounce={debounce}", flush=True)
    check("P2a gateway accepted every bridge payload", get_json("/health")["invalid_messages"] == invalid_before,
          f"frames={bridge.det_seq} parse_failures={parser.parse_failures}")
    check("P2b PLAY/PAUSE sequence matches gateway debounce settings", cmds == expected,
          f"got {cmds}, expected {expected}")
    if not any(debounce[d]["min_count"] > 1 or debounce[d]["min_ms"] > 0 for d in ("play", "pause")):
        flips = sum(1 for a, b in zip(REPLAY_SCORES, REPLAY_SCORES[1:])
                    if (a is not None and a >= THRESHOLD) != (b is not None and b >= THRESHOLD))
        print(f"  debounce off: {flips + 1} switches for {len(REPLAY_SCORES)} flickering frames", flush=True)
    check("P2c WebSocket source=edge_impulse with numeric confidence",
          bool(got) and all(m["source"] == "edge_impulse" and isinstance(m["confidence"], (int, float)) for m in got),
          str([m["confidence"] for m in got]))

    dets = [r["payload"] for r in rows if r["kind"] == "detection"]
    zero = [d for d in dets if d["confidence"] == 0]
    check("P2d collector stored all frames valid, confidence 0 kept, threshold recorded",
          len(dets) == len(REPLAY_SCORES) and all(r["valid"] for r in rows) and len(zero) == REPLAY_SCORES.count(None)
          and all(d.get("threshold") == THRESHOLD for d in dets),
          f"detections={len(dets)} zero_conf={len(zero)} rows={len(rows)}")
    if MODEL_KIND == "classification":
        check("P2e no bbox for classification model", not any("bbox" in d for d in dets), "")
    else:
        check("P2e bbox only when raw_face_detected",
              all(("bbox" in d) == d["raw_face_detected"] for d in dets), "")
    ok, tail = run_analyzer(results_dir, REPLAY_MODEL)
    check("P2f analyzer summary for replay session", ok, str(tail))


async def phase_timeout(rec: WsRecorder) -> None:
    print("\n== P3 replay device silent -> fail-safe DEVICE_TIMEOUT ==", flush=True)
    dev = get_json("/api/state")["devices"].get(REPLAY_DEV, {})
    timeout_s = get_json("/api/state")["device_timeout_ms"] / 1000
    if dev.get("command") != "PLAY":
        check("P3 fail-safe timeout", False, f"replay device not PLAYING ({dev.get('command')}), skipped")
        return
    before = len(rec.for_device(REPLAY_DEV))
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s + 5 and len(rec.for_device(REPLAY_DEV)) == before:
        await asyncio.sleep(0.2)
    got = rec.for_device(REPLAY_DEV)[before:]
    elapsed = time.monotonic() - t0 + (dev.get("ms_since_last_detection") or 0) / 1000
    ok = len(got) == 1 and got[0]["command"] == "PAUSE" and got[0]["detail"] == "DEVICE_TIMEOUT"
    check("P3 fail-safe PAUSE/DEVICE_TIMEOUT", ok, f"{[(m['command'], m['detail']) for m in got]} "
          f"~{elapsed:.1f}s after last detection (timeout {timeout_s:.0f}s)")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frame-interval", type=float, default=2.3, help="replay seconds per frame")
    ap.add_argument("--skip-timeout", action="store_true", help="skip P3 (saves ~25 s)")
    ap.add_argument("--model", choices=["fomo", "classification"], default="fomo",
                    help="serial output format to replay")
    args = ap.parse_args()
    global MODEL_KIND, THRESHOLD
    MODEL_KIND = args.model
    THRESHOLD = 0.5 if args.model == "classification" else 0.6

    for _ in range(30):  # a just-restarted broker takes a few seconds to be reconnected
        health = get_json("/health")
        if health["mqtt_connected"]:
            break
        time.sleep(0.5)
    check("H gateway /health", health["status"] == "ok" and health["mqtt_connected"], json.dumps(health))
    ps = compose("--profile", "benchmark", "ps", "--format", "{{.Service}}", check_rc=False).stdout.split()
    need = {"mqtt-broker", "control-gateway", "web-ui", "model-benchmark"}
    check("H containers running", need <= set(ps), str(sorted(ps)))
    if not need <= set(ps):
        return 1

    results_dir = f"/tmp/e2e-{int(time.time())}"  # inside the container; real results/ untouched
    rec = WsRecorder()
    async with websockets.connect(WS_URL) as ws:
        task = asyncio.create_task(rec.run(ws))
        await asyncio.sleep(0.5)
        await phase_mock(rec, results_dir)
        await phase_replay(rec, results_dir, args.frame_interval)
        if not args.skip_timeout:
            await phase_timeout(rec)
        task.cancel()

    print("\n=== SUMMARY ===")
    for name, ok, _ in results:
        print(f"{'PASS' if ok else 'FAIL':8} {name}")
    print("\nTest devices remain in the gateway: docker compose restart control-gateway")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
