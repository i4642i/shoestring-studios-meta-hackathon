"""Tool registry + builtin tools. Stdlib only.

Each tool takes (ctx, args) and returns JSON-serializable data.
ctx: {"run_dir":..., "agent_dir":..., "input_md":...}
"""
import importlib.util
import json
import os
import time
import urllib.error
import urllib.request

from . import graph
from . import pc
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


def write_structure(ctx, args):
    bundle = args.get("result")
    if not isinstance(bundle, dict):
        return {"ok": False, "errors": [
            "call with {result: {concept: {...}, structure: {...}}}"]}
    errors = validate_concept(bundle.get("concept"))
    errors += validate_structure(bundle.get("structure"),
                                 ctx.get("input_md"))
    if errors:
        return {"ok": False, "errors": errors}
    return _save_categories(ctx, {"concept": bundle["concept"],
                                  "structure": bundle["structure"]})


def write_request(ctx, args):
    obj = args.get("request")
    errors = validate_request(obj)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "request", obj)


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


def _write_report(ctx, args, category, validator):
    obj = args.get(category)
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["call with {%s: {...}}" % category]}
    errors = validator(obj)
    if errors:
        return {"ok": False, "errors": errors}
    for i, p in enumerate(obj["parts"]):
        where = "%s.parts[%d]" % (category, i)
        for cw, cl in _claims_of(category, p):
            for n, cit in enumerate((cl or {}).get("citations") or []):
                if not isinstance(cit, dict):
                    continue
                _check_quote(errors, cit.get("ref"), cit.get("quote"),
                             "%s.%s.citations[%d]" % (where, cw, n))
        for m, pk in enumerate(p.get("picks") or []):
            if not isinstance(pk, dict):
                continue
            ev = pk.get("evidence") or {}
            if isinstance(ev, dict):
                _check_quote(errors, ev.get("ref"), ev.get("quote"),
                             "%s.picks[%d].evidence" % (where, m))
    if errors:
        return {"ok": False, "errors": errors}
    got = _report_pick_refs(obj)
    want = _run_pick_refs(ctx)
    for ref in sorted(got - want):
        errors.append("pick %s was never picked in this run" % ref)
    for ref in sorted(want - got):
        errors.append("picked %s is missing from the report" % ref)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, category, obj)


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


def pc_list_source(ctx, args):
    entry, err = _entry_for(ctx, (args or {}).get("ref"))
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
            pcname, _id, _frag = pc.parse_ref(args["ref"])
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
        return pc.open_ref(entry, ref)
    except (OSError, KeyError, ValueError) as exc:
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
    return {"ref": r["ref"], "doc_id": r["doc_id"],
            "duplicate": r["duplicate"], "title": r["title"],
            "paras": r["paras"], "chars": r["chars"],
            "supersedes": r["supersedes"]}


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
        out = pc.open_ref(entry, ref)
    except (OSError, KeyError, ValueError) as exc:
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
    """Read a Theory PC ref verbatim with provenance. Later agents:
    only entries picked for their order."""
    return _pc_read_web(ctx, args, "theory")


def pc_read_article(ctx, args):
    """Read an Article PC ref verbatim with provenance. Later agents:
    only entries picked for their order."""
    return _pc_read_web(ctx, args, "article")


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
        "Save the video production request for an order as this run's "
        "result.json (request category). Fails unless all 5 intake "
        "answers and production notes validate.",
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
        "figure/table counts.",
        {"type": "object",
         "properties": {"ref": {"type": "string"}},
         "additionalProperties": False},
    ),
    "pc_read_source": (
        pc_read_source,
        "Read one Source PC section or passage verbatim with provenance. "
        "Give section (e.g. 1.1) or a pc://source ref.",
        {"type": "object",
         "properties": {"section": {"type": "string"},
                        "ref": {"type": "string"},
                        "max_chars": {"type": "integer"}},
         "additionalProperties": False},
    ),
    "open_ref": (
        open_ref,
        "Open any stable pc:// ref verbatim with provenance. Refused "
        "without that PC's read grant; Theory/Article refs are "
        "picks-scoped.",
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
