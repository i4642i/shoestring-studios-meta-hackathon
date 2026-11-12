"""Learning across orders: turn a finished run's worker outputs into domain knowledge notes.

  python scripts/learn_run.py <run_id> [--project PATH] [--force] [--only WORKER] [--no-index]
  python scripts/learn_run.py --setup [--project PATH]

For each worker of a finished run (status done), the outputs of its blocks (copies <id>@n merged)
become one short Markdown note written by the project's LLM from those outputs only:
the order, what this worker decided and why, key facts and sources. The note is saved as
runs/<run_id>/learned/<worker>/run-<run_id>.md and added to the worker's domain knowledge with
`nextop index --worker <worker> --add <note>` (workers/<worker>/knowledge/run-<run_id>.md, then the
maps and the LightRAG index are built; needs the local LLM and the embedding server).

A run is learned once: runs/<run_id>/learned.json records each worker; workers already done are
skipped on the next call (a failed worker is tried again). --force writes and indexes every note again.

--setup (also done before every learning) makes the project ready for knowledge: each worker gets
"knowledge": {"index": <the project's index adapter>} in worker.json. It also removes a leftover
"add_outputs" from project.json defaults (temporary knowledge was removed from nextop in 0.1.3).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTE_BUDGET = 24000      # characters of outputs given to the LLM per worker
NOTE_TRIES = 2
WORKERS_AT_ONCE = 3      # notes written / indexed at the same time (one process per index)
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_LOCK = threading.Lock()


# ------------------------------------------------------------------ small helpers
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


def _write_like(p: pathlib.Path, data: dict) -> None:
    """Rewrite a JSON file keeping its line endings (worker.json / project.json)."""
    raw = p.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", nl) + nl
    p.write_bytes(text.encode("utf-8"))


def note_doc_id(run_id: str) -> str:
    """The document id of a run's note (nextop doc ids: letters, digits, '_' and '-'; lowercase)."""
    return "run-" + re.sub(r"[^\w\-]", "_", run_id).lower()


def is_learnable(root: pathlib.Path, run_id: str) -> tuple[bool, str]:
    d = root / "runs" / run_id
    st = read_json(d / "status.json", {}) or {}
    flow = read_json(d / "flow.json", {}) or {}
    if not st:
        return False, "no such run"
    if "ask" in flow or "inspect" in flow or run_id.startswith(("ask-", "chat-", "inspect-")):
        return False, "not a production run"
    if st.get("status") != "done":
        return False, "run is %s, not done" % st.get("status")
    return True, ""


# ------------------------------------------------------------------ setup
def setup(root: pathlib.Path) -> dict:
    """Give every worker an index and drop a leftover add_outputs from the project defaults (idempotent)."""
    proj_p = root / "project.json"
    proj = read_json(proj_p, {}) or {}
    indexes = list((proj.get("adapters") or {}).get("index") or {})
    if not indexes:
        raise RuntimeError("project.json has no adapters.index; knowledge needs one")
    index = indexes[0]
    changed = []
    for wp in sorted((root / "workers").glob("*/worker.json")):
        w = read_json(wp)
        if not isinstance(w, dict):
            continue
        k = w.get("knowledge") if isinstance(w.get("knowledge"), dict) else {}
        if not k.get("index"):
            w["knowledge"] = dict(k, index=index)
            _write_like(wp, w)
            changed.append(wp.parent.name)
    d = proj.get("defaults") if isinstance(proj.get("defaults"), dict) else {}
    proj_changed = "add_outputs" in d
    if proj_changed:
        d.pop("add_outputs")
        _write_like(proj_p, proj)
    return {"index": index, "workers_changed": changed, "add_outputs_removed": proj_changed}


# ------------------------------------------------------------------ outputs of one run, per worker
def worker_blocks(root: pathlib.Path, run_id: str) -> dict[str, list[str]]:
    """worker id -> its block ids in the run (copies included), from the run's own flow.json."""
    flow = read_json(root / "runs" / run_id / "flow.json", {}) or {}
    out: dict[str, list[str]] = {}
    workers = {b["id"]: b.get("worker") for b in flow.get("blocks", []) if b.get("type") == "worker"}
    blocks_dir = root / "runs" / run_id / "blocks"
    for p in sorted(blocks_dir.iterdir()) if blocks_dir.is_dir() else []:
        base = p.name.split("@", 1)[0]
        w = workers.get(base)
        if w and (root / "workers" / w / "worker.json").is_file():
            out.setdefault(w, []).append(p.name)
    for w in out:
        out[w].sort(key=lambda b: (len(b), b))
    return out


def _empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {} or (isinstance(v, dict) and all(_empty(x) for x in v.values()))


def digest(outputs: dict[str, dict]) -> str:
    """The outputs as compact JSON lines, cut so the whole fits NOTE_BUDGET."""
    each = max(1500, NOTE_BUDGET // max(len(outputs), 1))
    rows = []
    for b, o in outputs.items():
        text = json.dumps(o, ensure_ascii=False, separators=(",", ":"))
        rows.append("[%s] %s" % (b, text if len(text) <= each else text[:each] + " ...(cut)"))
    return "\n".join(rows)[:NOTE_BUDGET + 2000]


def _llm(root: pathlib.Path):
    from nextop.adapters.openai_compat import OpenAICompatLLM
    proj = read_json(root / "project.json", {})
    opts = dict(proj["adapters"]["llm"]["default"]["options"])
    env = opts.get("env_file")
    llm = OpenAICompatLLM(base_url=opts["base_url"], key_env=opts["key_env"],
                          env_file=str(root / env) if env else None, timeout=float(opts.get("timeout", 300)))
    model = next(m["name"] for m in proj.get("models", []) if m.get("llm", "default") == "default")
    return llm, model


NOTE_REQUEST = """You are {name} ({title}) at Shoestring Studios, an AI team that makes explainer videos.
Below are YOUR saved outputs from one finished order (run {run_id}). Write a short note for your own future
reference, so that on a later order you remember what you did here.

Write plain Markdown, at most about 350 words, with exactly these sections:
## What the order was
One or two sentences: the book or topic, the audience, the length and depth asked for.
## What I decided and why
3 to 7 bullets: the main choices you made in your outputs and the reason given for each.
## Key facts and sources
3 to 8 bullets: the most useful facts, numbers, names, quotes or cases, each with its source address
(fs://..., a URL or a page) exactly as it appears in the outputs.

Rules: use only what is in the order and the outputs below; never invent facts, numbers or sources.
No JSON, no code blocks, no title line (the program adds the title). English only.

ORDER (input of the run):
{order}

YOUR OUTPUTS ({blocks} block(s){copies}):
{outputs}
"""


def write_note(root: pathlib.Path, run_id: str, worker: str, blocks: list[str], outputs: dict[str, dict],
               llm, model) -> str:
    w = read_json(root / "workers" / worker / "worker.json", {}) or {}
    inp = read_json(root / "runs" / run_id / "input.json", {}) or {}
    order = {k: v for k, v in inp.items() if isinstance(v, (str, int, float)) and k not in ("source_folder", "pdf")}
    copies = sorted({b.split("@", 1)[1] for b in outputs if "@" in b}, key=int)
    prompt = NOTE_REQUEST.format(
        name=w.get("name") or worker, title=w.get("title") or worker, run_id=run_id,
        order=json.dumps(order, ensure_ascii=False, indent=1), blocks=len(outputs),
        copies=(", copies " + ", ".join("@" + c for c in copies)) if copies else "",
        outputs=digest(outputs))
    body, last = "", ""
    for _ in range(NOTE_TRIES):
        reply = llm.chat(model, [{"role": "user", "content": prompt}], None)
        body = _THINK_RE.sub("", reply.text or "").strip()
        body = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", body).strip()
        body = re.sub(r"^#\s+.*\n+", "", body)            # the program writes the title
        if "## " in body and len(body) > 200:
            break
        last, body = body[:200], ""
    if not body:
        raise RuntimeError("the LLM did not write the note (last reply: %r)" % last)
    title = str(inp.get("video_title") or inp.get("title") or run_id)
    head = ["# Order %s: %s" % (run_id, title), "",
            "Learned by %s (%s) from run %s, finished %s. Blocks: %s." % (
                w.get("name") or worker, worker, run_id,
                time.strftime("%Y-%m-%d", time.localtime((read_json(root / "runs" / run_id / "status.json", {}) or {})
                                                          .get("ended") or time.time())),
                ", ".join(outputs)), ""]
    return "\n".join(head) + "\n" + body.rstrip() + "\n"


def index_note(root: pathlib.Path, worker: str, note: pathlib.Path) -> str:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-m", "nextop", "index", str(root), "--worker", worker, "--add", str(note)],
                       cwd=str(root), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0 or "[error]" in out:
        errs = [ln for ln in out.splitlines() if "[error]" in ln or "Error" in ln]
        raise RuntimeError(("; ".join(errs[-3:]) or out[-400:]).strip())
    return out


# ------------------------------------------------------------------ learn one run
def learn(run_id: str, root: pathlib.Path = ROOT, force: bool = False, only: str | None = None,
          do_index: bool = True, log=print) -> dict:
    ok, why = is_learnable(root, run_id)
    if not ok:
        raise RuntimeError("run %s cannot be learned: %s" % (run_id, why))
    rd = root / "runs" / run_id
    lp = rd / "learned.json"
    rec = read_json(lp, {}) or {}
    if rec.get("status") == "done" and not force and not only:
        log("run %s was learned already (%s)" % (run_id, lp))
        return rec
    s = setup(root)
    if s["workers_changed"] or s["add_outputs_removed"]:
        log("setup: index '%s' for %s; leftover add_outputs removed: %s" % (s["index"], s["workers_changed"] or "-",
                                                                          s["add_outputs_removed"]))
    from nextop import records
    run = records.load_run(rd)
    groups = worker_blocks(root, run_id)
    rec.update(run_id=run_id, status="learning", started=time.time())
    rec.setdefault("workers", {})
    write_json(lp, rec)
    llm, model = _llm(root)
    doc = note_doc_id(run_id)

    def one(worker: str, blocks: list[str]) -> None:
        prev = rec["workers"].get(worker) or {}
        if prev.get("status") in ("done", "skipped") and not force:
            return
        t0 = time.time()
        row = {"blocks": blocks}
        try:
            outputs = {b: o for b in blocks if not _empty(o := run.output(b))}
            if not outputs:
                row.update(status="skipped", reason="no saved outputs (empty or failed blocks)")
            else:
                text = write_note(root, run_id, worker, blocks, outputs, llm, model)
                note = rd / "learned" / worker / (doc + ".md")
                note.parent.mkdir(parents=True, exist_ok=True)
                note.write_text(text, encoding="utf-8")
                row.update(note=str(note.relative_to(root)).replace("\\", "/"), words=len(text.split()),
                           used=list(outputs))
                if do_index:
                    index_note(root, worker, note)
                    row.update(status="done", doc=doc, knowledge="workers/%s/knowledge/%s.md" % (worker, doc))
                else:
                    row.update(status="written", reason="--no-index: note written, not added to knowledge")
        except Exception as e:  # recorded, tried again on the next call
            row.update(status="failed", error="%s: %s" % (type(e).__name__, str(e)[:500]))
        row["seconds"] = round(time.time() - t0, 1)
        with _LOCK:
            rec["workers"][worker] = row
            write_json(lp, rec)
        log("  %-10s %-8s %5.1fs %s" % (worker, row["status"], row["seconds"], row.get("error") or row.get("note") or
                                        row.get("reason") or ""))

    todo = {w: b for w, b in groups.items() if not only or w == only}
    log("learning run %s: %d worker(s)" % (run_id, len(todo)))
    with ThreadPoolExecutor(WORKERS_AT_ONCE) as ex:
        list(ex.map(lambda kv: one(*kv), todo.items()))
    states = [rec["workers"].get(w, {}).get("status") for w in groups]
    rec["status"] = "done" if all(s in ("done", "skipped") for s in states) else "partial"
    rec["ended"] = time.time()
    rec["learned_workers"] = sorted(w for w in groups if rec["workers"].get(w, {}).get("status") == "done")
    write_json(lp, rec)
    log("run %s: %s (%d learned, %s)" % (run_id, rec["status"], len(rec["learned_workers"]), lp))
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--project", default=str(ROOT))
    ap.add_argument("--force", action="store_true", help="write and index every note again")
    ap.add_argument("--only", help="only this worker")
    ap.add_argument("--no-index", action="store_true", help="write the notes only (no knowledge change)")
    ap.add_argument("--setup", action="store_true", help="only give workers an index (and drop a leftover add_outputs)")
    a = ap.parse_args()
    root = pathlib.Path(a.project).resolve()
    if a.setup:
        print(json.dumps(setup(root), ensure_ascii=False))
        return 0
    if not a.run_id:
        ap.error("give a run id (or --setup)")
    rec = learn(a.run_id, root, force=a.force, only=a.only, do_index=not a.no_index)
    return 0 if rec.get("status") == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
