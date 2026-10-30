"""Build a Source PC entry's map + LightRAG index in the background.

Usage (from repo root): python scripts/pc_worker.py <doc_id>
Reads storage/_pc/source/entries/<doc_id>/entry.json, writes map.json
(status pending -> done/partial), appends per-entry log.jsonl (map/index
time, LLM calls, tokens), then inserts the entry text into
storage/_pc/source/index/<active-profile>/. Indexing is serialized per
profile with a lock dir. Exit nonzero on failure; details go to
log.jsonl and worker.log.
"""
import json
import os
import shutil
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import graph, pc, runner  # noqa: E402

LOCK_WAIT = 600
LOCK_STALE = 1800
POLL = 5
META_VISION_MODEL = "muse-spark-1.3"  # Meta Model API flagship; second
# vision attempt when the primary model cannot take images.
FIG_KINDS = ("chart", "diagram", "photo", "formula", "table-image")


def log(edir, obj):
    obj = dict(obj, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    with open(os.path.join(edir, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _lock(idx):
    """Serialize index writers per profile. Returns the lock dir."""
    lockd = os.path.join(idx, "BUILDING")
    info = os.path.join(lockd, "INFO")
    t0 = time.time()
    while True:
        try:
            os.makedirs(lockd)
            with open(info, "w", encoding="utf-8") as f:
                f.write("%d %s" % (os.getpid(),
                                   time.strftime("%Y-%m-%dT%H:%M:%S")))
            return lockd
        except OSError:
            pass
        try:
            age = time.time() - os.path.getmtime(info)
        except OSError:
            age = 0
        if age > LOCK_STALE:
            shutil.rmtree(lockd, ignore_errors=True)
            continue
        if time.time() - t0 > LOCK_WAIT:
            raise RuntimeError("index busy for %ds" % LOCK_WAIT)
        time.sleep(POLL)


def _unlock(lockd):
    shutil.rmtree(lockd, ignore_errors=True)


def _llm_json(model, prompt):
    resp = runner._chat(model, [{"role": "user", "content": prompt}],
                        None, timeout=180)
    text = (resp.get("choices") or [{}])[0].get("message", {}).get(
        "content", "")
    obj, status = runner.parse_json_answer(text or "")
    if status != "ok" or not isinstance(obj, dict):
        raise ValueError("no JSON in map reply")
    return obj, len(prompt), len(text or "")


def _section_map(model, n, heading, paras, stats):
    numbered = "\n".join("p%d: %s" % (k + 1, p["text"])
                         for k, p in enumerate(paras))
    prompt = ("Summarize this document section for NAVIGATION (never quote "
              "it as evidence). Reply with ONLY a JSON object, no other "
              "text:\n{\"summary\": [{\"text\": \"...\", "
              "\"see\": \"p1-p3\"}]}\nRules: 2-6 bullets; each see covers "
              "exactly the summarized paragraphs (pN or pN-pM, 1..%d); "
              "short texts; English.\n\nSECTION %s: %s\n%s"
              % (len(paras), n, heading, numbered))
    last = None
    for _ in range(2):
        try:
            obj, pin, rout = _llm_json(model, prompt)
            stats["calls"] += 1
            stats["prompt_chars"] += pin
            stats["reply_chars"] += rout
            items = obj.get("summary")
            if not isinstance(items, list) or not items:
                raise ValueError("empty summary")
            for it in items:
                if not isinstance(it, dict) or not it.get("text") \
                        or not pc.check_see(it.get("see", ""),
                                             len(paras)):
                    raise ValueError("bad see range")
            return items, False
        except (ValueError, KeyError) as exc:
            last = exc
    print("section %s summary missing: %s" % (n, last), flush=True)
    return [], True


def _vision_models(primary):
    """Vision attempt order: primary map model first, Meta flagship
    next. Models without keys are skipped."""
    out = []
    for m in (primary, META_VISION_MODEL):
        if m and m not in out and runner.key_present(m):
            out.append(m)
    return out


def _describe_one(model, blob, caption):
    import base64
    prompt = ("Describe this document figure for NAVIGATION (never quote "
              "it as evidence). Reply with ONLY a JSON object, no other "
              "text:\n{\"description\": \"2-4 sentences: what it shows "
              "and its point\", \"text_in_image\": \"all readable words, "
              "labels, legend, axis names\", \"numbers\": [\"key values\"], "
              "\"kind\": \"chart|diagram|photo|formula|table-image\"}\n"
              + ("Printed caption: %s" % caption if caption else
                 "No printed caption."))
    msg = {"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(blob)
            .decode(), "detail": "auto"}}]}
    resp = runner._chat(model, [msg], None, timeout=180)
    text = (resp.get("choices") or [{}])[0].get("message", {}).get(
        "content", "")
    obj, status = runner.parse_json_answer(text or "")
    if status != "ok" or not isinstance(obj, dict):
        raise ValueError("no JSON in describe reply")
    if not isinstance(obj.get("description"), str) \
            or not obj["description"].strip():
        raise ValueError("empty description")
    if obj.get("kind") not in FIG_KINDS:
        raise ValueError("bad kind %r" % obj.get("kind"))
    nums = obj.get("numbers", [])
    obj["numbers"] = [str(n) for n in nums] if isinstance(nums, list) \
        else []
    use = resp.get("usage", {})
    toks = use.get("prompt_tokens", 0) + use.get("completion_tokens", 0)
    return obj, toks or (len(prompt) + len(text or "")) // 4


def describe_figures(entry, edir, model):
    """Describe each figure once (table-images included). The first
    figure probes vision support; on failure the rest stay
    caption-only. Returns (described, failed, calls, tokens, backend).
    AI text is navigation only, never evidence."""
    figs = entry.get("figures", [])
    if not figs:
        return 0, 0, 0, 0, "none"
    models = _vision_models(model)
    if not models:
        for fig in figs:
            fig["described_by"] = "caption-only"
        return 0, len(figs), 0, 0, "no-key"
    backend, ok_n, fail_n, calls, toks = None, 0, 0, 0, 0
    for fig in figs:
        with open(os.path.join(edir, "figures", fig["file"]),
                  "rb") as f:
            blob = f.read()
        done = False
        for m in models if backend is None else [backend]:
            for _ in range(2):
                try:
                    obj, tk = _describe_one(m, blob,
                                            fig.get("caption", ""))
                    calls += 1
                    toks += tk
                    fig["description"] = obj["description"].strip()
                    if not fig.get("text_in_image"):
                        fig["text_in_image"] = str(
                            obj.get("text_in_image", "")).strip()
                    fig["numbers"] = obj["numbers"]
                    if fig.get("kind") != "table-image":
                        fig["kind"] = obj["kind"]
                    fig["described"] = True
                    fig["described_by"] = m
                    fig["generated_at"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%S")
                    backend = backend or m
                    done = True
                    break
                except Exception as exc:  # noqa: BLE001 - next try/model
                    calls += 1
                    print("describe %s via %s failed: %s"
                          % (fig["addr"], m, exc), flush=True)
            if done:
                break
        if done:
            ok_n += 1
        else:
            fail_n += 1
            fig["described_by"] = "caption-only"
            if backend is None:
                break  # vision dead everywhere: rest stay caption-only
    if backend is None:
        fail_n = len(figs)
        for fig in figs:
            fig.setdefault("described_by", "caption-only")
    return ok_n, fail_n, calls, toks, backend or "unavailable"


def _sec_no(addr):
    return addr[3:].rsplit(".", 1)[0]


def _fig_desc(fig):
    if fig.get("description"):
        first = fig["description"].split(".")[0].strip()
        return first + "." if first else fig.get("caption", "")
    return fig.get("caption", "")


def _tab_desc(tab):
    rows = tab.get("rows") or []
    cols = max([len(r) for r in rows] or [0])
    head = "Table %dx%d" % (len(rows), cols)
    if tab.get("caption"):
        head += ": " + tab["caption"]
    return head


def build_map(entry, model):
    stats = {"calls": 0, "prompt_chars": 0, "reply_chars": 0}
    flat = entry["paragraphs"]
    pre = "s" if entry.get("pc", "source") == "source" else "g"
    out, missing = [], 0
    for s in entry["sections"]:
        if s.get("non_content"):
            continue
        paras = flat[s["start"]:s["start"] + s["count"]]
        sec = {"n": s["n"], "heading": s["heading"], "paras": paras,
               "figures": entry.get("figures", []),
               "tables": entry.get("tables", [])}
        items, miss = _section_map(model, s["n"], s["heading"], paras,
                                   stats)
        missing += 1 if miss else 0
        has, terms = [], pc.rank_key_terms(sec)[:pc.TERMS_PER_SECTION]
        for fig in entry.get("figures", []):
            if _sec_no(fig["addr"]) != s["n"]:
                continue
            has.append({"ref": entry["ref"] + "#" + fig["addr"],
                        "caption": fig.get("caption", ""),
                        "desc": _fig_desc(fig)})
            for t in pc.caption_terms(fig.get("caption", "")):
                if t not in terms and len(terms) < pc.TERMS_PER_SECTION:
                    terms.append(t)
        for tab in entry.get("tables", []):
            if _sec_no(tab["addr"]) != s["n"]:
                continue
            has.append({"ref": entry["ref"] + "#" + tab["addr"],
                        "caption": tab.get("caption", ""),
                        "desc": _tab_desc(tab)})
            for t in pc.caption_terms(tab.get("caption", "")):
                if t not in terms and len(terms) < pc.TERMS_PER_SECTION:
                    terms.append(t)
        base = entry["ref"] + "#" + pre + s["n"] \
            if pre == "s" else entry["ref"] + "#"
        out.append({"ref": pre + s["n"], "heading": s["heading"],
                    "summary": items,
                    "omitted": pc.resolve_omitted(
                        pc.omitted_candidates(sec), items, base),
                    "key_terms": terms, "has": has,
                    "chars": sum(len(p["text"]) for p in paras),
                    "subsections": list(s.get("subsections", []))})
        if miss:
            out[-1]["summary_missing"] = True
    entry_summary = ""
    if any(s["summary"] for s in out):
        joined = "\n".join(
            "Section %s (%s): %s" % (s["ref"], s["heading"], "; ".join(
                b["text"] for b in s["summary"])) for s in out
            if s["summary"])
        try:
            resp = runner._chat(
                model, [{"role": "user",
                         "content": "Summarize this document in 3-5 "
                                    "sentences from its section summaries. "
                                    "Plain text, English.\n\n" + joined}],
                None, timeout=180)
            stats["calls"] += 1
            entry_summary = ((resp.get("choices") or [{}])[0]
                             .get("message", {}).get("content", "")
                             or "").strip()
        except Exception as exc:  # noqa: BLE001 - logged, map stays partial
            print("entry summary failed: %s" % exc, flush=True)
    status = "done" if not missing and entry_summary else "partial"
    return {"ref": entry["ref"], "doc_id": entry["doc_id"],
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "llm_model": model, "map_version": pc.MAP_VERSION,
            "status": status, "entry_summary": entry_summary,
            "sections": out}, stats


def _log_lines(idx):
    p = os.path.join(idx, "llm_log.jsonl")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return f.read().splitlines()


def index_docs(entry):
    """(docs, ids) for the LightRAG index: main text plus one chunk
    per figure/table, each id its full ref."""
    heads = {s["n"]: s.get("heading", "")
             for s in entry.get("sections", [])}
    docs = ["\n\n".join("[%s] %s" % (p["addr"], p["text"])
                        for p in entry["paragraphs"])]
    ids = [entry["ref"]]
    for fig in entry.get("figures", []):
        kind = fig.get("kind") or "figure"
        ids.append(entry["ref"] + "#" + fig["addr"])
        docs.append(pc.chunk_text(
            ids[-1], "Figure (%s)" % kind,
            heads.get(_sec_no(fig["addr"]), ""), fig.get("caption", ""),
            fig.get("description", ""), fig.get("text_in_image", ""),
            fig.get("numbers", [])))
    for tab in entry.get("tables", []):
        ids.append(entry["ref"] + "#" + tab["addr"])
        docs.append(pc.chunk_text(
            ids[-1], "Table", heads.get(_sec_no(tab["addr"]), ""),
            tab.get("caption", ""), "", "", [],
            extra=tab.get("markdown", "")))
    return docs, ids


def main(doc_id, mode="all", pcname="source"):
    """Run worker stages. mode "all" (describe+map+index), "noindex"
    (describe+map, for sandboxes without the embed server), or
    "index" (index only, for the Rebuild-index button). pcname picks
    the PC (source/theory/article)."""
    if pcname not in pc.PCS:
        raise SystemExit("unknown PC: %r" % pcname)
    edir = pc.entry_dir(pcname, doc_id)
    with open(os.path.join(edir, "entry.json"), encoding="utf-8") as f:
        entry = json.load(f)
    mod = graph._adapter()
    model = mod.llm_settings()["model"]
    if not runner.key_present(model):
        msg = "%s missing: add it to .env" % runner.key_var(model)
        log(edir, {"ev": "map_failed", "error": msg})
        raise SystemExit(msg)
    if mode in ("all", "noindex"):
        t0 = time.time()
        ok_n, fail_n, dcalls, dtoks, backend = describe_figures(
            entry, edir, model)
        with open(os.path.join(edir, "entry.json"), "w",
                  encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        log(edir, {"ev": "describe_done",
                   "figures": len(entry.get("figures", [])),
                   "described": ok_n, "failed": fail_n, "calls": dcalls,
                   "tokens": dtoks, "backend": backend,
                   "seconds": round(time.time() - t0, 1)})
        print("describe %s: %d ok, %d failed (%s)"
              % (doc_id, ok_n, fail_n, backend), flush=True)
        t0 = time.time()
        mapd, stats = build_map(entry, model)
        with open(os.path.join(edir, "map.json"), "w",
                  encoding="utf-8") as f:
            json.dump(mapd, f, ensure_ascii=False, indent=2)
        log(edir, {"ev": "map_done", "status": mapd["status"],
                   "seconds": round(time.time() - t0, 1),
                   "llm_calls": stats["calls"],
                   "tokens_est": (stats["prompt_chars"]
                                  + stats["reply_chars"]) // 4})
        print("map %s: %s (%d calls)" % (doc_id, mapd["status"],
                                         stats["calls"]), flush=True)
    if mode in ("all", "index"):
        _run_index(mod, entry, edir, doc_id)


def _run_index(mod, entry, edir, doc_id):
    prof = mod.embed_settings()["profile"]
    idx = pc.index_dir(entry.get("pc", "source"), prof)
    docs, ids = index_docs(entry)
    lockd = _lock(idx)
    try:
        before = len(_log_lines(idx))
        t1 = time.time()
        res = mod.index_texts(docs, "pc-" + entry.get("pc", "source"),
                              prof, idx, doc_id, ids)
        calls, chars = 0, 0
        for ln in _log_lines(idx)[before:]:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            calls += 1
            chars += r.get("prompt_chars", 0) + r.get("reply_chars", 0)
        log(edir, {"ev": "index_done", "profile": prof,
                   "seconds": round(time.time() - t1, 1),
                   "llm_calls": calls, "tokens_est": chars // 4,
                   "dim": res["dim"]})
        print("index %s/%s: ok" % (doc_id, prof), flush=True)
    finally:
        _unlock(lockd)


if __name__ == "__main__":
    pcname = sys.argv[3] if len(sys.argv) > 3 else "source"
    try:
        main(sys.argv[1],
             sys.argv[2] if len(sys.argv) > 2 else "all", pcname)
    except Exception as exc:  # noqa: BLE001 - worker must log, not vanish
        try:
            detail = traceback.format_exc(limit=3)
            log(pc.entry_dir(pcname if pcname in pc.PCS else "source",
                             sys.argv[1]),
                {"ev": "failed", "error": str(exc),
                 "traceback": detail[-1500:]})
        except OSError:
            pass
        print("worker failed: %s" % exc, flush=True)
        raise SystemExit(1)
