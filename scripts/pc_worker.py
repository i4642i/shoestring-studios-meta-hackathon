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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import graph, pc, runner  # noqa: E402

LOCK_WAIT = 600
LOCK_STALE = 1800
POLL = 5


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


def build_map(entry, model):
    stats = {"calls": 0, "prompt_chars": 0, "reply_chars": 0}
    flat = entry["paragraphs"]
    out, missing = [], 0
    for s in entry["sections"]:
        paras = flat[s["start"]:s["start"] + s["count"]]
        sec = {"n": s["n"], "heading": s["heading"], "paras": paras}
        items, miss = _section_map(model, s["n"], s["heading"], paras,
                                   stats)
        missing += 1 if miss else 0
        pages = sorted({pg for p in paras for pg in p["pages"]})
        has = sorted({h for p in paras for h in p.get("has", [])})
        for img in entry.get("images", []):
            try:
                if int(img["addr"][3:].split(".")[0]) in pages:
                    has.append(img["addr"])
            except (ValueError, IndexError):
                pass
        out.append({"ref": "s" + s["n"], "heading": s["heading"],
                    "summary": items,
                    "omitted": pc.resolve_omitted(
                        pc.omitted_candidates(sec), items),
                    "key_terms": pc.key_terms(sec), "has": sorted(has),
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


def main(doc_id):
    edir = pc.entry_dir("source", doc_id)
    with open(os.path.join(edir, "entry.json"), encoding="utf-8") as f:
        entry = json.load(f)
    mod = graph._adapter()
    model = mod.llm_settings()["model"]
    if not runner.key_present(model):
        msg = "%s missing: add it to .env" % runner.key_var(model)
        log(edir, {"ev": "map_failed", "error": msg})
        raise SystemExit(msg)
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
    prof = mod.embed_settings()["profile"]
    idx = pc.index_dir("source", prof)
    text = "\n\n".join("[%s] %s" % (p["addr"], p["text"])
                       for p in entry["paragraphs"])
    lockd = _lock(idx)
    try:
        before = len(_log_lines(idx))
        t1 = time.time()
        res = mod.index_texts(text, "pc-source", prof, idx, doc_id)
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
    try:
        main(sys.argv[1])
    except Exception as exc:  # noqa: BLE001 - worker must log, not vanish
        try:
            log(pc.entry_dir("source", sys.argv[1]),
                {"ev": "failed", "error": str(exc)[:300]})
        except OSError:
            pass
        print("worker failed: %s" % exc, flush=True)
        raise SystemExit(1)
