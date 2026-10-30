"""collector 결과 → summary.csv / summary.md

판정 기준은 raw_face_detected. expected_face=true 그룹의 face_rate 는 검출률,
false 그룹의 face_rate 는 오탐률이다. 스키마 검증 실패 메시지는 지표에서 제외.
confidence / inference_ms 는 선택 필드(mock 은 미전송)라 있는 메시지만 집계하고, 없으면 "-".
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import common

THRESHOLDS = [round(0.3 + 0.1 * i, 1) for i in range(7)]  # 0.3 ~ 0.9
DEBOUNCE_FRAMES = [1, 2, 3, 4, 5]
HOLD_THRESHOLDS = [0.4, 0.5, 0.6]
HOLD_SECONDS = [2.5, 5, 7.5, 10]
HOLD_COMBOS = [(t, h) for t in HOLD_THRESHOLDS for h in HOLD_SECONDS]
# board_pkg / esp_nn 필드가 생기기 전 세션의 실제 환경 (meta.json 은 수정하지 않고 읽을 때 간주)
LEGACY_BOARD_PKG, LEGACY_ESP_NN = "3.3.12", "off"
META_COLUMNS = ["session_id", "label", "position", "distance", "env", "operator", "started_at", "board_pkg", "deploy",
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


def hold_simulation(frames, t, hold_ms):
    """비대칭 debounce (추정). frames: [(uptime_ms, confidence)] 시간순.

    confidence >= t 이면 검출. PLAY 는 검출 1회 즉시, PAUSE 는 마지막 검출 후 hold_ms 경과 시.
    반환: (plays, pauses, play_ms, span_ms) — span 은 첫 프레임 ~ 마지막 프레임.
    """
    if not frames:
        return 0, 0, 0, 0
    plays = pauses = play_ms = 0
    playing, play_start, last_det = False, 0, 0
    for ts, conf in frames:
        if playing and ts - last_det > hold_ms:
            playing, pauses = False, pauses + 1
            play_ms += last_det + hold_ms - play_start
        if conf >= t:
            if not playing:
                playing, plays, play_start = True, plays + 1, ts
            last_det = ts
    end = frames[-1][0]
    if playing:
        play_ms += min(last_det + hold_ms, end) - play_start
    return plays, pauses, play_ms, end - frames[0][0]


def distance_key(distance):
    """'50cm' → 50, 숫자 없으면 맨 뒤."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(distance))
    return (0, float(m[1])) if m else (1, 0.0)


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


def with_env(meta: dict) -> dict:
    """board_pkg / esp_nn 이 없는 예전 세션은 3.3.12 / off 로 간주한 사본 (원본 dict 는 그대로)."""
    return {**meta, "board_pkg": meta.get("board_pkg") or LEGACY_BOARD_PKG,
            "esp_nn": meta.get("esp_nn") or LEGACY_ESP_NN}


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
         "debounce": {n: 0 for n in DEBOUNCE_FRAMES},
         "hold": {k: [0, 0, 0, 0] for k in HOLD_COMBOS}, "has_conf": False}  # [plays, pauses, play_ms, span_ms]
    for dets in dets_by_dev.values():
        states = [d["raw_face_detected"] for d in dets]
        m["faces"] += states
        m["confs"] += [d["confidence"] for d in dets if "confidence" in d]
        m["inference_ms"] += [d["inference_ms"] for d in dets if "inference_ms" in d]
        m["transitions"] += transitions(states)
        for n in DEBOUNCE_FRAMES:
            m["debounce"][n] += transitions(debounce(states, n))
        frames = [(d["uptime_ms"], d["confidence"]) for d in dets if "confidence" in d]
        m["has_conf"] |= bool(frames)
        for t, hold_s in HOLD_COMBOS:
            acc = m["hold"][(t, hold_s)]
            for i, v in enumerate(hold_simulation(frames, t, hold_s * 1000)):
                acc[i] += v
        recv, exp = seq_stats([d["seq"] for d in dets])
        m["seq_received"] += recv
        m["seq_expected"] += exp
        ups = [d["uptime_ms"] for d in dets]
        m["frame_ms"] += [b - a for a, b in zip(ups, ups[1:]) if b > a]
    m["fps"] = [t["fps"] for t in tels if "fps" in t]
    if not m["fps"] and m["frame_ms"]:
        m["fps"] = [1000 / mean(m["frame_ms"])]
    return m


def aggregate(sessions, hold_out: list | None = None):
    """그룹별 지표 행 반환. hold_out 을 주면 비대칭 debounce 시뮬레이션 행을 채운다."""
    groups = defaultdict(list)
    for meta, records in sessions:
        meta = with_env(meta)
        key = (meta.get("model_id"), meta["board_pkg"], meta["esp_nn"], meta["label"],
               meta.get("position", "CENTER"), meta["distance"], meta["env"], meta.get("expected_face"))
        groups[key].append(session_metrics(meta, records))

    rows, hold_rows = [], []
    for (model_id, board_pkg, esp_nn, label, position, distance, env, expected), ms in sorted(
            groups.items(), key=lambda kv: (*map(str, kv[0][:5]), distance_key(kv[0][5]), str(kv[0][6]))):
        env_cols = {"board_pkg": board_pkg, "esp_nn": esp_nn}
        faces = [f for m in ms for f in m["faces"]]
        confs = [c for m in ms for c in m["confs"]]
        inf = [x for m in ms for x in m["inference_ms"]]
        fps = [x for m in ms for x in m["fps"]]
        frame_ms = [x for m in ms for x in m["frame_ms"]]
        recv, exp = sum(m["seq_received"] for m in ms), sum(m["seq_expected"] for m in ms)
        n = len(faces)
        row = {
            "model_id": model_id, **env_cols, "label": label, "position": position, "distance": distance, "env": env,
            "expected_face": expected, "metric": "detection_rate" if expected else "false_positive_rate",
            "sessions": len(ms), "frames": n, "invalid_msgs": sum(m["invalid"] for m in ms),
            "face_rate": sum(faces) / n if n else None,
        }
        for t in THRESHOLDS:
            row[f"rate@{t}"] = sum(c >= t for c in confs) / len(confs) if confs else None
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
        has_conf = any(m["has_conf"] for m in ms)
        for t, hold_s in HOLD_COMBOS:
            plays, pauses, play_ms, span_ms = (sum(m["hold"][(t, hold_s)][i] for m in ms) for i in range(4))
            hold_rows.append({
                **env_cols, "label": label, "position": position, "distance": distance, "env": env,
                "expected_face": expected, "t": t, "hold_s": hold_s,
                "wrong_pause": pauses if expected and has_conf else None,
                "play_ratio": play_ms / span_ms if has_conf and span_ms else None,
                "wrong_play": plays if not expected and has_conf else None,
                "pause_latency_s_est": hold_s,
            })
        rows.append(row)
    if hold_out is not None:
        hold_out.extend(hold_rows)
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


def write_csv(path: Path, rows):
    if rows:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def write_reports(rows, metas, out_dir: Path, hold_rows=()):
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "summary.csv", rows)
    write_csv(out_dir / "hold_simulation.csv", list(hold_rows))
    parts = [
        "# Model Benchmark Summary", "",
        "판정 기준: `raw_face_detected`. FACE 계열은 검출률, NO_FACE 계열은 오탐률.",
        f"board_pkg / esp_nn 이 기록되지 않은 세션은 {LEGACY_BOARD_PKG} / {LEGACY_ESP_NN} 으로 간주.", "",
        "## 측정 조건", "", md_table(META_COLUMNS, [with_env(m) for m in metas]), "",
    ]
    envs = sorted({(r["board_pkg"], r["esp_nn"]) for r in rows})
    for board_pkg, esp_nn in envs:
        def same(r):
            return (r["board_pkg"], r["esp_nn"]) == (board_pkg, esp_nn)
        parts += [f"# 환경: esp32 {board_pkg} / ESP-NN {esp_nn}", "",
                  *env_sections([r for r in rows if same(r)], [r for r in hold_rows if same(r)])]
    (out_dir / "summary.md").write_text("\n".join(parts), encoding="utf-8")


def env_sections(rows, hold_rows):
    face_hold = [r for r in hold_rows if r["expected_face"]]
    noface_hold = [r for r in hold_rows if not r["expected_face"]]
    key = ["label", "position", "distance", "env"]
    return [
        "## 검출률 / 오탐률", "",
        md_table(["model_id", *key, "metric", "sessions", "frames", "invalid_msgs", "face_rate"], rows), "",
        "## confidence 임계값별 비율 (저장된 confidence ≥ t, raw_face_detected 와 무관)", "",
        "기기 출력 임계값(측정 조건 표 device_threshold) 미만 박스는 기기가 출력하지 않으므로 그보다 낮은 t 는 의미 없음.", "",
        md_table([*key, *(f"rate@{t}" for t in THRESHOLDS)], rows), "",
        "## 성능 / 안정성", "",
        md_table([*key, "inference_ms_mean", "inference_ms_p50", "inference_ms_p95", "fps",
                  "transitions", "seq_loss_rate"], rows), "",
        "## Debounce 시뮬레이션 (N 프레임 연속 시 전환)", "",
        "`added_ms` = (N-1) × 평균 프레임 간격: 실제 전환이 늦어지는 추정 시간.", "",
        md_table([*key, *(f"debounce{k}_{s}" for k in DEBOUNCE_FRAMES for s in ("transitions", "added_ms"))], rows),
        "",
        "## 비대칭 Debounce 시뮬레이션 (추정)", "",
        "저장된 confidence ≥ t 를 검출로 보고, PLAY 는 검출 1회 즉시, PAUSE 는 마지막 검출 후 hold 초 경과 시.",
        "시간은 실제 프레임 수신 간격(uptime_ms) 기준. **실측이 아닌 시뮬레이션 결과**이며,",
        "`pause_latency_s_est` 는 hold 값 그대로인 추정치(실제 반응 지연은 미측정).",
        "한 번도 검출되지 않은 세션은 PAUSE 오류 0 / 재생 비율 0 이므로 debounce 로 해결할 수 없다.", "",
        "### FACE 세션: 잘못된 PAUSE (정면인데 멈춤), 재생 상태 시간 비율", "",
        md_table([*key, "t", "hold_s", "wrong_pause", "play_ratio", "pause_latency_s_est"], face_hold), "",
        "### NO_FACE 계열 세션 (빈 화면, 측면 등): 잘못된 PLAY 횟수, 재생 상태 시간 비율", "",
        md_table([*key, "t", "hold_s", "wrong_play", "play_ratio", "pause_latency_s_est"], noface_hold), "",
    ]


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
    hold_rows = []
    rows = aggregate(sessions, hold_rows)
    write_reports(rows, [m for m, _ in sessions], args.out or root, hold_rows)
    print(f"[analyzer] {len(sessions)} 세션 → {(args.out or root) / 'summary.md'}")


if __name__ == "__main__":
    main()
