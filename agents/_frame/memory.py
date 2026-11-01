"""Per-project employee memory (LightRAG). Stdlib only.

One memory per base employee per run: runs/<run_id>/memory/<agent_id>/
holds a LightRAG index of what the employee received (INPUTS.md per
clone/part) and wrote (result.json, report.md, render logs), plus
STATUS.json, log.jsonl and usage.json.

Builds run in background threads and never block the flow. Tests
inject a stub through _INDEXER / _RETRIEVER; production always uses
the real adapter (results are never faked).
"""
import json
import os
import shutil
import threading
import time

ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
RUNS_DIR = os.path.join(ROOT, "runs")

_INDEXER = None  # tests only: (docs, store_dir, log_id, profile) -> stats
_RETRIEVER = None  # tests only: (store_dir, q, log_id, profile) -> answer
_BUILD_LOCKS = {}
_BUILD_LOCKS_GUARD = threading.Lock()
MAX_FILE_CHARS = 200000
CLOSED_FILE = "MEMORY_CLOSED.json"


def is_closed(run_id, runs_root=None):
    """True once the owner closed this run's project."""
    return os.path.isfile(os.path.join(runs_root or RUNS_DIR,
                                       run_id, CLOSED_FILE))


def _adapter():
    from . import graph as _graph
    return _graph._adapter()


def mem_dir(run_id, agent_id, runs_root=None):
    return os.path.join(runs_root or RUNS_DIR, run_id, "memory",
                        agent_id)


def _lock_for(key):
    with _BUILD_LOCKS_GUARD:
        if key not in _BUILD_LOCKS:
            _BUILD_LOCKS[key] = threading.Lock()
        return _BUILD_LOCKS[key]


def memory_state(run_id, agent_id, runs_root=None):
    """none | building | ready | failed (+ error)."""
    st = {}
    try:
        with open(os.path.join(mem_dir(run_id, agent_id,
                                       runs_root), "STATUS.json"),
                  encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {"state": "none", "error": ""}
    if not isinstance(st, dict) or st.get("state") not in (
            "building", "ready", "failed"):
        return {"state": "none", "error": ""}
    return {"state": st["state"],
            "error": str(st.get("error", "") or "")}


def run_memory_states(run_id, runs_root=None):
    """{agent_id: {state, error}} for every memory dir of a run."""
    out = {}
    mdir = os.path.join(runs_root or RUNS_DIR, run_id, "memory")
    if not os.path.isdir(mdir):
        return out
    for agent in sorted(os.listdir(mdir)):
        if os.path.isdir(os.path.join(mdir, agent)):
            out[agent] = memory_state(run_id, agent,
                                      runs_root=runs_root)
    return out


def _read_capped(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    if len(text) > MAX_FILE_CHARS:
        text = text[:MAX_FILE_CHARS] + "\n[truncated]"
    return text


def collect_agent_docs(run_dir, base, part_nos=None):
    """[(name, text)] received + written, clones merged."""
    docs = []
    if part_nos:
        dirs = [("p%d" % no, os.path.join(run_dir, base,
                                          "p%d" % no))
                for no in part_nos]
    else:
        dirs = [("", os.path.join(run_dir, base))]
    for tag, d in dirs:
        pre = (tag + "/") if tag else ""
        for fn in ("INPUTS.md", "result.json", "report.md"):
            text = _read_capped(os.path.join(d, fn))
            if text is not None:
                docs.append((pre + fn, text))
        slides = os.path.join(d, "slides")
        if os.path.isdir(slides):
            for fn in sorted(os.listdir(slides)):
                if fn.endswith(".props.json"):
                    text = _read_capped(os.path.join(slides, fn))
                    if text is not None:
                        docs.append((pre + "slides/" + fn, text))
    return docs


def collect_sam_docs(order_dir, meta):
    """Sam's memory: consultation in, request + Source ref out."""
    docs = []
    try:
        with open(os.path.join(order_dir, "chat.jsonl"),
                  encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    turns = []
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("role") in (
                "user", "assistant"):
            who = "CLIENT" if ev["role"] == "user" else "SAM"
            turns.append("%s: %s" % (who, ev.get("content", "")))
    if turns:
        docs.append(("consultation chat",
                     "\n\n".join(turns)[:MAX_FILE_CHARS]))
    docs.append(("client answers",
                 json.dumps((meta or {}).get("answers", {}),
                            ensure_ascii=False, indent=1)))
    files = (meta or {}).get("files", {}) or {}
    facts = {"upload_name": files.get("upload_name", ""),
             "bytes": files.get("bytes", 0),
             "source_ref": files.get("pc_ref", "")}
    try:
        with open(os.path.join(order_dir, "intake.json"),
                  encoding="utf-8") as f:
            intake = json.load(f)
        if isinstance(intake, dict):
            facts["sections"] = len(intake.get("sections", []) or [])
    except (OSError, ValueError):
        pass
    docs.append(("source pdf facts",
                 json.dumps(facts, ensure_ascii=False, indent=1)))
    for fn in ("result.json", "report.md"):
        text = _read_capped(os.path.join(order_dir, fn))
        if text is not None:
            docs.append(("request " + fn, text))
    return docs


def _log_line(mdir, ev):
    ev = dict(ev)
    ev["at"] = time.strftime("%H:%M:%S")
    with open(os.path.join(mdir, "log.jsonl"), "a",
              encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _real_indexer(docs, store_dir, log_id, profile):
    mod = _adapter()
    texts = ["# DOC: %s\n\n%s" % (name, text)
             for name, text in docs]
    return mod.index_texts(texts, log_id, profile, store_dir)


def build_memory(run_id, agent_id, docs, runs_root=None,
                 profile=None, keep_log=None):
    """Build (or rebuild) one memory synchronously. Returns
    {ok, state, ...}; failures are recorded, never raised."""
    runs_root = runs_root or RUNS_DIR
    mdir = mem_dir(run_id, agent_id, runs_root)
    lock = _lock_for((runs_root, run_id, agent_id))
    with lock:
        os.makedirs(mdir, exist_ok=True)
        if keep_log:
            with open(os.path.join(mdir, "log.jsonl"), "w",
                      encoding="utf-8") as f:
                for ln in keep_log:
                    f.write(json.dumps(ln, ensure_ascii=False)
                            + "\n")
            _log_line(mdir, {"ev": "mem_rebuilt",
                             "note": "rebuilt after re-run"})
        with open(os.path.join(mdir, "STATUS.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"state": "building", "run_id": run_id,
                       "agent_id": agent_id}, f)
        chars = sum(len(t) for _, t in docs)
        _log_line(mdir, {"ev": "mem_build_start",
                         "docs": len(docs), "chars": chars,
                         "profile": profile or "active"})
        if not docs:
            err = "nothing to index: no stage files yet"
            with open(os.path.join(mdir, "STATUS.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"state": "failed", "run_id": run_id,
                           "agent_id": agent_id, "error": err}, f)
            _log_line(mdir, {"ev": "mem_build_failed",
                             "error": err})
            return {"ok": False, "error": err}
        store = os.path.join(mdir, "index")
        t0 = time.time()
        try:
            indexer = _INDEXER or _real_indexer
            stats = indexer(docs, store,
                            "mem-%s-%s" % (run_id, agent_id),
                            profile)
            stats = stats if isinstance(stats, dict) else {}
        except Exception as exc:  # noqa: BLE001 - recorded+returned
            err = str(exc)[:200] or "indexer failed"
            with open(os.path.join(mdir, "STATUS.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"state": "failed", "run_id": run_id,
                           "agent_id": agent_id, "error": err}, f)
            _log_line(mdir, {"ev": "mem_build_failed",
                             "error": err,
                             "seconds": round(time.time() - t0,
                                              1)})
            return {"ok": False, "error": err}
        secs = round(time.time() - t0, 1)
        calls, pin, rout = (0, 0, 0)
        if indexer is _real_indexer:
            try:
                calls, pin, rout = _adapter().count_llm_log(store)
            except Exception:  # noqa: BLE001 - cost stays zero
                pass
        else:
            calls = stats.get("llm_calls", 0)
        prof = stats.get("profile", profile or "active")
        with open(os.path.join(mdir, "STATUS.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"state": "ready", "run_id": run_id,
                       "agent_id": agent_id, "profile": prof,
                       "docs": len(docs), "chars": chars,
                       "seconds": secs,
                       "at": time.strftime("%Y-%m-%d %H:%M")}, f)
        with open(os.path.join(mdir, "usage.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"llm_calls": calls, "prompt_tokens": 0,
                       "completion_tokens": 0,
                       "prompt_chars": pin, "reply_chars": rout,
                       "note": "token counts are unavailable on "
                               "the LightRAG path; chars logged"},
                      f)
        _log_line(mdir, {"ev": "mem_build_done", "seconds": secs,
                         "llm_calls": calls, "prompt_chars": pin,
                         "reply_chars": rout, "profile": prof})
        return {"ok": True, "state": "ready", "seconds": secs,
                "llm_calls": calls}


def queue_build(run_id, agent_id, docs_fn, runs_root=None,
                profile=None):
    """Build in a background thread; never blocks the caller.
    docs_fn() runs inside the thread so a rebuild reads the current
    files. A previous build's log is kept across rebuilds. Refuses
    when no indexer is configured (suites stay inert)."""
    if _INDEXER is None:
        return {"ok": False, "error": "memory indexer not configured"}
    runs_root = runs_root or RUNS_DIR

    def _work():
        mdir = mem_dir(run_id, agent_id, runs_root)
        keep = None
        cur = memory_state(run_id, agent_id, runs_root)
        if cur["state"] in ("ready", "failed"):
            try:
                with open(os.path.join(mdir, "log.jsonl"),
                          encoding="utf-8") as f:
                    keep = [json.loads(ln) for ln in
                            f.read().splitlines()]
            except (OSError, ValueError):
                keep = []
            shutil.rmtree(mdir, ignore_errors=True)
        try:
            docs = docs_fn()
        except Exception as exc:  # noqa: BLE001 - recorded
            docs = []
            os.makedirs(mdir, exist_ok=True)
            with open(os.path.join(mdir, "STATUS.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"state": "failed", "run_id": run_id,
                           "agent_id": agent_id,
                           "error": str(exc)[:200]}, f)
            _log_line(mdir, {"ev": "mem_build_failed",
                             "error": str(exc)[:200]})
            return {"ok": False, "error": str(exc)[:200]}
        return build_memory(run_id, agent_id, docs,
                            runs_root=runs_root, profile=profile,
                            keep_log=keep)

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    return {"ok": True, "queued": True, "run_id": run_id,
            "agent_id": agent_id}


def query_memory(run_id, agent_id, question, runs_root=None,
                 profile=None):
    """Answer one question from a ready memory. Raises RuntimeError
    (with the exact user-facing reason) unless it is ready."""
    st = memory_state(run_id, agent_id, runs_root)
    if st["state"] == "building":
        raise RuntimeError("My memory of this project is still "
                           "building.")
    if st["state"] == "failed":
        raise RuntimeError("My memory of this project failed to "
                           "build: %s" % (st["error"]
                                           or "unknown reason"))
    if st["state"] != "ready":
        raise RuntimeError("I have not worked on this project yet.")
    store = os.path.join(mem_dir(run_id, agent_id, runs_root),
                         "index")
    if _RETRIEVER is not None:
        return str(_RETRIEVER(store, question,
                              "mem-%s-%s" % (run_id, agent_id),
                              profile))
    out = _adapter().query_dir(
        store, question, "mem-%s-%s" % (run_id, agent_id),
        profile)
    return str(out.get("answer", ""))


def close_run_memory(run_id, runs_root=None):
    """Delete ONLY the memories of one run. Results, video,
    reports and logs stay. Leaves a closed marker behind."""
    runs_root = runs_root or RUNS_DIR
    run_dir = os.path.join(runs_root, run_id)
    if not os.path.isdir(run_dir):
        return False
    shutil.rmtree(os.path.join(run_dir, "memory"),
                  ignore_errors=True)
    with open(os.path.join(run_dir, CLOSED_FILE), "w",
              encoding="utf-8") as f:
        json.dump({"closed": True,
                   "at": time.strftime("%Y-%m-%d %H:%M"),
                   "by": "owner"}, f)
    return True


def default_docs_fn(run_id, agent_id, runs_root=None):
    """docs_fn for retry: re-collect from the current files."""
    from . import parts as _parts
    runs_root = runs_root or RUNS_DIR
    run_dir = os.path.join(runs_root, run_id)

    def _sam():
        try:
            with open(os.path.join(run_dir, "STATUS.json"),
                      encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        oid = st.get("order_id", "") if isinstance(st, dict) \
            else ""
        odir = os.path.join(ROOT, "orders", oid)
        meta = {}
        if oid and os.path.isfile(
                os.path.join(odir, "meta.json")):
            try:
                with open(os.path.join(odir, "meta.json"),
                          encoding="utf-8") as f:
                    meta = json.load(f)
            except ValueError:
                meta = {}
        return collect_sam_docs(odir, meta or {})

    def _agent():
        nos = None
        if agent_id in _parts.CLONE_NODES:
            plan = _parts.load_split(run_dir)
            if plan:
                nos = [p.get("no")
                       for p in plan.get("parts") or []]
        return collect_agent_docs(run_dir, agent_id, nos)

    if agent_id == "sales_sam":
        return _sam
    return _agent
