"""Order start-progress check (one shot, no model calls).

Starts scripts/server.py (never 8000), drives headless Edge over CDP,
opens the Order tab on a fresh order, then stages a fake in-flight
start on disk (meta starting flag + timeline rows, like live
ord-20261101-253) and reloads: the room must dim with the
"Order received - preparing production" card and live lines.
Then the flag is cleared on disk (start died, failure kept): the card
must show "Couldn't start", then undim, re-enable chat and post Sam's
retry line. Finally the start_result reload path is asserted through
the progress endpoint. Always stops the server + Edge (try/finally).
Stdlib only.
"""
import _browser
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = int(os.environ.get("CHECK_PORT", 8765))
CDP_PORT = int(os.environ.get("CHECK_CDP_PORT", 9444))
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
RUNS = os.path.join(ROOT, "runs")
SERVER_LOG = os.path.join(RUNS, "order_progress_server.log")

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
                {"expression": expr, "returnByValue": True,
                 "awaitPromise": True}, timeout=timeout)
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


def wait_for(ws, expr, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js_eval(ws, expr):
            return True
        time.sleep(1)
    return False


CARD_JS = """(() => {
  const card = document.getElementById('o-startcard');
  if (!card) return null;
  return {
    h: (card.querySelector('h3') || {}).textContent || '',
    lines: Array.from(
      card.querySelectorAll('#o-startlines div')).map(d => d.textContent),
    elapsed: (document.getElementById('o-startelapsed') || {})
      .textContent || '',
    dim: !!document.querySelector('#o-scene .olockdim'),
    inputOff: document.getElementById('o-input').disabled
  };
})()"""

SAMBUB_JS = """(() => {
  const el = document.getElementById('o-sambub');
  return el ? el.textContent : '';
})()"""


def api(method, path, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(
        "http://127.0.0.1:%d/%s" % (SERVER_PORT, path),
        data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {}


def open_edge(seed_oid=None):
    profile = os.path.join(tempfile.gettempdir(),
                           "order_progress_profile")
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
        if seed_oid:
            ws.call("Page.addScriptToEvaluateOnNewDocument",
                    {"source": "try { sessionStorage.setItem("
                               "'shoestring_order', '%s'); }"
                               "catch (e) {}" % seed_oid})
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/#order" % SERVER_PORT})
        drain_dialogs(ws, 12)
    except Exception:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        raise
    return edge, ws, profile


def oid_of(ws):
    m = re.search(r"ord-[0-9]{8}-[0-9]{3}",
                  js_eval(ws, "document.getElementById('o-status')"
                              ".textContent") or "")
    return m.group(0) if m else None


def write_meta(oid, **kw):
    mp = os.path.join(ROOT, "orders", oid, "meta.json")
    with open(mp, encoding="utf-8") as f:
        meta = json.load(f)
    meta.update(kw)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


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
        st, created = api("POST", "api/orders",
                          {"assignee": "sales_sam", "force": True})
        oid = (created or {}).get("id", "")
        ok(st == 201 and bool(oid), "fixture order created (%s)" % oid)
        if not oid:
            print("1 FAILURES")
            return 1
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(
            time.time() + 9 * 3600))
        write_meta(oid, answers={"audience": "beginners",
                                 "length": "10 minutes",
                                 "depth": "comprehensive",
                                 "theme": "story-led"},
                   files={"source": "source.pdf"},
                   starting={"at": now}, status="consulting")
        odir = os.path.join(ROOT, "orders", oid)
        with open(os.path.join(odir, "chat.jsonl"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps({"user": "beginners",
                                "reply": "noted"}) + "\n")
            f.write(json.dumps({"user": "yes, start",
                                "reply": "Order received"}) + "\n")
        rows = [
            {"at": now.replace("T", " "), "source": "order",
             "ev": "confirmed", "summary": "client said yes",
             "run_id": "", "node": "", "part": None, "file": ""},
            {"at": now.replace("T", " "), "source": "sam",
             "ev": "start", "summary": "Sam runs the report",
             "run_id": "", "node": "sales_sam", "part": None,
             "file": ""},
            {"at": now.replace("T", " "), "source": "pc_worker",
             "ev": "start", "summary": "source abc (all)",
             "run_id": "", "node": "", "part": None, "file": ""},
            {"at": now.replace("T", " "), "source": "pc_worker",
             "ev": "failed", "summary": "name 'secs' is not defined",
             "run_id": "", "node": "", "part": None, "file": ""},
        ]
        with open(os.path.join(odir, "timeline.jsonl"), "w",
                  encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        edge, ws, profile = open_edge(seed_oid=oid)
        ok(wait_for(ws, "!!document.querySelector('#o-scene canvas')"),
           "reception canvas mounted")
        ok(*_browser.renderer_verdict(
            js_eval(ws, _browser.RENDERER_JS)))
        ok(wait_for(ws, "!!document.getElementById('o-startcard')"),
           "progress card appears on reload while starting")
        time.sleep(3)
        card = js_eval(ws, CARD_JS) or {}
        print("measure card: %s"
              % repr(card).encode("ascii", "backslashreplace")
              .decode(), flush=True)
        ok(card and card.get("h") ==
           "Order received \u2014 preparing production.",
           "card title (%s)" % ((card or {}).get("h")))
        ok(card and any("Sam is writing" in l
                        for l in card.get("lines", [])),
           "sam line shown")
        ok(card and any("secs" in l for l in card.get("lines", [])),
           "failed worker line shown")
        ok(card and re.match(r"^\d+ s elapsed$",
                             card.get("elapsed", "")),
           "elapsed ticks (%s)" % card.get("elapsed"))
        ok(card and card.get("dim") is True
           and card.get("inputOff") is True,
           "room dimmed, chat disabled")
        prog = js_eval(ws, "fetch('api/orders/%s/progress')"
                           ".then(r=>r.json())" % oid)
        ok(prog and prog.get("starting") is True
           and prog.get("failed") is True
           and prog.get("reason") == "name 'secs' is not defined",
           "progress endpoint reports starting + failure")
        write_meta(oid, status="consulting")
        mp = os.path.join(odir, "meta.json")
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        meta.pop("starting", None)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        ok(wait_for(ws, "!!document.querySelector("
                        "'#o-startcard h3') && "
                        "document.querySelector('#o-startcard h3')"
                        ".textContent.indexOf(\"Couldn't start\") === 0",
                    timeout=15),
           "card shows the failure")
        ok(wait_for(ws, "!document.getElementById('o-startcard') && "
                        "!document.getElementById('o-input').disabled",
                    timeout=15),
           "room brightens, chat back after a few seconds")
        ok(wait_for(ws, "document.getElementById('o-sambub')"
                        ".textContent.indexOf(\"Say 'start' to try "
                        "again.\") >= 0", timeout=15),
           "sam posts the retry line")
        write_meta(oid, status="in_production")
        with open(os.path.join(odir, "start_result.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"ok": True, "files": ["intake.json"],
                       "intake": {"order_id": oid},
                       "report_md": "# hi", "stages": [],
                       "run_id": ""}, f)
        prog2 = js_eval(ws, "fetch('api/orders/%s/progress')"
                            ".then(r=>r.json())" % oid)
        ok(prog2 and prog2.get("starting") is False
           and (prog2.get("start_result") or {}).get("report_md")
           == "# hi",
           "finished order serves its start result")
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
