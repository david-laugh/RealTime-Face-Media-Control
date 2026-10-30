#!/usr/bin/env python3
"""Browser E2E: drive the real web-ui page (headless Chrome, DevTools Protocol) with MQTT signals.

MQTT (xiao-01 mock payloads) -> mqtt-broker -> control-gateway -> WS /ws -> web-ui -> YouTube player

Prerequisite:
    docker compose up -d --build mqtt-broker control-gateway web-ui
    pip install -r services/control-gateway/requirements-dev.txt
    Google Chrome installed (override with CHROME_PATH env var); internet access for YouTube

Run from the repo root (W6 restarts the mqtt-broker container):
    python scripts/webui_e2e_test.py

Read-only with respect to web-ui: it only loads the page, clicks 시작하기 and reads the DOM / player state.
Note: web-ui reacts to every device_id, so do not run this while someone is using the page.
"""
import json, os, subprocess, sys, tempfile, time, urllib.request
import paho.mqtt.client as mqtt
from websockets.sync.client import connect

CHROME = os.getenv("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PORT = 9333
URL = "http://localhost:8080/"
DEV = "xiao-01"

profile = tempfile.mkdtemp(prefix="webui-e2e-")
proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                         "--autoplay-policy=no-user-gesture-required", "--mute-audio", "--no-first-run",
                         "--window-size=1280,900", "about:blank"])
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1); break
        except Exception:
            time.sleep(0.2)
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{URL}", method="PUT")
    tab = json.loads(urllib.request.urlopen(req).read())
    cdp = connect(tab["webSocketDebuggerUrl"], max_size=None)
    mid = 0

    def ev(expr):
        global mid
        mid += 1
        cdp.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                             "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
        while True:
            m = json.loads(cdp.recv())
            if m.get("id") == mid:
                r = m["result"]
                if "exceptionDetails" in r:
                    return f"<exception {r['exceptionDetails'].get('text')}>"
                return r["result"].get("value")

    SNAP = """({conn: document.getElementById('connText').textContent,
      label: document.getElementById('label').textContent,
      meta: document.getElementById('meta').textContent,
      conf: document.getElementById('sConf').textContent,
      pauses: document.getElementById('sPause').textContent,
      ready, started,
      yt: (ready && player.getPlayerState) ? player.getPlayerState() : null,
      log: [...document.querySelectorAll('#log div')].slice(0,3).map(d=>d.textContent)})"""
    YT = {-1: "UNSTARTED", 0: "ENDED", 1: "PLAYING", 2: "PAUSED", 3: "BUFFERING", 5: "CUED", None: "n/a"}

    def snap(tag):
        s = ev(SNAP)
        print(f"[{time.strftime('%H:%M:%S')}] {tag}\n    conn={s['conn']!r} label={s['label']!r} conf={s['conf']} "
              f"pauses={s['pauses']} youtube={YT.get(s['yt'], s['yt'])}\n    meta={s['meta']!r}\n    log={s['log']}", flush=True)
        return s

    # wait for WS + YouTube player
    for _ in range(60):
        s = ev("({c: document.getElementById('connText').textContent, r: typeof ready !== 'undefined' && ready})")
        if s and s["c"] == "게이트웨이 연결됨" and s["r"]:
            break
        time.sleep(0.5)
    snap("page loaded (before 시작하기)")
    ev("document.getElementById('start').click()")
    time.sleep(1.5)
    snap("after clicking 시작하기")

    m = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="webui-e2e")
    m.connect("localhost", 1883); m.loop_start()
    st = lambda online: json.dumps({"schema_version": "1.0", "device_id": DEV, "source": "mock", "online": online})
    seq = 0

    def det(face):
        global seq
        seq += 1
        m.publish(f"smart-media/{DEV}/detection", json.dumps({"schema_version": "1.0", "device_id": DEV, "seq": seq,
                  "uptime_ms": seq * 10000, "source": "mock", "model_id": "mock-v1", "raw_face_detected": face})).wait_for_publish()

    results = []

    def check(name, s, label, yt_ok):
        ok = s["label"] == label and s["yt"] in yt_ok
        results.append((name, ok))
        print(f"    => {'PASS' if ok else 'FAIL'} {name}", flush=True)

    m.publish(f"smart-media/{DEV}/status", st(True), qos=1, retain=True).wait_for_publish()
    det(True); time.sleep(3)
    check("W1 detection true -> 보고 있어요 + PLAYING", snap("MQTT detection true"), "보고 있어요", (1, 3))
    det(False); time.sleep(2)
    check("W2 detection false -> 자리 비움 + PAUSED", snap("MQTT detection false"), "자리 비움", (2,))
    det(True); time.sleep(3)
    check("W3 detection true again -> PLAYING", snap("MQTT detection true"), "보고 있어요", (1, 3))
    m.publish(f"smart-media/{DEV}/status", st(False), qos=1, retain=True).wait_for_publish(); time.sleep(2)
    check("W4 status offline -> 카메라 끊김 + PAUSED", snap("MQTT status offline"), "카메라 끊김", (2,))
    m.publish(f"smart-media/{DEV}/status", st(True), qos=1, retain=True).wait_for_publish()
    det(True); time.sleep(3)
    snap("MQTT detection true (before timeout wait)")
    print("    waiting 27 s without detections ...", flush=True)
    time.sleep(27)
    check("W5 no detection 25 s -> 카메라 끊김 + PAUSED", snap("after 27 s silence"), "카메라 끊김", (2,))
    det(True); time.sleep(3)
    snap("MQTT detection true")
    subprocess.run(["docker", "compose", "restart", "mqtt-broker"], capture_output=True, check=True)
    time.sleep(2)
    check("W6 broker restart -> 판단 불가 + PAUSED", snap("after docker compose restart mqtt-broker"), "판단 불가", (2,))
    time.sleep(2)
    det(True); time.sleep(3)
    check("W7 after broker recovery, true -> PLAYING", snap("MQTT detection true after recovery"), "보고 있어요", (1, 3))
    # reload page: snapshot sync
    ev("location.reload()"); time.sleep(6)
    check("W8 page reload -> current state synced (before 시작하기)", snap("after page reload"), "보고 있어요", (-1, 5, None))
    det(False); time.sleep(1)
    m.loop_stop(); m.disconnect()
    print("\n=== SUMMARY ===")
    for n, ok in results:
        print(("PASS " if ok else "FAIL ") + n)
    sys.exit(0 if all(ok for _, ok in results) else 1)
finally:
    proc.terminate()
