"""About tab layout + claims check, J21 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP, and asserts: the Motivation/Problem/Answer trio side
by side (stacked at 390), four grouped credit tables with the right
headers and row count, the corrected claim strings, compact lists,
the shared card width and no horizontal scroll. Saves
runs/about_1920.png and runs/about_390.png, then ALWAYS stops the
server + Edge (try/finally). Stdlib only.
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
PNG1920 = os.path.join(RUNS, "about_1920.png")
PNG390 = os.path.join(RUNS, "about_390.png")
SERVER_LOG = os.path.join(RUNS, "about_server.log")

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


ABOUT_JS = """(() => {
  const trio = Array.from(
    document.querySelectorAll('#p-about .about3c'));
  const tables = Array.from(
    document.querySelectorAll('#p-about table.credtab'));
  const heads = Array.from(document.querySelectorAll(
    '#p-about .card:nth-child(2) h3')).map(h => h.textContent);
  const firstHeads = tables.length ? Array.from(
    tables[0].querySelectorAll('th')).map(t => t.textContent)
    : [];
  let rows = 0;
  tables.forEach(t => {
    rows += t.querySelectorAll('tr').length - 1;
  });
  const txt = document.getElementById('p-about').textContent;
  const lr = Array.from(document.querySelectorAll(
    '#p-about table.credtab td:first-child'));
  const lrRow = lr.filter(
    td => td.textContent.indexOf('LightRAG') === 0);
  const remo = lr.filter(
    td => td.textContent === 'Remotion');
  const card = document.querySelector('#p-about > .card');
  const de = document.documentElement;
  return {
    trio: trio.length,
    tops: trio.map(
      c => Math.round(c.getBoundingClientRect().top)),
    tables: tables.length,
    heads: heads,
    firstHeads: firstHeads,
    rows: rows,
    revise: txt.indexOf('revise until pass') >= 0,
    gates: txt.indexOf('until the owner approves the stage')
      >= 0,
    lrCell: lrRow.length ? lrRow[0].parentElement
      .textContent.slice(0, 400) : '',
    remoCell: remo.length ? remo[0].parentElement
      .textContent.slice(0, 400) : '',
    credits: document.querySelectorAll(
      '#p-about ul.credits li').length,
    log: document.querySelectorAll(
      '#p-about ul.log li').length,
    cardW: card ? Math.round(
      card.getBoundingClientRect().width) : -1,
    vw: window.innerWidth,
    noH: de.scrollWidth <= de.clientWidth + 2
  };
})()"""


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
       "screenshot saved (%s)" % os.path.basename(path))


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
    profile = os.path.join(tempfile.gettempdir(), "about_profile")
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
        ws.call("Page.enable")
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
                    "('nav button[data-p=about]').click()")
        time.sleep(1)
        a = js_eval(ws, ABOUT_JS)
        ok(a.get("trio") == 3, "three top cards")
        tops = a.get("tops", [])
        ok(len(tops) == 3 and tops[0] == tops[1]
           and tops[1] == tops[2],
           "side by side at 1920 (%s)" % tops)
        ok(a.get("tables") == 4, "four group tables (%s)"
           % a.get("tables"))
        ok(a.get("heads") == ["BACKEND", "AI & RAG", "VIDEO",
                              "3D & ASSETS"],
           "group order (%s)" % a.get("heads"))
        ok(a.get("firstHeads") == ["Name", "Version", "License",
                                   "What we use it for", "Link"],
           "column headers (%s)" % a.get("firstHeads"))
        ok(a.get("rows") == 22, "22 package rows (%s)"
           % a.get("rows"))
        ok(a.get("revise") is False, "old QA claim gone")
        ok(a.get("gates") is True, "real gates stated")
        ok("no tool searches it yet" in (a.get("lrCell") or ""),
           "honest lightrag cell")
        ok("NOT open source" in (a.get("remoCell") or ""),
           "remotion stays non-open-source")
        ok(a.get("credits") == 2, "developer compact list")
        ok(a.get("log", 0) >= 8, "build log list (%s)"
           % a.get("log"))
        want = min(1600, a.get("vw", 0) - 32)
        ok(abs(a.get("cardW", -1) - want) <= 2,
           "wide card %s (want %s)" % (a.get("cardW"), want))
        ok(a.get("noH") is True, "no horizontal scroll")
        js_eval(ws, "window.scrollTo(0, 0)")
        time.sleep(0.5)
        shot(ws, PNG1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        js_eval(ws, "window.scrollTo(0, 0)")
        time.sleep(0.5)
        a2 = js_eval(ws, ABOUT_JS)
        tops2 = a2.get("tops", [])
        ok(len(tops2) == 3 and tops2[0] < tops2[1]
           and tops2[1] < tops2[2],
           "stacked at 390 (%s)" % tops2)
        ok(a2.get("noH") is True,
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
