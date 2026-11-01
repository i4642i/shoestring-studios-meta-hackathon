"""Live Board tab check against a real local server (one shot).

Writes a throwaway fixture run into runs/boardshot1, starts
scripts/server.py on port 8765 (never 8000), drives headless Edge
over CDP like a user (open /, click the Board nav item), asserts
the stage strip + table + side panel + verify cards + summary bar,
saves runs/board_1920.png, runs/board_1280.png,
runs/board_cell.png (photo cell clicked) and
runs/board_verify_1920.png, then re-runs the Board against an
empty runs folder (SHOESTRING_RUNS_DIR) for runs/board_empty.png,
and ALWAYS stops servers + Edge and deletes the fixture run
(try/finally). Stdlib only.

Usage (needs a sandbox exception for the socket bind):
  .venv\\Scripts\\python scripts/board_live_check.py
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
FIX = os.path.join(RUNS, "boardshot1")
PNG1920 = os.path.join(RUNS, "board_1920.png")
PNG1280 = os.path.join(RUNS, "board_1280.png")
PNGCELL = os.path.join(RUNS, "board_cell.png")
PNGVERIFY = os.path.join(RUNS, "board_verify_1920.png")
PNGEMPTY = os.path.join(RUNS, "board_empty.png")
SERVER_LOG = os.path.join(RUNS, "board_live_server.log")

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
                for ev in self.events:
                    pass
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
  const t = document.getElementById('bd-table');
  const rows = t ? t.querySelectorAll('tbody tr') : [];
  const h2 = t ? t.querySelectorAll('thead tr')[1] : null;
  const pills = document.querySelectorAll('#bd-strip .bd-pill');
  const side = document.getElementById('bd-side');
  const sel = t ? t.querySelector('.bd-sel') : null;
  return {
    tabActive: document.getElementById('p-board')
      .classList.contains('active'),
    pills: pills.length,
    rows: rows.length,
    cols: h2 ? h2.children.length : 0,
    group1: t && t.querySelector('.bd-grp-story') ?
      t.querySelector('.bd-grp-story').textContent : '',
    group2: t && t.querySelector('.bd-grp-video') ?
      t.querySelector('.bd-grp-video').textContent : '',
    side: side ? side.textContent.slice(0, 60) : '',
    sel: sel ? (sel.getAttribute('data-col') + '/' +
      sel.getAttribute('data-cut')) : null,
    viewport: [innerWidth, innerHeight],
    scrollX: document.documentElement.scrollWidth >
      document.documentElement.clientWidth
  };
})()"""

CLICK_PHOTO_JS = """(() => {
  const td = document.querySelector(
    '#bd-table td[data-col="photo"][data-cut="s1c1"]');
  if (td) td.click();
  return !!td;
})()"""

SIDETITLE_JS = """(() => {
  const h = document.querySelector('#bd-side h3');
  return h ? h.textContent : '';
})()"""

PILLS_JS = """(() => {
  const pills = Array.from(
    document.querySelectorAll('#bd-strip .bd-pill'));
  const pp = document.querySelectorAll(
    '#bd-strip .bd-pill .bd-pp');
  return {pills: pills.length, pp: pp.length,
          sample: pills[4] ? pills[4].textContent : ''};
})()"""

CLICK_JS = """((col, cut) => {
  const td = document.querySelector(
    '#bd-table td[data-col="' + col + '"][data-cut="' +
    cut + '"]');
  if (td) td.click();
  return !!td;
})"""

SIDECARDS_JS = """(() => {
  const side = document.getElementById('bd-side');
  const cards = Array.from(
    side.querySelectorAll('.bd-card h5'))
    .map(h => h.textContent);
  return {cards: cards,
          boxes: side.querySelectorAll(
            '.bd-mini i').length,
          text: side.textContent};
})()"""

NARROW_JS = """(() => {
  const w = document.getElementById('bd-tablewrap');
  const s = document.getElementById('bd-side');
  if (!w || !s) return null;
  const wr = w.getBoundingClientRect();
  const sr = s.getBoundingClientRect();
  return {wrapBottom: wr.bottom, sideTop: sr.top,
          wrapH: wr.height};
})()"""

SUMMARY_JS = """(() => {
  const s = document.getElementById('bd-sum');
  const a = s ? s.querySelector('a') : null;
  const t = document.querySelector(
    '#bd-table tr.bd-emptyrow td');
  return {text: s ? s.textContent : '',
          href: a ? a.getAttribute('href') : '',
          empty: t ? t.textContent : ''};
})()"""

HLCOUNT_JS = """(() => document.querySelectorAll(
  '#bd-table td.bd-hl').length)()"""

CLICK_HL_JS = """((id) => {
  const b = document.getElementById(id);
  if (b) b.click();
  return !!b;
})"""

VALL_JS = """((on) => {
  const c = document.getElementById('bd-vall');
  if (!c) return {has: false};
  c.checked = !!on;
  c.dispatchEvent(new Event('change'));
  const cols = Array.from(document.querySelectorAll(
    '#bd-side .bd-vcols > div'))
    .map(d => (d.querySelector('b') || {}).textContent);
  return {has: true, cols: cols};
})"""

SIDECLONE_JS = """(() => {
  const c = document.querySelector('#bd-side .bd-clone');
  const v = document.getElementById('bd-vall');
  return {clone: c ? c.textContent : '',
          allParts: !!v};
})()"""

EMPTY_JS = """(() => {
  const t = document.getElementById('bd-table');
  const h2 = t ? t.querySelectorAll('thead tr')[1] : null;
  const row = t ? t.querySelector('tr.bd-emptyrow td') : null;
  const sel = document.getElementById('bd-run');
  return {cols: h2 ? h2.children.length : 0,
          group1: t && t.querySelector('.bd-grp-story') ?
            t.querySelector('.bd-grp-story').textContent : '',
          group2: t && t.querySelector('.bd-grp-video') ?
            t.querySelector('.bd-grp-video').textContent : '',
          empty: row ? row.textContent : '',
          picker: sel ? sel.textContent : ''};
})()"""


def wres(node, categories):
    ndir = os.path.join(FIX, node)
    os.makedirs(ndir, exist_ok=True)
    res = {"producer": node, "format_version": 1,
           "order_id": "ord-shot-001", "run_id": "boardshot1",
           "created_at": "2026-01-01", "status": "unverified",
           "categories": {
               name: {"version": 1, "data": data}
               for name, data in categories.items()}}
    with open(os.path.join(ndir, "result.json"), "w",
              encoding="utf-8") as f:
        json.dump(res, f)
    with open(os.path.join(ndir, "report.md"), "w",
              encoding="utf-8") as f:
        f.write("# shot report for %s\n" % node)
    with open(os.path.join(ndir, "INPUTS.md"), "w",
              encoding="utf-8") as f:
        f.write("# inputs for %s\n" % node)


STRUCT = {
    "source_ref": "pc://source/shot",
    "parts": [
        {"id": "p1", "heading": "1.1 First Steps",
         "ref": "pc://source/shot#s1.1", "covers": "basics",
         "keywords": ["alpha"]},
        {"id": "p2", "heading": "1.2 Next Moves",
         "ref": "pc://source/shot#s1.2", "covers": "advanced",
         "keywords": ["beta"]}],
    "links": [{"from": "p1", "to": "p2", "why": "builds up"}],
    "duration": {"total_s": 60, "parts": [
        {"part_id": "p1", "seconds": 30, "why": "intro"},
        {"part_id": "p2", "seconds": 30, "why": "deep"}]}}

DRAFT = {"total_s": 60, "scenes": [
    {"n": 1, "start_s": 0, "end_s": 30, "part_id": "p1",
     "role": "explain", "viewer_learns": "msg one",
     "screen_idea": "card", "narration_points": [],
     "materials": [], "handoff": [], "next_link": "then"},
    {"n": 2, "start_s": 30, "end_s": 60, "part_id": "p2",
     "role": "recap", "viewer_learns": "msg two",
     "screen_idea": "card", "narration_points": [],
     "materials": [], "handoff": [], "next_link": ""}],
    "unused_picks": []}

NARR = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 15,
     "lines": [{"text": "Alpha beta.", "citations": []}],
     "words": 2, "audio": {}, "attempts": 1},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 15, "end_s": 30,
     "lines": [{"text": "Second cut line.", "citations": []}],
     "words": 3, "audio": {}, "attempts": 1},
    {"cut_id": "s2c1", "scene_n": 2, "start_s": 30, "end_s": 60,
     "lines": [{"text": "Third cut speaks.", "citations": []}],
     "words": 3, "audio": {}, "attempts": 1}]}

BOARD = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 15,
     "show_what": "Show a card", "show_why": "Intro",
     "on_screen_text": ["Alpha"]},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 15, "end_s": 30,
     "show_what": "Show a chart", "show_why": "Proof",
     "on_screen_text": ["Numbers"]},
    {"cut_id": "s2c1", "scene_n": 2, "start_s": 30, "end_s": 60,
     "show_what": "Show recap", "show_why": "Close",
     "on_screen_text": ["Thanks"]}]}

GUIDE = {"palette": {"background": "#101418", "text": "#f5f2ea",
                     "accent": "#e0a458"},
         "fonts": {"heading": "sans", "body": "sans"},
         "image_tone": "plain", "rules": ["Keep it calm."]}

SHOT_IMG = "0123456789ab"

PHOTO = {"cuts": [
    {"cut_id": "s1c1", "decision": "use", "kind": "web",
     "ref": "pc://image/%s" % SHOT_IMG, "file": "pick.png",
     "source_url": "https://example.com/pic", "license": "CC0",
     "reason": "shows alpha"},
    {"cut_id": "s1c2", "decision": "use", "kind": "web",
     "ref": "pc://image/shot2", "file": "",
     "source_url": "https://example.com/pic2", "license": "CC-BY",
     "reason": "shows beta"},
    {"cut_id": "s2c1", "decision": "none",
     "reason": "no visual needed"}]}

GEN = {"cuts": [
    {"cut_id": "s1c1", "decision": "none"},
    {"cut_id": "s1c2", "decision": "none"},
    {"cut_id": "s2c1", "decision": "none"}],
    "images": []}

ANIM = {"cuts": [
    {"cut_id": "s1c1", "decision": "none"},
    {"cut_id": "s1c2", "decision": "none"},
    {"cut_id": "s2c1", "decision": "none"}]}

SLIDE = {"cuts": [
    {"cut_id": "s1c1", "start_s": 0, "end_s": 15,
     "preset": "main_side",
     "blocks": [{"kind": "photo",
                 "box": {"x": 64, "y": 64, "w": 560, "h": 400},
                 "reason": "shows alpha"}],
     "on_screen_text": ["Alpha"], "transitions": [],
     "why": "photo left"},
    {"cut_id": "s1c2", "start_s": 15, "end_s": 30,
     "preset": "full",
     "blocks": [{"kind": "text",
                 "box": {"x": 64, "y": 64, "w": 1152, "h": 200},
                 "reason": "caption"}],
     "on_screen_text": ["Numbers"], "transitions": [],
     "why": "text"},
    {"cut_id": "s2c1", "start_s": 30, "end_s": 60,
     "preset": "full",
     "blocks": [{"kind": "text",
                 "box": {"x": 64, "y": 64, "w": 1152, "h": 200},
                 "reason": "closing line"}],
     "on_screen_text": ["Thanks"], "transitions": [],
     "why": "text card"}]}

RLOG = {"cuts": [
    {"cut_id": "s1c1", "slide_file": "", "renders_n": 1,
     "adjustments": [{"field": "x", "was": 64, "now": 80}],
     "issues": []},
    {"cut_id": "s1c2", "slide_file": "", "renders_n": 1,
     "adjustments": [], "issues": []},
    {"cut_id": "s2c1", "slide_file": "", "renders_n": 1,
     "adjustments": [], "issues": []}]}

ASSEMBLY = {"segments": [
    {"cut_id": "s1c1", "at_s": 0, "dur_s": 15},
    {"cut_id": "s1c2", "at_s": 15, "dur_s": 15},
    {"cut_id": "s2c1", "at_s": 30, "dur_s": 30}],
    "total_s": 60}

FULL = [("pd_marty", {"structure": STRUCT}),
        ("plan_ash", {"storyboard_draft": DRAFT}),
        ("voice_wren", {"narration": NARR}),
        ("board_penn", {"storyboard": BOARD,
                        "style_guide": GUIDE}),
        ("photo_pia", {"photo_picks": PHOTO}),
        ("image_gene", {"gen_picks": GEN}),
        ("anim_max", {"anim_picks": ANIM}),
        ("board_vera", {"slide_draft": SLIDE}),
        ("slide_remy", {"render_log": RLOG}),
        ("video_production", {"video": {"file": "video.mp4"}})]

CLONE_NODES = ("photo_pia", "image_gene", "anim_max",
               "board_vera", "slide_remy")

APPROVED = [n for n, _c in FULL] + [
    "%s@p%d" % (n, no) for n in CLONE_NODES for no in (1, 2)]


ONEPX = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
         b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
         b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
         b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")

PCFIX = os.path.join(ROOT, "storage", "_pc", "image",
                     "entries", SHOT_IMG)


def make_fixture():
    shutil.rmtree(FIX, ignore_errors=True)
    shutil.rmtree(PCFIX, ignore_errors=True)
    os.makedirs(RUNS, exist_ok=True)
    for node, cats in FULL:
        wres(node, cats)
    fdir = os.path.join(PCFIX, "files")
    os.makedirs(fdir, exist_ok=True)
    with open(os.path.join(PCFIX, "entry.json"), "w",
              encoding="utf-8") as f:
        json.dump({"pc": "image", "doc_id": SHOT_IMG,
                   "ref": "pc://image/%s" % SHOT_IMG,
                   "file": "pick.png",
                   "source_url": "https://example.com/pic",
                   "license": "CC0"}, f)
    with open(os.path.join(fdir, "pick.png"), "wb") as f:
        f.write(ONEPX)
    sdir = os.path.join(FIX, "part_split")
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "split.json"), "w",
              encoding="utf-8") as f:
        json.dump({"version": 1, "parts": [
            {"no": 1, "part_id": "p1"},
            {"no": 2, "part_id": "p2"}]}, f)
    for node in CLONE_NODES:
        for no in (1, 2):
            pdir = os.path.join(FIX, node, "p%d" % no)
            os.makedirs(pdir, exist_ok=True)
            with open(os.path.join(pdir, "result.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"producer": "%s@p%d" % (node, no),
                           "categories": {}}, f)
    vdir = os.path.join(FIX, "video_production")
    with open(os.path.join(vdir, "assembly.json"), "w",
              encoding="utf-8") as f:
        json.dump(ASSEMBLY, f)
    with open(os.path.join(FIX, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"run_id": "boardshot1", "flow_id": "default",
                   "order_id": "ord-shot-001", "state": "done",
                   "approved": APPROVED}, f)
    with open(os.path.join(FIX, "events.jsonl"), "w",
              encoding="utf-8") as f:
        f.write('{"at": "09:00:01", "ev": "agent_start", '
                '"agent": "pd_marty"}\n')
        f.write('{"at": "09:00:05", "ev": "agent_done", '
                '"agent": "pd_marty"}\n')
        f.write('{"at": "09:00:06", "ev": "agent_start", '
                '"agent": "photo_pia@p1"}\n')
    _verify_files(os.path.join(FIX, "pd_marty"), "pd_marty",
                  None, True)
    _verify_files(os.path.join(FIX, "photo_pia", "p1"),
                  "photo_pia", 1, False)


def _wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _wjsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _verify_files(ndir, node, part, spec_ok):
    """J15 files: usage, events, inputs_log, inputs_check,
    reads_log. The pia clone fails one tool + the spec."""
    label = node if part is None else "%s@p%d" % (node, part)
    _wjson(os.path.join(ndir, "usage.json"),
           {"llm_calls": 2 if part is None else 1,
            "prompt_tokens": 100 if part is None else 10,
            "completion_tokens": 50 if part is None else 5})
    if part is None:
        _wjsonl(os.path.join(ndir, "events.jsonl"), [
            {"t": "09:00:02", "ev": "run_start",
             "agent": node},
            {"t": "09:00:03", "ev": "tool", "step": 1,
             "tool": "pc_read_source", "ok": True,
             "detail": "s1.1"},
            {"t": "09:00:04", "ev": "tool", "step": 2,
             "tool": "write_structure", "ok": True}])
        reads = [{"at": "2026-01-01T09:00:03",
                  "tool": "pc_read_source", "pc": "source",
                  "ref": "pc://source/shot#s1.1",
                  "section": "s1.1", "item": "",
                  "allowed": True, "reason": ""}]
    else:
        _wjsonl(os.path.join(ndir, "events.jsonl"), [
            {"t": "09:00:07", "ev": "tool", "step": 1,
             "tool": "pc_search_images", "ok": True,
             "detail": "alpha"},
            {"t": "09:00:08", "ev": "tool", "step": 2,
             "tool": "pc_pick_image", "ok": False,
             "error": "shot refusal"}])
        reads = [
            {"at": "2026-01-01T09:00:07",
             "tool": "pc_search_images", "pc": "image",
             "ref": "", "section": "", "item": "alpha",
             "allowed": True, "reason": ""},
            {"at": "2026-01-01T09:00:08",
             "tool": "pc_pick_image", "pc": "image",
             "ref": "pc://image/%s" % SHOT_IMG,
             "section": "", "item": "", "allowed": False,
             "reason": "shot refusal"}]
    _wjsonl(os.path.join(ndir, "reads_log.jsonl"), reads)
    _wjson(os.path.join(ndir, "inputs_log.json"),
           {"node": label, "order_id": "ord-shot-001",
            "run_id": "boardshot1",
            "received": [{"item": "request",
                          "category": "request",
                          "from": "sales_sam"}],
            "pc": [{"pc": "source", "kind": "full"}],
            "est_input_tokens": 1200, "sha1": "abc",
            "inputs_md_bytes": 10})
    _wjson(os.path.join(ndir, "inputs_check.json"),
           {"node": label, "spec": "expected_inputs.json",
            "ok": spec_ok,
            "missing": [] if spec_ok else ["concept"],
            "extra": [], "wrong_part": [],
            "wrong_kind": []})


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
    make_fixture()
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(),
                           "board_live_profile")
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
                    "('nav button[data-p=board]').click()")
        t0 = time.time()
        while time.time() - t0 < 30:
            n = js_eval(ws, "document.querySelectorAll"
                            "('#bd-table tbody tr').length")
            if n:
                break
            time.sleep(0.5)
        time.sleep(1)
        out = js_eval(ws, PROBE_JS)
        if out is None:
            detail = js_eval(ws, "(() => { try {"
                             " return document.getElementById"
                             "('p-board') ? 'board-dom-ok' :"
                             " 'no-board-dom'; } catch (e) {"
                             " return 'probe-threw: ' + e; } })()")
            print("probe detail: %s" % detail, flush=True)
        ok(out.get("tabActive") is True, "board tab activates")
        ok(out.get("pills") == 10,
           "10 stage pills (got %s)" % out.get("pills"))
        ok(out.get("rows") == 3,
           "3 cut rows (got %s)" % out.get("rows"))
        ok(out.get("cols") == 12,
           "12 columns (got %s)" % out.get("cols"))
        ok(out.get("group1") == "STORYBOARD TEAM"
           and out.get("group2") == "VIDEO TEAM",
           "group headers storyboard/video")
        ok("Click any cell" in (out.get("side") or ""),
           "side panel shows the hint")
        ok(out.get("scrollX") is False, "no page h-scroll")
        vp = out.get("viewport") or [0, 0]
        print("viewport: %sx%s" % (vp[0], vp[1]), flush=True)
        shot(ws, PNG1920)
        ok(os.path.isfile(PNG1920)
           and os.path.getsize(PNG1920) > 1000,
           "screenshot saved (%s)" % PNG1920)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 1280, "height": 720,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        out2 = js_eval(ws, PROBE_JS)
        ok(out2.get("rows") == 3 and out2.get("cols") == 12,
           "1280 view keeps 3 rows x 12 cols")
        shot(ws, PNG1280)
        ok(os.path.isfile(PNG1280)
           and os.path.getsize(PNG1280) > 1000,
           "screenshot saved (%s)" % PNG1280)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 1920, "height": 1080,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        ok(js_eval(ws, CLICK_PHOTO_JS) is True,
           "photo cell s1c1 found + clicked")
        time.sleep(1)
        out3 = js_eval(ws, PROBE_JS)
        ok(out3.get("sel") == "photo/s1c1",
           "clicked cell selected (%s)" % out3.get("sel"))
        title = js_eval(ws, SIDETITLE_JS)
        ok("Part 1" in (title or "")
           and "Scene 1" in (title or "")
           and "Cut 1" in (title or ""),
           "side panel titles the cut (%s)" % title)
        pp = js_eval(ws, PILLS_JS)
        ok(pp.get("pp") == 10,
           "video pills carry 2 part pills each (%s)" % pp)
        ok("P1" in pp.get("sample", "")
           and "P2" in pp.get("sample", ""),
           "part pills read P1/P2 (%s)" % pp.get("sample"))
        ok(js_eval(ws, CLICK_JS + '("slide_plan", "s1c1")')
           is True, "vera cell clicked")
        time.sleep(0.5)
        vc = js_eval(ws, SIDECARDS_JS)
        ok(vc.get("boxes") == 1
           and "SLIDE PLAN" in vc.get("cards", []),
           "vera minimap draws the block (%s/%s)"
           % (vc.get("boxes"), vc.get("cards")))
        ok(js_eval(ws, CLICK_JS + '("slide_build", "s1c1")')
           is True, "remy cell clicked")
        time.sleep(0.5)
        rc = js_eval(ws, SIDECARDS_JS)
        ok("x: 64 -> 80" in (rc.get("text") or ""),
           "remy render log shows the fix")
        ok(js_eval(ws, CLICK_JS + '("screen", "s1c1")')
           is True, "screen cell clicked")
        time.sleep(0.5)
        sc = js_eval(ws, SIDECARDS_JS)
        ok("#e0a458" in (sc.get("text") or "").lower()
           or "e0a458" in (sc.get("text") or ""),
           "screen card shows the style guide")
        ok(js_eval(ws, CLICK_JS + '("photo", "s1c1")')
           is True, "photo cell re-clicked for the shot")
        time.sleep(0.5)
        thumbs = js_eval(ws, "(() => ({cell: document."
                         "querySelectorAll('#bd-table "
                         "td[data-col=\"photo\"] img').length,"
                         " side: document.querySelectorAll("
                         "'#bd-side .bd-gal img').length}))()")
        ok(thumbs.get("cell", 0) >= 1
           and thumbs.get("side", 0) >= 1,
           "photo thumbnails in cell + gallery (%s)" % thumbs)
        shot(ws, PNGCELL)
        ok(os.path.isfile(PNGCELL)
           and os.path.getsize(PNGCELL) > 1000,
           "screenshot saved (%s)" % PNGCELL)
        vurl = ("http://127.0.0.1:%d/api/flows/runs/boardshot1"
                "/verify?node=photo_pia&part=1" % SERVER_PORT)
        with urllib.request.urlopen(vurl, timeout=10) as r:
            vpay = json.load(r)
        ok(vpay.get("ok") is True and vpay.get("clone") ==
           "photo_pia@p1" and vpay["spec"]["ok"] is False
           and len(vpay["events"]) == 3
           and sum(1 for e in vpay["events"]
                   if e.get("ev") == "tool"
                   and e.get("phrase")) == 2,
           "verify endpoint: clone/spec/events/phrases")
        furl = ("http://127.0.0.1:%d/api/flows/runs/boardshot1"
                "/files" % SERVER_PORT)
        with urllib.request.urlopen(furl, timeout=10) as r:
            fbody = r.read().decode("utf-8", "replace")
        ok(r.status == 200 and "STATUS.json" in fbody
           and "photo_pia/p1/events.jsonl" in fbody,
           "files endpoint lists the run folder")
        time.sleep(1)
        vc2 = js_eval(ws, SIDECARDS_JS)
        for want in ("INPUTS RECEIVED", "PC READS",
                     "SPEC CHECK", "EVENTS", "COST & TIME"):
            ok(want in vc2.get("cards", []),
               "side shows %s (%s)"
               % (want, vc2.get("cards")))
        ok("REFUSED" in (vc2.get("text") or "")
           and "shot refusal" in (vc2.get("text") or ""),
           "refused read shown red with the reason")
        ok("differs from spec" in (vc2.get("text") or "")
           and "concept" in (vc2.get("text") or ""),
           "spec failure shown with the missing item")
        ok("3 events" in (vc2.get("text") or ""),
           "events card merges node + run rows")
        sc2 = js_eval(ws, SIDECLONE_JS)
        ok(sc2.get("clone") == "photo_pia@p1"
           and sc2.get("allParts") is True,
           "clone cell shows its id + All parts (%s)" % sc2)
        sm = js_eval(ws, SUMMARY_JS)
        ok("done" in (sm.get("text") or "")
           and "Errors: 1" in (sm.get("text") or "")
           and "Spec failures: 1" in (sm.get("text") or "")
           and "3 calls" in (sm.get("text") or "")
           and (sm.get("href") or "").endswith(
               "api/flows/runs/boardshot1/files"),
           "summary bar state/errors/spec/cost/link (%s)"
           % sm.get("text"))
        ok(js_eval(ws, CLICK_HL_JS + '("bd-hl-err")') is True,
           "errors count clicked")
        time.sleep(0.5)
        ok(js_eval(ws, HLCOUNT_JS) >= 1,
           "error cells highlighted")
        ok(js_eval(ws, CLICK_HL_JS + '("bd-hl-spec")')
           is True, "spec count clicked")
        time.sleep(0.5)
        ok(js_eval(ws, HLCOUNT_JS) >= 1,
           "spec cells highlighted")
        ok(js_eval(ws, CLICK_HL_JS + '("bd-hl-spec")')
           is True, "spec count clicked again")
        time.sleep(0.5)
        ok(js_eval(ws, HLCOUNT_JS) == 0,
           "highlight toggles off")
        vv = js_eval(ws, VALL_JS + "(true)")
        ok(vv.get("has") is True, "all-parts toggle present")
        time.sleep(1.5)
        cols = js_eval(ws, "Array.from(document.querySelectorAll"
                           "('#bd-side .bd-vcols > div > b'))"
                           ".map(b => b.textContent)")
        ok(cols == ["photo_pia@p1", "photo_pia@p2"],
           "all parts shown side by side (%s)" % cols)
        js_eval(ws, VALL_JS + "(false)")
        time.sleep(1.5)
        shot(ws, PNGVERIFY)
        ok(os.path.isfile(PNGVERIFY)
           and os.path.getsize(PNGVERIFY) > 1000,
           "screenshot saved (%s)" % PNGVERIFY)
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844,
                 "deviceScaleFactor": 1, "mobile": False})
        time.sleep(1)
        nar = js_eval(ws, NARROW_JS)
        ok(nar is not None
           and nar["sideTop"] >= nar["wrapBottom"] - 2,
           "390px: side panel drops under the table (%s)"
           % nar)
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "zero console errors (got %d)" % nerr)
    finally:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        stop_proc(server, "server")
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(FIX, ignore_errors=True)
        shutil.rmtree(PCFIX, ignore_errors=True)
    if not fails:
        empty_phase()
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


def empty_phase():
    """Board against an empty runs folder: headers + grey row."""
    empty_runs = os.path.join(tempfile.gettempdir(),
                              "board_empty_runs")
    shutil.rmtree(empty_runs, ignore_errors=True)
    os.makedirs(empty_runs)
    server, edge, ws = None, None, None
    profile = os.path.join(tempfile.gettempdir(),
                           "board_empty_profile")
    shutil.rmtree(profile, ignore_errors=True)
    try:
        logf = open(SERVER_LOG, "w", encoding="utf-8")
        env = dict(os.environ)
        env["SHOESTRING_RUNS_DIR"] = empty_runs
        server = subprocess.Popen(
            [sys.executable, "scripts/server.py",
             "--port", str(SERVER_PORT)],
            cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT,
            env=env)
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
            ok(False, "empty-phase server answers")
            return
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/flows/runs"
                % SERVER_PORT, timeout=10) as r:
            runs = json.load(r)
        ok(runs.get("runs") == [], "empty runs list")
        edge = subprocess.Popen(
            _browser.launch_args(CDP_PORT, profile, 1280, 720))
        t0 = time.time()
        targets = None
        while time.time() - t0 < 40:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/json/list"
                        % CDP_PORT, timeout=3) as r:
                    targets = json.load(r)
                if targets:
                    break
            except OSError:
                time.sleep(1)
        if not targets:
            ok(False, "empty-phase edge cdp answers")
            return
        page = next((t for t in targets
                     if t.get("type") == "page"), None)
        if page is None:
            ok(False, "empty-phase page target found")
            return
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
        js_eval(ws, "document.querySelector"
                    "('nav button[data-p=board]').click()")
        t0 = time.time()
        while time.time() - t0 < 30:
            n = js_eval(ws, "document.querySelectorAll"
                            "('#bd-table tr.bd-emptyrow td')"
                            ".length")
            if n:
                break
            time.sleep(0.5)
        time.sleep(1)
        out = js_eval(ws, EMPTY_JS)
        ok(out.get("cols") == 12,
           "empty state keeps 12 columns (%s)"
           % out.get("cols"))
        ok(out.get("group1") == "STORYBOARD TEAM"
           and out.get("group2") == "VIDEO TEAM",
           "empty state keeps group headers")
        ok("No runs yet" in (out.get("empty") or "")
           and "Order tab" in (out.get("empty") or ""),
           "empty grey row text")
        ok("no runs" in (out.get("picker") or ""),
           "run picker says no runs")
        stext = js_eval(ws, "document.getElementById('bd-sum')"
                            ".textContent")
        ok("No runs yet" in (stext or ""),
           "summary says no runs yet")
        shot(ws, PNGEMPTY)
        ok(os.path.isfile(PNGEMPTY)
           and os.path.getsize(PNGEMPTY) > 1000,
           "screenshot saved (%s)" % PNGEMPTY)
        ws.call("Runtime.disable")
        nerr = console_errors(ws.events)
        ok(nerr == 0, "empty state: zero console errors "
           "(got %d)" % nerr)
    finally:
        if ws is not None:
            ws.close()
        _browser.stop_tree(edge, "edge")
        stop_proc(server, "server")
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(empty_runs, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
