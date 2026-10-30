"""Tool registry + builtin tools. Stdlib only.

Each tool takes (ctx, args) and returns JSON-serializable data.
ctx: {"run_dir":..., "agent_dir":..., "input_md":...}
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import graph
from . import pc
from . import pdfingest
from . import results
from .schemas import (list_headings, validate_cases, validate_concept,
                      validate_concepts, validate_draft, validate_request,
                      validate_structure)


def read_md_section(ctx, args):
    path = args.get("path") or ctx.get("input_md")
    max_chars = int(args.get("max_chars", 4000))
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return {"error": "no such file: %s. Call again with no path "
                         "to read this run's input." % path}
    lines = text.splitlines()
    heads = [(i, ln) for i, ln in enumerate(lines) if ln.startswith("#")]
    sections = [t for _, t in list_headings(text)]
    want = (args.get("section") or "").strip().lower()
    if want:
        for idx, (li, ln) in enumerate(heads):
            if ln.lstrip("# ").strip().lower() == want:
                end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
                return {"section": ln.strip(),
                        "text": "\n".join(lines[li:end])[:max_chars]}
        return {"error": "section not found", "sections": sections}
    return {"sections": sections, "text": text[:max_chars],
            "truncated": len(text) > max_chars}


def write_draft(ctx, args):
    draft = args.get("draft")
    errors = validate_draft(draft)
    if errors:
        return {"ok": False, "errors": errors}
    out = os.path.join(ctx["run_dir"], "draft.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    return {"ok": True, "path": out, "output": "draft.json"}


def _save_categories(ctx, categories):
    """Wrap validated payloads as the run's result.json + report.md."""
    try:
        res = results.make_result(ctx["producer"], ctx["order_id"],
                                  ctx["run_id"], categories)
    except (KeyError, RuntimeError) as exc:
        return {"ok": False, "errors": ["bad result context: %s" % exc]}
    problems = results.check_result(res)
    if problems:
        return {"ok": False, "errors": problems}
    try:
        out = results.save_result(ctx["run_dir"], res)
    except RuntimeError as exc:
        return {"ok": False, "errors": [str(exc)]}
    report_path = os.path.join(ctx["run_dir"], "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(results.render_report(res))
    return {"ok": True, "path": out, "output": "result.json",
            "report": report_path}


def _save_category(ctx, category, obj):
    return _save_categories(ctx, {category: obj})


def _received_refs(ctx, category):
    """Entry refs received for a category in this run (flow lines)."""
    out = set()
    d = (ctx or {}).get("run_dir", "")
    if not d or not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not (fn.startswith("received.") and fn.endswith(
                ".%s.json" % category)):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                data = json.load(f).get("data", {})
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("ref"):
            out.add(data["ref"])
    return out


def write_structure(ctx, args):
    bundle = args.get("result")
    if not isinstance(bundle, dict):
        return {"ok": False, "errors": [
            "call with {result: {concept: {...}, structure: {...}}}"]}
    errors = validate_concept(bundle.get("concept"))
    check = ctx.get("input_md")
    sref = (bundle.get("structure") or {}).get("source_ref", "")
    if isinstance(sref, str) and sref.startswith("pc://source/"):
        try:
            check = pc.entry_markdown(pc.load_entry_by_ref(sref))
        except (OSError, ValueError, KeyError):
            pass
    pointed = _received_refs(ctx, "source")
    if pointed and sref not in pointed:
        errors.append("source_ref %r was not sent to this run" % (sref,))
    errors += validate_structure(bundle.get("structure"), check)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_categories(ctx, {"concept": bundle["concept"],
                                  "structure": bundle["structure"]})


def write_request(ctx, args):
    """Save Sam's two categories: the request report plus the source
    v3 pointer, built from the entry Sam sent this run (never
    model-written). Needs send.json (pc_send_source ran here) and a
    non-empty recipient list for this order."""
    obj = (args or {}).get("request")
    errors = validate_request(obj)
    if errors:
        return {"ok": False, "errors": errors}
    d = (ctx or {}).get("run_dir", "")
    try:
        with open(os.path.join(d, "send.json"), encoding="utf-8") as f:
            sent = json.load(f)
    except (OSError, ValueError):
        return {"ok": False, "errors": [
            "no source sent in this run: call pc_send_source first"]}
    try:
        entry = pc.load_entry_by_ref(sent.get("ref", ""))
    except (OSError, ValueError, KeyError) as exc:
        return {"ok": False, "errors": ["sent entry missing: %s" % exc]}
    rows = [r for r in pc.recipients_of(entry) or []
            if isinstance(r, dict)
            and r.get("order_id") == (ctx or {}).get("order_id")]
    if not rows:
        return {"ok": False, "errors": [
            "no recipients for this order: call pc_set_recipients "
            "before writing"]}
    source = {"ref": entry.get("ref", ""), "title": entry.get("title"),
              "chars": entry.get("chars", 0),
              "sections": len(entry.get("sections", [])),
              "recipients": rows}
    return _save_categories(ctx, {"request": obj, "source": source})


def _verbatim_haystack(passage):
    """Text a quote may match. Figure descriptions are AI-written, so
    figure quotes match caption/image text/numbers only, never them."""
    kind = passage.get("kind", "")
    if kind == "figure":
        bits = [passage.get("caption", ""),
                passage.get("text_in_image", ""),
                " ".join(passage.get("numbers", []) or [])]
        return "\n".join(b for b in bits if b)
    if kind == "table":
        bits = [passage.get("caption", ""), passage.get("markdown", "")]
        return "\n".join(b for b in bits if b)
    return passage.get("text", "")


def _norm_ws(s):
    return " ".join(str(s).split())


def _check_quote(errors, ref, quote, where):
    """One {ref, quote} pair passes only when the quote appears
    verbatim (whitespace normalized) in the passage at the ref."""
    if not isinstance(ref, str) or not ref.strip():
        errors.append("%s: missing ref" % where)
        return
    if not isinstance(quote, str) or not quote.strip():
        errors.append("%s: missing quote" % where)
        return
    try:
        rpc, rid, frag = pc.parse_ref(ref)
    except ValueError:
        errors.append("%s: bad ref %r" % (where, ref))
        return
    if not frag:
        errors.append("%s: cite a passage, not the whole entry (%r)"
                      % (where, ref))
        return
    try:
        entry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid))
    except (OSError, ValueError, KeyError) as exc:
        errors.append("%s: cannot open %r (%s)" % (where, ref, exc))
        return
    try:
        passage = pc.open_ref(entry, ref)
    except (ValueError, KeyError) as exc:
        errors.append("%s: cannot open %r (%s)" % (where, ref, exc))
        return
    if _norm_ws(quote) not in _norm_ws(_verbatim_haystack(passage)):
        errors.append("%s: quote not found verbatim in %r" % (where, ref))


def _run_pick_refs(ctx):
    """Entry refs picked in this run (research.jsonl pick events)."""
    out = set()
    d = (ctx or {}).get("run_dir", "")
    log = os.path.join(d, "research.jsonl") if d else ""
    if not log or not os.path.isfile(log):
        return out
    with open(log, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if ev.get("ev") != "pick" or not ev.get("ref"):
            continue
        try:
            rpc, rid, _frag = pc.parse_ref(ev["ref"])
        except ValueError:
            continue
        out.add(pc.entry_ref(rpc, rid))
    return out


def _report_pick_refs(report):
    out = set()
    for p in report.get("parts") or []:
        if not isinstance(p, dict):
            continue
        for pk in p.get("picks") or []:
            if not isinstance(pk, dict):
                continue
            try:
                rpc, rid, _frag = pc.parse_ref(pk.get("ref", ""))
            except ValueError:
                continue
            out.add(pc.entry_ref(rpc, rid))
    return out


def _claims_of(category, part):
    if category == "concepts":
        return [("claims[%d]" % m, cl)
                for m, cl in enumerate(part.get("claims") or [])]
    out = []
    for m, cs in enumerate(part.get("cases") or []):
        for n, cl in enumerate((cs or {}).get("claims") or []):
            out.append(("cases[%d].claims[%d]" % (m, n), cl))
    return out


def _omitted_hints(ctx, errors):
    """Suggest map omitted refs when evidence fails (§13.4.3). Reads
    the run's received structure for the source entry; silent when
    anything is missing (ad-hoc runs)."""
    if not any(k in " ".join(errors)
               for k in ("citation", "claim", "verbatim", "evidence",
                         "needs >=1 case")):
        return []
    d = (ctx or {}).get("run_dir", "")
    if not d:
        return []
    try:
        with open(os.path.join(d, "INPUTS.json"), encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return []
    hints = []
    seen = set()
    for item in (manifest or {}).get("received") or []:
        if not isinstance(item, dict):
            continue
        if item.get("category") != "structure" or not item.get("file"):
            continue
        try:
            with open(os.path.join(d, item["file"]),
                      encoding="utf-8") as f:
                data = json.load(f).get("data", {})
        except (OSError, ValueError):
            continue
        sref = (data or {}).get("source_ref", "")
        if not sref:
            continue
        try:
            mp = pc.load_map_by_ref(sref)
        except (OSError, ValueError, KeyError):
            continue
        for sec in mp.get("sections", []):
            for om in (sec or {}).get("omitted") or []:
                ref = (om or {}).get("ref", "")
                what = (om or {}).get("what", "")
                if ref and ref not in seen:
                    seen.add(ref)
                    hints.append("hint: try %s (%s)" % (ref, what))
                if len(hints) >= 3:
                    return hints
    return hints


def _write_report(ctx, args, category, validator):
    obj = args.get(category)
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["call with {%s: {...}}" % category]}
    errors = validator(obj)
    if errors:
        return {"ok": False,
                "errors": errors + _omitted_hints(ctx, errors)}
    cited = {}
    for i, p in enumerate(obj["parts"]):
        where = "%s.parts[%d]" % (category, i)
        pid = p.get("part_id", "p%d" % (i + 1))
        for cw, cl in _claims_of(category, p):
            for n, cit in enumerate((cl or {}).get("citations") or []):
                if not isinstance(cit, dict):
                    continue
                _check_quote(errors, cit.get("ref"), cit.get("quote"),
                             "%s.%s.citations[%d]" % (where, cw, n))
                if isinstance(cit.get("ref"), str):
                    cited.setdefault(pid, []).append(cit["ref"])
        for m, pk in enumerate(p.get("picks") or []):
            if not isinstance(pk, dict):
                continue
            ev = pk.get("evidence") or {}
            if isinstance(ev, dict):
                _check_quote(errors, ev.get("ref"), ev.get("quote"),
                             "%s.picks[%d].evidence" % (where, m))
                if isinstance(ev.get("ref"), str):
                    cited.setdefault(pid, []).append(ev["ref"])
    if errors:
        return {"ok": False,
                "errors": errors + _omitted_hints(ctx, errors)}
    got = _report_pick_refs(obj)
    want = _run_pick_refs(ctx)
    for ref in sorted(got - want):
        errors.append("pick %s was never picked in this run" % ref)
    for ref in sorted(want - got):
        errors.append("picked %s is missing from the report" % ref)
    if errors:
        return {"ok": False, "errors": errors}
    saved = _save_category(ctx, category, obj)
    if saved.get("ok"):
        for pid in sorted(cited):
            _log_research(ctx, {"ev": "citations", "part_id": pid,
                                "refs": sorted(set(cited[pid]))})
    return saved


def research_status(ctx, args):
    """One-line retrieval status from this run's research log:
    searches run, hits seen, picks made, citations written."""
    d = (ctx or {}).get("run_dir", "")
    log = os.path.join(d, "research.jsonl") if d else ""
    searches = hits = picks = cites = 0
    parts = {}
    if log and os.path.isfile(log):
        with open(log, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for ln in lines:
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            kind = ev.get("ev")
            if kind == "search":
                searches += 1
                hits += len(ev.get("hits") or [])
            elif kind == "pick":
                picks += 1
                pid = ev.get("part_id") or "?"
                slot = parts.setdefault(pid, {"picks": [],
                                              "citations": 0})
                slot["picks"].append(ev.get("ref", ""))
            elif kind == "citations":
                refs = ev.get("refs") or []
                cites += len(refs)
                pid = ev.get("part_id") or "?"
                slot = parts.setdefault(pid, {"picks": [],
                                              "citations": 0})
                slot["citations"] += len(refs)
    line = ("STATUS searches=%d hits_seen=%d picks=%d citations=%d"
            % (searches, hits, picks, cites))
    return {"searches": searches, "hits_seen": hits, "picks": picks,
            "citations": cites, "parts": parts, "line": line}


def write_concepts(ctx, args):
    return _write_report(ctx, args, "concepts", validate_concepts)


def write_cases(ctx, args):
    return _write_report(ctx, args, "cases", validate_cases)


def query_graph(ctx, args):
    st = graph.get_status(ctx["agent_dir"])
    if st["state"] != "indexed":
        return {"state": st["state"], "reason": st.get("reason", ""),
                "hint": "read input_md directly instead"}
    ans = graph.query(ctx["agent_dir"], args.get("question", ""))
    out = {"state": "indexed", "answer": ans}
    if isinstance(ans, dict):
        for k in ("profile", "model", "dim"):
            if ans.get(k) is not None:
                out[k] = ans[k]
    return out


def _entry_for(ctx, ref):
    """The Source entry for this run: explicit ref, else the order's."""
    if not ref:
        ref = pc.order_entry_ref(ctx.get("order_id", ""))
    if not ref:
        return None, {"error": "no Source PC entry for this order"}
    try:
        return pc.load_entry_by_ref(ref), None
    except (OSError, ValueError, KeyError) as exc:
        return None, {"error": "cannot load entry: %s" % exc}


def _recipients_error(ctx, entry, ref=None):
    """None when ctx may read (ref None: list the entry); else the
    refusal dict. Parts-limited rows open listed parts only."""
    if ref is None:
        ok = pc.may_read(entry, (ctx or {}).get("producer", ""),
                         (ctx or {}).get("order_id", ""))
    else:
        ok = pc.entry_parts_allow(entry, (ctx or {}).get("producer",
                                                         ""),
                                  (ctx or {}).get("order_id", ""), ref)
    return None if ok else {"error": "no access to this item"}


def pc_list_source(ctx, args):
    entry, err = _entry_for(ctx, (args or {}).get("ref"))
    if err:
        return err
    err = _recipients_error(ctx, entry)
    if err:
        return err
    return {"ref": entry.get("ref", ""), "title": entry.get("title", ""),
            "sections": [{"n": s["n"], "heading": s["heading"],
                          "paras": s["count"],
                          "non_content": bool(s.get("non_content")),
                          "ref": entry["ref"] + "#s" + s["n"]}
                         for s in entry.get("sections", [])],
            "figures": len(entry.get("figures", [])),
            "tables": len(entry.get("tables", []))}


def pc_read_source(ctx, args):
    args = args or {}
    entry, err = _entry_for(ctx, args.get("ref"))
    if err:
        return err
    if args.get("ref"):
        try:
            pcname, _id, frag = pc.parse_ref(args["ref"])
        except ValueError:
            return {"error": "bad ref"}
        if pcname != "source":
            return {"error": "pc_read_source reads Source only; "
                             "use open_ref"}
        want = args["ref"]
    elif not args.get("section"):
        return {"error": "give section or ref"}
    else:
        want = entry["ref"] + "#s" + args["section"].strip()
        frag = "s" + args["section"].strip()
    err = _recipients_error(ctx, entry, want)
    if err:
        return err
    if not frag:
        return _full_entry_text(entry, args)
    try:
        out = pc.open_ref(entry, want)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc)}
    cap = int(args.get("max_chars", 8000))
    text = out.get("text", "")
    if len(text) > cap:
        out["text"] = text[:cap]
        out["truncated"] = len(text) - cap
    return out


def _full_entry_text(entry, args):
    """Whole entry as markdown (content sections, exact headings).
    Capped like any other read; truncation says how much is missing."""
    try:
        cap = int((args or {}).get("max_chars", 60000))
    except (TypeError, ValueError):
        cap = 60000
    text = pc.entry_markdown(entry)
    out = {"kind": "full-text", "ref": entry.get("ref", ""),
           "title": entry.get("title", ""),
           "provenance": {"title": entry.get("title", ""),
                           "origin_file": entry.get("origin_file", "")}}
    if len(text) > cap:
        out["text"] = text[:cap]
        out["truncated"] = len(text) - cap
    else:
        out["text"] = text
    return out


def _held_tools(ctx):
    try:
        with open(os.path.join((ctx or {}).get("agent_dir", ""),
                               "agent.json"), encoding="utf-8") as f:
            return json.load(f).get("tools", [])
    except (OSError, ValueError):
        return []


def _need_grant(ctx, pcname):
    need = "pc_read_" + pcname
    if need not in _held_tools(ctx):
        return {"error": "no read grant for %s" % pcname}
    return None


def open_ref(ctx, args):
    """Any-PC ref reader with grant enforcement: the caller must hold
    pc_read_<pc>. Grants are the tools listed in its agent.json.
    Theory/Article refs are picks-scoped (§13.2)."""
    ref = (args or {}).get("ref", "")
    try:
        pcname, _id, _frag = pc.parse_ref(ref)
    except ValueError:
        return {"error": "bad ref"}
    err = _need_grant(ctx, pcname)
    if err:
        return err
    err = _pick_scope_error(ctx, pcname, ref)
    if err:
        return err
    try:
        entry = pc.load_entry_by_ref(ref)
    except (OSError, KeyError, ValueError) as exc:
        return {"error": str(exc)}
    err = _recipients_error(ctx, entry, ref)
    if err:
        return err
    try:
        return pc.open_ref(entry, ref)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc)}


# ---- Tavily web research + picks (§13.1-13.3) ----
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
PICKERS = {"theory": "explain_cleo", "article": "case_rex"}
FETCH_CAP = 60000


def _tavily_key():
    return os.environ.get("TAVILY_API_KEY", "")


def _tavily_post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("tavily %s: %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError("tavily unreachable: %s" % exc)


def _tavily_search(query, limit):
    key = _tavily_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY missing: add it to .env")
    data = _tavily_post(TAVILY_SEARCH_URL,
                        {"api_key": key, "query": query,
                         "search_depth": "basic", "max_results": limit,
                         "include_answer": False})
    return [{"title": h.get("title", ""), "url": h.get("url", ""),
             "snippet": (h.get("content") or "")[:300]}
            for h in data.get("results", [])[:limit]]


def _tavily_extract(url):
    key = _tavily_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY missing: add it to .env")
    data = _tavily_post(TAVILY_EXTRACT_URL,
                        {"api_key": key, "urls": [url],
                         "extract_depth": "basic"})
    res = (data.get("results") or [{}])[0]
    text = res.get("content") or res.get("raw_content") or ""
    if not text.strip():
        fails = data.get("failed_results", [])
        why = fails[0].get("error", "empty") if fails else "empty"
        raise RuntimeError("extract failed for %s: %s" % (url, why))
    return {"title": res.get("title", ""), "text": text}


def _log_research(ctx, obj):
    d = (ctx or {}).get("run_dir", "")
    if not d:
        return
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "research.jsonl"), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _order_picks(order_id):
    """Union of picks[].ref across concepts/cases results for the
    order. The reports ARE the pick set (§13.2); no new store."""
    out = set()
    if not order_id:
        return out
    try:
        rids = os.listdir(os.path.join(pc._base(None), "runs"))
    except OSError:
        return out
    for rid in rids:
        rd = os.path.join(pc._base(None), "runs", rid)
        try:
            with open(os.path.join(rd, "STATUS.json"),
                      encoding="utf-8") as f:
                if json.load(f).get("order_id") != order_id:
                    continue
        except (OSError, ValueError):
            continue
        for ag in ("explain_cleo", "case_rex"):
            try:
                with open(os.path.join(rd, ag, "result.json"),
                          encoding="utf-8") as f:
                    res = json.load(f)
            except (OSError, ValueError):
                continue
            for cat in res.get("categories", {}).values():
                data = (cat or {}).get("data", {})
                for part in data.get("parts", []):
                    for pk in part.get("picks", []):
                        if pk.get("ref"):
                            out.add(pk["ref"])
    return out


def _pick_scope_error(ctx, pcname, ref):
    """None when ctx may open ref; else an error dict. The picker
    reads the whole PC; everyone else only entries picked for their
    order (§13.2)."""
    if pcname not in PICKERS:
        return None
    if (ctx or {}).get("producer") == PICKERS[pcname]:
        return None
    try:
        epc, eid, _frag = pc.parse_ref(ref)
    except ValueError:
        return {"error": "bad ref"}
    if epc != pcname:
        return {"error": "bad ref"}
    if pc.entry_ref(epc, eid) not in _order_picks(
            (ctx or {}).get("order_id")):
        return {"error": "not picked for this order"}
    return None


def _domain(url):
    try:
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _first_line(text):
    for ln in (text or "").splitlines():
        if ln.strip() and len(ln.strip()) <= 160:
            return ln.strip()
    return ""


def _pc_search(ctx, args, tool):
    q = ((args or {}).get("query") or "").strip()
    if not q:
        return {"error": "give query"}
    try:
        limit = min(10, max(1, int((args or {}).get("max_results", 5))))
    except (TypeError, ValueError):
        limit = 5
    try:
        hits = _tavily_search(q, limit)
    except RuntimeError as exc:
        return {"error": str(exc)}
    _log_research(ctx, {"ev": "search", "query": q, "tool": tool,
                        "hits": hits})
    return {"query": q, "hits": hits}


def pc_search_theory(ctx, args):
    """Web search for theory (Tavily basic). Hits stay in the run log;
    nothing is stored until picked."""
    return _pc_search(ctx, args, "pc_search_theory")


def pc_search_articles(ctx, args):
    """Web search for cases/articles (Tavily basic). Hits stay in the
    run log; nothing is stored until picked."""
    return _pc_search(ctx, args, "pc_search_articles")


def _pc_pick(ctx, args, pcname):
    args = args or {}
    missing = [k for k in ("url", "part_id", "why_important",
                           "how_to_use")
               if not (args.get(k) or "").strip()]
    if missing:
        return {"error": "missing: " + ", ".join(missing)}
    url = args["url"].strip()
    try:
        got = _tavily_extract(url)
    except RuntimeError as exc:
        return {"error": str(exc)}
    text = got["text"]
    trunc = len(text) - FETCH_CAP if len(text) > FETCH_CAP else 0
    if trunc:
        text = text[:FETCH_CAP]
    title = got.get("title", "").strip() or _first_line(text) or url
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    fn = pc.ingest_theory if pcname == "theory" else pc.ingest_article
    try:
        r = fn(url, title, _domain(url), "", now,
               (ctx or {}).get("producer", ""), text)
    except (OSError, ValueError) as exc:
        return {"error": "ingest failed: %s" % exc}
    ev = {"ev": "pick", "ref": r["ref"], "url": url,
          "part_id": args["part_id"].strip(),
          "picked_by": (ctx or {}).get("producer", ""),
          "order_id": (ctx or {}).get("order_id", ""),
          "run_id": (ctx or {}).get("run_id", ""),
          "reason": args["why_important"].strip(),
          "how_to_use": args["how_to_use"].strip(),
          "duplicate": r["duplicate"]}
    if trunc:
        ev["truncated_from"] = trunc + FETCH_CAP
    _log_research(ctx, ev)
    rec_err = ""
    try:
        pc.set_recipients(pcname, r["doc_id"],
                           (ctx or {}).get("order_id", ""),
                           [(ctx or {}).get("producer", "")],
                           (ctx or {}).get("producer", ""),
                           kind="full")
    except (OSError, ValueError) as exc:
        rec_err = str(exc)
    out = {"ref": r["ref"], "doc_id": r["doc_id"],
           "duplicate": r["duplicate"], "title": r["title"],
           "paras": r["paras"], "chars": r["chars"],
           "supersedes": r["supersedes"]}
    if rec_err:
        out["recipients_error"] = rec_err
    return out


def pc_pick_theory(ctx, args):
    """Pick a search hit into the Theory PC (full ingest) and get its
    ref. Pick only what will be cited or read by later agents."""
    return _pc_pick(ctx, args, "theory")


def pc_pick_article(ctx, args):
    """Pick a search hit into the Article PC (full ingest) and get its
    ref. Pick only what will be cited or read by later agents."""
    return _pc_pick(ctx, args, "article")


def _pc_read_web(ctx, args, pcname):
    args = args or {}
    err = _need_grant(ctx, pcname)
    if err:
        return err
    ref = (args.get("ref") or "").strip()
    if not ref:
        return {"error": "give ref"}
    try:
        rpc, _id, _frag = pc.parse_ref(ref)
    except ValueError:
        return {"error": "bad ref"}
    if rpc != pcname:
        return {"error": "pc_read_%s reads %s only; use open_ref"
                         % (pcname, pcname)}
    err = _pick_scope_error(ctx, pcname, ref)
    if err:
        return err
    try:
        entry = pc.load_entry_by_ref(ref)
    except (OSError, KeyError, ValueError) as exc:
        return {"error": str(exc)}
    err = _recipients_error(ctx, entry, ref)
    if err:
        return err
    try:
        out = pc.open_ref(entry, ref)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc)}
    try:
        cap = int(args.get("max_chars", 8000))
    except (TypeError, ValueError):
        cap = 8000
    text = out.get("text", "")
    if len(text) > cap:
        out["text"] = text[:cap]
        out["truncated"] = len(text) - cap
    return out


def pc_read_theory(ctx, args):
    """Read a Theory PC ref verbatim with provenance. Refused unless
    listed as a recipient; later agents also need this order's pick."""
    return _pc_read_web(ctx, args, "theory")


def pc_read_article(ctx, args):
    """Read an Article PC ref verbatim with provenance. Refused unless
    listed as a recipient; later agents also need this order's pick."""
    return _pc_read_web(ctx, args, "article")


# ---- Sam's intake tools (§8.1): send PDF, set recipients ----
SEND_TIMEOUT = 900  # blocking worker wait per pc_send_source call
INTAKE_PRODUCER = "sales_sam"


def _order_meta(order_id):
    p = os.path.join(pc._base(None), "orders", order_id or "",
                     "meta.json")
    try:
        with open(p, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None, None
    return (meta if isinstance(meta, dict) else None), p


def _indexed(pcname, prof, doc_id):
    try:
        with open(os.path.join(pc.index_dir(pcname, prof),
                               "index.json"), encoding="utf-8") as f:
            return doc_id in json.load(f).get("entries", [])
    except (OSError, ValueError):
        return False


def _worker_reason(edir):
    """Last failure reason from the entry log (best effort)."""
    try:
        with open(os.path.join(edir, "log.jsonl"),
                  encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    for ln in reversed(lines[-5:]):
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if ev.get("ev") in ("failed", "map_failed") and ev.get("error"):
            return str(ev["error"])[:200]
    return ""


def pc_send_source(ctx, args):
    """Send this order's attached PDF to the Source PC: parse, ingest,
    build the map, index. Returns the entry ref + counts. Sam only;
    idempotent (same PDF = same ref, finished stages are skipped)."""
    ctx = ctx or {}
    if ctx.get("producer") != INTAKE_PRODUCER:
        return {"error": "pc_send_source is Sam's tool"}
    order_id = ctx.get("order_id", "")
    meta, meta_p = _order_meta(order_id)
    if meta is None:
        return {"error": "no such order: %r" % order_id}
    base = pc._base(None)
    fname = (meta.get("files", {}) or {}).get("source", "source.pdf")
    pdf_p = os.path.join(base, "orders", order_id, fname)
    try:
        with open(pdf_p, "rb") as f:
            raw = f.read()
    except OSError:
        return {"error": "order has no attached PDF yet"}
    try:
        pages, images, tables, skipped, marks = pdfingest.pdf_parse(raw)
    except RuntimeError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - broken PDF, reported
        return {"error": "cannot parse PDF: %s" % exc}
    if not "\n\n".join(pages).strip():
        return {"error": "no extractable text in PDF"}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        r = pc.ingest_source(
            order_id, (meta.get("files", {}) or {}).get(
                "upload_name", fname),
            now, ctx.get("producer", ""), pages, images, tables,
            skipped, marks=marks)
    except (OSError, ValueError) as exc:
        return {"error": "ingest failed: %s" % exc}
    try:
        pc.set_recipients("source", r["doc_id"], order_id,
                           [ctx.get("producer", "")],
                           ctx.get("producer", ""), kind="full")
    except (OSError, ValueError) as exc:
        return {"error": "ingested %s but cannot list recipients: %s"
                         % (r["ref"], exc)}
    try:
        prof = graph._adapter().embed_settings()["profile"]
    except (RuntimeError, KeyError):
        prof = "jetson"
    mp = pc.load_map_by_ref(r["ref"])
    map_done = isinstance(mp, dict) and mp.get("status") == "done"
    indexed = _indexed("source", prof, r["doc_id"])
    worker_note = "skipped (map + index done)"
    warning = ""
    jetson_down = ""
    if prof == "jetson":
        try:
            graph._adapter().jetson_health()
        except (RuntimeError, ImportError, OSError) as exc:
            jetson_down = str(exc)
    if (args or {}).get("build", "all") == "skip":
        worker_note = "skipped (build=skip)"
    if jetson_down and map_done and not indexed \
            and (args or {}).get("build", "all") != "skip":
        worker_note = "skipped (map done, index skipped: jetson down)"
        warning = ("index skipped (%s); the map is done so the crew "
                   "can read (REBUILD INDEX when the Jetson is up)"
                   % jetson_down)
    if not (map_done and indexed) and not warning \
            and (args or {}).get("build", "all") != "skip":
        if jetson_down:
            mode = "noindex"
        else:
            mode = "index" if map_done else ("noindex" if indexed
                                             else "all")
        try:
            done = subprocess.run(
                [sys.executable, os.path.join("scripts",
                                              "pc_worker.py"),
                 r["doc_id"], mode, "source"],
                cwd=base, capture_output=True, timeout=SEND_TIMEOUT)
            worker_note = "mode %s exit %d" % (mode, done.returncode)
        except subprocess.TimeoutExpired:
            worker_note = "mode %s timed out after %ds" \
                % (mode, SEND_TIMEOUT)
            warning = ("worker timed out; map/index may still be "
                       "pending (REBUILD from the PC page)")
        if not warning:
            mp = pc.load_map_by_ref(r["ref"])
            map_done = isinstance(mp, dict) \
                and mp.get("status") == "done"
            indexed = _indexed("source", prof, r["doc_id"])
            if done.returncode != 0 and not map_done:
                return {"error": "map build failed: %s"
                                 % (_worker_reason(
                                     pc.entry_dir("source",
                                                  r["doc_id"]))
                                    or worker_note)}
            if done.returncode != 0:
                warning = ("index failed (%s); the map is done so "
                           "the crew can read" % (
                               _worker_reason(pc.entry_dir(
                                   "source", r["doc_id"]))
                               or worker_note))
    try:
        entry = pc.load_entry_by_ref(r["ref"])
    except (OSError, ValueError, KeyError) as exc:
        return {"error": "sent entry missing: %s" % exc}
    if ctx.get("run_dir"):
        try:
            os.makedirs(ctx["run_dir"], exist_ok=True)
            with open(os.path.join(ctx["run_dir"], "send.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"ref": r["ref"], "doc_id": r["doc_id"],
                           "at": now}, f)
        except OSError as exc:
            return {"error": "cannot record send: %s" % exc}
    meta.setdefault("files", {}).update({
        "pc_ref": r["ref"], "pc_duplicate": r["duplicate"],
        "pc_title": r["title"], "pc_sections": r["sections"],
        "pc_chars": r["chars"], "pc_figures": r["figures"],
        "pc_tables": r["tables"]})
    try:
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        return {"error": "cannot record pc_ref: %s" % exc}
    out = {"ref": r["ref"], "doc_id": r["doc_id"],
           "duplicate": r["duplicate"], "title": r["title"],
           "sections": [{"n": s["n"], "heading": s["heading"]}
                        for s in entry.get("sections", [])],
           "section_count": r["sections"], "paras": r["paras"],
           "chars": r["chars"], "figures": r["figures"],
           "tables": r["tables"], "map": "done" if map_done
           else "pending", "index": indexed, "worker": worker_note}
    if warning:
        out["warning"] = warning
    return out


def pc_set_recipients(ctx, args):
    """Set who receives this order's Source entry (merged per agent).
    Sam only; the entry must be sent first."""
    ctx = ctx or {}
    if ctx.get("producer") != INTAKE_PRODUCER:
        return {"error": "pc_set_recipients is Sam's tool"}
    agents = (args or {}).get("agents")
    if not isinstance(agents, list) or not agents \
            or any(not isinstance(a, str) or not a for a in agents):
        return {"error": "give agents: [agent ids]"}
    aroot = os.path.dirname(os.path.abspath(ctx.get("agent_dir", "")
                                             or "agents"))
    if not os.path.isdir(aroot):
        aroot = os.path.join(pc._base(None), "agents")
    bad = [a for a in agents
           if not os.path.isfile(os.path.join(aroot, a, "agent.json"))]
    if bad:
        return {"error": "unknown agents: %s (use agent ids, e.g. "
                         "pd_marty, explain_cleo, case_rex)" % ", ".join(bad)}
    order_id = ctx.get("order_id", "")
    ref = pc.order_entry_ref(order_id)
    if not ref:
        return {"error": "no Source entry for this order: call "
                         "pc_send_source first"}
    try:
        _pcn, doc_id, _frag = pc.parse_ref(ref)
        rows = pc.set_recipients("source", doc_id, order_id, agents,
                                  ctx.get("producer", ""))
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}
    return {"ref": ref,
            "recipients": [r for r in rows
                            if r.get("order_id") == order_id]}


# Writer tool -> run output file. The server keeps agent.json io.output
# in sync with the employee's single write_* tool. Since the Q6 cutover
# every run writes result.json (one envelope, categories inside).
OUTPUTS = {
    "write_draft": "draft.json",
    "write_structure": "result.json",
    "write_request": "result.json",
}

TOOLS = {
    "read_md_section": (
        read_md_section,
        "Read the input markdown file: lists sections, returns head or one section.",
        {"type": "object",
         "properties": {"path": {"type": "string"},
                        "section": {"type": "string"},
                        "max_chars": {"type": "integer"}},
         "additionalProperties": False},
    ),
    "write_draft": (
        write_draft,
        "Save the finished storyboard draft. Fails unless it passes validation.",
        {"type": "object",
         "properties": {"draft": {"type": "object"}},
         "required": ["draft"], "additionalProperties": False},
    ),
    "write_structure": (
        write_structure,
        "Save this run's result.json (concept + structure categories). "
        "Fails unless the concept is complete and every section is "
        "mapped in source order with refs and neighbour links.",
        {"type": "object",
         "properties": {"result": {"type": "object"}},
         "required": ["result"], "additionalProperties": False},
    ),
    "write_request": (
        write_request,
        "Save this run's result.json (request + source categories). "
        "The source pointer is built from the sent entry. Fails "
        "unless the request validates, the source was sent here, "
        "and recipients are set.",
        {"type": "object",
         "properties": {"request": {"type": "object"}},
         "required": ["request"], "additionalProperties": False},
    ),
    "write_concepts": (
        write_concepts,
        "Save Cleo's theory report as this run's result.json "
        "(concepts category). Fails unless every claim cites a "
        "verbatim passage and the picks match this run's picks.",
        {"type": "object",
         "properties": {"concepts": {"type": "object"}},
         "required": ["concepts"], "additionalProperties": False},
    ),
    "write_cases": (
        write_cases,
        "Save Rex's case report as this run's result.json (cases "
        "category). Fails unless every claim cites a verbatim passage "
        "and the picks match this run's picks.",
        {"type": "object",
         "properties": {"cases": {"type": "object"}},
         "required": ["cases"], "additionalProperties": False},
    ),
    "research_status": (
        research_status,
        "Show this run's retrieval status: searches, hits seen, picks "
        "made, citations written, per part. Call it before writing.",
        {"type": "object", "properties": {},
         "additionalProperties": False},
    ),
    "query_graph": (
        query_graph,
        "Ask the employee knowledge graph. Honest when no index exists yet.",
        {"type": "object",
         "properties": {"question": {"type": "string"}},
         "required": ["question"], "additionalProperties": False},
    ),
    "pc_list_source": (
        pc_list_source,
        "List the Source PC entry for this order: sections with refs, "
        "figure/table counts. Refused unless you are a recipient.",
        {"type": "object",
         "properties": {"ref": {"type": "string"}},
         "additionalProperties": False},
    ),
    "pc_read_source": (
        pc_read_source,
        "Read one Source PC section or passage verbatim with "
        "provenance, or the whole entry when ref has no #part. "
        "Give section (e.g. 1.1) or a pc://source ref. Refused "
        "unless this order lists you as a recipient.",
        {"type": "object",
         "properties": {"section": {"type": "string"},
                        "ref": {"type": "string"},
                        "max_chars": {"type": "integer"}},
         "additionalProperties": False},
    ),
    "pc_send_source": (
        pc_send_source,
        "Send this order's attached PDF to the Source PC (parse, "
        "ingest, map, index) and get the entry ref. Sam only; "
        "idempotent. Call once, then pc_set_recipients.",
        {"type": "object", "properties": {},
         "additionalProperties": False},
    ),
    "pc_set_recipients": (
        pc_set_recipients,
        "Set which crew members receive this order's Source entry "
        "(merged). Sam only; send first.",
        {"type": "object",
         "properties": {"agents": {"type": "array",
                                   "items": {"type": "string"}}},
         "required": ["agents"], "additionalProperties": False},
    ),
    "open_ref": (
        open_ref,
        "Open any stable pc:// ref verbatim with provenance. Refused "
        "without that PC's read grant or a recipient listing; "
        "Theory/Article refs are picks-scoped.",
        {"type": "object",
         "properties": {"ref": {"type": "string"}},
         "required": ["ref"], "additionalProperties": False},
    ),
    "pc_search_theory": (
        pc_search_theory,
        "Web search for theory (Tavily basic). Hits stay in the run "
        "log; nothing is stored until picked.",
        {"type": "object",
         "properties": {"query": {"type": "string"},
                        "max_results": {"type": "integer"}},
         "required": ["query"], "additionalProperties": False},
    ),
    "pc_search_articles": (
        pc_search_articles,
        "Web search for cases/articles (Tavily basic). Hits stay in "
        "the run log; nothing is stored until picked.",
        {"type": "object",
         "properties": {"query": {"type": "string"},
                        "max_results": {"type": "integer"}},
         "required": ["query"], "additionalProperties": False},
    ),
    "pc_pick_theory": (
        pc_pick_theory,
        "Pick a search hit into the Theory PC (full ingest: fetch, "
        "clean, id, addresses, map, index) and get its ref.",
        {"type": "object",
         "properties": {"url": {"type": "string"},
                        "part_id": {"type": "string"},
                        "why_important": {"type": "string"},
                        "how_to_use": {"type": "string"}},
         "required": ["url", "part_id", "why_important", "how_to_use"],
         "additionalProperties": False},
    ),
    "pc_pick_article": (
        pc_pick_article,
        "Pick a search hit into the Article PC (full ingest: fetch, "
        "clean, id, addresses, map, index) and get its ref.",
        {"type": "object",
         "properties": {"url": {"type": "string"},
                        "part_id": {"type": "string"},
                        "why_important": {"type": "string"},
                        "how_to_use": {"type": "string"}},
         "required": ["url", "part_id", "why_important", "how_to_use"],
         "additionalProperties": False},
    ),
    "pc_read_theory": (
        pc_read_theory,
        "Read a Theory PC ref verbatim with provenance. Later "
        "agents: only entries picked for their order.",
        {"type": "object",
         "properties": {"ref": {"type": "string"},
                        "max_chars": {"type": "integer"}},
         "required": ["ref"], "additionalProperties": False},
    ),
    "pc_read_article": (
        pc_read_article,
        "Read an Article PC ref verbatim with provenance. Later "
        "agents: only entries picked for their order.",
        {"type": "object",
         "properties": {"ref": {"type": "string"},
                        "max_chars": {"type": "integer"}},
         "required": ["ref"], "additionalProperties": False},
    ),
}


def get_tools(agent_dir):
    """Builtin registry + per-employee tools/<name>.py (D33, auto-discovered)."""
    merged = dict(TOOLS)
    tdir = os.path.join(agent_dir, "tools")
    if not os.path.isdir(tdir):
        return merged
    for fn in sorted(os.listdir(tdir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        spec = importlib.util.spec_from_file_location(
            "tool_" + name, os.path.join(tdir, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if (getattr(mod, "NAME", None) != name
                or not callable(getattr(mod, "run", None))
                or not isinstance(getattr(mod, "SCHEMA", None), dict)):
            raise ValueError("bad custom tool file: %s" % fn)
        merged[name] = (mod.run, getattr(mod, "DESC", "custom tool " + name),
                        mod.SCHEMA)
    return merged
