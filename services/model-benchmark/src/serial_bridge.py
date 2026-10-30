"""Edge Impulse 예제 스케치 시리얼 출력 → MQTT detection/telemetry (호스트에서 직접 실행).

개인정보 보호: allowlist 파싱. 아래 3 형식만 처리하고 나머지 줄은 저장/로그/publish 없이 개수만 센다.
  "Predictions (DSP: %d ms., Classification: %d ms., Anomaly: %d ms.): "
  "Object detection bounding boxes:"
  "  %s (%f) [ x: %u, y: %u, width: %u, height: %u ]"
200자 초과 또는 숫자 나열이 긴 줄(debug_nn features 덤프 의심)은 내용 없이 경고 카운트만 남긴다.

변환 규칙:
- source = "edge_impulse".
- 한 프레임의 박스 중 최고 confidence 박스 사용. 박스가 없으면 confidence=0, bbox 필드 생략.
- raw_face_detected = (최고 confidence >= --threshold, 기본 0.6 = 모델 원래 판정 기준).
  기기는 출력 임계값(0.2) 이상 박스를 모두 출력하므로 임계값 미만이어도 confidence 는 그대로 보내
  analyzer 가 임계값 스윕에 쓴다 (이때 bbox 생략).
- DSP → telemetry.preprocess_ms, Classification → inference_ms.
- bbox 는 --input-width/--input-height 로 나눈 0~1 값. FOMO 는 중심점 검출 모델이라
  width/height 는 얼굴 크기가 아니라 출력 격자 셀 크기(예: 96x96 입력 → 8px)다. 위치(x, y)만 의미 있음.
- seq / uptime_ms 는 시리얼에 없으므로 bridge 가 생성 (uptime_ms = bridge 시작 후 경과 시간).
"""
import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field

import common

MAX_LINE_LEN = 200
MAX_NUMBERS = 12  # 정상 허용 줄은 숫자 6개 이하

PRED_RE = re.compile(
    r"^Predictions \(DSP: (\d+) ms\., Classification: (\d+) ms\., Anomaly: (-?\d+) ms\.\):\s*$")
BOXES_HEADER = "Object detection bounding boxes:"
BOX_RE = re.compile(
    r"^\s*(.+?) \((\d+(?:\.\d+)?)\) \[ x: (\d+), y: (\d+), width: (\d+), height: (\d+) \]\s*$")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class Box:
    label: str
    conf: float
    x: int
    y: int
    w: int
    h: int


@dataclass
class Frame:
    dsp_ms: int
    classification_ms: int
    t_host: float
    boxes: list[Box] = field(default_factory=list)


class SerialParser:
    def __init__(self, log=lambda msg: print(msg, file=sys.stderr)):
        self.log = log
        self.current: Frame | None = None
        self.in_boxes = False
        self.ignored = 0
        self.suspicious = 0
        self.parse_failures = 0

    def feed(self, line: str, now: float | None = None) -> Frame | None:
        """한 줄 처리. 새 프레임이 시작되면 이전 프레임을 반환."""
        line = line.strip()
        if not line:
            return None
        if len(line) > MAX_LINE_LEN or len(NUM_RE.findall(line)) > MAX_NUMBERS:
            self.suspicious += 1
            if self.suspicious == 1 or self.suspicious % 100 == 0:
                self.log(f"[bridge] 경고: 의심 줄 {self.suspicious}개 (내용 미기록) "
                         "- debug_nn이 켜져 있을 수 있음. 스케치에서 debug_nn=false 확인")
            return None

        if line.startswith("Predictions ("):
            m = PRED_RE.match(line)
            if not m:
                self._fail(line)
                return None
            done = self.flush()
            self.current = Frame(int(m[1]), int(m[2]), time.monotonic() if now is None else now)
            return done

        if line == BOXES_HEADER:
            self.in_boxes = self.current is not None
            return None

        m = BOX_RE.match(line)
        if m and self.current is not None and self.in_boxes:
            self.current.boxes.append(Box(m[1], float(m[2]), *map(int, m.groups()[2:])))
            return None
        if "[ x:" in line and self.in_boxes:
            self._fail(line)
            return None

        self.ignored += 1
        return None

    def flush(self) -> Frame | None:
        done, self.current, self.in_boxes = self.current, None, False
        return done

    def _fail(self, line: str):
        # 허용 형식 후보(접두어 일치, 200자 이하, 숫자 적음)만 디버깅용으로 남긴다
        self.parse_failures += 1
        self.log(f"[bridge] 파싱 실패: {line!r}")


def _clamp01(v: float) -> float:
    return round(min(max(v, 0.0), 1.0), 4)


class Bridge:
    """Frame → 스키마 메시지 생성 및 publish. publish(topic, dict) 주입 가능."""

    def __init__(self, publish, device_id, model_id, input_w, input_h, face_labels=None, start=None,
                 threshold=0.6):
        self.publish = publish
        self.threshold = threshold
        self.device_id, self.model_id = device_id, model_id
        self.input_w, self.input_h = input_w, input_h
        self.face_labels = set(face_labels or [])
        self.start = time.monotonic() if start is None else start
        self.det_seq = self.tel_seq = 0
        self.last_t: float | None = None

    def handle(self, frame: Frame):
        boxes = [b for b in frame.boxes if not self.face_labels or b.label in self.face_labels]
        best = max(boxes, key=lambda b: b.conf, default=None)
        face = best is not None and best.conf >= self.threshold
        uptime_ms = max(int((frame.t_host - self.start) * 1000), 0)
        det = {
            "schema_version": common.SCHEMA_VERSION, "device_id": self.device_id, "seq": self.det_seq,
            "uptime_ms": uptime_ms, "source": "edge_impulse", "model_id": self.model_id,
            "raw_face_detected": face,
            "confidence": _clamp01(best.conf) if best else 0,
            "inference_ms": frame.classification_ms,
        }
        if face:
            det["bbox"] = {
                "x": _clamp01(best.x / self.input_w), "y": _clamp01(best.y / self.input_h),
                "w": _clamp01(best.w / self.input_w), "h": _clamp01(best.h / self.input_h)}
        tel = {
            "schema_version": common.SCHEMA_VERSION, "device_id": self.device_id, "seq": self.tel_seq,
            "uptime_ms": uptime_ms, "model_id": self.model_id,
            "preprocess_ms": frame.dsp_ms, "inference_ms": frame.classification_ms,
        }
        if self.last_t is not None and frame.t_host > self.last_t:
            tel["fps"] = round(1 / (frame.t_host - self.last_t), 3)
        self.last_t = frame.t_host
        self.publish(common.topic(self.device_id, "detection"), det)
        self.publish(common.topic(self.device_id, "telemetry"), tel)
        self.det_seq += 1
        self.tel_seq += 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", required=True, help="예: COM5, /dev/ttyACM0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--device-id", default="xiao-bench-01")
    p.add_argument("--model-id", default=common.DEFAULT_MODEL_ID)
    p.add_argument("--input-width", type=int, required=True)
    p.add_argument("--input-height", type=int, required=True)
    p.add_argument("--face-label", action="append", help="얼굴로 볼 라벨 (기본: 모든 라벨)")
    p.add_argument("--threshold", type=float, default=0.6, help="raw_face_detected 판정 임계값 (모델 원래 기준 0.6)")
    p.add_argument("--mqtt-host", default="localhost")
    p.add_argument("--mqtt-port", type=int, default=common.MQTT_PORT)
    p.add_argument("--stats-every", type=float, default=30, help="통계 출력 주기(초)")
    args = p.parse_args()

    import serial

    client = common.mqtt_client()
    client.connect(args.mqtt_host, args.mqtt_port)
    client.loop_start()
    parser = SerialParser()
    bridge = Bridge(lambda t, m: client.publish(t, json.dumps(m)), args.device_id, args.model_id,
                    args.input_width, args.input_height, args.face_label, threshold=args.threshold)
    print(f"[bridge] {args.port}@{args.baud} → smart-media/{args.device_id}/* ({args.mqtt_host}:{args.mqtt_port})")

    last_stats = time.monotonic()
    try:
        with serial.Serial(args.port, args.baud, timeout=0.3) as ser:
            while True:
                raw = ser.readline()
                frame = parser.feed(raw.decode("utf-8", errors="replace")) if raw else parser.flush()
                if frame:
                    bridge.handle(frame)
                if time.monotonic() - last_stats >= args.stats_every:
                    last_stats = time.monotonic()
                    print(f"[bridge] frames={bridge.det_seq} ignored={parser.ignored} "
                          f"suspicious={parser.suspicious} parse_failures={parser.parse_failures}")
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
