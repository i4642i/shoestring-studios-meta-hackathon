"""Order chat bubble check (J32, one shot).

Starts scripts/server.py (never 8000), drives headless Edge over CDP,
opens the Order tab, and asserts the chat restyle without any model
call: the bubble DOM is filled directly (same nodes samSay/addMsg
create), then computed style + geometry are asserted and two captures
saved (runs/order_chat_1920.png, runs/order_chat_390.png). Always
stops the server + Edge (try/finally). Stdlib only.

Asserts: Sam bubble 24px on rgba(255,255,255,.8), fixed at the left
and vertically centred, max 40% of the room (full width at 390px),
tail on the Sam side; client bubbles 26px on rgba(0,100,224,.8);
input 28px and taller; the render tick no longer moves Sam's bubble.
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
PNG1920 = os.path.join(RUNS, "order_chat_1920.png")
PNG390 = os.path.join(RUNS, "order_chat_390.png")
SERVER_LOG = os.path.join(RUNS, "order_chat_server.log")

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


FILL_JS = """(() => {
  const sam = document.getElementById('o-sambub');
  sam.innerHTML = '';
  const who = document.createElement('b');
  who.textContent = 'Sam';
  const line = document.createElement('span');
  line.textContent = 'Perfect \\u2014 story-led at 10 minutes for a '
    + 'beginner viewer, noted. One quick check \\u2014 comprehensive '
    + 'coverage, or just the key concepts?';
  sam.append(who, line);
  sam.style.visibility = 'visible';
  const wrap = document.getElementById('o-mebub');
  wrap.innerHTML = '';
  const d = document.createElement('div');
  d.className = 'bub bub-me';
  d.textContent = 'I think it is about 10 min, story-led please.';
  wrap.appendChild(d);
  document.getElementById('o-input').value = 'real-life examples please';
  return true;
})()"""

GEOM_JS = """(() => {
  const box = document.getElementById('o-bubbles').getBoundingClientRect();
  const sam = document.getElementById('o-sambub');
  const r = sam.getBoundingClientRect();
  const cs = getComputedStyle(sam);
  const tail = getComputedStyle(sam, '::after');
  const me = document.querySelector('#o-mebub .bub-me');
  const mcs = me ? getComputedStyle(me) : {};
  const inp = document.getElementById('o-input');
  const ics = getComputedStyle(inp);
  return {
    boxW: box.width, boxH: box.height,
    samLeft: r.left - box.left, samW: r.width,
    samVC: Math.abs((r.top + r.height / 2) - (box.top + box.height / 2)),
    samFont: cs.fontSize, samBg: cs.backgroundColor,
    samName: getComputedStyle(sam.querySelector('b')).fontSize,
    samTop: r.top - box.top, samBottom: r.bottom - box.top,
    samPos: cs.position, samParent: sam.parentNode.id,
    meTop: (document.querySelector('#o-mebub .bub-me') ||
      {getBoundingClientRect: () => ({top: 1e9})})
      .getBoundingClientRect().top - box.top,
    samMaxW: cs.maxWidth,
    tailRight: tail.right,
    meFont: mcs.fontSize || '', meBg: mcs.backgroundColor || '',
    inFont: ics.fontSize, inH: inp.getBoundingClientRect().height
  };
})()"""


def open_edge():
    profile = os.path.join(tempfile.gettempdir(), "order_chat_profile")
    shutil.rmtree(profile, ignore_errors=True)
    edge = subprocess.Popen(
        _browser.launch_args(CDP_PORT, profile, 1920, 1080))
    ws = None
    try:
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
        page = next((t for t in targets or []
                     if t.get("type") == "page"), None)
        if page is None:
            raise RuntimeError("no page target")
        wsu = page["webSocketDebuggerUrl"]
        hostport, _, path = wsu.split("://", 1)[1].partition("/")
        host, _, port = hostport.partition(":")
        ws = WS(host, int(port or 80), "/" + path)
        ws.call("Runtime.enable")
        ws.call("Page.enable")
        ws.call("Page.addScriptToEvaluateOnNewDocument",
                {"source": "window.confirm=()=>false;"})
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/#order" % SERVER_PORT})
        drain_dialogs(ws, 12)
    except Exception:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        raise
    return edge, ws, profile


def wait_for(ws, expr, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js_eval(ws, expr):
            return True
        time.sleep(1)
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
    server, edge, ws = None, None, None
    profile = ""
    try:
        logf = open(SERVER_LOG, "w", encoding="utf-8")
        server = subprocess.Popen(
            [sys.executable, "scripts/server.py",
             "--port", str(SERVER_PORT)],
            cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 60:
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
        edge, ws, profile = open_edge()
        ok(wait_for(ws, "!!document.querySelector('#o-scene canvas')"),
           "reception canvas mounted")
        ok(*_browser.renderer_verdict(
            js_eval(ws, _browser.RENDERER_JS)))
        ok(js_eval(ws, FILL_JS), "bubble DOM filled (no model call)")
        time.sleep(3)  # let the render tick run: it must not move Sam
        g = js_eval(ws, GEOM_JS)
        print("measure 1920:", g, flush=True)
        ok(g.get("samFont") == "24px",
           "sam text 2x (%s)" % g.get("samFont"))
        ok(g.get("samName") == "20px",
           "sam name 2x (%s)" % g.get("samName"))
        ok((g.get("samBg") or "").replace(" ", "") ==
           "rgba(255,255,255,0.8)",
           "sam bubble 80pct (%s)" % g.get("samBg"))
        ok(abs(g.get("samLeft", -99) - 12) < 3,
           "sam bubble pinned left (%s)" % g.get("samLeft"))
        ok(g.get("samParent") == "o-bubbles",
           "sam lives in the room overlay (%s)"
           % g.get("samParent"))
        ok(g.get("samVC", 999) < 6,
           "sam bubble vertically centred (%s)" % g.get("samVC"))
        ok(g.get("samW", 9999) <= g.get("boxW", 0) * 0.4 + 2,
           "sam max 40pct of room (%s/%s)"
           % (g.get("samW"), g.get("boxW")))
        ok(g.get("tailRight") == "-9px",
           "tail on the sam side (%s)" % g.get("tailRight"))
        ok(g.get("meFont") == "26px",
           "client text 2x (%s)" % g.get("meFont"))
        ok((g.get("meBg") or "").replace(" ", "") ==
           "rgba(0,100,224,0.8)",
           "client bubble 80pct (%s)" % g.get("meBg"))
        ok(g.get("inFont") == "28px",
           "input text 2x (%s)" % g.get("inFont"))
        ok(g.get("inH", 0) > 44,
           "input box grew (%s)" % g.get("inH"))
        shot(ws, PNG1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(2)
        g2 = js_eval(ws, GEOM_JS)
        print("measure 390:", g2, flush=True)
        ok(g2.get("samParent") == "o-chatbelow"
           and g2.get("samPos") == "static",
           "sam moved below the room at 390 (%s/%s)"
           % (g2.get("samParent"), g2.get("samPos")))
        ok(g2.get("samW", 0) >= g2.get("boxW", 0) - 2,
           "sam spans the full width at 390 (%s/%s)"
           % (g2.get("samW"), g2.get("boxW")))
        ok(g2.get("samFont") == "24px",
           "sam still 2x at 390 (%s)" % g2.get("samFont"))
        ok(g2.get("samBottom", 9999) <= g2.get("meTop", -1),
           "no bubble overlap at 390 (%s/%s)"
           % (g2.get("samBottom"), g2.get("meTop")))
        shot(ws, PNG390)
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        stop_proc(server, "server")
        shutil.rmtree(profile or "", ignore_errors=True)
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
