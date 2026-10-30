"""collector 결과 → summary.csv / summary.md

판정 기준은 raw_face_detected. expected_face=true 그룹의 face_rate 는 검출률,
false 그룹의 face_rate 는 오탐률이다. 스키마 검증 실패 메시지는 지표에서 제외.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import common

THRESHOLDS = [round(0.3 + 0.1 * i, 1) for i in range(7)]  # 0.3 ~ 0.9
DEBOUNCE_FRAMES = [1, 2, 3, 4, 5]
META_COLUMNS = ["session_id", "label", "distance", "env", "operator", "started_at", "deploy",
                "esp_nn", "color", "device_threshold", "bridge_threshold", "download_date", "lighting", "camera_height", "camera_position", "notes"]


def percentile(values, q):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def mean(values):
    return sum(values) / len(values) if values else None


def transitions(states):
    return sum(a != b for a, b in zip(states, states[1:]))


def debounce(states, n):
    """n 프레임 연속 같은 값이 나와야 상태 변경. 첫 상태는 첫 프레임 값."""
    if not states:
        return []
    out, cur, run_val, run = [], states[0], states[0], 0
    for s in states:
        run = run + 1 if s == run_val else 1
        run_val = s
        if run >= n:
            cur = s
        out.append(cur)
    return out


def seq_stats(seqs):
    """(수신, 기대) — seq 감소 시 재부팅으로 보고 구간 분리."""
    if not seqs:
        return 0, 0
    received = expected = 0
    seg = [seqs[0]]
    for s in seqs[1:]:
        if s < seg[-1]:
            received, expected = received + len(set(seg)), expected + max(seg) - min(seg) + 1
            seg = []
        seg.append(s)
    return received + len(set(seg)), expected + max(seg) - min(seg) + 1


def load_sessions(root: Path):
    for meta_path in sorted(root.glob("**/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        records = []
        jl = meta_path.parent / "messages.jsonl"
        if jl.exists():
            records = [json.loads(line) for line in jl.read_text(encoding="utf-8").splitlines() if line.strip()]
        yield meta, records


def session_metrics(meta, records):
    dets_by_dev, tels = defaultdict(list), []
    invalid = 0
    for r in sorted(records, key=lambda r: r["received_at"]):
        if not r["valid"]:
            invalid += 1
        elif r["kind"] == "detection":
            dets_by_dev[r["payload"]["device_id"]].append(r["payload"])
        else:
            tels.append(r["payload"])

    m = {"faces": [], "confs": [], "inference_ms": [], "fps": [], "transitions": 0,
         "seq_received": 0, "seq_expected": 0, "invalid": invalid, "frame_ms": [],
         "debounce": {n: 0 for n in DEBOUNCE_FRAMES}}
    for dets in dets_by_dev.values():
        states = [d["raw_face_detected"] for d in dets]
        m["faces"] += states
        m["confs"] += [d["confidence"] for d in dets]
        m["inference_ms"] += [d["inference_ms"] for d in dets]
        m["transitions"] += transitions(states)
        for n in DEBOUNCE_FRAMES:
            m["debounce"][n] += transitions(debounce(states, n))
        recv, exp = seq_stats([d["seq"] for d in dets])
        m["seq_received"] += recv
        m["seq_expected"] += exp
        ups = [d["uptime_ms"] for d in dets]
        m["frame_ms"] += [b - a for a, b in zip(ups, ups[1:]) if b > a]
    m["fps"] = [t["fps"] for t in tels if "fps" in t]
    if not m["fps"] and m["frame_ms"]:
        m["fps"] = [1000 / mean(m["frame_ms"])]
    return m


def aggregate(sessions):
    groups = defaultdict(list)
    for meta, records in sessions:
        key = (meta.get("model_id"), meta["label"], meta["distance"], meta["env"], meta.get("expected_face"))
        groups[key].append(session_metrics(meta, records))

    rows = []
    for (model_id, label, distance, env, expected), ms in sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0]))):
        faces = [f for m in ms for f in m["faces"]]
        confs = [c for m in ms for c in m["confs"]]
        inf = [x for m in ms for x in m["inference_ms"]]
        fps = [x for m in ms for x in m["fps"]]
        frame_ms = [x for m in ms for x in m["frame_ms"]]
        recv, exp = sum(m["seq_received"] for m in ms), sum(m["seq_expected"] for m in ms)
        n = len(faces)
        row = {
            "model_id": model_id, "label": label, "distance": distance, "env": env,
            "expected_face": expected, "metric": "detection_rate" if expected else "false_positive_rate",
            "sessions": len(ms), "frames": n, "invalid_msgs": sum(m["invalid"] for m in ms),
            "face_rate": sum(faces) / n if n else None,
        }
        for t in THRESHOLDS:
            row[f"rate@{t}"] = sum(c >= t for c in confs) / n if n else None
        row.update({
            "inference_ms_mean": mean(inf), "inference_ms_p50": percentile(inf, 0.5),
            "inference_ms_p95": percentile(inf, 0.95), "fps": mean(fps),
            "transitions": sum(m["transitions"] for m in ms),
            "seq_loss_rate": 1 - recv / exp if exp else None,
        })
        frame = mean(frame_ms)
        for k in DEBOUNCE_FRAMES:
            row[f"debounce{k}_transitions"] = sum(m["debounce"][k] for m in ms)
            row[f"debounce{k}_added_ms"] = (k - 1) * frame if frame else None
        rows.append(row)
    return rows


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(fmt(r.get(h)) for h in headers) + " |" for r in rows]
    return "\n".join(lines)


def write_reports(rows, metas, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    if rows:
        with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    key = ["label", "distance", "env"]
    parts = [
        "# Model Benchmark Summary", "",
        "판정 기준: `raw_face_detected`. FACE 계열은 검출률, NO_FACE 계열은 오탐률.", "",
        "## 측정 조건", "", md_table(META_COLUMNS, metas), "",
        "## 검출률 / 오탐률", "",
        md_table(["model_id", *key, "metric", "sessions", "frames", "invalid_msgs", "face_rate"], rows), "",
        "## confidence 임계값별 비율 (저장된 confidence ≥ t, raw_face_detected 와 무관)", "",
        "기기는 0.2 이상 박스를 출력하므로 bridge 임계값보다 낮은 t 도 계산 가능.", "",
        md_table([*key, *(f"rate@{t}" for t in THRESHOLDS)], rows), "",
        "## 성능 / 안정성", "",
        md_table([*key, "inference_ms_mean", "inference_ms_p50", "inference_ms_p95", "fps",
                  "transitions", "seq_loss_rate"], rows), "",
        "## Debounce 시뮬레이션 (N 프레임 연속 시 전환)", "",
        "`added_ms` = (N-1) × 평균 프레임 간격: 실제 전환이 늦어지는 추정 시간.", "",
        md_table([*key, *(f"debounce{k}_{s}" for k in DEBOUNCE_FRAMES for s in ("transitions", "added_ms"))], rows),
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(parts), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", type=Path, default=common.RESULTS_DIR)
    p.add_argument("--model-id", default=common.DEFAULT_MODEL_ID)
    p.add_argument("--date", help="YYYYMMDD, 생략 시 해당 모델 전체")
    p.add_argument("--out", type=Path, help="기본: 분석 대상 디렉터리")
    args = p.parse_args()

    root = args.results_dir / args.model_id
    if args.date:
        root /= args.date
    sessions = list(load_sessions(root))
    if not sessions:
        raise SystemExit(f"세션 없음: {root}")
    rows = aggregate(sessions)
    write_reports(rows, [m for m, _ in sessions], args.out or root)
    print(f"[analyzer] {len(sessions)} 세션 → {(args.out or root) / 'summary.md'}")


if __name__ == "__main__":
    main()
