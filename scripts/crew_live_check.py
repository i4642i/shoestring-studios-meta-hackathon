"""Crew portraits + team sections check, J1/J2/J23/J24 (one shot).

Starts scripts/server.py on port 8765 (never 8000), drives headless
Edge over CDP (1920x1080 then 390x844), clicks the Crew nav item, and
asserts: 13 employee cards, 13 non-empty portraits (one shared
offscreen renderer, so no canvas elements inside the roster), the 88px
square layout (64px at 390px), team sections (story/video/none, sorted
by stage then id, team-colour stripes), the required Team select on
Add employee, zero console errors. Creates a temp video employee via
the API, checks it lands in the Video section and in the office (desk
sharing is reported), edits its team, then deletes it. Saves
runs/crew_1920.png, runs/crew_390.png, runs/crew_square_1920.png,
runs/crew_teams_1920.png and runs/crew_teams_390.png, then ALWAYS
stops the server + Edge (try/finally). Stdlib only.
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
PNG1920 = os.path.join(RUNS, "crew_1920.png")
PNG390 = os.path.join(RUNS, "crew_390.png")
PNGSQUARE = os.path.join(RUNS, "crew_square_1920.png")
PNGTEAMS1920 = os.path.join(RUNS, "crew_teams_1920.png")
PNGTEAMS390 = os.path.join(RUNS, "crew_teams_390.png")
TMP_ID = "tmp24_vid"
SERVER_LOG = os.path.join(RUNS, "crew_live_server.log")

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


PROBE_JS = """(() => {
  const cards = Array.from(
    document.querySelectorAll('#roster .idcard'));
  const imgs = Array.from(
    document.querySelectorAll('#roster .idpic img'));
  const full = imgs.filter(
    i => (i.src || '').length > 1000);
  const pic = document.querySelector('#roster .idpic');
  const pr = pic ? pic.getBoundingClientRect() : null;
  const nm = document.querySelector('#roster .idcard .nm');
  return {
    cards: cards.length,
    imgs: imgs.length,
    full: full.length,
    canvases: document.querySelectorAll(
      '#roster canvas').length,
    picW: pr ? Math.round(pr.width) : 0,
    picRound: pic ?
      getComputedStyle(pic).borderRadius : '',
    nameLeftOfPic: nm && pr ?
      Math.round(nm.getBoundingClientRect().left -
        pr.right) : -999,
    meta: (document.querySelector(
      '#roster .idcard .meta') || {}).textContent || '',
    graph: (document.querySelector(
      '#roster .idcard .g') || {}).textContent || ''
  };
})()"""


TEAMS_JS = """(() => {
  const heads = Array.from(
    document.querySelectorAll('#roster .teamhead'))
    .map(h => h.textContent);
  const grids = Array.from(
    document.querySelectorAll('#roster .idgrid'))
    .map(g => ({
      team: g.dataset.team || '',
      ids: Array.from(g.querySelectorAll('.idcard'))
        .map(c => (c.getAttribute('aria-label') || '')
          .replace(/^Employee /, '')),
      stripe: (() => {
        const s = g.querySelector('.idcard .stripe');
        return s ? getComputedStyle(s).backgroundColor : '';
      })()
    }));
  return {
    heads: heads,
    grids: grids,
    note: (document.querySelector('#roster .teamnote') || {})
      .textContent || ''
  };
})()"""


def http_json(method, path, body=None):
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (SERVER_PORT, path),
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
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
    profile = os.path.join(tempfile.gettempdir(), "crew_live_profile")
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
                    "('nav button[data-p=crew]').click()")
        ok(wait_for(ws, "document.querySelectorAll("
                        "'#roster .idcard').length === 13",
                    timeout=30),
           "13 employee cards")
        ok(wait_for(ws, "Array.from(document.querySelectorAll("
                        "'#roster .idpic img')).filter(i => "
                        "(i.src || '').length > 1000).length === 13",
                    timeout=90),
           "13 non-empty portraits")
        out = js_eval(ws, PROBE_JS)
        ok(out.get("cards") == 13, "13 cards (got %s)"
           % out.get("cards"))
        ok(out.get("full") == 13, "13 portraits rendered (got %s)"
           % out.get("full"))
        ok(out.get("canvases") == 0,
           "no canvas per card (shared renderer)")
        ok(out.get("picW") == 88, "portrait square 88px (got %s)"
           % out.get("picW"))
        ok(out.get("picRound") == "6px",
           "portrait is a square, radius 6px (%s)"
           % out.get("picRound"))
        ok(out.get("nameLeftOfPic", -999) >= 8,
           "name sits right of the portrait (%spx)"
           % out.get("nameLeftOfPic"))
        ok("sales_sam" in (out.get("meta") or ""),
           "id/model line unchanged (%s)" % out.get("meta"))
        ok(not out.get("graph"),
           "graph line gone (%s)" % out.get("graph"))
        teams = js_eval(ws, TEAMS_JS)
        ok(teams.get("heads") == ["STORYBOARD TEAM (7)",
                                  "VIDEO TEAM (5)",
                                  "NO TEAM (1)"],
           "sections in order with counts (%s)"
           % teams.get("heads"))
        grids = {g["team"]: g for g in teams.get("grids", [])}
        ok(grids.get("story", {}).get("ids")
           == ["sales_sam", "pd_marty", "case_rex", "explain_cleo",
               "plan_ash", "voice_wren", "board_penn"],
           "story sorted by stage then id (%s)"
           % grids.get("story", {}).get("ids"))
        ok(grids.get("video", {}).get("ids")
           == ["anim_max", "image_gene", "photo_pia",
               "board_vera", "slide_remy"],
           "video sorted by stage then id (%s)"
           % grids.get("video", {}).get("ids"))
        ok(grids.get("none", {}).get("ids") == ["voice_iris"],
           "no-team holds only voice_iris (%s)"
           % grids.get("none", {}).get("ids"))
        ok(teams.get("note") == "Not in the current flow.",
           "no-team note shown (%r)" % teams.get("note"))
        ok(grids.get("story", {}).get("stripe")
           == "rgb(0, 100, 224)"
           and grids.get("video", {}).get("stripe")
           == "rgb(194, 87, 27)",
           "stripes use the team colours (%s/%s)"
           % (grids.get("story", {}).get("stripe"),
              grids.get("video", {}).get("stripe")))
        js_eval(ws, "document.querySelector"
                    "('#crew-tabs [data-ct=add]').click()")
        time.sleep(0.5)
        add = js_eval(ws, "(() => { const s = "
                          "document.getElementById('n-team'); return {"
                          "opts: Array.from(s.options).map(o => o.value),"
                          "sel: s.value, "
                          "dis: document.getElementById('n-create')"
                          ".disabled}; })()")
        ok(add.get("opts") == ["", "story", "video"]
           and add.get("sel") == "",
           "team select storyboard/video, no default (%s)"
           % add)
        ok(add.get("dis") is True,
           "create disabled until a team is picked")
        js_eval(ws, "(() => { const s = "
                    "document.getElementById('n-team'); s.value = 'video';"
                    " s.dispatchEvent(new Event('change')); })()")
        ok(js_eval(ws, "document.getElementById('n-create')"
                       ".disabled") is False,
           "create enables after picking a team")
        js_eval(ws, "document.querySelector"
                    "('#crew-tabs [data-ct=list]').click()")
        time.sleep(0.5)
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG1920, "wb") as f:
            f.write(base64.b64decode(data))
        with open(PNGSQUARE, "wb") as f:
            f.write(base64.b64decode(data))
        with open(PNGTEAMS1920, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG1920)
           and os.path.getsize(PNG1920) > 1000,
           "screenshot saved (%s)" % PNG1920)
        ok(os.path.isfile(PNGSQUARE)
           and os.path.getsize(PNGSQUARE) > 1000,
           "screenshot saved (%s)" % PNGSQUARE)
        ok(os.path.isfile(PNGTEAMS1920)
           and os.path.getsize(PNGTEAMS1920) > 1000,
           "screenshot saved (%s)" % PNGTEAMS1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1.5)
        out2 = js_eval(ws, PROBE_JS)
        ok(out2.get("picW") == 64,
           "390px: portrait stays 64px (got %s)"
           % out2.get("picW"))
        ok(out2.get("full") == 13, "390px: portraits kept")
        data = ws.call("Page.captureScreenshot",
                       {"format": "png"})["data"]
        with open(PNG390, "wb") as f:
            f.write(base64.b64decode(data))
        with open(PNGTEAMS390, "wb") as f:
            f.write(base64.b64decode(data))
        ok(os.path.isfile(PNG390)
           and os.path.getsize(PNG390) > 1000,
           "screenshot saved (%s)" % PNG390)
        ok(os.path.isfile(PNGTEAMS390)
           and os.path.getsize(PNGTEAMS390) > 1000,
           "screenshot saved (%s)" % PNGTEAMS390)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 1920, "height": 1080,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        st, rej = http_json("POST", "/api/crew",
                            {"id": TMP_ID, "name": "Tmp",
                             "title": "Tester"})
        ok(st == 400, "create without team is refused (%s)" % st)
        tmp_path = os.path.join(ROOT, "agents", TMP_ID)
        try:
            st, created = http_json(
                "POST", "/api/crew",
                {"id": TMP_ID, "name": "Tmp", "title": "Tester",
                 "team": "video"})
            ok(st == 201, "temp video employee created (%s)" % st)
            prof = os.path.join(tmp_path, "profile.md")
            ok(os.path.isfile(prof) and "Team: Video team" in
               open(prof, encoding="utf-8").read(),
               "temp profile card says Video team")
            ws.call("Page.navigate",
                    {"url": "http://localhost:%d/" % SERVER_PORT})
            drain_dialogs(ws, 12)
            t0 = time.time()
            while time.time() - t0 < 40:
                if js_eval(ws, "document.readyState") == "complete":
                    break
                time.sleep(0.5)
            js_eval(ws, "document.querySelector"
                        "('nav button[data-p=crew]').click()")
            ok(wait_for(ws, "document.querySelectorAll("
                            "'#roster .idcard').length === 14",
                        timeout=30),
               "14 cards with the temp employee")
            teams2 = js_eval(ws, TEAMS_JS)
            grids2 = {g["team"]: g
                      for g in teams2.get("grids", [])}
            ok(TMP_ID in grids2.get("video", {}).get("ids", []),
               "temp employee shows in the Video section (%s)"
               % grids2.get("video", {}).get("ids"))
            st, upd = http_json("PUT", "/api/crew/" + TMP_ID,
                                {"team": "story"})
            ok(st == 200 and "team" in (upd.get("changed") or []),
               "detail edit path changes the team (%s)" % st)
            ok("Team: Storyboard team" in
               open(prof, encoding="utf-8").read(),
               "profile card rebuilt after the team edit")
            st, upd = http_json("PUT", "/api/crew/" + TMP_ID,
                                {"team": "video"})
            ok(st == 200, "temp employee moved back to video")
            js_eval(ws, "document.querySelector"
                        "('nav button[data-p=studio]').click()")
            ok(wait_for(ws, "(() => { const f = document.querySelector("
                            "'#p-studio iframe.office'); try { return !!(f "
                            "&& f.contentWindow.__officeReady); } "
                            "catch (e) { return false; } })()",
                        timeout=180),
               "office boots with the temp employee")
            status = js_eval(ws, "JSON.parse(JSON.stringify("
                                 "document.querySelector("
                                 "'#p-studio iframe.office')"
                                 ".contentWindow.__officeStatus))")
            ok((status or {}).get("video") == 6,
               "office spawns 6 video members (%s)" % status)
            ok(TMP_ID in (status or {}).get("sharing", []),
               "desk run-out names the temp employee (%s)"
               % (status or {}).get("sharing"))
        finally:
            http_json("DELETE", "/api/crew/" + TMP_ID)
            shutil.rmtree(tmp_path, ignore_errors=True)
            ok(not os.path.exists(tmp_path),
               "temp employee removed")
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
