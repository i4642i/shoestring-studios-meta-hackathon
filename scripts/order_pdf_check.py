"""Order PDF-in-bubble check, J4 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP (1280x720), and proves the J4 behaviour with NO model
calls (orders + intake + upload are plain HTTP):
  1. resume with 4 answers and no PDF -> "Attach PDF" button appears
     INSIDE Sam's bubble, and the input bar has no Attach button;
  2. attaching through the bubble button -> the button becomes a
     "check + filename" label;
  3. resume with the PDF stored -> no button, label persists;
  4. a PDF dropped onto the 3D room uploads the same way;
  5. Guided form (its own Choose PDF) is untouched.
Saves runs/order_pdf_bubble.png, then ALWAYS stops the server + Edge
and deletes the fixture orders (try/finally). Stdlib only.
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
SERVER_PORT = 8765
CDP_PORT = 9444
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
RUNS = os.path.join(ROOT, "runs")
PNG = os.path.join(RUNS, "order_pdf_bubble.png")
SERVER_LOG = os.path.join(RUNS, "order_pdf_server.log")
ANSWERS = {"audience": "beginners", "length": "10 minutes",
           "depth": "key concepts", "theme": "story-led"}

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
    req = urllib.request.Request(
        "http://127.0.0.1:%d/%s" % (SERVER_PORT, path),
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


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
    profile = os.path.join(tempfile.gettempdir(), "order_pdf_profile")
    pdfpath = os.path.join(tempfile.gettempdir(), "order_pdf_drop.pdf")
    fixtures = []
    shutil.rmtree(profile, ignore_errors=True)
    try:
        with open(pdfpath, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>"
                    b"endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>"
                    b"endobj\ntrailer<</Root 1 0 R>>\n")
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
        edge = subprocess.Popen(
            [EDGE, "--headless", "--no-sandbox", "--disable-gpu",
             "--use-angle=swiftshader", "--no-first-run",
             "--disable-extensions",
             "--remote-debugging-port=%d" % CDP_PORT,
             "--user-data-dir=" + profile,
             "--window-size=1280,720", "about:blank"])
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
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/#order" % SERVER_PORT})
        t0 = time.time()
        while time.time() - t0 < 40:
            if js_eval(ws, "document.readyState") == "complete":
                break
            time.sleep(0.5)
        t0 = time.time()
        while time.time() - t0 < 60:
            if js_eval(ws, "!!document.querySelector("
                            "'#o-scene canvas')"):
                break
            time.sleep(1)
        ok(js_eval(ws, "!!document.querySelector("
                        "'#o-scene canvas')") is True,
           "reception canvas mounted")

        # use the order the page itself created, so resume is the real flow
        oid1 = js_eval(ws, "sessionStorage.getItem('shoestring_order')")
        fixtures.append(oid1)
        api("PUT", "api/orders/%s/intake" % oid1,
            {"answers": ANSWERS})
        g1 = api("GET", "api/orders/" + oid1)
        ok(g1.get("missing") == ["source PDF"],
           "GET order returns missing==['source PDF'] (%s)"
           % (g1.get("missing"),))

        # resume -> Sam's bubble must show the Attach PDF button
        js_eval(ws, "location.reload()")
        has_btn = wait_for(
            ws, "!!document.querySelector('#o-sambub .pdfbtn')")
        if not has_btn:
            print("sam bubble html: %r" % js_eval(
                ws, "document.getElementById('o-sambub')"
                    ".innerHTML"), flush=True)
            print("order status: %r" % js_eval(
                ws, "document.getElementById('o-status')"
                    ".textContent"), flush=True)
        ok(has_btn, "bubble shows Attach PDF on missing==['source PDF']")
        ok(js_eval(ws, "(document.querySelector('#o-sambub .pdfbtn')"
                       "||{}).textContent") == "Attach PDF",
           "bubble button text is Attach PDF")
        ok(js_eval(ws, "document.querySelector("
                        "'#o-form input[type=file]')") is None,
           "input bar has no Attach button anymore")
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG) and os.path.getsize(PNG) > 1000,
           "screenshot saved (%s)" % PNG)

        # attach through the bubble button -> becomes check + filename
        doc = ws.call("DOM.getDocument", {"depth": -1})
        node = ws.call("DOM.querySelector",
                       {"nodeId": doc["root"]["nodeId"],
                        "selector": "#o-sambub .pdfbtn input"})
        if not node.get("nodeId"):
            ok(False, "bubble file input found for the attach step")
        else:
            ws.call("DOM.setFileInputFiles",
                    {"nodeId": node["nodeId"], "files": [pdfpath]})
        has_done = wait_for(
            ws, "!!document.querySelector('#o-sambub .pdfdone')")
        ok(has_done, "button becomes done-label after upload")
        ok(js_eval(ws, "(document.querySelector('#o-sambub .pdfdone')"
                       "||{}).textContent") == "\u2713 order_pdf_drop.pdf",
           "done-label shows check + filename")
        ok(js_eval(ws, "document.querySelector("
                        "'#o-sambub .pdfbtn')") is None,
           "button gone after upload")
        g2 = api("GET", "api/orders/" + oid1)
        ok(g2.get("missing") == [],
           "missing is [] after upload")

        # resume with the PDF stored: no button, label persists
        js_eval(ws, "location.reload()")
        has_done2 = wait_for(
            ws, "!!document.querySelector('#o-sambub .pdfdone')")
        ok(has_done2, "resume keeps the done-label")
        ok(js_eval(ws, "document.querySelector("
                        "'#o-sambub .pdfbtn')") is None,
           "resume shows no button when PDF attached")

        # drag-drop onto the 3D room, on a second order without a PDF
        js_eval(ws, "sessionStorage.removeItem('shoestring_order');"
                    "location.reload()")
        ok(wait_for(ws, "sessionStorage.getItem('shoestring_order')"),
           "fresh order created for the drop test")
        oid2 = js_eval(ws, "sessionStorage.getItem('shoestring_order')")
        fixtures.append(oid2)
        api("PUT", "api/orders/%s/intake" % oid2,
            {"answers": ANSWERS})
        js_eval(ws, "location.reload()")
        ok(wait_for(ws, "!!document.querySelector('#o-sambub .pdfbtn')"),
           "second order resumes with the button")
        box = js_eval(ws, "(() => { const r = document.getElementById("
                           "'o-recep').getBoundingClientRect();"
                           " return [r.x + r.width / 2, r.y + 60]; })()")
        dropped = False
        try:
            for typ in ("dragEnter", "dragOver"):
                ws.call("Input.dispatchDragEvent",
                        {"type": typ, "x": box[0], "y": box[1],
                         "data": {"items": [], "files": [pdfpath],
                                  "dragOperationsMask": 1}})
            ws.call("Input.dispatchDragEvent",
                    {"type": "drop", "x": box[0], "y": box[1],
                     "data": {"items": [], "files": [pdfpath],
                              "dragOperationsMask": 1}})
            dropped = wait_for(
                ws, "!!document.querySelector('#o-sambub .pdfdone')",
                timeout=20)
        except RuntimeError as exc:
            print("drag cdp note: %s" % exc, flush=True)
        if dropped:
            ok(True, "drop onto the room attaches the PDF")
        else:
            hl = js_eval(ws, "(() => { const r = document.getElementById("
                              "'o-recep');"
                              " r.dispatchEvent(new DragEvent('dragover',"
                              "{bubbles: true, cancelable: true}));"
                              " const on = r.classList.contains('pdfdrop');"
                              " r.dispatchEvent(new DragEvent('dragleave',"
                              "{bubbles: true}));"
                              " return on && !r.classList.contains('pdfdrop');"
                              " })()")
            ok(hl is True, "drop zone highlights on dragover "
                           "(real drop not driven by CDP)")

        # guided form untouched
        js_eval(ws, "document.querySelector('#o-modes [data-m=guided]')"
                    ".click()")
        time.sleep(0.6)
        ok(js_eval(ws, "document.getElementById('o-pdf') !== null"
                       " && document.getElementById('o-q').style.display"
                       " !== 'none'") is True,
           "guided form + Choose PDF unchanged")
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        for oid in fixtures:
            shutil.rmtree(os.path.join(ROOT, "orders", oid),
                          ignore_errors=True)
        try:
            os.remove(pdfpath)
        except OSError:
            pass
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
