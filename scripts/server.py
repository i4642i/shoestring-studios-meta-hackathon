"""Shoestring Studios site server (stdlib + nextop): the homepage, Sam's order chat and the live Studio.

  python scripts/server.py [--port 8000]

Production runs are nextop runs of this project (flows/main.json), started in the background like
`nextop studio` does: python -m nextop run . --flow main --run-id <order id> --input orders/<id>/input.json
Everything read from run records goes through scripts/site_runs.py.
"""

from __future__ import annotations

import argparse
import atexit
import json
import mimetypes
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))     # the project: tools/_orders.py

import intake_muse as intake  # noqa: E402
from tools import _orders as orders  # noqa: E402
import platform_page  # noqa: E402
import site_runs as sr  # noqa: E402

ROOT = sr.ROOT
ORDERS = ROOT / "orders"
SETTINGS = ROOT / "data" / "settings.json"
ORDER_ID_RE = re.compile(r"^ord-[0-9]{8}-[0-9]{3}$")
MAX_PDF_BYTES = 40 * 1024 * 1024
STUDIO_URL = "http://127.0.0.1:8775/"
SITE_URL = "http://127.0.0.1:8000/"   # this server's own address (set in main); Sam's finalize_and_send calls it
CHANNEL = "Shoestring Studios"
CLOSING = "Thanks for watching"
_LOCK = threading.Lock()
_PROCS: dict[str, subprocess.Popen] = {}


# ------------------------------------------------------------------ small helpers
def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def read_json(p: pathlib.Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: pathlib.Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def settings() -> dict:
    s = read_json(SETTINGS, {}) or {}
    return {"office_fps": int(s.get("office_fps") or 20), "step_new_orders": bool(s.get("step_new_orders")),
            "studio_url": "/"}     # the platform tabs are served here, at the site root


def save_settings(**kw) -> dict:
    s = read_json(SETTINGS, {}) or {}
    s.update(kw)
    write_json(SETTINGS, s)
    return settings()


def tail_jsonl(p: pathlib.Path, n: int) -> list[dict]:
    try:
        lines = p.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


# ------------------------------------------------------------------ orders on disk
def order_dir(oid: str) -> pathlib.Path | None:
    if not ORDER_ID_RE.match(oid or ""):
        return None
    d = ORDERS / oid
    return d if (d / "meta.json").is_file() else None


def meta_of(d: pathlib.Path) -> dict:
    return read_json(d / "meta.json", {}) or {}


def save_meta(d: pathlib.Path, meta: dict) -> None:
    write_json(d / "meta.json", meta)


def log_event(oid: str, source: str, ev: str, summary: str, **kw) -> None:
    d = ORDERS / oid
    row = {"at": now_iso(), "source": source, "ev": ev, "summary": summary}
    row.update(kw)
    with _LOCK, open(d / "timeline.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def form_of(d: pathlib.Path) -> dict:
    return orders.form_of(d)


def save_form(d: pathlib.Path, fields: dict) -> dict:
    return orders.save_form(d, fields)


def missing_of(d: pathlib.Path) -> list[str]:
    form = form_of(d)
    miss = [k for k in intake.FORM_FIELDS if not form.get(k, "").strip()]
    if not (meta_of(d).get("files") or {}).get("source"):
        miss.append("source PDF")
    return miss


# Chat history sent to the LLM (ORDER with Sam and the OFFICE crew chat alike): the last CHAT_HISTORY
# earlier messages (owner's and the crew member's together), each cut at CHAT_MSG_CHARS characters.
CHAT_HISTORY = 20
CHAT_MSG_CHARS = 3000


def transcript(d: pathlib.Path) -> list[dict]:
    """Chat turns as LLM messages (oldest first): the last CHAT_HISTORY messages, each cut at CHAT_MSG_CHARS."""
    turns = []
    for t in tail_jsonl(d / "chat.jsonl", 200):
        if t.get("user"):
            turns.append({"role": "user", "content": t["user"][:CHAT_MSG_CHARS]})
        if t.get("reply"):
            turns.append({"role": "assistant", "content": t["reply"][:CHAT_MSG_CHARS]})
    return turns[-CHAT_HISTORY:]


def chat_append(d: pathlib.Path, user: str, reply: str) -> None:
    with open(d / "chat.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"user": user, "reply": reply, "at": now_iso()}, ensure_ascii=False) + "\n")


def order_of_run() -> dict[str, str]:
    out = {}
    for p in ORDERS.glob("ord-*/meta.json") if ORDERS.is_dir() else []:
        m = read_json(p, {}) or {}
        if m.get("run_id"):
            out[m["run_id"]] = p.parent.name
    return out


# ------------------------------------------------------------------ runs (processes)
def _python() -> str:
    return sys.executable


def spawn_nextop(run_id: str, args: list[str]) -> subprocess.Popen:
    """Start `python -m nextop <args>` in the background (output to runs/.shoestring/<id>.log)."""
    with _LOCK:
        for rid, p in list(_PROCS.items()):
            if p.poll() is None:
                raise RuntimeError("run %s is still going; stop or pause it in Studio first" % rid)
        for r in sr.runs_list():
            if r["state"] in ("running", "pausing") and r["run_id"] != run_id:
                raise RuntimeError("run %s is still going; stop or pause it in Studio first" % r["run_id"])
        sr.SITE.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        log = open(sr.SITE / f"{run_id}.log", "a", encoding="utf-8")
        log.write("\n$ nextop " + " ".join(args) + "  (" + now_iso() + ")\n")
        log.flush()
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        p = subprocess.Popen([_python(), "-m", "nextop"] + args, cwd=str(ROOT), env=env, stdout=log,
                             stderr=subprocess.STDOUT, creationflags=flags,
                             start_new_session=(os.name != "nt"))
        _PROCS[run_id] = p
        sr.set_site_note(run_id, pid=p.pid, started=time.time(), kind=args[0], paused=False, pausing=False)
        return p


# ------------------------------------------------------------------ learning across orders
LEARN_EVERY = 30            # seconds between looks at the runs
_SEEN_UNFINISHED: set[str] = set()
_LEARN_LOCK = threading.Lock()


def _learn(run_id: str) -> None:
    import learn_run
    log_p = sr.SITE / ("learn-%s.log" % run_id)
    sr.SITE.mkdir(parents=True, exist_ok=True)
    with _LEARN_LOCK, open(log_p, "a", encoding="utf-8") as log:
        def say(msg):
            log.write(msg + "\n")
            log.flush()
        say("== %s learning run %s" % (now_iso(), run_id))
        try:
            learn_run.learn(run_id, ROOT, log=say)
        except Exception as e:
            say("[error] %s: %s" % (type(e).__name__, e))


def learn_watch() -> None:
    """When a run this server saw unfinished becomes done, learn it once (scripts/learn_run.py) in the
    background. Runs that finished before the server started are learned by hand: python scripts/learn_run.py <id>."""
    while True:
        try:
            for r in sr.runs_list():
                rid = r["run_id"]
                st = read_json(sr.run_dir(rid) / "status.json", {}) or {}
                if st.get("status") != "done":
                    _SEEN_UNFINISHED.add(rid)
                elif rid in _SEEN_UNFINISHED:
                    _SEEN_UNFINISHED.discard(rid)      # one try per server life; retry by hand
                    if (read_json(sr.run_dir(rid) / "learned.json", {}) or {}).get("status") != "done":
                        threading.Thread(target=_learn, args=(rid,), name="learn-" + rid, daemon=True).start()
        except Exception:
            traceback.print_exc()
        time.sleep(LEARN_EVERY)


def run_log_errors(run_id: str) -> str:
    """The [error] lines of the last nextop call in runs/.shoestring/<id>.log (or its last lines)."""
    try:
        text = (sr.SITE / f"{run_id}.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "no log"
    last = text.rsplit("\n$ nextop ", 1)[-1].splitlines()[1:]
    errs = [ln.replace("[error] ", "") for ln in last if ln.startswith("[error]")]
    return "; ".join(errs or last[-3:])[:400] or "no output"


def stop_run(run_id: str, pause: bool) -> dict:
    note = sr.site_note(run_id)
    pid = note.get("pid")
    if not sr.pid_alive(pid):
        raise RuntimeError("nothing is running for run %s" % run_id)
    sr.set_site_note(run_id, pausing=pause)
    sr.kill_tree(pid)
    p = _PROCS.get(run_id)
    if p is not None:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
    d = sr.run_dir(run_id)
    st = read_json(d / "status.json", {}) or {}
    if st.get("status") == "running":
        # same as `nextop studio` STOP: the killed process could not close its record
        st.update(status="stopped", running=[], ended=time.time(),
                  reason=("paused from the Shoestring site" if pause else "stopped from the Shoestring site"))
        write_json(d / "status.json", st)
        with open(d / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "event": "run_stopped", "by": "shoestring site",
                                "pause": pause}) + "\n")
    sr.set_site_note(run_id, paused=pause, pausing=False)
    oid = order_of_run().get(run_id)
    if oid:
        log_event(oid, "studio", "paused" if pause else "stopped", "run %s %s" % (run_id, "paused" if pause else "stopped"))
    return sr.run_state(run_id)


def resume_run(run_id: str) -> dict:
    p = spawn_nextop(run_id, ["resume", run_id, "--project", str(ROOT)])
    try:
        code = p.wait(timeout=6)            # a resume that cannot start ends within seconds
    except subprocess.TimeoutExpired:
        code = None
    if code not in (None, 0):
        raise RuntimeError("resume failed: " + run_log_errors(run_id))
    oid = order_of_run().get(run_id)
    if oid:
        log_event(oid, "studio", "resumed", "run %s resumed" % run_id)
    return sr.run_state(run_id)


def approve_reviews(run_id: str) -> dict:
    from nextop.runtime.flow import FlowError, decide_review
    st = read_json(sr.run_dir(run_id) / "status.json", {}) or {}
    waiting = list(st.get("review") or [])
    if not waiting:
        raise RuntimeError("no block of run %s is waiting for review" % run_id)
    for b in waiting:
        try:
            decide_review(sr.run_dir(run_id), b, "approve")
        except FlowError as e:
            raise RuntimeError(str(e)) from None
    return resume_run(run_id)


# ------------------------------------------------------------------ order start pipeline
def flow_input(d: pathlib.Path, title: str) -> dict:
    form = form_of(d)
    mins = orders.parse_minutes(form["length"])
    mins = min(max(mins if mins is not None else 5.0, orders.MIN_MINUTES), orders.MAX_MINUTES)
    words = ("Audience: %s. Target length: %s. Depth: %s. Theme direction: %s."
             % (form["audience"], form["length"], form["depth"], form["theme"]))
    return {"order": words, "audience": form["audience"], "length_min": round(mins, 2),
            "depth": orders.depth_value(form["depth"]) or "key_points", "theme": form["theme"], "voice": "draft",
            "video_title": title, "subtitle": "", "closing": CLOSING, "channel": CHANNEL,
            "pdf": str((d / "source.pdf").resolve()), "book_title": title}


def report_md(oid: str, form: dict, pdf_name: str, inp: dict | None) -> str:
    lines = ["# Production request %s" % oid, "", "## Client answers", ""]
    for k in intake.FORM_FIELDS:
        lines.append("- %s: %s" % (intake.FORM_LABELS[k], form.get(k) or "—"))
    lines.append("- Source PDF: %s" % (pdf_name or "—"))
    if inp:
        lines += ["", "## Flow input (input.json, read by the start worker Sam)", "", "```json",
                  json.dumps(inp, ensure_ascii=False, indent=1), "```"]
    return "\n".join(lines) + "\n"


def _book_title(pdf: pathlib.Path, upload_name: str) -> tuple[str, int]:
    title, pages = "", 0
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        pages = doc.page_count
        title = str((doc.metadata or {}).get("title") or "").strip()
    except Exception:  # noqa: BLE001 - title is optional
        pass
    if not title or len(title) < 4 or title.lower().startswith(("microsoft", "untitled")):
        stem = pathlib.Path(upload_name or pdf.name).stem
        title = re.sub(r"[_-]+", " ", stem).strip() or "Document"
    return title[:120], pages


def start_pipeline(oid: str) -> None:
    """Background: flow input (form + the PDF path) -> nextop run. The run's parser block reads the PDF."""
    d = ORDERS / oid
    try:
        meta = meta_of(d)
        files = meta.get("files") or {}
        title, _pages = _book_title(d / "source.pdf", files.get("upload_name", ""))
        inp = flow_input(d, title)
        write_json(d / "input.json", inp)
        (d / "report.md").write_text(report_md(oid, form_of(d), files.get("upload_name", ""), inp), encoding="utf-8")
        log_event(oid, "order", "start", "starting the crew flow (run %s)" % oid)
        args = ["run", str(ROOT), "--flow", "main", "--run-id", oid, "--input", str(d / "input.json")]
        if settings()["step_new_orders"]:
            args.append("--step")
        p = spawn_nextop(oid, args)
        log_event(oid, "order", "start", "waiting for the run record")
        t0 = time.time()
        while time.time() - t0 < 60 and not (sr.run_dir(oid) / "status.json").is_file():
            if p.poll() is not None:
                raise RuntimeError("the crew flow did not start: " + run_log_errors(oid))
            time.sleep(0.5)
        meta = meta_of(d)
        meta.pop("starting", None)
        meta.update(status="in_production", run_id=oid, started=now_iso())
        save_meta(d, meta)
        result = start_result(oid, d)
        write_json(d / "start_result.json", result)
    except Exception as e:  # noqa: BLE001 - shown on the order card
        reason = str(e) or type(e).__name__
        traceback.print_exc()
        log_event(oid, "order", "failed", reason[:300])
        meta = meta_of(d)
        meta.pop("starting", None)
        meta.update(status="consulting", start_failed=reason[:300])
        save_meta(d, meta)


def start_result(oid: str, d: pathlib.Path) -> dict:
    meta = meta_of(d)
    inp = read_json(d / "input.json", {}) or {}
    rmd = (d / "report.md").read_text(encoding="utf-8") if (d / "report.md").is_file() else ""
    return {"ok": True, "handed_over": True, "intake": inp, "report_md": rmd,
            "files": ["form.json", "input.json", "report.md"], "form": form_of(d),
            "answers": form_of(d), "stages": stages(oid), "run_id": meta.get("run_id", "")}


def stages(oid: str) -> list[str]:
    return ["a) request form filled in chat (audience, length, depth, theme)",
            "b) the run's parser block reads the PDF (orders/%s/source.pdf) into source files for the Source PC" % oid,
            "c) crew flow started: nextop run --flow main --run-id %s" % oid]


def handover(oid: str, d: pathlib.Path) -> tuple[bool, object]:
    """Sam's finalize_and_send: code checks readiness, then the start runs in the background."""
    meta = meta_of(d)
    if meta.get("status") in intake.STARTED:
        return False, "already started"
    if meta.get("starting"):
        return True, dict(start_result(oid, d), starting=True)
    miss = missing_of(d)
    if miss:
        return False, {"where": "finalize_and_send", "now": "missing: " + ", ".join(miss),
                       "change_to": "ask the client for the missing items first (PDF: the Attach PDF button)",
                       "why": "the crew needs all four answers and the source PDF"}
    meta["starting"] = {"at": now_iso()}
    meta.pop("start_failed", None)
    save_meta(d, meta)
    log_event(oid, "sam", "start", "request handed over")
    (d / "report.md").write_text(report_md(oid, form_of(d), (meta.get("files") or {}).get("upload_name", ""), None),
                                 encoding="utf-8")
    log_event(oid, "sam", "done", "request written from the form")
    threading.Thread(target=start_pipeline, args=(oid,), daemon=True).start()
    out = start_result(oid, d)
    return True, out


def progress_rows(d: pathlib.Path, since: str) -> list[dict]:
    since = since.replace("T", " ")
    rows = []
    for r in tail_jsonl(d / "timeline.jsonl", 200):
        r = dict(r, at=str(r.get("at", "")).replace("T", " "))
        if r["at"] >= since:
            rows.append(r)
    return rows


# ------------------------------------------------------------------ Studio chat with a crew member
ASK_TIMEOUT = 600   # seconds one question to a worker may take


def main_worker(c: dict) -> str:
    """The worker a crew member speaks as: the first of their blocks that is a worker folder ('' for none)."""
    for b in c.get("blocks", []):
        if (ROOT / "workers" / b / "worker.json").is_file():
            return b
    return ""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def clean_reply(text: str) -> str:
    """A worker's answer as chat text: no thinking block, no imitated control or function blocks."""
    return intake.clean_chat_reply(_THINK_RE.sub("", text or ""))


def crew_chat(cid: str, body: dict) -> str:
    """One reply from a crew member: nextop's question mode (`nextop ask`: the worker's persona, tools and domain
    knowledge, recorded as runs/chat-.../)."""
    c = next((x for x in sr.load_crew() if x["id"] == cid), None)
    if not c:
        raise RuntimeError("no such crew member: " + cid)
    msgs = [m for m in (body.get("messages") or []) if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)][-(CHAT_HISTORY + 1):]   # earlier messages + this question
    if not msgs or msgs[-1]["role"] != "user":
        raise RuntimeError("need {messages: [...]} ending with your message")
    worker = main_worker(c)
    if not worker:
        raise RuntimeError("%s has no worker to answer as" % c["name"])
    text, _rid = ask_worker(worker, c["name"], ask_question(c, msgs, str(body.get("run_id") or "")),
                            log={"crew": c["id"], "order_run": str(body.get("run_id") or ""),
                                 "question": msgs[-1]["content"]})
    return clean_reply(text) or "(no reply)"


def ask_question(c: dict, msgs: list[dict], rid: str) -> str:
    """The question text: which order is meant (the selected run), the chat so far, then the question."""
    lines = ["The studio owner is asking you a question in the Studio chat of Shoestring Studios. "
             "Answer in plain English, briefly (a few sentences), as yourself."]
    if rid and sr.run_ok(rid):
        st = read_json(sr.run_dir(rid) / "status.json", {}) or {}
        lines.append("The order meant is run %s (\"%s\", status %s). Notes you learned from finished orders are "
                     "titled with their run id in your domain knowledge, if you have any for it."
                     % (rid, sr.run_title(rid), st.get("status", "unknown")))
    else:
        lines.append("No order is selected.")
    if len(msgs) > 1:
        lines.append("\nThe chat so far:")
        for m in msgs[:-1]:
            who = "Owner" if m["role"] == "user" else c["name"]
            lines.append("%s: %s" % (who, m["content"][:CHAT_MSG_CHARS]))
    lines.append("\nQuestion: " + msgs[-1]["content"])
    return "\n".join(lines)


def ask_worker(worker: str, who: str, question: str, history: list[dict] | None = None,
               log: dict | None = None) -> tuple[str, str]:
    """`nextop ask <worker> @question [--history FILE]` in a child process. Returns (answer text, ask run id).
    The child gets this server's address (SHOESTRING_SITE_URL) for tools that call the site (finalize_and_send)."""
    run_id = "chat-%s-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), worker, os.urandom(2).hex())
    qdir = sr.SITE / "ask"
    qdir.mkdir(parents=True, exist_ok=True)
    qfile = qdir / (run_id + ".txt")
    qfile.write_text(question, encoding="utf-8")
    cmd = [_python(), "-m", "nextop", "ask", "--project", str(ROOT), "--run-id", run_id, worker, "@" + str(qfile)]
    if history:
        hfile = qdir / (run_id + ".history.json")
        write_json(hfile, history)
        cmd += ["--history", str(hfile)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **{orders.SITE_URL_ENV: SITE_URL})
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=ASK_TIMEOUT)
        out = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        raise RuntimeError("%s took longer than %d s to answer (run %s)" % (who, ASK_TIMEOUT, run_id))
    from nextop import records
    rd = sr.run_dir(run_id)
    ans = records.load_run(rd).output(worker) if rd.is_dir() else None
    text = ((ans or {}).get("answer") or {}).get("answer") if isinstance(ans, dict) else None
    with open(qdir / "chat_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(log or {}, at=now_iso(), worker=worker, run_id=run_id, answer=text or "",
                                seconds=round(time.time() - t0, 1)), ensure_ascii=False) + "\n")
    if not text:
        st = read_json(rd / "status.json", {}) or {}
        why = st.get("reason") or "; ".join(ln for ln in out.splitlines() if "[error]" in ln) or out[-300:]
        raise RuntimeError("%s could not answer (run %s): %s" % (who, run_id, str(why)[:400]))
    return text, run_id


def order_question(oid: str, d: pathlib.Path, last: str, mode: str) -> str:
    """The ORDER chat question for Sam: the order id, the current form, the PDF, the chat mode, the client's words."""
    files = meta_of(d).get("files") or {}
    pdf = ("attached: %s (%d bytes)" % (files.get("upload_name") or "source.pdf", files.get("bytes", 0))
           if files.get("source") else "none attached yet")
    lines = ["[ORDER CONSULTATION] You are consulting a client in the order chat of the Shoestring Studios site.",
             "Order id: %s (pass it to your tools)." % oid,
             "Current form: " + json.dumps(form_of(d), ensure_ascii=False),
             "Missing (decided by the site): " + (", ".join(missing_of(d)) or "nothing"),
             "Source PDF: " + pdf + ".",
             ("Guided mode: keep questions short; the client may also fill the form by hand."
              if mode != "free" else "Free mode: the client talks freely; you fill the form."),
             "Reply to the client in chat text only (a few sentences, English).",
             "",
             "Client: " + last]
    return "\n".join(lines)



# ------------------------------------------------------------------ multipart
def parse_multipart(headers, body: bytes) -> dict[str, tuple[str, bytes]]:
    ctype = headers.get("Content-Type", "")
    msg = BytesParser(policy=email_policy).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    out = {}
    if not msg.is_multipart():
        return out
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            out[name] = (part.get_filename() or "", part.get_payload(decode=True) or b"")
    return out


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "Shoestring/2"
    _body = b""

    def log_message(self, *a):
        pass

    # -- plumbing
    def _send(self, code: int, data: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _err(self, code: int, msg: str, **kw):
        self._json(code, dict({"error": msg}, **kw))

    def _slurp(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._body = self.rfile.read(n) if n > 0 else b""

    def _jbody(self) -> dict:
        try:
            v = json.loads(self._body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return v if isinstance(v, dict) else {}

    def _parts(self) -> list[str]:
        return [p for p in unquote(self.path.split("?", 1)[0]).split("/") if p]

    def _query(self) -> dict:
        return dict(parse_qsl(self.path.split("?", 1)[1])) if "?" in self.path else {}

    def _file(self, p: pathlib.Path, ctype: str | None = None):
        """Serve a file with Range support (video seeking)."""
        try:
            size = p.stat().st_size
        except OSError:
            return self._err(404, "not found")
        ctype = ctype or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        start, end, code = 0, size - 1, 200
        if m and size:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2) or 0))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        if ctype.startswith("text/html"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

    def _static(self, parts: list[str]):
        if not parts:
            parts = ["index.html"]
        if any(p.startswith(".") for p in parts) or parts[0] in ("orders", "runs", "data", "scripts", "workers",
                                                                     "functions", "tools", "adapters", "inputs"):
            return self._err(403, "forbidden")
        full = (ROOT / pathlib.Path(*parts)).resolve()
        if ROOT not in full.parents or not full.is_file():
            return self._err(404, "not found")
        return self._file(full)

    def _guard(self, fn, *a):
        try:
            return fn(*a)
        except RuntimeError as e:
            return self._err(409, str(e))
        except Exception as e:  # noqa: BLE001 - reported to the page
            traceback.print_exc()
            return self._err(500, "%s: %s" % (type(e).__name__, e))

    # -- verbs
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self._is_proxy():
            return self._guard(self._proxy)
        self._guard(self._get, self._parts())

    def do_POST(self):
        self._slurp()
        if self._is_proxy():
            return self._guard(self._proxy)
        self._guard(self._post, self._parts())

    def do_PUT(self):
        self._slurp()
        if self._is_proxy():
            return self._guard(self._proxy)
        self._guard(self._put, self._parts())

    def do_DELETE(self):
        if self._is_proxy():
            self._slurp()
            return self._guard(self._proxy)
        self._err(405, "read only here: manage the crew in the WORKERS tab")

    # -- platform page (the nextop studio page + ORDER / STUDIO) and its studio calls
    def _is_proxy(self) -> bool:
        return self.path.startswith("/" + platform_page.API_PREFIX)

    def _proxy(self):
        """Forward /nx/api/<rest> to <studio>/api/<rest> (same method, query and body)."""
        url = STUDIO_URL + "api/" + self.path[len("/" + platform_page.API_PREFIX):]
        headers = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "accept")}
        data = self._body if self.command in ("POST", "PUT", "DELETE") else None
        req = urllib.request.Request(url, data=data, method=self.command, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            resp = e
        except (urllib.error.URLError, OSError) as e:
            return self._err(502, "nextop studio is not reachable at %s (%s); start it with start_server.bat"
                             % (STUDIO_URL, getattr(e, "reason", e)))
        with resp:
            raw = resp.read()
            self._send(resp.status if hasattr(resp, "status") else resp.code, raw,
                       resp.headers.get("Content-Type") or "application/octet-stream")

    def _platform(self):
        try:
            html = platform_page.compose(STUDIO_URL)
        except ValueError as e:
            return self._err(500, str(e))
        return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    # -- routes
    def _get(self, p):
        if not p:
            return self._platform()
        if p[:1] != ["api"]:
            return self._static(p)
        r = p[1:]
        if r == ["crew"]:
            return self._json(200, self.crew_list())
        if len(r) == 2 and r[0] == "crew":
            c = next((x for x in self.crew_list() if x["id"] == r[1]), None)
            return self._json(200, c) if c else self._err(404, "no such employee")
        if r == ["settings"]:
            return self._json(200, settings())
        if r == ["version"]:
            return self._json(200, {"stale": False, "server": "shoestring-2"})
        if r == ["orders"]:
            return self._json(200, {"orders": self.orders_list()})
        if len(r) >= 2 and r[0] == "orders":
            d = order_dir(r[1])
            if not d:
                return self._err(404, "no such order")
            if len(r) == 2:
                return self._json(200, self.order_get(r[1], d))
            if r[2:] == ["progress"]:
                return self._json(200, self.order_progress(r[1], d))
            if r[2:] == ["projectlog"]:
                return self._send(200, self.projectlog(r[1], d).encode("utf-8"), "text/plain; charset=utf-8")
        if r == ["gallery"]:
            return self._json(200, {"cards": sr.gallery_cards(order_of_run())})
        if r == ["flows", "runs"]:
            return self._json(200, {"runs": sr.runs_list()})
        if len(r) == 4 and r[:2] == ["flows", "runs"]:
            rid = r[2]
            if not sr.run_ok(rid):
                return self._err(404, "no such run")
            if r[3] == "state":
                return self._json(200, dict(sr.run_state(rid), pause_each_stage=settings()["step_new_orders"]))
            if r[3] == "office":
                return self._json(200, sr.office(rid))
            if r[3] == "memory":
                return self._json(200, {"closed": False, "agents": {}})
        if len(r) >= 3 and r[0] == "runs" and sr.run_ok(r[1]):
            rid = r[1]
            if r[2] == "video":
                v = sr.video_path(rid)
                return self._file(v, "video/mp4") if v else self._err(404, "no video yet")
            if r[2] == "thumb":
                t = sr.thumb_path(rid)
                return self._file(t, "image/jpeg") if t else self._err(404, "no thumbnail")
            if r[2] == "events":
                return self._send(200, self.run_log(rid).encode("utf-8"), "text/plain; charset=utf-8")
            if r[2] == "fs" and len(r) == 5:
                f = sr.pc_item_file(rid, r[3], r[4])
                if not f:
                    return self._err(404, "no such file")
                ctype = "text/plain; charset=utf-8" if f.suffix.lower() in (".md", ".txt", ".json") else None
                return self._file(f, ctype)
        if r == ["pcs"]:
            rid = self.pc_run(self._query().get("order", ""))
            return self._json(200, {"pcs": sr.pcs_list(rid), "run_id": rid})
        if r == ["pcs", "rights"]:
            rid = self.pc_run(self._query().get("order", ""))
            return self._json(200, sr.pc_rights(rid))
        if len(r) == 3 and r[0] == "pcs" and r[2] == "entries":
            rid = self.pc_run(self._query().get("order", ""))
            return self._json(200, {"entries": sr.pc_entries(rid, r[1]), "run_id": rid})
        if r == ["studio"]:
            return self._json(200, {"url": "/"})
        return self._err(404, "not found")

    def _post(self, p):
        r = p[1:] if p[:1] == ["api"] else []
        body = self._jbody()
        if r == ["orders"]:
            return self.order_create(body)
        if len(r) == 3 and r[0] == "orders":
            d = order_dir(r[1])
            if not d:
                return self._err(404, "no such order")
            fn = {"chat": self.order_chat, "upload": self.order_upload, "approve": self.order_approve,
                  "handover": self.order_handover,
                  "start": self.order_start, "confirm": self.order_confirm, "close": self.order_close,
                  "complete": self.order_start}.get(r[2])
            if fn:
                return fn(r[1], d, body)
        if len(r) == 4 and r[:2] == ["flows", "runs"]:
            rid = r[2]
            if not sr.run_ok(rid):
                return self._err(404, "no such run")
            act = r[3]
            if act == "stop":
                return self._json(200, stop_run(rid, pause=False))
            if act == "pause":
                return self._json(200, stop_run(rid, pause=True))
            if act == "resume":
                state = sr.site_state(rid)
                if state not in ("paused", "stopped", "error"):
                    raise RuntimeError("run %s is %s; Resume works on a paused, stopped or failed run" % (rid, state))
                return self._json(200, resume_run(rid))
            if act == "step":
                return self._json(200, approve_reviews(rid))
            if act == "control":
                s = save_settings(step_new_orders=bool(body.get("pause_each_stage")))
                return self._json(200, dict(sr.run_state(rid), step_new_orders=s["step_new_orders"]))
            if act == "close":
                return self._json(200, {"ok": True, "closed": False,
                                        "note": "nothing to close: run records stay in runs/"})
        if len(r) == 3 and r[0] == "crew" and r[2] == "chat":
            return self._json(200, {"reply": crew_chat(r[1], body)})
        if r == ["settings"]:
            return self._json(200, save_settings(**{k: body[k] for k in ("office_fps",) if k in body}))
        return self._err(404, "not found")

    def _put(self, p):
        r = p[1:] if p[:1] == ["api"] else []
        if len(r) == 3 and r[0] == "orders" and r[2] == "intake":
            d = order_dir(r[1])
            if not d:
                return self._err(404, "no such order")
            return self.order_intake(r[1], d, self._jbody())
        return self._err(404, "not found")

    # -- crew
    @staticmethod
    def crew_list() -> list[dict]:
        out = []
        for c in sr.load_crew():
            out.append({"id": c["id"], "name": c["name"], "title": c["title"], "team": c["team"],
                        "stage": c.get("stage"), "appearance": c.get("appearance") or {}, "tools": c.get("tools", []),
                        "model": "qwen3.8-flash-next", "blocks": c.get("blocks", []), "graph": "none"})
        return out

    # -- orders
    @staticmethod
    def orders_list() -> list[dict]:
        out = []
        for p in sorted(ORDERS.glob("ord-*/meta.json"), reverse=True) if ORDERS.is_dir() else []:
            m = read_json(p, {}) or {}
            out.append({"id": p.parent.name, "status": m.get("status", ""), "closed": bool(m.get("closed")),
                        "created": m.get("created", ""), "run_id": m.get("run_id", "")})
        known = {o["run_id"] for o in out}
        for r in sr.runs_list():                # runs without an order (e.g. started from nextop studio)
            if r["run_id"] not in known and (sr.run_dir(r["run_id"]) / "file_servers").is_dir():
                out.append({"id": r["run_id"], "status": "run " + r["state"], "closed": False, "created": "",
                            "run_id": r["run_id"]})
        out.sort(key=lambda o: not (o["run_id"] and sr.run_ok(o["run_id"])))   # ones with a run first (stable)
        return out

    @staticmethod
    def pc_run(order: str) -> str:
        if order:
            d = order_dir(order)
            if d:
                rid = meta_of(d).get("run_id", "")
                if rid and sr.run_ok(rid):
                    return rid
                return ""
            if sr.run_ok(order):
                return order
        return sr.latest_run_with_files()

    def order_create(self, body):
        day = time.strftime("%Y%m%d")
        ORDERS.mkdir(exist_ok=True)
        with _LOCK:
            oid = next(("ord-%s-%03d" % (day, n) for n in range(1, 1000)
                        if not (ORDERS / ("ord-%s-%03d" % (day, n))).exists()), None)
            if not oid:
                return self._err(503, "order book full for today")
            (ORDERS / oid).mkdir()
        meta = {"id": oid, "assignee": "sales_sam", "created": now_iso(), "status": "consulting",
                "answers": {}, "files": {}}
        save_meta(ORDERS / oid, meta)
        write_json(ORDERS / oid / "form.json", intake.blank_form())
        log_event(oid, "order", "created", "order opened (sales_sam)")
        return self._json(201, dict(meta, created=True))

    def order_get(self, oid, d) -> dict:
        meta = meta_of(d)
        turns = transcript(d)
        meta["transcript"] = [{"user": turns[i]["content"],
                               "reply": turns[i + 1]["content"] if i + 1 < len(turns)
                               and turns[i + 1]["role"] == "assistant" else ""}
                              for i in range(0, len(turns)) if turns[i]["role"] == "user"]
        meta["missing"] = missing_of(d)
        meta["form"] = form_of(d)
        meta["run_id"] = meta.get("run_id", "")
        return meta

    def order_chat(self, oid, d, body):
        msgs = body.get("messages")
        if not isinstance(msgs, list) or not msgs or not isinstance(msgs[-1], dict) \
                or msgs[-1].get("role") != "user" or not str(msgs[-1].get("content") or "").strip():
            return self._err(400, "need {messages: [{role, content}*]} ending with the user's message")
        last = str(msgs[-1]["content"])[:2000]
        meta = meta_of(d)
        if meta.get("status") in intake.STARTED:
            return self._err(409, "already started: consultation is closed")
        files = meta.get("files") or {}
        before = form_of(d)
        was_starting = bool(meta.get("starting"))
        try:
            say, _rid = ask_worker("sam", "Sam", order_question(oid, d, last, body.get("mode") or "free"),
                                   history=transcript(d), log={"order": oid, "question": last})
            say = clean_reply(say)
        except Exception as e:  # noqa: BLE001 - shown as Sam's failure line
            traceback.print_exc()
            log_event(oid, "sam", "error", "chat turn failed: %s" % e)
            chat_append(d, last, intake.CHAT_UNREADABLE)
            bad = intake.chat_reply_payload(intake.CHAT_UNREADABLE, False, missing_of(d), form_of(d))
            bad.update(accepted=False, error=str(e)[:300])
            return self._json(200, bad)
        form = form_of(d)
        meta = meta_of(d)
        handed = ((not was_starting and bool(meta.get("starting"))) or meta.get("status") in intake.STARTED)
        out = {"say": say, "changed": [k for k in form if form[k] != before.get(k)],
               "handed": start_result(oid, d) if handed else None}
        if out["changed"]:
            log_event(oid, "order", "form", "fields updated: " + ", ".join(sorted(set(out["changed"]))))
        if out["handed"]:
            reply = out["say"] or intake.START_LINE
            chat_append(d, last, reply)
            log_event(oid, "order", "chat", "client: %s / Sam: %s" % (last, reply))
            res = out["handed"]
            payload = intake.chat_reply_payload(reply, False, [], res.get("form"))
            payload.update(accepted=True, handed_over=True, answers=res.get("answers"), stages=res.get("stages"),
                           form=res.get("form"), pdf={"file": "source.pdf", "bytes": files.get("bytes", 0)})
            return self._json(200, payload)
        text = out["say"] or intake.CHAT_UNREADABLE
        chat_append(d, last, text)
        log_event(oid, "order", "chat", "client: %s / Sam: %s" % (last, text))
        miss = missing_of(d)
        return self._json(200, intake.chat_reply_payload(text, not miss, miss, form_of(d)))

    def order_handover(self, oid, d, body):
        """Sam's finalize_and_send tool (in the `nextop ask sam` child process) calls this: handover() checks
        readiness by code and starts the run in the background."""
        ok, out = handover(oid, d)
        if not ok:
            return self._err(409, "not handed over", detail=out)
        return self._json(200, {"ok": True, "handed_over": True, "starting": bool(out.get("starting"))})

    def order_upload(self, oid, d, body):
        files = parse_multipart(self.headers, self._body)
        if "file" not in files:
            return self._err(400, "need multipart field 'file'")
        name, raw = files["file"]
        base = os.path.basename(name or "source.pdf")
        if not base.lower().endswith(".pdf") or not raw.startswith(b"%PDF"):
            return self._err(400, "accepts .pdf only")
        if len(raw) > MAX_PDF_BYTES:
            return self._err(400, "PDF over 40 MB")
        meta = meta_of(d)
        if meta.get("status") in intake.STARTED or meta.get("starting"):
            return self._err(409, "already started")
        (d / "source.pdf").write_bytes(raw)
        meta["files"] = {"source": "source.pdf", "bytes": len(raw), "upload_name": base}
        meta["parsed"] = False
        save_meta(d, meta)
        log_event(oid, "order", "upload", "%s (%d bytes)" % (base, len(raw)))
        return self._json(200, {"ok": True, "file": "source.pdf", "bytes": len(raw), "name": base,
                                "missing": missing_of(d)})

    def order_intake(self, oid, d, body):
        answers = body.get("answers")
        if not isinstance(answers, dict):
            return self._err(400, "need {answers: {...}}")
        clean = {}
        for k in intake.FORM_FIELDS:
            v = answers.get(k)
            if not isinstance(v, str) or not v.strip() or len(v) > 500:
                return self._err(400, "answers.%s must be 1-500 chars" % k)
            clean[k] = v.strip()
        prob = orders.length_problem(clean["length"])
        if prob:
            return self._err(400, "Target length: %s (now: %s)" % (prob["change_to"], prob["now"]), **prob)
        form = save_form(d, clean)
        log_event(oid, "order", "intake", "form saved (%d keys)" % len(clean))
        return self._json(200, {"ok": True, "answers": clean, "form": form})

    def order_approve(self, oid, d, body):
        if body.get("approved") is not True:
            return self._err(400, "need {approved: true}")
        meta = meta_of(d)
        meta["approved"] = {"at": now_iso()}
        save_meta(d, meta)
        log_event(oid, "order", "approved", "answers approved")
        return self._json(200, {"ok": True, "approved": True})

    def order_start(self, oid, d, body):
        meta = meta_of(d)
        if meta.get("status") in intake.STARTED:
            return self._json(200, start_result(oid, d))
        if not meta.get("approved"):
            return self._err(409, "not approved yet")
        ok, out = handover(oid, d)
        if not ok:
            return self._err(409, out if isinstance(out, str) else out.get("now", "not ready"),
                             **(out if isinstance(out, dict) else {}))
        return self._json(200, out)

    def order_confirm(self, oid, d, body):
        if body.get("confirm") is False:
            chat_append(d, intake.NO_LINE, intake.DECLINE_ACK)
            return self._json(200, {"ok": True, "declined": True, "reply": intake.DECLINE_ACK})
        ok, out = handover(oid, d)
        if not ok:
            return self._err(409, out if isinstance(out, str) else out.get("now", "not ready"))
        chat_append(d, intake.YES_LINE, intake.START_LINE)
        return self._json(200, out)

    def order_close(self, oid, d, body):
        meta = meta_of(d)
        meta["closed"] = True
        save_meta(d, meta)
        return self._json(200, {"ok": True})

    def order_progress(self, oid, d) -> dict:
        meta = meta_of(d)
        rid = meta.get("run_id", "")
        if meta.get("status") in intake.STARTED and rid and not sr.run_ok(rid) and not sr.process_alive(rid):
            reason = "the crew flow did not start: " + run_log_errors(rid)
            log_event(oid, "order", "failed", reason[:300])
            meta.update(status="consulting", start_failed=reason[:300], run_id="")
            save_meta(d, meta)
        starting = meta.get("starting") if isinstance(meta.get("starting"), dict) else None
        out = {"starting": bool(starting), "lines": [], "failed": False, "reason": "",
               "status": meta.get("status", ""), "run_id": meta.get("run_id", "")}
        if starting:
            lines, failed, reason = intake.progress_lines(progress_rows(d, starting.get("at", "")), [])
            out.update(lines=lines, failed=failed, reason=reason)
        elif meta.get("start_failed"):
            out.update(failed=True, reason=meta["start_failed"])
        if not starting and meta.get("status") in intake.STARTED:
            out["start_result"] = read_json(d / "start_result.json") or start_result(oid, d)
        return out

    def projectlog(self, oid, d) -> str:
        meta = meta_of(d)
        lines = ["PROJECT LOG  %s  (status: %s)" % (oid, meta.get("status", "")), ""]
        for r in tail_jsonl(d / "timeline.jsonl", 2000):
            lines.append("%s  %-9s %-10s %s" % (str(r.get("at", "")).replace("T", " "), r.get("source", ""),
                                                 r.get("ev", ""), r.get("summary", "")))
        rid = meta.get("run_id")
        if rid and sr.run_ok(rid):
            lines += ["", self.run_log(rid)]
        return "\n".join(lines) + "\n"

    @staticmethod
    def run_log(rid: str) -> str:
        names = {b: c["name"] for c in sr.load_crew() for b in c.get("blocks", [])}
        lines = ["RUN %s  (%s)  %s" % (rid, sr.site_state(rid), sr.cost_text(sr.cost_of(rid))), ""]
        for e in tail_jsonl(sr.run_dir(rid) / "events.jsonl", 5000):
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("time") or 0))
            b = str(e.get("block") or e.get("decision") or "")
            who = names.get(sr.base_of(b), "")
            extra = {k: v for k, v in e.items() if k not in ("time", "event", "block")}
            lines.append("%s  %-17s %-16s %-6s %s" % (t, e.get("event", ""), b, who,
                                                      json.dumps(extra, ensure_ascii=False)[:200] if extra else ""))
        return "\n".join(lines)


def _studio_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "api/project", timeout=2):
            return True
    except Exception:
        return False


def start_studio(port: int) -> None:
    """One address for people: the site starts `nextop studio` for this project as a child process on an internal
    port (127.0.0.1 only) and serves its tabs through /. An already running studio on that port is reused."""
    url = "http://127.0.0.1:%d/" % port
    if _studio_up(url):
        print("nextop studio already running on internal port %d (reused)" % port, flush=True)
        return
    log = ROOT / "runs" / ".shoestring" / "studio.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    out = open(log, "a", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "nextop", "studio", str(ROOT), "--port", str(port), "--no-browser"],
                            cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, env=env)
    atexit.register(lambda: proc.poll() is None and proc.terminate())
    for _ in range(60):
        if _studio_up(url):
            return
        if proc.poll() is not None:
            print("[WARN] nextop studio stopped at start; see %s" % log, flush=True)
            return
        time.sleep(0.5)
    print("[WARN] nextop studio did not answer in 30 s; see %s" % log, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--studio-port", type=int, default=8775,
                    help="internal port of `nextop studio` (started here unless one already runs there; "
                         "people use only the site port)")
    ap.add_argument("--no-learn", action="store_true",
                    help="do not learn finished runs (a test server next to the real one)")
    args = ap.parse_args()
    global STUDIO_URL, SITE_URL
    STUDIO_URL = "http://127.0.0.1:%d/" % args.studio_port
    start_studio(args.studio_port)
    last = None
    if not args.no_learn:
        threading.Thread(target=learn_watch, name="learn-watch", daemon=True).start()
    for port in range(args.port, args.port + 6):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as e:
            last = e
            continue
        SITE_URL = "http://127.0.0.1:%d/" % port
        print("Shoestring Studios at http://localhost:%d  (nextop studio: %s)" % (port, STUDIO_URL), flush=True)
        srv.serve_forever()
        return
    raise SystemExit("no free port %d-%d: %s" % (args.port, args.port + 5, last))


if __name__ == "__main__":
    main()
