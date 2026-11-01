"""Studio run-controls check, J7 (one shot).

Writes a fixture run (STATUS paused on photo_pia@p2, CONTROL with
pause_each_stage on, usage files for cost), starts scripts/server.py
on port 8765 (never 8000), drives headless Edge over CDP, and
asserts the Studio control bar (run picker, status chip, Now, cost,
Resume/Pause/One step/Stop enabled by state, each-stage toggle
persisted through the API) plus the matching Board chip/buttons.
Saves runs/studio_controls_1920.png and runs/studio_controls_390.png,
then ALWAYS stops the server + Edge and deletes the fixture run
(try/finally). Stdlib only. No model calls.
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = int(os.environ.get("CHECK_PORT", 8765))
CDP_PORT = int(os.environ.get("CHECK_CDP_PORT", 9444))
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
RUNS = os.path.join(ROOT, "runs")
FIX = os.path.join(RUNS, "studioctl1")
PNG1920 = os.path.join(RUNS, "studio_controls_1920.png")
PNG390 = os.path.join(RUNS, "studio_controls_390.png")
SERVER_LOG = os.path.join(RUNS, "studio_live_server.log")

fails = 0


def ok(cond, msg):
    global fails
    line = ("PASS " if cond else "FAIL ") + msg
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    if not cond:
        fails += 1


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        return True
    except OSError:
        return False


class WS:
    def __init__(self, host, port, path):
        self.s = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((
            "GET %s HTTP/1.1\r\nHost: %s:%d\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
            % (path, host, port, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.s.recv(4096)
            if not chunk:
                raise RuntimeError("ws handshake failed")
            head += chunk
        if b"101" not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError("ws not accepted: %r" % head[:80])
        self.buf = b""
        self.mid = 0
        self.events = []

    def _fill(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise RuntimeError("ws closed")
            self.buf += chunk

    def recv_msg(self):
        self._fill(2)
        b1, b2 = self.buf[0], self.buf[1]
        ln, off = b2 & 0x7F, 2
        if ln == 126:
            self._fill(4)
            ln, off = struct.unpack(">H", self.buf[2:4])[0], 4
        elif ln == 127:
            self._fill(10)
            ln, off = struct.unpack(">Q", self.buf[2:10])[0], 10
        mask = None
        if b2 & 0x80:
            self._fill(off + 4)
            mask, off = self.buf[off:off + 4], off + 4
        self._fill(off + ln)
        payload = self.buf[off:off + ln]
        self.buf = self.buf[off + ln:]
        if b1 & 0x8:
            if b1 == 0x8:
                raise RuntimeError("ws closed by peer")
            return self.recv_msg()
        if mask:
            payload = bytes(c ^ mask[i % 4]
                            for i, c in enumerate(payload))
        return payload.decode("utf-8", "replace")

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        ln = len(data)
        if ln < 126:
            head = bytes([0x81, 0x80 | ln])
        elif ln < 65536:
            head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", ln)
        else:
            head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", ln)
        self.s.sendall(head + mask + bytes(
            c ^ mask[i % 4] for i, c in enumerate(data)))

    def call(self, method, params=None, timeout=30):
        self.mid += 1
        self.send({"id": self.mid, "method": method,
                   "params": params or {}})
        deadline = time.time() + timeout
        while True:
            if time.time() > deadline:
                raise RuntimeError("cdp timeout: " + method)
            msg = json.loads(self.recv_msg())
            if msg.get("id") == self.mid:
                if "error" in msg:
                    raise RuntimeError("cdp %s: %s"
                                       % (method, msg["error"]))
                return msg.get("result", {})
            if "id" not in msg:
                self.events.append(msg)

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def js_eval(ws, expr, timeout=30):
    r = ws.call("Runtime.evaluate",
                {"expression": expr, "returnByValue": True},
                timeout=timeout)
    return (r.get("result") or {}).get("value")


def drain_dialogs(ws, seconds):
    """Dismiss any JS dialog. Headless has no UI to close one:
    without this the renderer deadlocks and CDP goes silent."""
    try:
        ws.s.settimeout(1.0)
    except OSError:
        pass
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            try:
                msg = json.loads(ws.recv_msg())
            except Exception:
                continue
            if msg.get("method") == "Page.javascriptDialogOpening":
                try:
                    ws.call("Page.handleJavaScriptDialog",
                            {"accept": False}, timeout=10)
                except Exception:
                    pass
            elif "id" not in msg:
                ws.events.append(msg)
    finally:
        try:
            ws.s.settimeout(30)
        except OSError:
            pass


def console_errors(events):
    n = 0
    for m in events:
        if m.get("method") == "Runtime.consoleAPICalled" \
                and m.get("params", {}).get("type") == "error":
            n += 1
        elif m.get("method") == "Runtime.exceptionThrown":
            n += 1
    return n


ST_JS = """JSON.stringify({
  chip: document.getElementById('st-chip').textContent,
  cls: document.getElementById('st-chip').className,
  now: document.getElementById('st-now').textContent,
  cost: document.getElementById('st-cost').textContent,
  resume: !document.getElementById('st-resume').disabled,
  pause: !document.getElementById('st-pause').disabled,
  step: !document.getElementById('st-step').disabled,
  stop: !document.getElementById('st-stop').disabled,
  each: document.getElementById('st-each').checked,
  err: document.getElementById('st-err').textContent,
  runs: Array.from(document.getElementById('st-run').options)
    .map(o => o.value)
})"""


def stop_proc(proc, name):
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except (OSError, subprocess.SubprocessError):
            pass
    print("stopped %s (exit %s)" % (name, proc.poll()), flush=True)


def wait_for(ws, expr, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js_eval(ws, expr):
            return True
        time.sleep(0.5)
    return False


def main():
    os.makedirs(RUNS, exist_ok=True)
    if port_open(SERVER_PORT):
        ok(False, "port %d already busy, touching nothing"
           % SERVER_PORT)
        print("1 FAILURES")
        return 1
    if port_open(CDP_PORT):
        ok(False, "cdp port %d already busy, touching nothing"
           % CDP_PORT)
        print("1 FAILURES")
        return 1
    if not os.path.isfile(EDGE):
        ok(False, "edge binary found")
        print("1 FAILURES")
        return 1
    shutil.rmtree(FIX, ignore_errors=True)
    os.makedirs(os.path.join(FIX, "sales_sam"))
    os.makedirs(os.path.join(FIX, "photo_pia", "p2"))
    with open(os.path.join(FIX, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"run_id": "studioctl1", "flow_id": "default",
                   "order_id": "octl", "state": "paused",
                   "current": "photo_pia@p2",
                   "completed": ["sales_sam", "pd_marty"],
                   "error": ""}, f)
    with open(os.path.join(FIX, "CONTROL.json"), "w",
              encoding="utf-8") as f:
        json.dump({"pause": True, "stop": False, "step_once": False,
                   "step_ack": False, "wake": False,
                   "pause_each_stage": True}, f)
    with open(os.path.join(FIX, "sales_sam", "usage.json"), "w",
              encoding="utf-8") as f:
        json.dump({"llm_calls": 2, "prompt_tokens": 20,
                   "completion_tokens": 10, "tools": {}}, f)
    with open(os.path.join(FIX, "photo_pia", "p2", "usage.json"),
              "w", encoding="utf-8") as f:
        json.dump({"llm_calls": 1, "prompt_tokens": 5,
                   "completion_tokens": 2, "tools": {}}, f)
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(),
                           "studio_live_profile")
    shutil.rmtree(profile, ignore_errors=True)
    try:
        logf = open(SERVER_LOG, "w", encoding="utf-8")
        server = subprocess.Popen(
            [sys.executable, "scripts/server.py",
             "--port", str(SERVER_PORT)],
            cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 40:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/version"
                        % SERVER_PORT, timeout=3) as r:
                    if r.status == 200:
                        break
            except OSError:
                time.sleep(1)
        else:
            ok(False, "server answers on %d" % SERVER_PORT)
            print("1 FAILURES")
            return 1
        ok(True, "server answers on %d" % SERVER_PORT)
        edge = subprocess.Popen(
            [EDGE, "--headless", "--no-sandbox", "--disable-gpu",
             "--use-angle=swiftshader", "--no-first-run",
             "--disable-extensions",
             "--remote-debugging-port=%d" % CDP_PORT,
             "--user-data-dir=" + profile,
             "--window-size=1920,1080", "about:blank"])
        t0 = time.time()
        targets = None
        while time.time() - t0 < 40:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/list" % CDP_PORT,
                        timeout=3) as r:
                    targets = json.load(r)
                if targets:
                    break
            except OSError:
                time.sleep(1)
        if not targets:
            ok(False, "edge cdp answers")
            print("1 FAILURES")
            return 1
        page = next((t for t in targets
                     if t.get("type") == "page"), None)
        if page is None:
            ok(False, "edge page target found")
            print("1 FAILURES")
            return 1
        wsu = page["webSocketDebuggerUrl"]
        hostport, _, path = wsu.split("://", 1)[1].partition("/")
        host, _, port = hostport.partition(":")
        ws = WS(host, int(port or 80), "/" + path)
        ws.call("Runtime.enable")
        ws.call("Page.enable")  # neuter + dialog events need this
        ws.call("Page.addScriptToEvaluateOnNewDocument",
                {"source": "window.confirm=()=>false;"})
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/" % SERVER_PORT})
        drain_dialogs(ws, 12)
        t0 = time.time()
        while time.time() - t0 < 40:
            if js_eval(ws, "document.readyState") == "complete":
                break
            time.sleep(0.5)
        js_eval(ws, "document.querySelector"
                    "('nav button[data-p=studio]').click()")
        ok(wait_for(ws, "document.getElementById('st-chip')"
                        ".textContent === 'Paused'"),
           "studio bar shows the paused run")
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'st-run'); s.value = 'studioctl1';"
                    " s.dispatchEvent(new Event('change')); })()")
        ok(wait_for(ws, "document.getElementById('st-now')"
                        ".textContent !== ''"),
           "now line fills in")
        st = json.loads(js_eval(ws, ST_JS) or "{}")
        ok("studioctl1" in (st.get("runs") or []),
           "run picker lists the fixture run")
        ok(st.get("chip") == "Paused" and st.get("cls") == "paused",
           "chip reads Paused (%s/%s)"
           % (st.get("chip"), st.get("cls")))
        ok(st.get("now") == "Now: Pia (Part 2)",
           "now names the clone (%s)" % st.get("now"))
        ok(st.get("cost") == "Cost: 3 calls \u00b7 25/12 tok",
           "cost sums stages + clones (%s)" % st.get("cost"))
        ok(st.get("resume") is True and st.get("step") is True
           and st.get("pause") is False and st.get("stop") is True,
           "buttons enable by state (resume/step/stop on)")
        ok(st.get("each") is True, "toggle reflects CONTROL")
        js_eval(ws, "document.getElementById('st-resume').click()")
        ok(wait_for(ws, "document.getElementById('st-err')"
                        ".textContent !== ''"),
           "resume with no live run shows the 409")
        ok("live" in (json.loads(js_eval(ws, ST_JS) or "{}")
                      .get("err") or ""),
           "error names the missing live run")
        js_eval(ws, "(() => { const c = document.getElementById("
                    "'st-each'); c.checked = false;"
                    " c.dispatchEvent(new Event('change')); })()")
        t0 = time.time()
        flipped = False
        while time.time() - t0 < 15:
            try:
                with open(os.path.join(FIX, "CONTROL.json"),
                          encoding="utf-8") as f:
                    ctl = json.load(f)
                if ctl.get("pause_each_stage") is False:
                    flipped = True
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        ok(flipped, "toggle persists through the API")
        time.sleep(6)
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG1920, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG1920)
           and os.path.getsize(PNG1920) > 1000,
           "screenshot saved (%s)" % PNG1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1.5)
        ok(js_eval(ws, "document.documentElement.scrollWidth > "
                        "document.documentElement.clientWidth + 1")
           is False, "390px: no page h-scroll")
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG390, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG390)
           and os.path.getsize(PNG390) > 1000,
           "screenshot saved (%s)" % PNG390)
        js_eval(ws, "document.querySelector"
                    "('nav button[data-p=board]').click()")
        ok(wait_for(ws, "document.getElementById('bd-resume')"
                        " !== null"),
           "board has the same buttons")
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'bd-run'); s.value = 'studioctl1';"
                    " s.dispatchEvent(new Event('change')); })()")
        ok(wait_for(ws, "document.getElementById('bd-chip')"
                        ".textContent === 'Paused'", timeout=20),
           "board chip shows the same state")
        js_eval(ws, "document.getElementById('bd-resume').click()")
        ok(wait_for(ws, "document.getElementById('bd-err')"
                        ".textContent !== ''"),
           "board resume shows the same 409")
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        shutil.rmtree(FIX, ignore_errors=True)
        if ws is not None:
            ws.close()
        stop_proc(edge, "edge")
        stop_proc(server, "server")
        shutil.rmtree(profile, ignore_errors=True)
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
