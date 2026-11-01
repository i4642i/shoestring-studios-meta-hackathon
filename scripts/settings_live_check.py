"""Settings layout check, J17 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP, opens the Settings tab, and asserts the two-column
layout, the Local/Jetson index matrix, the active-profile line and
the build-all gate (confirm neutered, so nothing is built). Saves
runs/settings_1920.png and runs/settings_390.png, then ALWAYS stops
the server + Edge (try/finally). Stdlib only. Read-only: no build
is ever started.
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
PNG1920 = os.path.join(RUNS, "settings_1920.png")
PNG390 = os.path.join(RUNS, "settings_390.png")
SERVER_LOG = os.path.join(RUNS, "settings_server.log")

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


LAYOUT_JS = """(() => {
  const L = document.getElementById('se-left');
  const R = document.getElementById('se-right');
  const lr = L.getBoundingClientRect();
  const rr = R.getBoundingClientRect();
  const wrap = document.getElementById('se-tablewrap');
  const wr = wrap.getBoundingClientRect();
  const card = document.querySelector('#p-settings > .card');
  const cr = card.getBoundingClientRect();
  const de = document.documentElement;
  const head = document.querySelector('header');
  const foot = document.querySelector('footer');
  return {
    sideBySide: Math.abs(lr.top - rr.top) < 4 &&
      rr.left >= lr.right - 2,
    stacked: rr.top >= lr.bottom - 2,
    cardW: cr.width, vw: window.innerWidth,
    cardL: cr.left, cardR: cr.right, cardB: cr.bottom,
    cardH: cr.height, leftH: lr.height, rightH: rr.height,
    wrapH: wr.height, headB: head ?
      head.getBoundingClientRect().bottom : 0,
    footH: foot ? foot.getBoundingClientRect().height : 0,
    docH: de.scrollHeight, winH: de.clientHeight,
    cliW: de.clientWidth,
    th: Array.from(document.querySelectorAll(
      '#se-table thead th')).map(t => t.textContent),
    on: Array.from(document.querySelectorAll(
      '#se-table thead th.se-on')).map(t => t.textContent),
    onCells: document.querySelectorAll(
      '#se-table td.se-on').length,
    rows: document.querySelectorAll('#se-rows tr').length,
    cells: document.querySelectorAll(
      '#se-rows tr:first-child td').length,
    buildAll: !!document.getElementById('se-buildall'),
    active: document.getElementById('se-active').textContent,
    pageScroll: de.scrollHeight > de.clientHeight + 2,
    hscroll: de.scrollWidth > de.clientWidth + 2
  };
})()"""

CLICK_BUILDALL_JS = """(() => {
  const b = document.getElementById('se-buildall');
  if (b) b.click();
  return !!b;
})()"""

AFTER_ERR_JS = \
    "document.getElementById('se-err').textContent"
AFTER_BAMSG_JS = \
    "document.getElementById('se-bamsg').textContent"
AFTER_BUILDING_JS = """Array.from(document.querySelectorAll(
  '#se-rows .se-st')).filter(
  e => e.textContent === 'building').length"""


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


def shot(ws, path):
    data = ws.call("Page.captureScreenshot",
                   {"format": "png"})["data"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    ok(os.path.isfile(path) and os.path.getsize(path) > 1000,
       "screenshot saved (%s)" % path)


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
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(),
                           "settings_profile")
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
            _browser.launch_args(CDP_PORT, profile, 1920, 1000))
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
        ok(*_browser.renderer_verdict(
            js_eval(ws, _browser.RENDERER_JS)))
        js_eval(ws, "document.querySelector"
                    "('nav button[data-p=settings]').click()")
        t0 = time.time()
        while time.time() - t0 < 20:
            n = js_eval(ws, "document.querySelectorAll"
                            "('#se-rows tr').length")
            if n:
                break
            time.sleep(0.5)
        time.sleep(1)
        lay = js_eval(ws, LAYOUT_JS)
        print("measure 1920:", {k: lay.get(k) for k in
              ("cardH", "leftH", "rightH", "wrapH", "headB",
               "footH", "docH", "winH", "cardB")}, flush=True)
        ok(lay.get("sideBySide") is True,
           "two columns side by side at 1920")
        ok(abs(lay.get("cardW", 0) - 1600) < 2,
           "card width 1600 at 1920 (%s)"
           % lay.get("cardW"))
        ok(lay.get("th") == ["AGENT", "LOCAL", "JETSON"],
           "matrix headers (%s)" % lay.get("th"))
        ok(len(lay.get("on", [])) == 1,
           "active column highlighted (%s)" % lay.get("on"))
        ok(lay.get("onCells") == lay.get("rows"),
           "active cells match rows (%s/%s)"
           % (lay.get("onCells"), lay.get("rows")))
        ok(lay.get("rows", 0) >= 10 and lay.get("cells") == 3,
           "one row per agent, 3 cells (%s rows)"
           % lay.get("rows"))
        ok(lay.get("buildAll") is True,
           "build-all button present")
        ok((lay.get("active") or "").startswith("Active:"),
           "active profile line (%s)" % lay.get("active"))
        ok(lay.get("pageScroll") is False,
           "no page scroll at 1920x1000")
        ok(lay.get("hscroll") is False,
           "no horizontal scroll at 1920")
        ok(js_eval(ws, CLICK_BUILDALL_JS) is True,
           "build-all clicked (confirm neutered)")
        time.sleep(1)
        drain_dialogs(ws, 2)
        after_err = js_eval(ws, AFTER_ERR_JS)
        after_bamsg = js_eval(ws, AFTER_BAMSG_JS)
        after_building = js_eval(ws, AFTER_BUILDING_JS)
        after = {"err": after_err, "bamsg": after_bamsg,
                 "building": after_building}
        ok(after_building == 0 and after_err == ""
           and after_bamsg in ("", "Everything is built."),
           "build-all gate: nothing started (%s)" % after)
        shot(ws, PNG1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        lay2 = js_eval(ws, LAYOUT_JS)
        ok(lay2.get("stacked") is True,
           "single column at 390")
        ok(abs(lay2.get("cardL", 0) - 16) < 3
           and abs(lay2.get("cliW", 0)
                   - lay2.get("cardR", 0) - 16) < 3,
           "card gutters 16px at 390 (L %s R %s layout %s)"
           % (lay2.get("cardL"), lay2.get("cardR"),
              lay2.get("cliW")))
        ok(lay2.get("hscroll") is False,
           "no horizontal scroll at 390")
        shot(ws, PNG390)
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
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
