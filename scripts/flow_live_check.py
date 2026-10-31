"""Live Flow tab check against a real local server (one shot).

Starts scripts/server.py on port 8765 (never 8000), waits until it
answers, drives headless Edge over CDP like a user (open /, click
the Flow nav item), asserts a live svg box holding all 42 paths,
saves runs/flow_live.png, and ALWAYS stops the server + Edge
(try/finally). Stdlib only.

Usage (needs a sandbox exception for the socket bind):
  .venv\\Scripts\\python scripts/flow_live_check.py
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PORT = 8765
CDP_PORT = 9444
EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
RUNS = os.path.join(ROOT, "runs")
PNG = os.path.join(RUNS, "flow_live.png")
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
    labelClash: labelClash
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
    profile = os.path.join(RUNS, "flow_live_profile")
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
            [EDGE, "--headless", "--no-sandbox", "--disable-gpu",
             "--use-angle=swiftshader", "--no-first-run",
             "--disable-extensions",
             "--remote-debugging-port=%d" % CDP_PORT,
             "--user-data-dir=" + profile,
             "--window-size=1800,1000", "about:blank"])
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
        ws.call("Page.navigate",
                {"url": "http://localhost:%d/" % SERVER_PORT})
        t0 = time.time()
        while time.time() - t0 < 40:
            if js_eval(ws, "document.readyState") == "complete":
                break
            time.sleep(0.5)
        js_eval(ws, "document.querySelector"
                    "('nav button[data-p=flow]').click()")
        time.sleep(2)
        out = js_eval(ws, PROBE_JS)
        ok(out.get("tabActive") is True, "flow tab activates")
        sw, sh = (out.get("svg") or [0, 0])[:2]
        ok(sw > 0 and sh > 0, "svg is live (%dx%d)" % (sw, sh))
        ok(out.get("solid") == 13 and out.get("dotted") == 29,
           "13 solid + 29 dotted paths (nodes %s)"
           % out.get("nodes"))
        ok(sw > 0 and sh > 0 and out.get("inside") == 42,
           "all 42 paths inside the svg box (%s)"
           % out.get("inside"))
        perr = out.get("portErr", [])
        bad = [e for e in perr
               if e.get("error") or e.get("dOut", 99) > 6
               or e.get("dIn", 99) > 6]
        ok(len(perr) == 13 and not bad,
           "13 solid paths start/end at their own dots (%d, %s)"
           % (len(perr), bad or "all<=6px"))
        under = [e["ln"] for e in perr
                 if e.get("edgeGap", 99) > 8]
        ok(len(perr) == 13 and not under,
           "no line starts under its own node (%d, %s)"
           % (len(perr), under or "ok"))
        m = out.get("marty", {})
        ok(m.get("rows") == 2
           and m.get("labels") == ["concept", "structure"],
           "marty shows concept + structure ports (%s)" % m)
        s = out.get("sam", {})
        ok(s.get("rows") == 1 and s.get("labels") == ["request"],
           "sam shows only the request port (%s)" % s)
        ok(out.get("dots") == 29 and out.get("dotErr") == [],
           "29 dotted crew ends on edges/ports (%s)"
           % (out.get("dotErr") or "ok"))
        ok(out.get("shownLabels") == ["full text"],
           "only the full-text dotted label shows (%s)"
           % out.get("shownLabels"))
        ok(out.get("solidVisible") == 13
           and out.get("labelClash", -1) == 0,
           "13 solid labels visible, none overlap (%s/%s)"
           % (out.get("solidVisible"), out.get("labelClash")))
        shot = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG, "wb") as f:
            f.write(base64.b64decode(shot))
        ok(os.path.isfile(PNG) and os.path.getsize(PNG) > 1000,
           "screenshot saved (%s)" % PNG)
    finally:
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
