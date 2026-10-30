"""지정 시간 동안 detection/telemetry 를 구독해 세션 JSONL + meta.json 으로 저장.

저장 위치: {RESULTS_DIR}/{model_id}/{YYYYMMDD}/{HHMMSS}_{label}_{distance}_{env}/
개인정보: 스키마에 정의된 필드만 저장한다 (JSON 이 아니거나 스키마 밖 필드는 버림).
"""
import argparse
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import common


def build_record(topic: str, raw: bytes, ctx: dict) -> dict | None:
    kind = common.kind_of(topic)
    if kind is None:
        return None
    rec = {"received_at": time.time(), "topic": topic, "kind": kind, **ctx}
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {**rec, "payload": None, "valid": False, "errors": ["<root>:not_json"]}
    errors = common.validate(kind, payload)
    if isinstance(payload, dict):
        fields = common.schema_fields(kind)
        payload = {k: v for k, v in payload.items() if k in fields}
    else:
        payload = None
    return {**rec, "payload": payload, "valid": not errors, "errors": errors}


class Recorder:
    """recording=True 인 동안만 저장. 카운트다운 중 수신 메시지는 dropped 로만 센다."""

    def __init__(self, fh, ctx: dict):
        self.fh, self.ctx = fh, ctx
        self.recording = False
        self.lock = threading.Lock()
        self.counts = {"detection": 0, "telemetry": 0, "invalid": 0, "dropped_before_start": 0}

    def handle(self, topic: str, raw: bytes) -> bool:
        with self.lock:
            if not self.recording:
                if common.kind_of(topic):
                    self.counts["dropped_before_start"] += 1
                return False
            rec = build_record(topic, raw, self.ctx)
            if rec is None:
                return False
            self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.counts[rec["kind"]] += 1
            self.counts["invalid"] += not rec["valid"]
            return True

    def start(self):
        with self.lock:
            self.recording = True

    def stop(self):
        with self.lock:
            self.recording = False


def countdown(seconds: float, sleep=time.sleep, out=print):
    remaining = int(seconds)
    if seconds > remaining:
        sleep(seconds - remaining)
    for i in range(remaining, 0, -1):
        out(f"[collector] 시작까지 {i}초 (자세를 잡으세요, 이 동안 수신 메시지는 저장 안 함)")
        sleep(1)


def resolve_case(args) -> dict:
    case = {"label": args.label, "position": args.position, "distance": args.distance, "env": args.env,
            "duration_s": args.duration, "expected_face": None, "case_id": None}
    if args.case:
        found = {c["id"]: c for c in common.load_cases()}.get(args.case)
        if not found:
            raise SystemExit(f"cases.yaml 에 없는 case: {args.case}")
        case.update({k: found[k] for k in ("label", "position", "distance", "env", "duration_s", "expected_face")},
                    case_id=found["id"])
    for k in ("label", "distance", "env"):
        if case[k] is None:
            raise SystemExit(f"--{k} 또는 --case 가 필요합니다")
    if args.duration is not None:
        case["duration_s"] = args.duration
    if case["duration_s"] is None:
        case["duration_s"] = 120
    if case["expected_face"] is None:
        case["expected_face"] = case["label"] == "FACE"
    if case["position"] is None:
        case["position"] = "CENTER" if case["expected_face"] else "-"
    return case


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", help="cases.yaml 의 id (label/distance/env/duration 자동 설정)")
    p.add_argument("--label", help="FACE | NO_FACE (cases.yaml 의 label 확장 가능)")
    p.add_argument("--position", help="CENTER | OFFSET_LEFT | OFFSET_RIGHT (기본: FACE면 CENTER, 아니면 '-')")
    p.add_argument("--distance", help="예: 50cm, 없으면 '-'")
    p.add_argument("--env", help="NORMAL | BRIGHT | LOW_LIGHT")
    p.add_argument("--duration", type=float, help="수집 시간(초), 기본 120")
    p.add_argument("--start-delay", type=float, default=10, help="수집 시작 전 카운트다운(초), 기본 10")
    p.add_argument("--model-id", default=common.DEFAULT_MODEL_ID)
    p.add_argument("--device-id", default="+", help="기본 '+' (모든 디바이스)")
    p.add_argument("--mqtt-host", default=common.MQTT_HOST)
    p.add_argument("--mqtt-port", type=int, default=common.MQTT_PORT)
    p.add_argument("--results-dir", type=Path, default=common.RESULTS_DIR)
    # meta.json
    p.add_argument("--operator", default="", help="측정자 이니셜/별칭 (실명 금지)")
    p.add_argument("--deploy", default="int8+EON", help="배포 옵션, 예: int8+EON, int8")
    p.add_argument("--esp-nn", default="off", choices=["on", "off"])
    p.add_argument("--color", default="grayscale", choices=["grayscale", "rgb"])
    p.add_argument("--device-threshold", type=float, default=0.2,
                   help="기기 FOMO 출력 임계값 (model_variables.h, 원래 0.6 → 스윕용 0.2)")
    p.add_argument("--bridge-threshold", type=float, default=0.6, help="serial_bridge --threshold 값")
    p.add_argument("--download-date", default="", help="Edge Impulse 라이브러리 다운로드 날짜 YYYY-MM-DD")
    p.add_argument("--lighting", default="", help="조명 설명")
    p.add_argument("--camera-height", default="", help="카메라 높이, 예: 110cm")
    p.add_argument("--camera-position", default="", help="카메라 위치, 예: 모니터 상단 중앙")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    case = resolve_case(args)
    now = datetime.now()
    session_id = f"{now:%H%M%S}_{case['label']}_{case['position']}_{case['distance']}_{case['env']}".replace("/", "-")
    out_dir = args.results_dir / args.model_id / f"{now:%Y%m%d}" / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "session_id": session_id, "model_id": args.model_id, "device_id": args.device_id,
        "case_id": case["case_id"], "label": case["label"], "position": case["position"],
        "distance": case["distance"], "env": case["env"], "expected_face": case["expected_face"], "duration_s": case["duration_s"],
        "operator": args.operator, "start_delay_s": args.start_delay,
        "deploy": args.deploy, "esp_nn": args.esp_nn, "color": args.color,
        "device_threshold": args.device_threshold, "bridge_threshold": args.bridge_threshold,
        "download_date": args.download_date, "lighting": args.lighting,
        "camera_height": args.camera_height, "camera_position": args.camera_position,
        "notes": args.notes,
    }
    ctx = {"label": case["label"], "position": case["position"], "distance": case["distance"], "env": case["env"]}
    fh = (out_dir / "messages.jsonl").open("w", encoding="utf-8")
    recorder = Recorder(fh, ctx)

    def on_connect(client, _ud, _flags, rc, _props):
        if rc.is_failure:
            print(f"[collector] 연결 실패: {rc}")
            return
        for kind in common.KINDS:
            client.subscribe(common.topic(args.device_id, kind), qos=0)

    def on_message(_client, _ud, msg):
        recorder.handle(msg.topic, msg.payload)

    client = common.mqtt_client()
    client.on_connect, client.on_message = on_connect, on_message
    client.connect(args.mqtt_host, args.mqtt_port)
    client.loop_start()
    try:
        countdown(args.start_delay)
        recorder.start()
        meta["started_at"] = datetime.now().isoformat(timespec="seconds")
        print(f"[collector] {session_id}: {case['duration_s']}s 수집 시작 → {out_dir}")
        time.sleep(case["duration_s"])
    except KeyboardInterrupt:
        print("[collector] 중단됨")
    recorder.stop()
    client.loop_stop()
    client.disconnect()
    fh.close()
    meta.update(ended_at=datetime.now().isoformat(timespec="seconds"), counts=recorder.counts)
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[collector] 완료: {recorder.counts}")


if __name__ == "__main__":
    main()
