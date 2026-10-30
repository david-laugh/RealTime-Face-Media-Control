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
    p.add_argument("--model-id", default=common.DEFAULT_MODEL_ID)
    p.add_argument("--device-id", default="+", help="기본 '+' (모든 디바이스)")
    p.add_argument("--mqtt-host", default=common.MQTT_HOST)
    p.add_argument("--mqtt-port", type=int, default=common.MQTT_PORT)
    p.add_argument("--results-dir", type=Path, default=common.RESULTS_DIR)
    # meta.json
    p.add_argument("--operator", default="", help="측정자 이니셜/별칭 (실명 금지)")
    p.add_argument("--deploy", default="int8", help="배포 옵션, 예: int8, int8+EON")
    p.add_argument("--esp-nn", default="off", choices=["on", "off"])
    p.add_argument("--color", default="grayscale", choices=["grayscale", "rgb"])
    p.add_argument("--device-threshold", type=float, default=0.6,
                   help="기기 FOMO 출력 임계값 (model_variables.h, 2026-10-30 확인값 0.6)")
    p.add_argument("--bridge-threshold", type=float, default=0.5, help="serial_bridge --threshold 값")
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
        "operator": args.operator, "started_at": now.isoformat(timespec="seconds"),
        "deploy": args.deploy, "esp_nn": args.esp_nn, "color": args.color,
        "device_threshold": args.device_threshold, "bridge_threshold": args.bridge_threshold,
        "download_date": args.download_date, "lighting": args.lighting,
        "camera_height": args.camera_height, "camera_position": args.camera_position,
        "notes": args.notes,
    }
    ctx = {"label": case["label"], "position": case["position"], "distance": case["distance"], "env": case["env"]}
    lock = threading.Lock()
    counts = {"detection": 0, "telemetry": 0, "invalid": 0}
    fh = (out_dir / "messages.jsonl").open("w", encoding="utf-8")

    def on_connect(client, _ud, _flags, rc, _props):
        if rc.is_failure:
            print(f"[collector] 연결 실패: {rc}")
            return
        for kind in common.KINDS:
            client.subscribe(common.topic(args.device_id, kind), qos=0)

    def on_message(_client, _ud, msg):
        rec = build_record(msg.topic, msg.payload, ctx)
        if rec is None:
            return
        with lock:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            counts[rec["kind"]] += 1
            counts["invalid"] += not rec["valid"]

    client = common.mqtt_client()
    client.on_connect, client.on_message = on_connect, on_message
    client.connect(args.mqtt_host, args.mqtt_port)
    client.loop_start()
    print(f"[collector] {session_id}: {case['duration_s']}s 수집 → {out_dir}")
    try:
        time.sleep(case["duration_s"])
    except KeyboardInterrupt:
        print("[collector] 중단됨")
    client.loop_stop()
    client.disconnect()
    with lock:
        fh.close()
    meta.update(ended_at=datetime.now().isoformat(timespec="seconds"), counts=counts)
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[collector] 완료: {counts}")


if __name__ == "__main__":
    main()
