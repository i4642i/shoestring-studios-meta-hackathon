"""Office live-states check, J10/J11 (one shot).

Writes a fixture run with a working agent, a done agent, a mixed
clone node, an approved agent and memory states, starts
scripts/server.py on port 8765 (never 8000), drives headless Edge
over CDP, and asserts inside the Studio office iframe: the working
agent sits at its own desk with the real action in its bubble, the
clone bubble lists parts, approved/memory/waiting states render,
clicking a bubble selects that employee in the chat picker and
highlights them, and clicking empty sky clears the highlight. Then
the run is flipped to paused and the next-up pause bubble is
asserted. Saves runs/studio_states_1920.png, then ALWAYS stops the
server + Edge and deletes the fixture run (try/finally). Stdlib
only. No model calls.
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
FIX = os.path.join(RUNS, "officectl1")
PNG = os.path.join(RUNS, "studio_states_1920.png")
SERVER_LOG = os.path.join(RUNS, "office_live_server.log")

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


OFFICE = ("document.querySelector('#p-studio iframe.office')"
          ".contentWindow")
LIVE_JS = ("JSON.stringify((%s.__officeLive || (() => null))())"
           % OFFICE)


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


def wait_for(ws, expr, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js_eval(ws, expr):
            return True
        time.sleep(1)
    return False


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def wevs(path, evs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ev in evs:
            f.write(json.dumps(ev) + "\n")


def write_fixture(status):
    shutil.rmtree(FIX, ignore_errors=True)
    os.makedirs(FIX)
    shutil.copy(os.path.join(ROOT, "data", "flows", "default.json"),
                os.path.join(FIX, "flow.json"))
    wjson(os.path.join(FIX, "STATUS.json"), status)
    for base in ("sales_sam", "pd_marty", "explain_cleo",
                 "case_rex", "plan_ash", "voice_wren",
                 "board_penn"):
        wjson(os.path.join(FIX, base, "result.json"),
              {"producer": base, "categories": {}})
    wjson(os.path.join(FIX, "part_split", "split.json"),
          {"parts": [{"no": 1}, {"no": 2}, {"no": 3}]})
    wevs(os.path.join(FIX, "photo_pia", "p1", "events.jsonl"),
         [{"ev": "tool", "step": 1, "tool": "pc_search_images",
           "ok": True, "detail": "solar"}])
    wjson(os.path.join(FIX, "photo_pia", "p2", "result.json"),
          {"producer": "photo_pia@p2", "categories": {}})
    wjson(os.path.join(FIX, "image_gene", "p1", "result.json"),
          {"producer": "image_gene@p1", "categories": {}})
    wjson(os.path.join(FIX, "memory", "case_rex", "STATUS.json"),
          {"state": "ready"})
    wjson(os.path.join(FIX, "memory", "voice_wren", "STATUS.json"),
          {"state": "building"})


def click(ws, x, y):
    for typ in ("mousePressed", "mouseReleased"):
        ws.call("Input.dispatchMouseEvent",
                {"type": typ, "x": x, "y": y, "button": "left",
                 "clickCount": 1})


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
    write_fixture({"run_id": "officectl1", "flow_id": "default",
                   "order_id": "o1", "state": "running",
                   "current": "photo_pia@p1",
                   "completed": ["sales_sam", "pd_marty",
                                 "explain_cleo", "case_rex",
                                 "plan_ash", "voice_wren",
                                 "board_penn", "part_split"],
                   "approved": ["board_penn"], "error": ""})
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(),
                           "office_live_profile")
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
        ok(wait_for(ws, "%s.__officeReady === true" % OFFICE,
                    timeout=120), "office boots")
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'st-run'); s.value = 'officectl1';"
                    " s.dispatchEvent(new Event('change')); })()")
        ok(wait_for(ws, "JSON.parse(%s).run_id"
                        " === 'officectl1'" % LIVE_JS,
                    timeout=30), "office takes the run")
        ok(wait_for(ws, "JSON.parse(%s).members['photo_pia']"
                        ".bubble !== ''" % LIVE_JS, timeout=30),
           "clone bubble fills from real events")
        live = json.loads(js_eval(ws, LIVE_JS) or "{}")
        ms = live.get("members", {})
        pia = ms.get("photo_pia", {})
        ok(pia.get("bubble") == "P1 Searching photos: solar"
           " \u00b7 P2 Report done \u00b7 P3 waiting",
           "clone bubble lists parts (%s)" % pia.get("bubble"))
        ok(wait_for(ws, "JSON.parse(%s).members['photo_pia']"
                        ".seated === true" % LIVE_JS, timeout=60),
           "working clone walks to its desk and sits")
        ok(wait_for(ws, "JSON.parse(%s).members['pd_marty']"
                        ".seated === true" % LIVE_JS, timeout=60),
           "done agent sits at its desk")
        live = json.loads(js_eval(ws, LIVE_JS) or "{}")
        ms = live.get("members", {})
        ok(ms.get("pd_marty", {}).get("bubble")
           == "Report done \u2014 waiting for approval",
           "done bubble waits for approval")
        ok(ms.get("board_penn", {}).get("bubble") == "Done \u2713"
           and ms.get("board_penn", {}).get("still") is True,
           "approved agent is done and still")
        ok(ms.get("case_rex", {}).get("bubble")
           == "Done \u2713 \u00b7 Memory ready",
           "memory-ready bubble")
        ok(ms.get("voice_wren", {}).get("bubble")
           == "Learning this project (LightRAG)\u2026",
           "memory-building bubble")
        ok(ms.get("board_vera", {}).get("stage") == "waiting"
           and ms.get("board_vera", {}).get("seated") is False,
           "unstarted clone node roams")
        gene = ms.get("image_gene", {})
        ok(gene.get("bubble") == "P1 Report done \u00b7 P2 waiting"
           " \u00b7 P3 waiting" and gene.get("seated") is True,
           "mixed parts bubble, seated (%s)" % gene.get("bubble"))
        pt = js_eval(ws, "(() => { const f = document.querySelector("
                          "'#p-studio iframe.office');"
                          " const fr = f.getBoundingClientRect();"
                          " const bs = Array.from(f.contentDocument"
                          ".querySelectorAll('.bubble'));"
                          " const b = bs.find(x => x.textContent"
                          ".includes('Searching photos'));"
                          " if (!b) return null;"
                          " const r = b.getBoundingClientRect();"
                          " return [fr.left + r.left + r.width / 2,"
                          " fr.top + r.top + r.height / 2]; })()")
        ok(pt is not None, "pia bubble found on screen")
        if pt is not None:
            click(ws, pt[0], pt[1])
            ok(wait_for(ws, "document.getElementById('chatwho')"
                            ".value === 'photo_pia'"),
               "bubble click selects pia in the chat picker")
            ok(wait_for(ws, "JSON.parse(%s).members['photo_pia']"
                            ".selected === true" % LIVE_JS),
               "clicked employee highlighted")
            sky = js_eval(ws, "(() => { const f = document."
                              "querySelector('#p-studio "
                              "iframe.office');"
                              " const r = f.getBoundingClientRect();"
                              " return [r.left + r.width - 20,"
                              " r.top + 60]; })()")
            click(ws, sky[0], sky[1])
            ok(wait_for(ws, "!JSON.parse(%s).members"
                            "['photo_pia'].selected" % LIVE_JS),
               "sky click clears the highlight")
        time.sleep(2)
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG) and os.path.getsize(PNG) > 1000,
           "screenshot saved (%s)" % PNG)
        write_fixture({"run_id": "officectl1", "flow_id": "default",
                       "order_id": "o1", "state": "paused",
                       "current": "",
                       "completed": ["sales_sam", "pd_marty"],
                       "approved": [], "error": ""})
        ok(wait_for(ws, "JSON.parse(%s).members['pd_marty']"
                        ".bubble === '\\u23f8 Paused'" % LIVE_JS,
                    timeout=30),
           "pause flip reaches the office (last finished waits)")
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
