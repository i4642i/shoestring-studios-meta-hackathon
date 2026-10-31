"""Studio tab responsive check: real Edge over the real server.

Opens index.html at 1280x720, 1920x1080 and 390x844, clicks the
Studio tab, waits for the office to boot, and records: office
canvas size vs viewport, bubble overlap, horizontal scroll, the
chat collapse round-trip, crew/desks/doorways from the boot
status, and console errors. Screenshots go to runs/.

Usage: .venv\\Scripts\\python scripts/studio_check.py
Needs: Edge (no install), free ports 8765 (server) and 9333 (CDP).
"""
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
SRV_PORT, CDP_PORT = 8765, 9333
SIZES = [(1280, 720), (1920, 1080), (390, 844)]

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


class CDP:
    """Minimal synchronous CDP client (stdlib only)."""

    def __init__(self, host, port, path):
        self.sock = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
             "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
             "Sec-WebSocket-Version: 13\r\n\r\n"
             % (path, host, port, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("cdp handshake failed")
            head += chunk
        if b"101 " not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError("cdp handshake: %r" % head[:80])
        self.mid = 0
        self.buf = b""
        self.events = []

    def _frame(self, text):
        raw = text.encode()
        head = bytes([0x81])
        n = len(raw)
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(
            b ^ mask[i % 4] for i, b in enumerate(raw)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("cdp closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv_msg(self, timeout=60):
        self.sock.settimeout(timeout)
        text = ""
        while True:
            b1, b2 = self._read(2)
            op, ln = b1 & 15, b2 & 127
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            if b2 & 128:
                mask = self._read(4)
                pay = bytes(c ^ mask[i % 4]
                            for i, c in enumerate(self._read(ln)))
            else:
                pay = self._read(ln)
            if op == 9:  # ping
                self.sock.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            if op == 8:
                raise RuntimeError("cdp closed by peer")
            text += pay.decode("utf-8", "replace")
            if b1 & 128:
                return json.loads(text)

    def call(self, method, params=None, session=None, timeout=60):
        self.mid += 1
        msg = {"id": self.mid, "method": method,
               "params": params or {}}
        if session:
            msg["sessionId"] = session
        self._frame(json.dumps(msg))
        while True:
            m = self.recv_msg(timeout)
            if m.get("id") == self.mid:
                if "error" in m:
                    raise RuntimeError("cdp %s: %s"
                                       % (method, m["error"]))
                return m.get("result", {})
            if "id" not in m:
                self.events.append(m)

    def drain(self, seconds=2):
        """Collect trailing protocol events (console/exceptions)."""
        end = time.time() + seconds
        while time.time() < end:
            try:
                m = self.recv_msg(
                    timeout=max(0.05, end - time.time()))
            except (TimeoutError, RuntimeError):
                break
            if "id" not in m:
                self.events.append(m)

    def close(self):
        try:
            self.sock.close()
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


def http_get(path, port=SRV_PORT):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path),
                                timeout=10) as r:
        return r.read()


def js_eval(cdp, sid, expr):
    r = cdp.call("Runtime.evaluate",
                 {"expression": expr, "returnByValue": True,
                  "awaitPromise": False}, session=sid)
    return (r.get("result", {}) or {}).get("value")


MEASURE_PARENT = """(() => {
  const f = document.querySelector("#p-studio iframe.office");
  const r = f ? f.getBoundingClientRect() : null;
  const de = document.documentElement;
  const chat = document.querySelector("#p-studio .chatbox");
  const cr = chat ? chat.getBoundingClientRect() : null;
  return { viewport: [innerWidth, innerHeight],
    iframe: r ? [r.x, r.y, r.width, r.height] : null,
    chat: cr ? [cr.width, cr.height] : null,
    chatHidden: !!document.querySelector(
      "#p-studio .studiowrap.chat-hidden"),
    scrollW: de.scrollWidth, clientW: de.clientWidth };
})()"""

MEASURE_OFFICE = """(() => {
  const f = document.querySelector("#p-studio iframe.office");
  if (!f || !f.contentDocument) return null;
  const d = f.contentDocument, w2 = f.contentWindow;
  const c = d.querySelector("#app canvas");
  const bs = [...d.querySelectorAll(".bubble")]
    .filter(b => b.style.display !== "none")
    .map(b => { const r = b.getBoundingClientRect();
      return [r.x, r.y, r.width, r.height,
        parseFloat(b.style.opacity || "1")]; });
  const clash = [];
  for (let i = 0; i < bs.length; i++)
    for (let j = i + 1; j < bs.length; j++) {
      const a = bs[i], b = bs[j];
      if (a[0] < b[0] + b[2] && b[0] < a[0] + a[2] &&
          a[1] < b[1] + b[3] && b[1] < a[1] + a[3])
        clash.push(i + "/" + j);
    }
  const pill = d.getElementById("pill");
  const err = d.getElementById("error");
  return { inner: [w2.innerWidth, w2.innerHeight],
    backing: c ? [c.width, c.height] : null,
    dpr: w2.devicePixelRatio || 1,
    bubbles: bs.length, clash,
    faded: bs.filter(b => b[4] < 1).length,
    allBubbles: d.querySelectorAll(".bubble").length,
    pill: pill ? pill.textContent : null,
    status: w2.__officeStatus || null,
    errHidden: !err || err.style.display !== "block",
    loadingGone: d.getElementById("loading").style.display
      === "none" };
})()"""


def wait_for(cdp, sid, expr, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if js_eval(cdp, sid, expr):
                return True
        except RuntimeError:
            pass
        time.sleep(1)
    return False


def main():
    edge = next((p for p in EDGE_PATHS if os.path.isfile(p)), None)
    ok(edge is not None, "edge binary found")
    if edge is None:
        print("1 FAILURES")
        return 1
    server = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "scripts", "server.py"),
         "--port", str(SRV_PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.time() + 30
        while time.time() < end:
            try:
                http_get("/api/version")
                break
            except OSError:
                time.sleep(0.5)
        else:
            ok(False, "server up on %d" % SRV_PORT)
            print("1 FAILURES")
            return 1
        ok(True, "server up on %d" % SRV_PORT)
        tmpd = tempfile.mkdtemp(prefix="studiocheck_")
        proc = subprocess.Popen(
            [edge, "--headless", "--no-sandbox", "--disable-gpu",
             "--use-angle=swiftshader", "--no-first-run",
             "--disable-extensions",
             "--user-data-dir=" + os.path.join(tmpd, "profile"),
             "--remote-debugging-port=%d" % CDP_PORT,
             "--remote-allow-origins=*", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            end = time.time() + 30
            ver = None
            while time.time() < end:
                try:
                    ver = json.loads(http_get("/json/version",
                                              port=CDP_PORT))
                    break
                except OSError:
                    time.sleep(0.5)
            if ver is None:
                ok(False, "cdp endpoint up")
                print("1 FAILURES")
                return 1
            path = ver["webSocketDebuggerUrl"].split(
                "127.0.0.1:%d" % CDP_PORT, 1)[1]
            cdp = CDP("127.0.0.1", CDP_PORT, path)
            report = []
            for w, h in SIZES:
                name = "studio_%dx%d" % (w, h)
                tgt = cdp.call("Target.createTarget",
                               {"url": "about:blank"})
                sid = cdp.call("Target.attachToTarget",
                               {"targetId": tgt["targetId"],
                                "flatten": True})["sessionId"]
                cdp.call("Page.enable", session=sid)
                cdp.call("Runtime.enable", session=sid)
                cdp.call("Emulation.setDeviceMetricsOverride",
                         {"width": w, "height": h,
                          "deviceScaleFactor": 1,
                          "mobile": False}, session=sid)
                ev0 = len(cdp.events)
                cdp.call("Page.navigate",
                         {"url": "http://127.0.0.1:%d/index.html"
                          % SRV_PORT}, session=sid)
                ok(wait_for(cdp, sid,
                            "document.readyState === 'complete'", 30),
                   "%s page loads" % name)
                js_eval(cdp, sid,
                        "document.querySelector("
                        "'nav button[data-p=\"studio\"]'"
                        ").click()")
                ok(wait_for(cdp, sid,
                            "document.querySelector("
                            "'#p-studio.active') !== null", 10),
                   "%s studio tab shows" % name)
                # office boots inside the iframe; the ready flag
                # proves spawnCrew finished (loading hides on
                # errors too)
                good = wait_for(
                    cdp, sid,
                    "(() => { const f = document.querySelector("
                    "'#p-studio iframe.office'); try { return !!(f "
                    "&& f.contentWindow.__officeReady); } "
                    "catch (e) { return false; } })()", 180)
                ok(good, "%s office boots" % name)
                time.sleep(4)  # chatter + bubbles settle
                m = js_eval(cdp, sid, MEASURE_PARENT)
                # same-origin iframe: measure through contentDocument
                om = js_eval(cdp, sid, MEASURE_OFFICE)
                shot = cdp.call("Page.captureScreenshot",
                                {"format": "png"}, session=sid)
                with open(os.path.join(ROOT, "runs", name + ".png"),
                          "wb") as f:
                    f.write(base64.b64decode(shot["data"]))
                cdp.drain()
                errs = console_errors(cdp.events[ev0:])
                report.append((name, w, h, m, om, errs))
                cdp.call("Target.closeTarget",
                         {"targetId": tgt["targetId"]})
            # collapse round-trip on the desktop layout
            tgt = cdp.call("Target.createTarget",
                           {"url": "about:blank"})
            sid = cdp.call("Target.attachToTarget",
                           {"targetId": tgt["targetId"],
                            "flatten": True})["sessionId"]
            cdp.call("Page.enable", session=sid)
            cdp.call("Emulation.setDeviceMetricsOverride",
                     {"width": 1280, "height": 720,
                      "deviceScaleFactor": 1, "mobile": False},
                     session=sid)
            cdp.call("Page.navigate",
                     {"url": "http://127.0.0.1:%d/index.html" % SRV_PORT},
                     session=sid)
            wait_for(cdp, sid, "document.readyState === 'complete'",
                     30)
            js_eval(cdp, sid,
                    "document.querySelector("
                    "'nav button[data-p=\"studio\"]'"
                    ").click()")
            wait_for(cdp, sid,
                     "document.querySelector('#p-studio.active')"
                     " !== null", 10)
            time.sleep(1)
            wide0 = js_eval(cdp, sid,
                            "document.querySelector("
                            "'#p-studio iframe.office')"
                            ".getBoundingClientRect().width")
            js_eval(cdp, sid,
                    "document.getElementById('chatcollapse').click()")
            time.sleep(0.5)
            wide1 = js_eval(cdp, sid,
                            "document.querySelector("
                            "'#p-studio iframe.office')"
                            ".getBoundingClientRect().width")
            js_eval(cdp, sid,
                    "document.getElementById('chatopen').click()")
            time.sleep(0.5)
            wide2 = js_eval(cdp, sid,
                            "document.querySelector("
                            "'#p-studio iframe.office')"
                            ".getBoundingClientRect().width")
            ok(wide1 > wide0 + 200 and abs(wide2 - wide0) < 2,
               "chat collapse gives the office its width (%d/%d/%d)"
               % (wide0, wide1, wide2))
            # tab round-trip: the studio panel must hide elsewhere
            vis = ("['studio','crew','gallery'].map(p => "
                   "getComputedStyle(document.getElementById('p-' + p))"
                   ".display).join(',')")
            js_eval(cdp, sid, "document.querySelector("
                    "'nav button[data-p=\"crew\"]'"
                    ").click()")
            time.sleep(0.5)
            hid = js_eval(cdp, sid, vis)
            js_eval(cdp, sid, "document.querySelector("
                    "'nav button[data-p=\"studio\"]'"
                    ").click()")
            time.sleep(0.5)
            back = js_eval(cdp, sid, vis)
            ok(hid == "none,block,none",
               "crew tab hides the office (%s)" % hid)
            ok(back == "flex,none,none",
               "studio tab shows only the office (%s)" % back)
            cdp.call("Target.closeTarget",
                     {"targetId": tgt["targetId"]})
            cdp.close()
            for name, w, h, m, om, errs in report:
                print("--- %s (viewport %dx%d) ---" % (name, w, h))
                if not m or not m.get("iframe"):
                    ok(False, "%s measurements present" % name)
                    continue
                iw, ih = m["iframe"][2], m["iframe"][3]
                print("office %.0fx%.0f  chat %s  scroll %s/%s" % (
                    iw, ih,
                    ("%.0fx%.0f" % tuple(m["chat"]))
                    if m.get("chat") else "n/a",
                    m["scrollW"], m["clientW"]))
                if om:
                    print("canvas css %dx%d backing %s dpr %s "
                          "bubbles %d clash %s faded %d" % (
                              om["inner"][0], om["inner"][1],
                              om["backing"], om["dpr"],
                              om["bubbles"], om["clash"] or "none",
                              om["faded"]))
                    print("pill %r status %s console_errors %d"
                          % (om.get("pill"), om.get("status"),
                             errs))
                else:
                    print("office metrics missing")
                cw = m["clientW"]
                if w >= 900:
                    ok(iw > cw * 0.55,
                       "%s office fills the width (%.0f of %d)"
                       % (name, iw, cw))
                    ok(m["chat"] and abs(m["chat"][0] - 320) < 3,
                       "%s chat is 320px" % name)
                    ok(abs(iw + 320 + 12 + 32 - cw) < 4,
                       "%s office takes the remaining width" % name)
                else:
                    ok(abs(iw - (cw - 32)) < 4,
                       "%s office full width on phone (%.0f of %d)"
                       % (name, iw, cw))
                    ok(abs(ih - h * 0.6) < h * 0.12,
                       "%s office about 60vh (%.0f of %d)"
                       % (name, ih, h))
                ok(m["scrollW"] <= m["clientW"] + 1,
                   "%s no horizontal scroll" % name)
                if om:
                    ok(om["backing"] and om["backing"][0] >=
                       om["inner"][0]
                       and om["backing"][1] >= om["inner"][1],
                       "%s canvas covers its box" % name)
                    ok(om["clash"] == [],
                       "%s no bubble overlaps" % name)
                    st = om.get("status") or {}
                    ok(st.get("crew") == 12
                       and om.get("allBubbles") == 12,
                       "%s 12 crew spawned" % name)
                    ok(st.get("story") == 7
                       and st.get("video") == 5,
                       "%s 7 story + 5 video" % name)
                    ok(st.get("desksOk") is True,
                       "%s every crew member has a desk" % name)
                    ok(st.get("doorwaysClear") is True,
                       "%s no furniture blocks either doorway"
                       % name)
                    ok(errs == 0,
                       "%s 0 console errors" % name)
                    ok(om.get("errHidden"),
                       "%s no error overlay" % name)
        finally:
            proc.kill()
            proc.wait()
            import shutil
            shutil.rmtree(tmpd, ignore_errors=True)
    finally:
        server.kill()
        server.wait()
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
