"""Order received-state check, J25 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP, and proves the locked "received" state with NO model
calls (a fixture order is flipped to in_production on disk):
  1. failed start (no approval) -> 409, status stays consulting,
     UI not locked;
  2. started order: chat POST refused (409 already started),
     confirm true/false refused, GET carries run_id;
  3. resume of the started order locks the Order tab: dim + centred
     card (title, order/run lines, Open Studio, Open Board,
     New order), Sam's fixed last bubble, chat/Send/modes/PDF/
     guided form disabled, Enter does nothing;
  4. Open Board/Studio switch tabs; New order unlocks with a fresh
     order (close-first rule applies).
Saves runs/order_received_1920.png and runs/order_received_390.png,
then ALWAYS stops the server + Edge and deletes the fixtures
(try/finally). Stdlib only.
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
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = int(os.environ.get("CHECK_PORT", 8765))
CDP_PORT = int(os.environ.get("CHECK_CDP_PORT", 9444))
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
RUNS = os.path.join(ROOT, "runs")
PNG1920 = os.path.join(RUNS, "order_received_1920.png")
PNG390 = os.path.join(RUNS, "order_received_390.png")
SERVER_LOG = os.path.join(RUNS, "order_received_server.log")
ANSWERS = {"audience": "beginners", "length": "10 minutes",
           "depth": "key concepts", "theme": "story-led"}
RUN_FIX = "recvfix1"

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


def open_edge(seed_oid=None, width=1920, height=1080):
    profile = os.path.join(tempfile.gettempdir(),
                           "order_received_profile")
    shutil.rmtree(profile, ignore_errors=True)
    edge = subprocess.Popen(
        _browser.launch_args(CDP_PORT, profile, width, height))
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
        page = next((t for t in (targets or [])
                     if t.get("type") == "page"), None)
        if page is None:
            _browser.stop_tree(edge, "edge")
            return None, None, profile
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


def close_edge(edge, ws, profile, all_events):
    if ws is not None:
        all_events.extend(ws.events)
        ws.close()
    _browser.stop_tree(edge, "edge")
    shutil.rmtree(profile or "", ignore_errors=True)


OID_RE = re.compile(r"ord-[0-9]{8}-[0-9]{3}")


def oid_of(ws):
    m = OID_RE.search(js_eval(
        ws, "document.getElementById('o-status').textContent") or "")
    return m.group(0) if m else None


def wait_oid(ws, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        oid = oid_of(ws)
        if oid:
            return oid
        time.sleep(0.5)
    return None


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


def api(method, path, body=None):
    """HTTP call returning (status, object); never raises on 4xx/5xx."""
    req = urllib.request.Request(
        "http://127.0.0.1:%d/%s" % (SERVER_PORT, path),
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {}


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


def wait_for(ws, expr, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js_eval(ws, expr):
            return True
        time.sleep(0.5)
    return False


LOCK_JS = """(() => {
  const card = document.querySelector('#o-scene .oreceived');
  const inp = document.getElementById('o-input');
  return {
    dim: !!document.querySelector('#o-scene .olockdim'),
    card: !!card,
    title: card ? (card.querySelector('h3') || {})
      .textContent || '' : '',
    lines: card ? Array.from(card.querySelectorAll('p'))
      .map(p => p.textContent) : [],
    studio: card ? !!Array.from(card.querySelectorAll(
      '.obtns button')).find(b =>
        b.textContent === 'Open Studio') : false,
    board: card ? !!Array.from(card.querySelectorAll(
      '.obtns button')).find(b =>
        b.textContent === 'Open Board') : false,
    neword: card ? (card.querySelector('.onew') || {})
      .textContent || '' : '',
    sam: (document.getElementById('o-sambub') || {})
      .textContent || '',
    disInput: !!(inp && inp.disabled),
    disSend: !!document.querySelector('#o-form button:disabled'),
    disModes: Array.from(document.querySelectorAll(
      '#o-modes [data-m]')).filter(b => b.disabled).length,
    disGuided: ['o-audience', 'o-length', 'o-depth',
      'o-theme', 'o-pdf'].filter(id =>
        document.getElementById(id).disabled).length,
    disStart: !!document.getElementById('start').disabled,
    pdfBtn: !!document.querySelector('#o-sambub .pdfbtn'),
    meCount: document.querySelectorAll('#o-mebub .bub-me').length,
    sceneLocked: document.getElementById('o-scene')
      .classList.contains('locked')
  };
})()"""


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
    server, edge, ws, profile = None, None, None, ""
    fixtures = []
    run_fixtures = []
    all_events = []
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
            print("server log tail:")
            print(open(SERVER_LOG, encoding="utf-8").read()[-800:])
            print("1 FAILURES")
            return 1
        ok(True, "server answers on %d" % SERVER_PORT)
        # Phase A: the page creates a real order; start fails
        # without approval and nothing locks.
        edge, ws, profile = open_edge()
        if ws is None:
            ok(False, "edge page target found")
            print("1 FAILURES")
            return 1
        ok(wait_for(ws, "!!document.querySelector("
                        "'#o-scene canvas')", timeout=60),
           "reception canvas mounted")
        ok(*_browser.renderer_verdict(
            js_eval(ws, _browser.RENDERER_JS)))
        oid1 = wait_oid(ws)
        ok(bool(oid1), "fresh order id in the status (%s)" % oid1)
        fixtures.append(oid1)
        st, _ = api("PUT", "api/orders/%s/intake" % oid1,
                    {"answers": ANSWERS})
        ok(st == 200, "intake answers saved (%s)" % st)
        st, obj = api("POST", "api/orders/%s/start" % oid1, {})
        ok(st == 409, "start without approval fails (%s)" % st)
        st, g = api("GET", "api/orders/" + oid1)
        ok(st == 200 and g.get("status") == "consulting",
           "failed start leaves consulting (%s)"
           % g.get("status"))
        ok(js_eval(ws, "document.querySelector("
                       "'#o-scene .oreceived')") is None
           and js_eval(ws, "document.getElementById('o-input')"
                           ".disabled") is False,
           "failed start does not lock the UI")
        close_edge(edge, ws, profile, all_events)
        edge, ws, profile = None, None, ""
        # Flip the fixture to in_production on disk (no model).
        mp = os.path.join(ROOT, "orders", oid1, "meta.json")
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        meta["status"] = "in_production"
        meta["approved"] = {"at": "2026-11-01T00:00:00",
                            "answers": dict(ANSWERS),
                            "via": "fixture"}
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        with open(os.path.join(ROOT, "orders", oid1,
                               "chat.jsonl"), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps({"user": "hi",
                                "reply": "Hello!"}) + "\n")
        rp = os.path.join(RUNS, RUN_FIX)
        os.makedirs(rp, exist_ok=True)
        with open(os.path.join(rp, "STATUS.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"run_id": RUN_FIX, "flow_id": "default",
                       "order_id": oid1, "state": "done"}, f)
        run_fixtures.append(RUN_FIX)
        st, g = api("GET", "api/orders/" + oid1)
        ok(st == 200 and g.get("run_id") == RUN_FIX,
           "GET carries the run id (%s)" % g.get("run_id"))
        st, obj = api(
            "POST", "api/orders/%s/chat" % oid1,
            {"messages": [{"role": "user", "content": "hey?"}]})
        ok(st == 409 and "already started" in
           (obj.get("error") or ""),
           "chat on a started order is refused (%s)" % st)
        st, _ = api("POST", "api/orders/%s/confirm" % oid1,
                    {"confirm": False})
        ok(st == 409, "decline after start is refused (%s)" % st)
        st, _ = api("POST", "api/orders/%s/confirm" % oid1,
                    {"confirm": True})
        ok(st == 409, "second confirm is refused (%s)" % st)
        # Phase B: resume locks the tab (1920x1080).
        edge, ws, profile = open_edge(seed_oid=oid1)
        ok(wait_for(ws, "!!document.querySelector("
                        "'#o-scene .oreceived')"),
           "resume of a started order locks the tab")
        out = js_eval(ws, LOCK_JS)
        ok(out.get("dim") is True and out.get("card") is True,
           "dim + centred card shown")
        ok(out.get("title") == "Order received \u2713",
           "card title (%r)" % out.get("title"))
        ok(any(oid1 in ln and RUN_FIX in ln
               for ln in out.get("lines", [])),
           "card names the order and run (%s)"
           % out.get("lines"))
        ok(any("Studio (live office)" in ln and "Board" in ln
               for ln in out.get("lines", [])),
           "card points at Studio and Board")
        ok(out.get("studio") is True
           and out.get("board") is True,
           "Open Studio + Open Board buttons")
        ok(out.get("neword") == "New order",
           "New order link (%r)" % out.get("neword"))
        ok("Thanks! Your order is in. The crew has started."
           in (out.get("sam") or ""),
           "Sam's last bubble is the fixed line")
        ok(out.get("disInput") is True
           and out.get("disSend") is True,
           "chat input + Send disabled")
        ok(out.get("disModes") == 2,
           "both mode buttons disabled (%s)"
           % out.get("disModes"))
        ok(out.get("disGuided") == 5
           and out.get("disStart") is True,
           "guided form + START disabled (%s)"
           % out.get("disGuided"))
        ok(out.get("pdfBtn") is False,
           "no PDF button while locked")
        ok(out.get("sceneLocked") is True,
           "scene carries the locked class")
        before = out.get("meCount")
        js_eval(ws, "(() => { const i = "
                    "document.getElementById('o-input');"
                    " i.value = 'should not send';"
                    " document.getElementById('o-form')"
                    ".requestSubmit(); })()")
        time.sleep(1.5)
        after = js_eval(ws, "document.querySelectorAll("
                            "'#o-mebub .bub-me').length")
        ok(after == before,
           "Enter/submit sends nothing while locked (%s/%s)"
           % (before, after))
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG1920, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG1920)
           and os.path.getsize(PNG1920) > 1000,
           "screenshot saved (%s)" % PNG1920)
        js_eval(ws, "Array.from(document.querySelectorAll("
                    "'#o-scene .oreceived .obtns button')).find("
                    "b => b.textContent === 'Open Board').click()")
        ok(wait_for(ws, "document.getElementById('p-board')"
                        ".classList.contains('active')"),
           "Open Board switches to the Board")
        js_eval(ws, "document.querySelector("
                    "'nav button[data-p=order]').click()")
        time.sleep(0.5)
        ok(js_eval(ws, "!!document.querySelector("
                       "'#o-scene .oreceived')") is True,
           "still locked after tab trip")
        js_eval(ws, "Array.from(document.querySelectorAll("
                    "'#o-scene .oreceived .obtns button')).find("
                    "b => b.textContent === 'Open Studio').click()")
        ok(wait_for(ws, "document.getElementById('p-studio')"
                        ".classList.contains('active')"),
           "Open Studio switches to Studio")
        js_eval(ws, "document.querySelector("
                    "'nav button[data-p=order]').click()")
        time.sleep(0.5)
        js_eval(ws, "document.querySelector("
                    "'#o-scene .oreceived .onew').click()")
        ok(wait_for(ws, "!document.querySelector("
                        "'#o-scene .oreceived')"),
           "New order unlocks the tab")
        oid2 = wait_oid(ws)
        ok(bool(oid2) and oid2 != oid1,
           "New order starts a fresh order (%s)" % oid2)
        fixtures.append(oid2)
        ok(js_eval(ws, "document.getElementById('o-input')"
                       ".disabled") is False,
           "chat usable again after New order")
        close_edge(edge, ws, profile, all_events)
        edge, ws, profile = None, None, ""
        # Phase C: locked card at 390x844.
        edge, ws, profile = open_edge(seed_oid=oid1, width=390,
                                      height=844)
        ok(wait_for(ws, "!!document.querySelector("
                        "'#o-scene .oreceived')"),
           "390px: locked card shows")
        fit = js_eval(ws, "(() => { const c = document.querySelector("
                          "'#o-scene .oreceived'); const r = "
                          "c.getBoundingClientRect(); return [Math.round("
                          "r.width), innerWidth]; })()")
        ok(fit[0] <= fit[1],
           "390px: card fits the width (%s)" % fit)
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG390, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG390)
           and os.path.getsize(PNG390) > 1000,
           "screenshot saved (%s)" % PNG390)
        close_edge(edge, ws, profile, all_events)
        edge, ws, profile = None, None, ""
        nerr = console_errors(all_events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        for oid in fixtures:
            if oid:
                shutil.rmtree(os.path.join(ROOT, "orders", oid),
                              ignore_errors=True)
        for rid in run_fixtures:
            shutil.rmtree(os.path.join(RUNS, rid),
                          ignore_errors=True)
        if ws is not None:
            all_events.extend(ws.events)
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
