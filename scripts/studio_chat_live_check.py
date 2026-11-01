"""Studio memory+chat check, J8/J9 (one shot).

Seeds a fixture run (marty memory ready, pia building, cleo failed,
wren none), starts scripts/server.py on port 8765 (never 8000) with
SHOESTRING_MEM_STUB=1, drives headless Edge over CDP, and asserts:
picker badges, failed-state retry through the real HTTP path, chat
gating (409 -> disabled input), a memory-backed reply, Close project
(deletes only the memory, marks closed), and zero console errors.
Saves runs/studio_chat_memory.png, then ALWAYS stops the server +
Edge and deletes the fixture run (try/finally). Stdlib only. No
model calls (the server stub answers, env-gated).
"""
import _browser
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
FIX = os.path.join(RUNS, "studiomem1")
PNG = os.path.join(RUNS, "studio_chat_memory.png")
SERVER_LOG = os.path.join(RUNS, "studio_chat_live_server.log")

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


def js_eval(ws, expr, timeout=30, tries=3):
    """Evaluate with retries: one hung answer must not kill the
    whole check on a busy PC."""
    err = None
    for _ in range(max(1, tries)):
        try:
            r = ws.call("Runtime.evaluate",
                        {"expression": expr, "returnByValue": True},
                        timeout=timeout)
            return (r.get("result") or {}).get("value")
        except Exception as exc:  # noqa: BLE001 - retried
            err = exc
            time.sleep(2)
    raise err


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


OPT_JS = """JSON.stringify(Array.from(
  document.getElementById('chatwho').options).map(o => o.text))"""

GATE_JS = """JSON.stringify({
  disabled: document.getElementById('chatinput').disabled,
  ph: document.getElementById('chatinput').placeholder,
  retry: document.getElementById('chatretry').style.display !== 'none'
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
    """Poll until true; a hung renderer answers late under software
    WebGL on a busy PC, so CDP timeouts mean 'not yet', not dead."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if js_eval(ws, expr):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def wfile(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


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
    wfile(os.path.join(FIX, "STATUS.json"),
          {"run_id": "studiomem1", "flow_id": "default",
           "order_id": "omem", "state": "paused",
           "current": "pd_marty", "completed": ["sales_sam"],
           "error": ""})
    wfile(os.path.join(FIX, "pd_marty", "INPUTS.md"),
          "# marty inputs\n")
    wfile(os.path.join(FIX, "pd_marty", "result.json"),
          {"categories": {}})
    wfile(os.path.join(FIX, "pd_marty", "report.md"),
          "# marty report\n")
    wfile(os.path.join(FIX, "memory", "pd_marty", "STATUS.json"),
          {"state": "ready", "docs": 3})
    wfile(os.path.join(FIX, "memory", "photo_pia", "STATUS.json"),
          {"state": "building"})
    wfile(os.path.join(FIX, "explain_cleo", "INPUTS.md"),
          "# cleo inputs\n")
    wfile(os.path.join(FIX, "explain_cleo", "result.json"),
          {"categories": {}})
    wfile(os.path.join(FIX, "explain_cleo", "report.md"),
          "# cleo report\n")
    wfile(os.path.join(FIX, "memory", "explain_cleo",
                       "STATUS.json"),
          {"state": "failed", "error": "stub boom"})
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(),
                           "studio_chat_live_profile")
    shutil.rmtree(profile, ignore_errors=True)
    try:
        logf = open(SERVER_LOG, "w", encoding="utf-8")
        env = dict(os.environ)
        env["SHOESTRING_MEM_STUB"] = "1"
        server = subprocess.Popen(
            [sys.executable, "scripts/server.py",
             "--port", str(SERVER_PORT)],
            cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT,
            env=env)
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
        ws = None
        attempt = 0
        for attempt in (1, 2, 3):
            if edge is not None:
                if ws is not None:
                    ws.close()
                    ws = None
                _browser.stop_tree(edge, "edge")
                edge = None
            shutil.rmtree(profile, ignore_errors=True)
            edge = subprocess.Popen(
                _browser.launch_args(CDP_PORT, profile, 1920, 1080))
            t0 = time.time()
            targets = None
            while time.time() - t0 < 40:
                try:
                    with urllib.request.urlopen(
                            "http://127.0.0.1:%d/json/list"
                            % CDP_PORT, timeout=3) as r:
                        targets = json.load(r)
                    if targets:
                        break
                except OSError:
                    time.sleep(1)
            page = next((t for t in (targets or [])
                             if t.get("type") == "page"), None)
            if page is None:
                continue
            try:
                wsu = page["webSocketDebuggerUrl"]
                hostport, _, path = wsu.split(
                    "://", 1)[1].partition("/")
                host, _, port = hostport.partition(":")
                ws = WS(host, int(port or 80), "/" + path)
                ws.call("Runtime.enable")
                ws.call("Page.enable")  # neuter + dialog events need this
                ws.call("Page.addScriptToEvaluateOnNewDocument",
                        {"source":
                         "window.confirm=()=>false;"})
                ws.call("Page.navigate",
                        {"url": "http://localhost:%d/"
                         % SERVER_PORT})
                drain_dialogs(ws, 12)
            except Exception:
                if ws is not None:
                    ws.close()
                    ws = None
                continue
            if wait_for(ws, "document.readyState === 'complete'",
                        timeout=90):
                break
            ws.close()
            ws = None
        else:
            ok(False, "page loads after 3 attempts")
            print("1 FAILURES")
            return 1
        ok(True, "page loads (attempt %d)" % attempt)
        ok(*_browser.renderer_verdict(
            js_eval(ws, _browser.RENDERER_JS)))
        js_eval(ws, "document.querySelector"
                    "('nav button[data-p=studio]').click()")
        ok(wait_for(ws, "Array.from(document.getElementById("
                        "'st-run').options).some(o => o.value === "
                        "'studiomem1')", timeout=30),
           "run picker lists the fixture run")
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'st-run'); s.value = 'studiomem1';"
                    " s.dispatchEvent(new Event('change')); })()")
        ok(wait_for(ws, "(" + OPT_JS + ").indexOf"
                        "('[memory ready]') >= 0", timeout=30),
           "badges paint after run select")
        opts = json.loads(js_eval(ws, OPT_JS) or "[]")
        by_id = {}
        ids = json.loads(js_eval(ws, "JSON.stringify(Array.from("
                                     "document.getElementById("
                                     "'chatwho').options).map(o => "
                                     "o.value))") or "[]")
        for i, v in enumerate(ids):
            by_id[v] = opts[i] if i < len(opts) else ""
        ok("[memory ready]" in by_id.get("pd_marty", ""),
           "marty badge ready (%s)"
           % by_id.get("pd_marty", ""))
        ok("[building" in by_id.get("photo_pia", ""),
           "pia badge building (%s)"
           % by_id.get("photo_pia", ""))
        ok("[failed]" in by_id.get("explain_cleo", ""),
           "cleo badge failed (%s)"
           % by_id.get("explain_cleo", ""))
        ok("[not yet]" in by_id.get("voice_wren", ""),
           "wren badge not yet (%s)"
           % by_id.get("voice_wren", ""))
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'chatwho'); s.value = 'explain_cleo';"
                    " s.dispatchEvent(new Event('change')); })()")
        time.sleep(1)
        gate = json.loads(js_eval(ws, GATE_JS) or "{}")
        ok(gate.get("disabled") is True
           and gate.get("retry") is True
           and "stub boom" in (gate.get("ph") or ""),
           "failed state disables input + retry (%s)"
           % gate.get("ph"))
        js_eval(ws, "document.getElementById('chatretry').click()")
        ok(wait_for(ws, "(JSON.parse(" + OPT_JS + ")).some(o => "
                        "o.indexOf('Cleo') >= 0 && o.indexOf("
                        "'[memory ready]') >= 0)", timeout=30),
           "retry rebuilds through the API")
        gate = json.loads(js_eval(ws, GATE_JS) or "{}")
        ok(gate.get("disabled") is False
           and gate.get("retry") is False,
           "input enabled after retry")
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'chatwho'); s.value = 'pd_marty';"
                    " s.dispatchEvent(new Event('change')); })()")
        time.sleep(1)
        gate = json.loads(js_eval(ws, GATE_JS) or "{}")
        ok(gate.get("disabled") is False,
           "ready memory leaves input enabled")
        js_eval(ws, "(() => { document.getElementById("
                    "'chatinput').value = 'what did you decide?';"
                    " document.getElementById('chatform')"
                    ".dispatchEvent(new Event('submit',"
                    " {cancelable: true})); })()")
        ok(wait_for(ws, "Array.from(document.querySelectorAll("
                        "'#chatmsgs .cmsg.them')).some(d => "
                        "d.textContent.indexOf('Stub reply from "
                        "memory') >= 0)", timeout=30),
           "memory-backed reply renders")
        ok(wait_for(ws, "Array.from(document.querySelectorAll("
                        "'#chatmsgs .cmsg.them')).some(d => "
                        "d.textContent.indexOf('project ctx: "
                        "True') >= 0)", timeout=10),
           "reply carried the project context")
        time.sleep(2)
        # Crew for the capture only; office_live_check asserts boot.
        wait_for(ws, "document.querySelector("
                     "'#p-studio iframe.office').contentWindow"
                     ".__officeReady === true", timeout=90)
        js_eval(ws, "(() => { const s = document.getElementById("
                    "'chatwho'); s.size = s.options.length; })()")
        time.sleep(0.5)
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG, "wb") as f:
            f.write(base64.b64decode(data))
        js_eval(ws, "document.getElementById('chatwho').size = 0")
        ok(os.path.isfile(PNG)
           and os.path.getsize(PNG) > 1000,
           "screenshot saved (%s)" % PNG)
        ok(js_eval(ws, "document.documentElement.scrollWidth > "
                        "document.documentElement.clientWidth + 1")
           is False, "1920px: no page h-scroll")
        js_eval(ws, "window.confirm = () => true")
        js_eval(ws, "document.getElementById('st-close').click()")
        ok(wait_for(ws, "(JSON.parse(" + OPT_JS + ")).every(o => "
                        "o.indexOf('[closed]') >= 0)", timeout=30),
           "close marks every badge closed")
        gate = json.loads(js_eval(ws, GATE_JS) or "{}")
        ok(gate.get("disabled") is True
           and gate.get("ph") == "This project is closed.",
           "closed project disables input")
        ok(not os.path.exists(os.path.join(FIX, "memory"))
           and os.path.isfile(os.path.join(
               FIX, "MEMORY_CLOSED.json"))
           and os.path.isfile(os.path.join(
               FIX, "pd_marty", "result.json")),
           "close deletes only the memory on disk")
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        shutil.rmtree(FIX, ignore_errors=True)
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        stop_proc(server, "server")
        shutil.rmtree(profile, ignore_errors=True)
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
