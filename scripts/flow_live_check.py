"""Live Flow tab check against a real local server (one shot).

Starts scripts/server.py on port 8765 (never 8000), waits until it
answers, drives headless Edge over CDP like a user (open /, click
the Flow nav item), asserts a live svg box holding all 91 paths,
saves runs/flow_live.png, and ALWAYS stops the server + Edge
(try/finally). Stdlib only.

Usage (needs a sandbox exception for the socket bind):
  .venv\\Scripts\\python scripts/flow_live_check.py
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
PNG1920 = os.path.join(RUNS, "flow_1920.png")
PNG1280 = os.path.join(RUNS, "flow_1280.png")
PNG390 = os.path.join(RUNS, "flow_390.png")
FACES1920 = os.path.join(RUNS, "flow_faces_1920.png")
FACES1280 = os.path.join(RUNS, "flow_faces_1280.png")
SERVER_LOG = os.path.join(RUNS, "flow_live_server.log")

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails += 1


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        return True
    except OSError:
        return False


class WS:
    """Minimal stdlib websocket client (text frames)."""

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


PROBE_JS = """(() => {
  const svg = document.getElementById('fl-svg');
  const sw = +svg.getAttribute('width') || 0;
  const sh = +svg.getAttribute('height') || 0;
  const paths = Array.from(
    svg.querySelectorAll('path.fl-line, path.fl-pcline'));
  let inside = 0;
  paths.forEach(p => {
    const nums = (p.getAttribute('d').match(/-?\\d+(\\.\\d+)?/g) ||
      []).map(Number);
    for (let i = 0; i + 1 < nums.length; i += 2)
      if (nums[i] >= 0 && nums[i] <= sw &&
          nums[i + 1] >= 0 && nums[i + 1] <= sh) {
        inside++;
        break;
      }
  });
  const sr = svg.getBoundingClientRect();
  const tm = getComputedStyle(document.getElementById("fl-zoom"))
    .transform;
  const pz = tm && tm !== "none" ?
    +(tm.split("(")[1].split(",")[0]) : 1;
  const boxOf = (id) => {
    const el = document.querySelector(
      '#fl-nodes .fl-node[data-n="' + id + '"]');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: (r.left - sr.left) / pz, y: (r.top - sr.top) / pz,
            w: r.width / pz, h: r.height / pz};
  };
  const ctr = (el) => {
    const r = el.getBoundingClientRect();
    return [(r.left - sr.left + r.width / 2) / pz,
            (r.top - sr.top + r.height / 2) / pz];
  };
  const portErr = [];
  svg.querySelectorAll('path.fl-line').forEach(p => {
    const from = p.getAttribute('data-from');
    const to = p.getAttribute('data-to');
    const nums = (p.getAttribute('d').match(/-?\d+(\.\d+)?/g) ||
      []).map(Number);
    const fb = boxOf(from);
    const inp = document.querySelector(
      '[data-in="' + to + '"]');
    const rows = Array.from(document.querySelectorAll(
      '[data-out="' + from + '"]'));
    if (!fb || !inp || !rows.length || nums.length < 4) {
      portErr.push({ln: p.getAttribute('data-ln'),
                    error: 'missing endpoint'});
      return;
    }
    const sx = nums[0], sy = nums[1];
    const ex = nums[nums.length - 2], ey = nums[nums.length - 1];
    const want = (p.getAttribute('data-cats') || '').split(',')
      .filter(Boolean).sort().join(',');
    const key = (r) => (r.getAttribute('data-cats') || '')
      .split(',').filter(Boolean).sort().join(',');
    let targets = rows.map(r => ctr(r.querySelector('i')));
    if (want)
      targets = rows.filter(r => key(r) === want)
        .map(r => ctr(r.querySelector('i')));
    if (!targets.length)
      targets = rows.map(r => ctr(r.querySelector('i')));
    const dOut = Math.min.apply(null, targets.map(
      d => Math.hypot(sx - d[0], sy - d[1])));
    const ic = ctr(inp);
    portErr.push({ln: p.getAttribute('data-ln'),
      dOut: Math.round(dOut * 10) / 10,
      dIn: Math.round(Math.hypot(ex - ic[0], ey - ic[1]) * 10) / 10,
      edgeGap: Math.round((fb.x + fb.w - sx) * 10) / 10});
  });
  const isCrew = (id) => {
    const el = document.querySelector(
      '#fl-nodes .fl-node[data-n="' + id + '"]');
    return el && !el.classList.contains('pcnode');
  };
  const dotErr = [];
  svg.querySelectorAll('path.fl-pcline').forEach(p => {
    const from = p.getAttribute('data-from');
    const to = p.getAttribute('data-to');
    const nums = (p.getAttribute('d').match(/-?\\d+(\\.\\d+)?/g) ||
      []).map(Number);
    if (!from || !to || nums.length < 4) {
      dotErr.push({ln: p.getAttribute('data-pl'),
                   error: 'missing endpoint'});
      return;
    }
    const sx = nums[0], sy = nums[1];
    const ex = nums[nums.length - 2], ey = nums[nums.length - 1];
    if (isCrew(from)) {
      const fb = boxOf(from);
      const gap = Math.abs(fb.x + fb.w - sx);
      const cx = Math.abs(fb.x + fb.w / 2 - sx);
      if (gap > 8 || cx < 20)
        dotErr.push({ln: p.getAttribute('data-pl'), why: 'start',
                     gap: Math.round(gap * 10) / 10,
                     cx: Math.round(cx * 10) / 10});
    }
    if (isCrew(to)) {
      const inp = document.querySelector('[data-in="' + to + '"]');
      const ic = ctr(inp);
      const dIn = Math.hypot(ex - ic[0], ey - ic[1]);
      if (dIn > 6)
        dotErr.push({ln: p.getAttribute('data-pl'), why: 'end',
                     dIn: Math.round(dIn * 10) / 10});
    }
  });
  const visLab = Array.from(
    svg.querySelectorAll('text.fl-label:not(.oh)'));
  let labelClash = 0;
  const visBox = visLab.map(t => {
    try { return t.getBBox(); } catch (e) { return null; }
  });
  for (let i = 0; i < visBox.length; i++)
    for (let j = i + 1; j < visBox.length; j++) {
      const a = visBox[i], b = visBox[j];
      if (a && b && a.x < b.x + b.width && b.x < a.x + a.width &&
          a.y < b.y + b.height && b.y < a.y + a.height)
        labelClash++;
    }
  const mrows = Array.from(
    document.querySelectorAll('[data-out="pd_marty"]'));
  const srows = Array.from(
    document.querySelectorAll('[data-out="sales_sam"]'));
  return {
    svg: [sw, sh],
    solid: svg.querySelectorAll('path.fl-line').length,
    dotted: svg.querySelectorAll('path.fl-pcline').length,
    inside: inside,
    nodes: document.querySelectorAll('#fl-nodes .fl-node').length,
    tabActive: document.getElementById('p-flow')
      .classList.contains('active'),
    portErr: portErr,
    marty: {rows: mrows.length,
            labels: mrows.map(
              r => r.querySelector('span').textContent)},
    sam: {rows: srows.length,
          labels: srows.map(
            r => r.querySelector('span').textContent)},
    dots: svg.querySelectorAll('path.fl-pcline').length,
    dotErr: dotErr,
    shownLabels: Array.from(
      svg.querySelectorAll('text.fl-pclabel.on'))
      .map(t => t.textContent),
    solidVisible: visLab.length,
    labelClash: labelClash,
    boxes: Array.from(
      document.querySelectorAll("#fl-nodes .fl-node"))
      .map(el => { const r = el.getBoundingClientRect();
        return [Math.round(r.x * 10) / 10,
                Math.round(r.y * 10) / 10,
                Math.round(r.width * 10) / 10,
                Math.round(r.height * 10) / 10]; }),
    canvas: (() => { const c =
      document.getElementById("fl-canvas");
      if (!c) return null;
      const r = c.getBoundingClientRect();
      return [Math.round(r.width), Math.round(r.height)];
    })(),
    scrollX: document.documentElement.scrollWidth >
      document.documentElement.clientWidth + 1,
    scrollY: document.documentElement.scrollHeight >
      document.documentElement.clientHeight + 1,
    viewport: [innerWidth, innerHeight],
    zoomLab: (document.getElementById("fl-zoomlab")
      || {}).textContent || "",
    layout: (() => { const s =
      document.getElementById("fl-scroll");
      const r = s.getBoundingClientRect();
      return {top: Math.round(r.top),
        h: Math.round(r.height),
        docH: document.documentElement.scrollHeight,
        winH: innerHeight}; })(),
  };
})()"""


FACES_JS = """(() => {
  const tm = getComputedStyle(document.getElementById("fl-zoom"))
    .transform;
  const pz = tm && tm !== "none" ?
    +(tm.split("(")[1].split(",")[0]) : 1;
  const emps = Array.from(
    document.querySelectorAll('#fl-nodes .fl-node.face'));
  return {
    faces: emps.length,
    ready: emps.filter(el => {
      const img = el.querySelector('.fl-face img');
      return img && (img.src || '').length > 1000;
    }).length,
    faceBox: emps.map(el => {
      const r = el.querySelector('.fl-face')
        .getBoundingClientRect();
      return [Math.round(r.width / pz),
              Math.round(r.height / pz)];
    }),
    empH: emps.map(el => Math.round(
      el.getBoundingClientRect().height / pz)),
    stray: document.querySelectorAll(
      '#fl-nodes .fl-node:not(.face) .fl-face').length
  };
})()"""


BOX_JS = """(() => {
  const sc = document.getElementById('fl-scroll');
  const sr = sc.getBoundingClientRect();
  const card = document.querySelector('#p-flow .card');
  const cs = getComputedStyle(card);
  const st = document.getElementById('fl-status');
  const tr = document.getElementById('fl-toolbar')
    .getBoundingClientRect();
  const str = st.getBoundingClientRect();
  const hint = document.getElementById('fl-hint');
  const tag = document.querySelector('#teamframe .teamtag');
  const cv = document.getElementById('fl-canvas')
    .getBoundingClientRect();
  let tagIn = false;
  if (tag) {
    const g = tag.getBoundingClientRect();
    tagIn = g.width > 0 && g.left >= cv.left - 1 &&
      g.top >= cv.top - 1 && g.right <= cv.right + 1 &&
      g.bottom <= cv.bottom + 1;
  }
  return {
    scroll: [Math.round(sr.width), Math.round(sr.height),
             Math.round(sr.top)],
    cardW: card.clientWidth,
    cardPad: parseFloat(cs.paddingLeft) +
      parseFloat(cs.paddingRight),
    scrollBg: getComputedStyle(sc).backgroundColor,
    canvasBg: getComputedStyle(
      document.getElementById('fl-canvas')).backgroundColor,
    wantH: innerHeight - Math.round(sr.top) - 12,
    docH: document.documentElement.scrollHeight,
    winH: innerHeight,
    scrollX: document.documentElement.scrollWidth >
      document.documentElement.clientWidth + 1,
    scrollY: document.documentElement.scrollHeight >
      document.documentElement.clientHeight + 1,
    status: st.textContent,
    statusRight: Math.round(tr.right - str.right),
    hintShown: getComputedStyle(hint).display !== 'none',
    helpBtn: !!document.getElementById('fl-help'),
    tagIn: tagIn,
    zoomLab: (document.getElementById('fl-zoomlab')
      || {}).textContent || ''
  };
})()"""


def box_overlaps(boxes):
    """Node-box pairs whose interiors overlap."""
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] \
                    and a[1] < b[1] + b[3] \
                    and b[1] < a[1] + a[3]:
                bad.append((i, j))
    return bad


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
                           "flow_live_profile")
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
            print("server log tail:")
            print(open(SERVER_LOG, encoding="utf-8").read()[-800:])
            print("1 FAILURES")
            return 1
        ok(True, "server answers on %d" % SERVER_PORT)
        edge = subprocess.Popen(
            _browser.launch_args(CDP_PORT, profile, 1920, 1080))
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
                    "('nav button[data-p=flow]').click()")
        time.sleep(2)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 1920, "height": 940,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        js_eval(ws, "window.__flowShown && window.__flowShown()")
        time.sleep(1)
        t0 = time.time()
        while time.time() - t0 < 12:
            if js_eval(ws, "document.getElementById('fl-status')"
                            ".textContent"):
                break
            time.sleep(0.5)
        out = js_eval(ws, PROBE_JS)
        box = js_eval(ws, BOX_JS)
        ok(out.get("tabActive") is True, "flow tab activates")
        sw, sh = (out.get("svg") or [0, 0])[:2]
        ok(sw > 0 and sh > 0, "svg is live (%dx%d)" % (sw, sh))
        ok(out.get("solid") == 47 and out.get("dotted") == 44,
           "47 solid + 44 dotted paths (nodes %s)"
           % out.get("nodes"))
        ok(sw > 0 and sh > 0 and out.get("inside") == 91,
           "all 91 paths inside the svg box (%s)"
           % out.get("inside"))
        perr = out.get("portErr", [])
        bad = [e for e in perr
               if e.get("error") or e.get("dOut", 99) > 6
               or e.get("dIn", 99) > 6]
        ok(len(perr) == 47 and not bad,
           "47 solid paths start/end at their own dots (%d, %s)"
           % (len(perr), bad or "all<=6px"))
        under = [e["ln"] for e in perr
                 if e.get("edgeGap", 99) > 8]
        ok(len(perr) == 47 and not under,
           "no line starts under its own node (%d, %s)"
           % (len(perr), under or "ok"))
        m = out.get("marty", {})
        ok(m.get("rows") == 2
           and m.get("labels") == ["concept", "structure"],
           "marty shows concept + structure ports (%s)" % m)
        s = out.get("sam", {})
        ok(s.get("rows") == 1 and s.get("labels") == ["request"],
           "sam shows only the request port (%s)" % s)
        ok(out.get("dots") == 44 and out.get("dotErr") == [],
           "44 dotted crew ends on edges/ports (%s)"
           % (out.get("dotErr") or "ok"))
        ok(out.get("shownLabels") == ["full text"],
           "only the full-text dotted label shows (%s)"
           % out.get("shownLabels"))
        ztxt = (out.get("zoomLab") or "").replace("%", "")
        try:
            znum = int(ztxt)
        except ValueError:
            znum = 100
        if znum < 70:
            ok(out.get("solidVisible", -1) == 0
               and out.get("labelClash", -1) == 0,
               "zoom %d%% < 70: labels hover-only"
               % znum)
        else:
            ok(out.get("solidVisible", -1) >= 30
               and out.get("labelClash", -1) == 0,
               "solid labels on, dense rest hover-only"
               " (%s/%s)"
               % (out.get("solidVisible"),
                  out.get("labelClash")))
        boxes = out.get("boxes") or []
        ok(len(boxes) == 21,
           "21 nodes on the canvas (got %d)"
           % len(boxes))
        clash = box_overlaps(boxes)
        ok(len(boxes) == 21 and not clash,
           "no node overlap (%s)" % (clash or "ok"))
        vp = out.get("viewport") or [0, 0]
        cv = out.get("canvas")
        print("viewport %sx%s canvas %s"
              % (vp[0], vp[1], cv), flush=True)
        ok(out.get("scrollX") is False,
           "no page h-scroll at 1920")
        ok(out.get("scrollY") is False,
           "no page v-scroll at 1920")
        sw_, sh_, stop_ = box.get("scroll") or [0, 0, 0]
        ok(abs(sw_ - (box.get("cardW", 0) - box.get("cardPad", 0)))
           <= 3,
           "grey box fills the card width (%d/%d)"
           % (sw_, box.get("cardW", 0) - box.get("cardPad", 0)))
        ok(200 <= sh_ <= (box.get("wantH", 0) + 2),
           "grey box height %d (want <= %d)"
           % (sh_, box.get("wantH", 0)))
        ok(box.get("scrollBg") == "rgb(247, 249, 252)",
           "scroller is the grey box (%s)"
           % box.get("scrollBg"))
        ok(box.get("canvasBg") in ("rgba(0, 0, 0, 0)",
                                   "transparent"),
           "stage inside is transparent (%s)"
           % box.get("canvasBg"))
        ok((box.get("status") or "").startswith("Valid"),
           "toolbar status shows the verdict (%r)"
           % box.get("status"))
        ok(abs(box.get("statusRight", 99)) <= 6,
           "status right-aligned (%dpx)"
           % box.get("statusRight", 99))
        ok(box.get("helpBtn") is True
           and box.get("hintShown") is False,
           "hint hidden behind the ? button")
        js_eval(ws, "document.getElementById('fl-help').click()")
        time.sleep(0.5)
        ok(js_eval(ws, "document.getElementById('fl-hint')"
                        ".classList.contains('show')") is True,
           "? button shows the hint")
        js_eval(ws, "document.getElementById('fl-help').click()")
        time.sleep(0.5)
        ok(box.get("tagIn") is True,
           "video-team frame title not clipped")
        print("1920x940 fit %s (box %dx%d at top %d, docH %d)"
              % (box.get("zoomLab"), sw_, sh_, stop_,
                 box.get("docH")), flush=True)
        t0 = time.time()
        faces = {}
        while time.time() - t0 < 90:
            faces = js_eval(ws, FACES_JS) or {}
            if faces.get("faces") == 12 \
                    and faces.get("ready") == 12:
                break
            time.sleep(1)
        ok(faces.get("faces") == 12,
           "12 employee nodes show a face (got %s)"
           % faces.get("faces"))
        ok(faces.get("ready") == 12,
           "12 faces rendered (got %s)"
           % faces.get("ready"))
        ok(all(b == [44, 44] for b in faces.get("faceBox", []))
           and len(faces.get("faceBox", [])) == 12,
           "faces are 44px squares (%s)"
           % faces.get("faceBox"))
        ok(faces.get("stray") == 0,
           "no face on PC/code/final nodes (got %s)"
           % faces.get("stray"))
        maxh = max(faces.get("empH") or [0])
        print("employee node heights %s (max %d)"
              % (faces.get("empH"), maxh), flush=True)
        ok(maxh <= 176,
           "employee nodes fit the 180px row pitch (max %d)"
           % maxh)
        js_eval(ws, "document.getElementById('fl-z100').click()")
        time.sleep(1)
        faces100 = js_eval(ws, FACES_JS) or {}
        maxh100 = max(faces100.get("empH") or [0])
        print("100%% employee node heights %s (max %d)"
              % (faces100.get("empH"), maxh100), flush=True)
        ok(maxh100 <= 176,
           "100%%: employee nodes fit the row pitch (max %d)"
           % maxh100)
        out100 = js_eval(ws, PROBE_JS) or {}
        clash100 = box_overlaps(out100.get("boxes") or [])
        ok(not clash100,
           "100%%: no node overlap (%s)" % (clash100 or "ok"))
        js_eval(ws, "document.getElementById('fl-zfit').click()")
        time.sleep(1)
        box = js_eval(ws, BOX_JS)
        print("1920x940 fit %s (restored after 100%%)"
              % box.get("zoomLab"), flush=True)
        shot = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG1920, "wb") as f:
            f.write(base64.b64decode(shot))
        with open(FACES1920, "wb") as f:
            f.write(base64.b64decode(shot))
        ok(os.path.isfile(PNG1920)
           and os.path.getsize(PNG1920) > 1000,
           "screenshot saved (%s)" % PNG1920)
        ok(os.path.isfile(FACES1920)
           and os.path.getsize(FACES1920) > 1000,
           "screenshot saved (%s)" % FACES1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 1280, "height": 720,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        js_eval(ws, "window.__flowShown && window.__flowShown()")
        time.sleep(1)
        out2 = js_eval(ws, PROBE_JS)
        box2 = js_eval(ws, BOX_JS)
        ok(out2.get("scrollX") is False
           and out2.get("scrollY") is False,
           "no page scroll at 1280")
        print("1280x720 fit %s (box %s, docH %s)"
              % (box2.get("zoomLab"), box2.get("scroll"),
                 box2.get("docH")), flush=True)
        print("1280 scroll %s/%s"
              % (out2.get("scrollX"), out2.get("scrollY")),
              flush=True)
        print("1280 layout %s" % out2.get("layout"),
              flush=True)
        shot = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG1280, "wb") as f:
            f.write(base64.b64decode(shot))
        with open(FACES1280, "wb") as f:
            f.write(base64.b64decode(shot))
        ok(os.path.isfile(PNG1280)
           and os.path.getsize(PNG1280) > 1000,
           "screenshot saved (%s)" % PNG1280)
        ok(os.path.isfile(FACES1280)
           and os.path.getsize(FACES1280) > 1000,
           "screenshot saved (%s)" % FACES1280)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        js_eval(ws, "window.__flowShown && window.__flowShown()")
        time.sleep(1)
        out3 = js_eval(ws, PROBE_JS)
        box3 = js_eval(ws, BOX_JS)
        print("390x844 fit %s (box %s, docH %s)"
              % (box3.get("zoomLab"), box3.get("scroll"),
                 box3.get("docH")), flush=True)
        print("390 scroll %s/%s"
              % (out3.get("scrollX"), out3.get("scrollY")),
              flush=True)
        print("390 layout %s" % out3.get("layout"),
              flush=True)
        ok(out3.get("scrollX") is False
           and out3.get("scrollY") is False,
           "no page scroll at 390")
        shot = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG390, "wb") as f:
            f.write(base64.b64decode(shot))
        ok(os.path.isfile(PNG390)
           and os.path.getsize(PNG390) > 1000,
           "screenshot saved (%s)" % PNG390)
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
