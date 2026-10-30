"""스키마 형식 가짜 디바이스 (기기 없이 gateway/web-ui/benchmark 테스트용).

모드: face | no_face | alternate (정면 --period 초 ↔ 부재 --period 초 반복) | random
"""
import argparse
import json
import random
import time

import common


def make_detection(device_id, model_id, seq, uptime_ms, face, rng, inference_ms):
    conf = round(rng.uniform(0.6, 0.95), 3) if face else 0.0
    bbox = None
    if face:
        w, h = round(rng.uniform(0.2, 0.4), 3), round(rng.uniform(0.25, 0.5), 3)
        bbox = {"x": round(rng.uniform(0, 1 - w), 3), "y": round(rng.uniform(0, 1 - h), 3), "w": w, "h": h}
    return {
        "schema_version": common.SCHEMA_VERSION, "device_id": device_id, "seq": seq,
        "uptime_ms": uptime_ms, "model_id": model_id, "raw_face_detected": face,
        "confidence": conf, "bbox": bbox, "inference_ms": inference_ms,
        "state": "FRONT_PRESENT" if face else "NOT_PRESENT",
    }


def make_telemetry(device_id, model_id, seq, uptime_ms, inference_ms, fps):
    return {
        "schema_version": common.SCHEMA_VERSION, "device_id": device_id, "seq": seq,
        "uptime_ms": uptime_ms, "model_id": model_id, "inference_ms": inference_ms,
        "fps": round(fps, 2),
    }


def face_at(mode, elapsed, period, rng):
    if mode == "face":
        return True
    if mode == "no_face":
        return False
    if mode == "alternate":
        return int(elapsed // period) % 2 == 0
    return rng.random() < 0.5


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device-id", default="mock-xiao-01")
    p.add_argument("--model-id", default="mock-model", help="실측 결과와 섞이지 않게 별도 ID")
    p.add_argument("--mode", choices=["face", "no_face", "alternate", "random"], default="alternate")
    p.add_argument("--period", type=float, default=5.0, help="alternate 모드 전환 주기(초)")
    p.add_argument("--fps", type=float, default=5.0)
    p.add_argument("--duration", type=float, default=0, help="0 이면 무한")
    p.add_argument("--telemetry-every", type=int, default=5, help="N 프레임마다 telemetry")
    p.add_argument("--drop", type=float, default=0.0, help="detection 유실 시뮬레이션 확률(seq 건너뜀)")
    p.add_argument("--seed", type=int)
    p.add_argument("--mqtt-host", default=common.MQTT_HOST)
    p.add_argument("--mqtt-port", type=int, default=common.MQTT_PORT)
    args = p.parse_args()

    rng = random.Random(args.seed)
    client = common.mqtt_client()
    client.connect(args.mqtt_host, args.mqtt_port)
    client.loop_start()
    det_topic = common.topic(args.device_id, "detection")
    tel_topic = common.topic(args.device_id, "telemetry")
    print(f"[mock] {args.mode} → {det_topic} @ {args.fps}fps")

    start = time.monotonic()
    det_seq = tel_seq = frame = 0
    try:
        while not args.duration or time.monotonic() - start < args.duration:
            elapsed = time.monotonic() - start
            uptime_ms = int(elapsed * 1000)
            inference_ms = int(rng.gauss(150, 10))
            face = face_at(args.mode, elapsed, args.period, rng)
            msg = make_detection(args.device_id, args.model_id, det_seq, uptime_ms, face, rng, max(inference_ms, 1))
            assert not common.validate("detection", msg), common.validate("detection", msg)
            if rng.random() >= args.drop:
                client.publish(det_topic, json.dumps(msg))
            det_seq += 1
            frame += 1
            if frame % args.telemetry_every == 0:
                tel = make_telemetry(args.device_id, args.model_id, tel_seq, uptime_ms, max(inference_ms, 1), args.fps)
                client.publish(tel_topic, json.dumps(tel))
                tel_seq += 1
            time.sleep(max(0.0, start + frame / args.fps - time.monotonic()))
    except KeyboardInterrupt:
        pass
    client.loop_stop()
    client.disconnect()
    print(f"[mock] 종료: detection {det_seq}건")


if __name__ == "__main__":
    main()
