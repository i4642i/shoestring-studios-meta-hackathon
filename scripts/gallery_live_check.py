"""Gallery + all-tabs width check, J19/J20 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP, and asserts: the gallery empty state, one fixture
order card (title, meta, chip, thumbnail, Play inline, table/board/
log links), video byte ranges, and the shared card width
min(100%-32px, 1600px) on the six card tabs with no horizontal
scroll on all nine tabs. Saves runs/gallery_1920.png,
runs/gallery_390.png and runs/tabs_1920_<tab>.png, then ALWAYS stops
the server + Edge and deletes the fixture order/run (try/finally).
Stdlib only.
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
PNG_GAL = os.path.join(RUNS, "gallery_1920.png")
PNG_GAL390 = os.path.join(RUNS, "gallery_390.png")
SERVER_LOG = os.path.join(RUNS, "gallery_server.log")
FIX_OID = "ord-20261101-900"
FIX_RUN = "galfix1"

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


GAL_JS = """(() => {
  const grid = document.getElementById('gal-grid');
  const cards = Array.from(
    grid.querySelectorAll('.galcard')).map(c => {
    const img = c.querySelector('.galthumb img');
    const q = (s) => c.querySelector(s);
    return {
      order: c.getAttribute('data-order'),
      title: (q('.galtitle') || {}).textContent || '',
      meta: (q('.galmeta') || {}).textContent || '',
      chip: (q('.galchip') || {}).textContent || '',
      imgSrc: img ? img.getAttribute('src') : null,
      imgW: img ? img.naturalWidth : -1,
      play: (q('[data-play]') || {})
        .getAttribute ? q('[data-play]')
        .getAttribute('data-play') : null,
      table: (q('a[href*="storyboard_table"]') || {})
        .getAttribute ? q('a[href*="storyboard_table"]')
        .getAttribute('href') : null,
      board: (q('[data-board]') || {})
        .getAttribute ? q('[data-board]')
        .getAttribute('data-board') : null,
      log: (q('a[href*="projectlog"]') || {})
        .getAttribute ? q('a[href*="projectlog"]')
        .getAttribute('href') : null
    };
  });
  const empty = grid.querySelector('.galempty');
  const cols = getComputedStyle(grid)
    .gridTemplateColumns.split(' ').length;
  return { cards: cards,
           empty: empty ? empty.textContent : null,
           cols: cols,
           reel: document.body.textContent
             .indexOf('REEL') >= 0 };
})()"""

WIDTH_JS = """((tab) => {
  const page = document.getElementById('p-' + tab);
  const card = page ? page.querySelector(':scope > .card')
    : null;
  const de = document.documentElement;
  return {
    wide: page ? page.classList.contains('wide') : false,
    cardW: card ? Math.round(
      card.getBoundingClientRect().width) : -1,
    vw: window.innerWidth,
    noH: de.scrollWidth <= de.clientWidth + 2
  };
})"""

PNG1 = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def make_fixture():
    od = os.path.join(ROOT, "orders", FIX_OID)
    rd = os.path.join(ROOT, "runs", FIX_RUN)
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"id": FIX_OID, "status": "in_production",
                   "created": "2026-11-01T15:00:00",
                   "closed": False,
                   "files": {"pc_title": "Test Reel",
                             "source": "chap2.pdf"}}, f)
    with open(os.path.join(od, "TIMELINE.md"), "w",
              encoding="utf-8") as f:
        f.write("# t\n")
    vd = os.path.join(rd, "video_production")
    os.makedirs(vd, exist_ok=True)
    with open(os.path.join(rd, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"run_id": FIX_RUN, "order_id": FIX_OID,
                   "state": "done"}, f)
    with open(os.path.join(vd, "storyboard_table.json"), "w",
              encoding="utf-8") as f:
        json.dump({"rows": []}, f)
    with open(os.path.join(vd, "result.json"), "w",
              encoding="utf-8") as f:
        json.dump({"categories": {"video": {"data": {
            "duration_s": 612}}}}, f)
    with open(os.path.join(vd, "assembly.json"), "w",
              encoding="utf-8") as f:
        json.dump({"total_s": 612, "segments": []}, f)
    with open(os.path.join(vd, "video.mp4"), "wb") as f:
        f.write(b"fixture-video-bytes")
    sd = os.path.join(rd, "slide_remy", "slides")
    os.makedirs(sd, exist_ok=True)
    with open(os.path.join(sd, "s1-c1.png"), "wb") as f:
        f.write(PNG1)


def drop_fixture():
    shutil.rmtree(os.path.join(ROOT, "orders", FIX_OID),
                  ignore_errors=True)
    shutil.rmtree(os.path.join(ROOT, "runs", FIX_RUN),
                  ignore_errors=True)


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


def click_tab(ws, tab):
    js_eval(ws, "document.querySelector"
                "('nav button[data-p=%s]').click()" % tab)
    t0 = time.time()
    while time.time() - t0 < 20:
        vis = js_eval(ws, "document.getElementById('p-%s')"
                          ".classList.contains('active')" % tab)
        if vis:
            break
        time.sleep(0.5)
    time.sleep(1)


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
    drop_fixture()
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(), "gal_profile")
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
        click_tab(ws, "gallery")
        g0 = js_eval(ws, GAL_JS)
        if not g0.get("cards"):
            ok((g0.get("empty") or "") ==
               "No finished videos yet \u2014 place an order"
               " in the Order tab.",
               "gallery empty state")
        else:
            ok(True, "gallery has real cards, empty skipped")
        ok(g0.get("reel") is False, "no REEL slots anywhere")
        make_fixture()
        js_eval(ws, "window.__galleryShown()")
        t0 = time.time()
        while time.time() - t0 < 20:
            g = js_eval(ws, GAL_JS)
            if [c for c in g.get("cards", [])
                    if c.get("order") == FIX_OID]:
                break
            time.sleep(0.5)
        g = js_eval(ws, GAL_JS)
        mine = [c for c in g.get("cards", [])
                if c.get("order") == FIX_OID]
        ok(len(mine) == 1, "fixture card shown")
        if not mine:
            print("%d FAILURES" % fails)
            return 1
        c = mine[0]
        ok(c.get("title") == "Test Reel", "card title (%s)"
           % c.get("title"))
        ok(FIX_OID in (c.get("meta") or "")
           and "2026-11-01" in (c.get("meta") or "")
           and "10:12" in (c.get("meta") or ""),
           "card meta order/date/length (%s)" % c.get("meta"))
        ok(c.get("chip") == "Video ready", "chip (%s)"
           % c.get("chip"))
        ok((c.get("imgSrc") or "")
           .endswith("node=slide_remy&path=slides/s1-c1.png")
           and c.get("imgW") == 1, "thumbnail loads (%s)"
           % c.get("imgSrc"))
        ok((c.get("play") or "")
           .endswith("node=video_production&path=video.mp4"),
           "play link (%s)" % c.get("play"))
        ok((c.get("table") or "").endswith(
            "name=storyboard_table.json"), "table link")
        ok(c.get("board") == FIX_RUN, "board run (%s)"
           % c.get("board"))
        ok((c.get("log") or "")
           == "/api/orders/%s/projectlog?name=TIMELINE.md"
           % FIX_OID, "log link")
        ok(g.get("cols", 0) >= 2, "grid multi-column (%s)"
           % g.get("cols"))
        js_eval(ws, "document.querySelector"
                    "('.galcard[data-order=\"%s\"] [data-play]')"
                    ".click()" % FIX_OID)
        time.sleep(1)
        vid = js_eval(ws, "(() => { const v = document"
                          ".querySelector('.galcard[data-order=\"%s\"]"
                          " .galthumb video');"
                          " return v ? v.getAttribute('src') : null;"
                          "})()" % FIX_OID)
        ok((vid or "").endswith("path=video.mp4"),
           "play opens inline video")
        vbase = "http://127.0.0.1:%d%s" % (SERVER_PORT,
                                            c["play"])
        req = urllib.request.Request(vbase,
                                     headers={"Range":
                                              "bytes=0-6"})
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            ok(r.status == 206 and r.headers.get(
                "Content-Range") == "bytes 0-6/19"
                and body == b"fixture",
               "video range 206 (%s)" % r.headers.get(
                   "Content-Range"))
        with urllib.request.urlopen(vbase, timeout=10) as r:
            ok(r.status == 200 and r.headers.get(
                "Accept-Ranges") == "bytes",
               "video full 200 + ranges")
        js_eval(ws, "document.querySelector"
                    "('.galcard[data-order=\"%s\"] [data-board]')"
                    ".click()" % FIX_OID)
        t0 = time.time()
        while time.time() - t0 < 30:
            bv = js_eval(ws, "document.getElementById"
                             "('bd-run').value")
            if bv == FIX_RUN:
                break
            time.sleep(0.5)
        ok(js_eval(ws, "document.getElementById('p-board')"
                       ".classList.contains('active')")
           and js_eval(ws, "document.getElementById"
                           "('bd-run').value") == FIX_RUN,
           "board button opens the run")
        click_tab(ws, "gallery")
        js_eval(ws, "window.scrollTo(0, 0)")
        time.sleep(0.5)
        shot(ws, PNG_GAL)
        for tab in ("order", "crew", "pc", "flow", "studio",
                    "board", "gallery", "settings", "about"):
            click_tab(ws, tab)
            w = js_eval(ws, WIDTH_JS + "('%s')" % tab)
            if tab in ("order", "crew", "pc", "gallery",
                       "settings", "about"):
                want = min(1600, w.get("vw", 0) - 32)
                ok(w.get("wide") is True
                   and abs(w.get("cardW", -1) - want) <= 2,
                   "%s card %s (want %s)" % (
                       tab, w.get("cardW"), want))
            ok(w.get("noH") is True,
               "%s no horizontal scroll" % tab)
            shot(ws, os.path.join(RUNS,
                                  "tabs_1920_%s.png" % tab))
        click_tab(ws, "about")
        about_w = js_eval(ws, "Math.round(document"
                              ".querySelector('#p-about .card p')"
                              ".getBoundingClientRect().width)")
        ok(about_w <= 862, "about text column <= 860 (%s)"
           % about_w)
        click_tab(ws, "gallery")
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        g2 = js_eval(ws, GAL_JS)
        ok(g2.get("cols") == 1, "grid one column at 390 (%s)"
           % g2.get("cols"))
        ok(js_eval(ws, "document.documentElement.scrollWidth"
                       " <= document.documentElement.clientWidth"
                       " + 2") is True,
           "no horizontal scroll at 390")
        shot(ws, PNG_GAL390)
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        stop_proc(server, "server")
        shutil.rmtree(profile, ignore_errors=True)
        drop_fixture()
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
