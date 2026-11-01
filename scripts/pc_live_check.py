"""PC tab layout + rights check, J18 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP, opens the PC tab, and asserts the six-card grid, the
order picker and the access-rights matrix (read-only: nothing is
built or changed). Saves runs/pc_1920.png and runs/pc_390.png, then
ALWAYS stops the server + Edge (try/finally). Stdlib only.
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
PNG1920 = os.path.join(RUNS, "pc_1920.png")
PNG390 = os.path.join(RUNS, "pc_390.png")
SERVER_LOG = os.path.join(RUNS, "pc_server.log")

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


GRID_JS = """(() => {
  const cards = Array.from(
    document.querySelectorAll('#pc-cards .pc-card'));
  const tops = {};
  cards.forEach(c => {
    const t = Math.round(c.getBoundingClientRect().top);
    tops[t] = (tops[t] || 0) + 1;
  });
  const grid = document.getElementById('pc-cards')
    .getBoundingClientRect();
  return {
    n: cards.length,
    rows: Object.values(tops).sort().join(','),
    chips: cards.filter(
      c => c.querySelector('.pc-chip')).length,
    uls: document.querySelectorAll('#pc-cards ul').length,
    opens: cards.map(
      c => (c.querySelector('.pc-open') || {})
        .getAttribute && c.querySelector('.pc-open')
        .getAttribute('href')),
    story: cards.filter(
      c => c.classList.contains('pc-story')).length,
    video: cards.filter(
      c => c.classList.contains('pc-video')).length,
    gridBottom: grid.bottom, winH: window.innerHeight,
    cardW: cards.length ? cards[0].getBoundingClientRect()
      .width : 0
  };
})()"""

MATRIX_JS = """(() => {
  const th = Array.from(document.querySelectorAll(
    '#pc-rights thead th')).map(t => t.textContent);
  const rows = document.querySelectorAll(
    '#pc-rrows tr').length;
  const body = document.getElementById('pc-rrows')
    .textContent.slice(0, 120);
  const links = Array.from(document.querySelectorAll(
    '#pc-rrows a')).slice(0, 3).map(a =>
    a.getAttribute('href'));
  return { th: th, rows: rows, body: body, links: links };
})()"""

PICKER_JS = """(() => {
  const sel = document.getElementById('pc-order');
  return {
    options: Array.from(sel.options).map(o => o.value),
    selected: sel.value
  };
})()"""

SETPICKER_JS = """((v) => {
  const sel = document.getElementById('pc-order');
  sel.value = v;
  sel.dispatchEvent(new Event('change'));
  return sel.value;
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
    profile = os.path.join(tempfile.gettempdir(), "pc_profile")
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
                    "('nav button[data-p=pc]').click()")
        t0 = time.time()
        while time.time() - t0 < 20:
            n = js_eval(ws, "document.querySelectorAll"
                            "('#pc-cards .pc-card').length")
            if n:
                break
            time.sleep(0.5)
        time.sleep(1)
        g = js_eval(ws, GRID_JS)
        ok(g.get("n") == 6, "six pc cards")
        ok(g.get("rows") == "3,3", "3 per row at 1920 (%s)"
           % g.get("rows"))
        ok(g.get("chips") == 6, "status chip per card")
        ok(g.get("uls") == 0, "no bullet lists in cards")
        ok(g.get("opens") == ["#/pc/%s" % p for p in
                              ("source", "theory", "article",
                               "image", "generated", "voice")],
           "open links in pc order (%s)" % g.get("opens"))
        ok(g.get("story") == 3 and g.get("video") == 3,
           "story blue row + video orange row")
        ok(g.get("gridBottom", 9999) <= g.get("winH", 0) + 2,
           "six cards fit at 1920x1000 (bottom %s/%s)"
           % (g.get("gridBottom"), g.get("winH")))
        pk = js_eval(ws, PICKER_JS)
        ok(len(pk.get("options", [])) >= 2
           and pk.get("options", ["x"])[0] == "",
           "order picker with blank + orders (%d)"
           % len(pk.get("options", [])))
        ok(pk.get("selected") == pk.get("options", ["", ""])[1],
           "latest order selected (%s)" % pk.get("selected"))
        t0 = time.time()
        while time.time() - t0 < 20:
            m = js_eval(ws, MATRIX_JS)
            if m.get("rows"):
                break
            time.sleep(0.5)
        m = js_eval(ws, MATRIX_JS)
        ok(m.get("th") == ["EMPLOYEE", "SOURCE", "THEORY",
                           "ARTICLE", "IMAGE", "GEN IMG",
                           "VOICE"],
           "matrix headers (%s)" % m.get("th"))
        ok(m.get("rows", 0) >= 10,
           "matrix rows per employee (%s)" % m.get("rows"))
        js_eval(ws, SETPICKER_JS + '("")')
        time.sleep(1)
        m2 = js_eval(ws, MATRIX_JS)
        ok("Pick an order" in (m2.get("body") or ""),
           "blank picker shows Pick an order")
        js_eval(ws, SETPICKER_JS + '("%s")'
                % pk.get("selected"))
        time.sleep(1)
        m3 = js_eval(ws, MATRIX_JS)
        ok(m3.get("rows", 0) >= 10,
           "reselect restores the matrix")
        deep = None
        for cand in pk.get("options", [])[1:]:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/pcs/rights"
                        "?order=%s" % (SERVER_PORT, cand),
                        timeout=10) as r:
                    pay = json.load(r)
            except OSError:
                continue
            for row in pay.get("rows", []):
                for pcname, cell in (
                        row.get("cells") or {}).items():
                    if cell and len(
                            cell.get("entries", [])) == 1:
                        deep = (pcname,
                                cell["entries"][0]["doc_id"])
                        break
                if deep:
                    break
            if deep:
                break
        if deep:
            js_eval(ws, "location.hash = '#/pc/%s/%s'" % deep)
            t0 = time.time()
            while time.time() - t0 < 20:
                vis = js_eval(ws, "document.getElementById"
                                  "('pc-detail').style.display")
                if vis == "block":
                    break
                time.sleep(0.5)
            ok(js_eval(ws, "document.getElementById"
                           "('pc-detail').style.display")
               == "block",
               "cell link opens the entry (#/pc/%s/%s)"
               % deep)
            js_eval(ws, "location.hash = '#/pc'")
            t0 = time.time()
            while time.time() - t0 < 20:
                n = js_eval(ws, "document.querySelectorAll"
                                "('#pc-cards .pc-card').length")
                if n == 6:
                    break
                time.sleep(0.5)
        else:
            ok(True, "no single-entry cell (deep-link skipped)")
        js_eval(ws, "window.scrollTo(0, 0)")
        time.sleep(0.5)
        shot(ws, PNG1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        g2 = js_eval(ws, GRID_JS)
        ok(g2.get("rows") == "1,1,1,1,1,1",
           "one per row at 390 (%s)" % g2.get("rows"))
        ok(js_eval(ws, "document.documentElement.scrollWidth"
                       " <= document.documentElement.clientWidth"
                       " + 2") is True,
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
