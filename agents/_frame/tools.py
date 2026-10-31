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

REMOTION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))),
    "video", "remotion")


from . import graph
from . import pc
from . import pdfingest
from . import results
from .media import MEDIA_TOOLS
from .schemas import (VOICE_MAX_ATTEMPTS, list_headings,
                      validate_anim_picks, validate_cases,
                      validate_concept, validate_concepts,
                      validate_draft, validate_gen_picks,
                      validate_narration, validate_photo_picks,
                      validate_render_log, validate_request,
                      validate_slide_draft, validate_storyboard,
                      validate_storyboard_draft,
                      validate_storyboard_table, validate_structure,
                      validate_style_guide)


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


def _received_data(ctx, category):
    """First received payload for a category in this run (flow
    lines), or {} when nothing arrived (ad-hoc runs)."""
    d = (ctx or {}).get("run_dir", "")
    if not d or not os.path.isdir(d):
        return {}
    for fn in sorted(os.listdir(d)):
        if not (fn.startswith("received.") and fn.endswith(
                ".%s.json" % category)):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                data = json.load(f).get("data", {})
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _readable_ref(errors, ref, producer, order_id, where):
    """A material ref opens only for a listed member (parts-aware)."""
    if not isinstance(ref, str) or not ref.strip():
        errors.append("%s: missing ref" % where)
        return
    try:
        rpc, rid, _frag = pc.parse_ref(ref)
    except ValueError:
        errors.append("%s: bad ref %r" % (where, ref))
        return
    try:
        entry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid))
    except (OSError, ValueError, KeyError) as exc:
        errors.append("%s: unknown entry for %r (%s)"
                      % (where, ref, exc))
        return
    if not pc.entry_parts_allow(entry, producer, order_id, ref):
        errors.append("%s: %r is not listed for you" % (where, ref))


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
            entry = pc.load_entry_by_ref(sref)
            check = pc.entry_markdown(entry)
            if not pc.may_read(entry, ctx.get("producer", ""),
                               ctx.get("order_id", "")):
                errors.append("source_ref %r is not listed for this "
                              "run" % (sref,))
        except (OSError, ValueError, KeyError):
            pass
    errors += validate_structure(bundle.get("structure"), check)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_categories(ctx, {"concept": bundle["concept"],
                                  "structure": bundle["structure"]})


def write_request(ctx, args):
    """Save Sam's request report. Needs send.json (pc_send_source ran
    here) and a non-empty recipient list for this order. The source
    pointer is NOT a category: the crew gets the entry through the
    order's pc_ref plus recipient rows."""
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
    return _save_categories(ctx, {"request": obj})


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
    if kind == "equation":
        # open_ref blanks latex/context for unchecked transcriptions,
        # so only checked formulas are quotable, like checked tables.
        bits = [passage.get("latex", ""), passage.get("context", "")]
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


def write_storyboard_draft(ctx, args):
    """Ash's scene plan: shape + times vs the received structure,
    verbatim citations, readable materials, every pick used or
    explained, then the handoff lists are applied."""
    obj = (args or {}).get("storyboard_draft")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": [
            "call with {storyboard_draft: {...}}"]}
    struct = _received_data(ctx, "structure")
    if not struct:
        return {"ok": False, "errors": [
            "no structure received in this run"]}
    errors = validate_storyboard_draft(obj, struct)
    if errors:
        return {"ok": False, "errors": errors}
    producer = (ctx or {}).get("producer", "")
    order_id = (ctx or {}).get("order_id", "")
    for i, sc in enumerate(obj["scenes"]):
        where = "scenes[%d]" % i
        for j, npt in enumerate(sc.get("narration_points", [])):
            for n, cit in enumerate((npt or {}).get("citations",
                                                    []) or []):
                if not isinstance(cit, dict):
                    continue
                _check_quote(errors, cit.get("ref"),
                             cit.get("quote"),
                             "%s.narration_points[%d].citations[%d]"
                             % (where, j, n))
        for j, m in enumerate(sc.get("materials", [])):
            if not isinstance(m, dict):
                continue
            _readable_ref(errors, m.get("ref"), producer, order_id,
                          "%s.materials[%d]" % (where, j))
            try:
                rpc, _rid, _frag = pc.parse_ref(m.get("ref", ""))
                if rpc != m.get("from"):
                    errors.append("%s.materials[%d].from %r != ref "
                                  "PC %r" % (where, j, m.get("from"),
                                             rpc))
            except ValueError:
                pass
    if errors:
        return {"ok": False, "errors": errors}
    picks = _report_pick_refs(_received_data(ctx, "concepts")) \
        | _report_pick_refs(_received_data(ctx, "cases"))
    if picks:
        used = set()
        for sc in obj["scenes"]:
            for key in ("materials", "handoff"):
                for it in sc.get(key, []) or []:
                    if not isinstance(it, dict):
                        continue
                    try:
                        rpc, rid, _frag = pc.parse_ref(
                            it.get("ref", ""))
                        used.add(pc.entry_ref(rpc, rid))
                    except ValueError:
                        continue
        explained = set()
        for j, u in enumerate(obj.get("unused_picks", []) or []):
            if not isinstance(u, dict):
                continue
            try:
                rpc, rid, _frag = pc.parse_ref(u.get("ref", ""))
                eref = pc.entry_ref(rpc, rid)
            except ValueError:
                errors.append("unused_picks[%d]: bad ref" % j)
                continue
            if eref not in picks:
                errors.append("unused_picks[%d] %s is not a pick of "
                              "this order" % (j, eref))
            else:
                explained.add(eref)
        for ref in sorted(picks - used - explained):
            errors.append("pick %s is neither used nor explained"
                          % ref)
    if errors:
        return {"ok": False, "errors": errors}
    applied = pc.apply_handoff(order_id, obj, set_by=producer or
                               "plan_ash")
    if "error" in applied:
        return {"ok": False, "errors": [applied["error"]]}
    return _save_category(ctx, "storyboard_draft", obj)


def write_storyboard(ctx, args):
    """Penn's cut descriptions v2 + style guide: exact cut match
    vs Wren's received narration, on-screen text ≤3 lines."""
    obj = (args or {}).get("storyboard")
    guide = (args or {}).get("style_guide")
    if not isinstance(obj, dict) or not isinstance(guide, dict):
        return {"ok": False, "errors": [
            "call with {storyboard: {...}, style_guide: {...}}"]}
    narr = _received_data(ctx, "narration")
    if not narr:
        return {"ok": False, "errors": [
            "no narration received in this run"]}
    errors = validate_storyboard(obj, narr)
    errors += ["style_guide: " + e
               for e in validate_style_guide(guide)]
    if errors:
        return {"ok": False, "errors": errors}
    return _save_categories(ctx, {"storyboard": obj,
                                  "style_guide": guide})


def write_narration(ctx, args):
    """Wren's cuts v2: tiling + fit math, digit lines cited, every
    citation verbatim and readable, every audio ref a stored Voice
    clip for this order."""
    obj = (args or {}).get("narration")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": ["call with {narration: {...}}"]}
    draft = _received_data(ctx, "storyboard_draft")
    if not draft:
        return {"ok": False, "errors": [
            "no storyboard_draft received in this run"]}
    errors = validate_narration(obj, draft)
    if errors:
        return {"ok": False, "errors": errors}
    producer = (ctx or {}).get("producer", "")
    order_id = (ctx or {}).get("order_id", "")
    for i, cut in enumerate(obj["cuts"]):
        for j, ln in enumerate(cut.get("lines", [])):
            if not isinstance(ln, dict):
                continue
            where = "cuts[%d].lines[%d]" % (i, j)
            cits = ln.get("citations", []) or []
            if any(ch.isdigit() for ch in str(ln.get("text", ""))) \
                    and not cits:
                errors.append("%s: a line with a number needs >=1 "
                              "citation" % where)
            for n, cit in enumerate(cits):
                if not isinstance(cit, dict):
                    continue
                _check_quote(errors, cit.get("ref"),
                             cit.get("quote"),
                             "%s.citations[%d]" % (where, n))
                _readable_ref(errors, cit.get("ref"), producer,
                              order_id,
                              "%s.citations[%d]" % (where, n))
        audio = cut.get("audio", {}) or {}
        _audio_ref_ok(errors, audio.get("voice_pc_ref"),
                      cut.get("cut_id"), order_id, "cuts[%d]" % i)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "narration", obj)


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
    pc_read_<pc> plus a recipient row for this order. Grants are the
    tools listed in its agent.json."""
    ref = (args or {}).get("ref", "")
    try:
        pcname, _id, _frag = pc.parse_ref(ref)
    except ValueError:
        return {"error": "bad ref"}
    err = _need_grant(ctx, pcname)
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
    listed as a recipient for this order."""
    return _pc_read_web(ctx, args, "theory")


def pc_read_article(ctx, args):
    """Read an Article PC ref verbatim with provenance. Refused unless
    listed as a recipient for this order."""
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
    """Grant map/full rows on one entry (merged per agent). The
    lister must hold a row on the entry for this order; only Sam
    grants full (on Source); map grants never widen a parts-limited
    row. ref defaults to this order's Source entry."""
    ctx = ctx or {}
    args = args or {}
    maps = args.get("map", [])
    fulls = args.get("full", [])
    for key, grp in (("map", maps), ("full", fulls)):
        if not isinstance(grp, list) \
                or any(not isinstance(a, str) or not a for a in grp):
            return {"error": "give %s: [agent ids]" % key}
    if not maps and not fulls:
        return {"error": "nothing to grant: give map and/or full lists"}
    producer = ctx.get("producer", "")
    order_id = ctx.get("order_id", "")
    ref = args.get("ref") or pc.order_entry_ref(order_id)
    if not ref:
        return {"error": "no entry: give ref, or send the Source first"}
    try:
        pcname, doc_id, _frag = pc.parse_ref(ref)
        entry = pc.load_entry_by_ref(ref)
    except (OSError, ValueError, KeyError) as exc:
        return {"error": str(exc)}
    mine = pc.entry_access(entry, producer, order_id)
    if mine is None:
        return {"error": "you hold no row on %s for this order" % ref}
    if fulls and (producer != INTAKE_PRODUCER or pcname != "source"):
        return {"error": "only Sam grants full (on Source)"}
    if pc.row_parts(mine):
        return {"error": "your row is parts-limited; granting the "
                         "whole entry would widen it"}
    aroot = os.path.dirname(os.path.abspath(ctx.get("agent_dir", "")
                                             or "agents"))
    if not os.path.isdir(aroot):
        aroot = os.path.join(pc._base(None), "agents")
    bad = [a for a in maps + fulls
           if not os.path.isfile(os.path.join(aroot, a, "agent.json"))]
    if bad:
        return {"error": "unknown agents: %s (use agent ids, e.g. "
                         "pd_marty, explain_cleo, case_rex)" % ", ".join(bad)}
    try:
        rows = entry.get("recipients", [])
        if maps:
            rows = pc.set_recipients(pcname, doc_id, order_id, maps,
                                     producer, kind="map")
        if fulls:
            rows = pc.set_recipients(pcname, doc_id, order_id, fulls,
                                     producer, kind="full")
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}
    return {"ref": entry.get("ref", ""),
            "recipients": [r for r in rows
                            if r.get("order_id") == order_id]}


# Writer tool -> run output file. The server keeps agent.json io.output
# in sync with the employee's single write_* tool. Since the Q6 cutover
# every run writes result.json (one envelope, categories inside).
OUTPUTS = {
    "write_draft": "draft.json",
    "write_structure": "result.json",
    "write_request": "result.json",
    "write_storyboard_draft": "result.json",
    "write_storyboard": "result.json",
    "write_narration": "result.json",
    "write_photo_picks": "result.json",
    "write_gen_picks": "result.json",
    "write_anim_picks": "result.json",
    "write_slide_draft": "result.json",
    "write_render_log": "result.json",
}

# ---- v8 cut writers, voice, slide render (appended) ----

def _audio_ref_ok(errors, ref, cut_id, order_id, where):
    try:
        rpc, _rid, frag = pc.parse_ref(ref or "")
    except ValueError:
        errors.append("%s: bad audio ref" % where)
        return
    if rpc != "voice" or frag != cut_id:
        errors.append("%s: audio ref must be this cut's Voice PC "
                      "clip" % where)
        return
    try:
        entry = pc.load_entry_by_ref(ref)
    except (OSError, ValueError, KeyError) as exc:
        errors.append("%s: cannot load voice clip: %s" % (where,
                                                          exc))
        return
    if entry.get("order_id") != order_id:
        errors.append("%s: voice clip is from another order"
                      % where)
    elif frag not in entry.get("cuts", {}):
        errors.append("%s: voice clip has no %s" % (where, frag))


def _checked_table_formula(errors, ref, where):
    try:
        entry = pc.load_entry_by_ref(ref)
        passage = pc.open_ref(entry, ref)
    except (OSError, ValueError, KeyError) as exc:
        errors.append("%s: cannot open %r (%s)" % (where, ref,
                                                   exc))
        return
    if passage.get("kind") not in ("table", "equation"):
        errors.append("%s: %r is not a table or formula" % (where,
                                                            ref))
    elif not passage.get("checked", True):
        errors.append("%s: %r is not a CHECKED table/formula"
                      % (where, ref))


def _counter(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _counter_save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def write_photo_picks(ctx, args):
    """Pia's picks: cut match vs Penn's received storyboard, every
    use pick licensed and (web) stored, source figures readable."""
    obj = (args or {}).get("photo_picks")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": [
            "call with {photo_picks: {...}}"]}
    board = _received_data(ctx, "storyboard")
    if not board:
        return {"ok": False, "errors": [
            "no storyboard received in this run"]}
    errors = validate_photo_picks(obj, board)
    if errors:
        return {"ok": False, "errors": errors}
    producer = (ctx or {}).get("producer", "")
    order_id = (ctx or {}).get("order_id", "")
    for i, cut in enumerate(obj["cuts"]):
        if not isinstance(cut, dict) or cut.get("decision") != "use":
            continue
        where = "cuts[%d]" % i
        if cut.get("kind") == "source_figure":
            _readable_ref(errors, cut.get("ref"), producer,
                          order_id, where)
        else:
            try:
                rpc, _rid, _frag = pc.parse_ref(cut.get("ref",
                                                        ""))
            except ValueError:
                errors.append("%s: bad image ref" % where)
                continue
            if rpc != "image":
                errors.append("%s: web picks ref the Image PC"
                              % where)
                continue
            try:
                entry = pc.load_entry_by_ref(cut["ref"])
            except (OSError, ValueError, KeyError) as exc:
                errors.append("%s: cannot load pick (%s)"
                              % (where, exc))
                continue
            if entry.get("license") != cut.get("license"):
                errors.append("%s: license %r != stored %r"
                              % (where, cut.get("license"),
                                 entry.get("license")))
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "photo_picks", obj)


def write_gen_picks(ctx, args):
    """Gene's choices: cut match, prompt per generate cut, ≤6
    images, every image stored in the Generated PC."""
    obj = (args or {}).get("gen_picks")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": [
            "call with {gen_picks: {...}}"]}
    board = _received_data(ctx, "storyboard")
    if not board:
        return {"ok": False, "errors": [
            "no storyboard received in this run"]}
    errors = validate_gen_picks(obj, board)
    if errors:
        return {"ok": False, "errors": errors}
    order_id = (ctx or {}).get("order_id", "")
    for i, im in enumerate(obj["images"]):
        if not isinstance(im, dict):
            continue
        where = "images[%d]" % i
        try:
            rpc, rid, _frag = pc.parse_ref(
                "pc://generated/%s" % _prompt_doc(im.get("prompt",
                                                         "")))
            entry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid))
        except (OSError, ValueError, KeyError) as exc:
            errors.append("%s: prompt has no stored image (%s)"
                          % (where, exc))
            continue
        if entry.get("file") != im.get("file"):
            errors.append("%s: file %r != stored %r"
                          % (where, im.get("file"),
                             entry.get("file")))
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "gen_picks", obj)


def _prompt_doc(prompt):
    return pc.content_id("generated:" + str(prompt or ""))


def write_anim_picks(ctx, args):
    """Max's picks: cut match, template + values + refs per use,
    every ref a CHECKED source table/formula readable by Max."""
    obj = (args or {}).get("anim_picks")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": [
            "call with {anim_picks: {...}}"]}
    board = _received_data(ctx, "storyboard")
    if not board:
        return {"ok": False, "errors": [
            "no storyboard received in this run"]}
    errors = validate_anim_picks(obj, board)
    if errors:
        return {"ok": False, "errors": errors}
    producer = (ctx or {}).get("producer", "")
    order_id = (ctx or {}).get("order_id", "")
    for i, cut in enumerate(obj["cuts"]):
        if not isinstance(cut, dict) or cut.get("decision") != "use":
            continue
        for j, ref in enumerate(cut.get("refs", []) or []):
            where = "cuts[%d].refs[%d]" % (i, j)
            _readable_ref(errors, ref, producer, order_id, where)
            _checked_table_formula(errors, ref, where)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "anim_picks", obj)


def _use_cuts(report):
    """{cut_id} with a use/generate decision in a helper report."""
    out = set()
    for c in ((report or {}).get("cuts") or []):
        if isinstance(c, dict) and c.get("decision") in ("use",
                                                         "generate"):
            out.add(c.get("cut_id"))
    return out


def write_slide_draft(ctx, args):
    """Vera's slide plan v2: cut+time match vs Wren's narration,
    layout-checked blocks, photo/generated backed by helper picks,
    source figures readable."""
    obj = (args or {}).get("slide_draft")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": [
            "call with {slide_draft: {...}}"]}
    narr = _received_data(ctx, "narration")
    if not narr:
        return {"ok": False, "errors": [
            "no narration received in this run"]}
    errors = validate_slide_draft(obj, narr)
    if errors:
        return {"ok": False, "errors": errors}
    producer = (ctx or {}).get("producer", "")
    order_id = (ctx or {}).get("order_id", "")
    have = {"photo": _use_cuts(_received_data(ctx, "photo_picks")),
            "generated": _use_cuts(_received_data(ctx,
                                                  "gen_picks")),
            "animation": _use_cuts(_received_data(ctx,
                                                  "anim_picks"))}
    for i, cut in enumerate(obj["cuts"]):
        for j, b in enumerate(cut.get("blocks", []) or []):
            if not isinstance(b, dict):
                continue
            where = "cuts[%d].blocks[%d]" % (i, j)
            kind = b.get("kind")
            if kind in ("photo", "generated"):
                if cut.get("cut_id") not in have.get(kind, set()):
                    errors.append("%s: no %s pick for cut %r"
                                  % (where, kind, cut.get("cut_id")))
            elif kind == "source_figure":
                _readable_ref(errors, b.get("ref"), producer,
                              order_id, where)
            elif kind not in ("table", "formula", "chart",
                              "steps", "text"):
                errors.append("%s: unknown block kind %r"
                              % (where, kind))
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "slide_draft", obj)


def write_render_log(ctx, args):
    """Remy's render record: cut match vs Vera's draft, ≤3
    renders, layout-only adjustments."""
    obj = (args or {}).get("render_log")
    if not isinstance(obj, dict):
        return {"ok": False, "errors": [
            "call with {render_log: {...}}"]}
    draft = _received_data(ctx, "slide_draft")
    if not draft:
        return {"ok": False, "errors": [
            "no slide_draft received in this run"]}
    errors = validate_render_log(obj, draft)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "render_log", obj)


def _stub_wav(text):
    """Deterministic silence: seconds = words/2.5, 16 kHz mono."""
    import io
    import struct
    import wave
    words = len(str(text or "").split())
    seconds = round(max(1.0, words / 2.5), 1)
    rate = 16000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % int(seconds * rate),
                                  *([0] * int(seconds * rate))))
    return buf.getvalue(), seconds


def _wav_seconds(blob):
    import io
    import wave
    with wave.open(io.BytesIO(blob), "rb") as w:
        return round(w.getnframes() / float(w.getframerate()), 1)


def _kokoro_tts(text):
    """Local Kokoro synthesis. Imported lazily; raises RuntimeError
    with the install hint when unavailable."""
    try:
        from kokoro import KPipeline
    except ImportError:
        raise RuntimeError(
            "kokoro not installed: pip install kokoro torch "
            "soundfile (plus the espeak-ng system package for "
            "English), or call make_voice with engine=stub")
    import io
    import soundfile
    import torch
    pipe = KPipeline(lang_code="a")
    audio = None
    rate = 24000
    for _gs, _ps, chunk in pipe(str(text or ""),
                                voice="af_heart"):
        part = chunk.detach().cpu()
        audio = part if audio is None else torch.cat([audio,
                                                      part])
    buf = io.BytesIO()
    soundfile.write(buf, audio.numpy(), rate, format="WAV")
    return buf.getvalue(), _wav_seconds(buf.getvalue())


def make_voice(ctx, args):
    """Wren's TTS: synthesize one cut's text into the Voice PC.
    Returns the real duration. Max 2 attempts per cut. engine:
    stub (default, deterministic) or kokoro (local install)."""
    producer = (ctx or {}).get("producer", "")
    if producer != "voice_wren":
        return {"error": "make_voice is Wren's tool"}
    cut_id = ((args or {}).get("cut_id") or "").strip()
    text = ((args or {}).get("text") or "").strip()
    plan = (args or {}).get("plan_seconds")
    if not cut_id or not text or not isinstance(plan,
                                                (int, float)) \
            or plan <= 0:
        return {"ok": False, "errors": [
            "call with {cut_id, text, plan_seconds}"]}
    engine = (args or {}).get("engine", "stub")
    if engine not in ("stub", "kokoro"):
        return {"ok": False, "errors": [
            "engine must be stub or kokoro"]}
    attp = os.path.join(ctx["run_dir"], "voice_attempts.json")
    attempts = _counter(attp)
    n = int(attempts.get(cut_id, 0)) + 1
    if n > VOICE_MAX_ATTEMPTS:
        return {"ok": False, "errors": [
            "cut %s already used %d voice attempts"
            % (cut_id, VOICE_MAX_ATTEMPTS)]}
    try:
        if engine == "kokoro":
            wav, seconds = _kokoro_tts(text)
        else:
            wav, seconds = _stub_wav(text)
    except RuntimeError as exc:
        return {"ok": False, "errors": [str(exc)]}
    saved = pc.voice_save(ctx.get("order_id", ""), cut_id, wav,
                          text, seconds, n, engine)
    attempts[cut_id] = n
    _counter_save(attp, attempts)
    return {"ok": True, "voice_pc_ref": saved["ref"],
            "seconds": seconds, "attempt": n,
            "within_15pct": abs(seconds - plan) <= plan * 0.15,
            "engine": engine}


def _have_remotion():
    """Remotion usable: node_modules installed and npx on PATH."""
    if not os.path.isdir(os.path.join(REMOTION_DIR, "node_modules")):
        return False
    for exe in ("npx.cmd", "npx"):
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if d.strip() and os.path.isfile(
                    os.path.join(d.strip(), exe)):
                return True
    return False


def _cut_slide_props(cut, guide):
    """Cut (slide_draft v2) + style guide -> CutSlide props."""
    dur = 20
    try:
        dur = int(round(float(cut.get("end_s", 20))
                        - float(cut.get("start_s", 0)))) or 20
    except (TypeError, ValueError):
        pass
    dur = min(max(dur, 1), 30)
    blocks = []
    for b in (cut.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        box = b.get("box") or {}
        nb = {"kind": b.get("kind"),
              "box": {k: box.get(k) for k in ("x", "y", "w", "h")},
              "order": b.get("order", 0),
              "appear_s": b.get("appear_s", 0),
              "reason": b.get("reason", ""),
              "font_size": b.get("font_size"),
              "data": b.get("data") or {}}
        if b.get("kind") in ("photo", "generated", "source_figure"):
            ref = b.get("ref") or ""
            nb["file"] = "" if ref.startswith("pc://") else ref
        blocks.append(nb)
    return {"cutId": cut.get("cut_id"), "seconds": dur,
            "preset": cut.get("preset", "full"), "blocks": blocks,
            "onScreenText": cut.get("on_screen_text") or [],
            "guide": guide if isinstance(guide, dict) else {}}


def render_slide(ctx, args):
    """Render one cut's slide PNG via the Remotion CutSlide
    composition (last frame of the cut). Max 3 renders per cut per
    run. Without Remotion the render is skipped honestly: ok True
    with status remotion_unavailable (the 3-render cap still
    applies)."""
    from . import video
    cut_id = ((args or {}).get("cut_id") or "").strip()
    if not cut_id:
        return {"ok": False, "errors": ["call with {cut_id}"]}
    draft = _received_data(ctx, "slide_draft")
    guide = _received_data(ctx, "style_guide")
    if not draft or not guide:
        return {"ok": False, "errors": [
            "need received slide_draft + style_guide"]}
    cut = next((c for c in draft.get("cuts", [])
                if isinstance(c, dict)
                and c.get("cut_id") == cut_id), None)
    if cut is None:
        return {"ok": False, "errors": ["no such cut: %r" % cut_id]}
    countp = os.path.join(ctx["run_dir"], "render_counts.json")
    counts = _counter(countp)
    n = int(counts.get(cut_id, 0)) + 1
    if n > video.RENDER_MAX:
        return {"ok": False, "errors": [
            "cut %s already used %d renders"
            % (cut_id, video.RENDER_MAX)]}
    if not _have_remotion():
        counts[cut_id] = n
        _counter_save(countp, counts)
        return {"ok": True, "slide_file": "",
                "status": "remotion_unavailable",
                "renders_n": 0,
                "note": "Remotion is not installed; run "
                        "tools/setup_video.ps1 to install it"}
    sdir = os.path.join(ctx["run_dir"], "slides")
    os.makedirs(sdir, exist_ok=True)
    out = os.path.join(sdir, "%s.png" % cut_id)
    props = _cut_slide_props(cut, guide)
    last_frame = props["seconds"] * 30 - 1
    exe = "npx.cmd" if os.name == "nt" else "npx"
    cmd = [exe, "remotion", "still", "CutSlide", out,
           "--props=%s" % json.dumps(props),
           "--public-dir=%s" % sdir,
           "--frame=%d" % last_frame]
    try:
        proc = subprocess.run(cmd, cwd=REMOTION_DIR,
                              capture_output=True, text=True,
                              timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "errors": ["render failed: %s" % exc]}
    if proc.returncode != 0 or not os.path.isfile(out):
        tail = (proc.stderr or "")[-400:]
        return {"ok": False, "errors": ["render failed: %s" % tail]}
    counts[cut_id] = n
    _counter_save(countp, counts)
    return {"ok": True, "slide_file": "slides/%s.png" % cut_id,
            "renders_n": n}


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
        "Save this run's result.json (request category). Fails "
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
    "write_storyboard_draft": (
        write_storyboard_draft,
        "Save Ash's scene plan as this run's result.json "
        "(storyboard_draft category). Fails unless scenes match "
        "Marty's plan, citations are verbatim, materials open, "
        "every pick is used or explained; then applies handoff.",
        {"type": "object",
         "properties": {"storyboard_draft": {"type": "object"}},
         "required": ["storyboard_draft"],
         "additionalProperties": False},
    ),
    "write_storyboard": (
        write_storyboard,
        "Save Penn's cut screens as this run's result.json "
        "(storyboard + style_guide categories). Fails unless cuts "
        "match Wren's narration exactly and the style guide is "
        "complete.",
        {"type": "object",
         "properties": {"storyboard": {"type": "object"},
                        "style_guide": {"type": "object"}},
         "required": ["storyboard", "style_guide"],
         "additionalProperties": False},
    ),
    "write_narration": (
        write_narration,
        "Save Wren's cuts as this run's result.json (narration "
        "category). Fails unless cuts tile the scenes, audio sits "
        "within ±15% of each cut, number lines are cited, "
        "citations are verbatim, and audio refs are stored.",
        {"type": "object",
         "properties": {"narration": {"type": "object"}},
         "required": ["narration"], "additionalProperties": False},
    ),
    "write_photo_picks": (
        write_photo_picks,
        "Save Pia's photo picks as this run's result.json "
        "(photo_picks category). Fails unless cuts match Penn's "
        "storyboard and every use pick is licensed and stored.",
        {"type": "object",
         "properties": {"photo_picks": {"type": "object"}},
         "required": ["photo_picks"],
         "additionalProperties": False},
    ),
    "write_gen_picks": (
        write_gen_picks,
        "Save Gene's generation choices as this run's result.json "
        "(gen_picks category). Fails unless cuts match, every "
        "generate cut has a prompt and a stored image, and the "
        "run holds at most 6 images.",
        {"type": "object",
         "properties": {"gen_picks": {"type": "object"}},
         "required": ["gen_picks"], "additionalProperties": False},
    ),
    "write_anim_picks": (
        write_anim_picks,
        "Save Max's animation picks as this run's result.json "
        "(anim_picks category). Fails unless cuts match and every "
        "use pick names a template with values from CHECKED "
        "source tables/formulas.",
        {"type": "object",
         "properties": {"anim_picks": {"type": "object"}},
         "required": ["anim_picks"], "additionalProperties": False},
    ),
    "write_slide_draft": (
        write_slide_draft,
        "Save Vera's slide plan as this run's result.json "
        "(slide_draft category). Fails unless cuts match Wren's "
        "narration and every material is backed by a helper pick.",
        {"type": "object",
         "properties": {"slide_draft": {"type": "object"}},
         "required": ["slide_draft"],
         "additionalProperties": False},
    ),
    "write_render_log": (
        write_render_log,
        "Save Remy's render record as this run's result.json "
        "(render_log category). Fails unless cuts match Vera's "
        "draft, renders stay ≤3 per cut, and adjustments are "
        "layout-only.",
        {"type": "object",
         "properties": {"render_log": {"type": "object"}},
         "required": ["render_log"], "additionalProperties": False},
    ),
    "make_voice": (
        make_voice,
        "Synthesize one cut's text into the Voice PC (Wren only). "
        "Returns the voice ref and the real duration. Max 2 "
        "attempts per cut; engine stub (default) or kokoro.",
        {"type": "object",
         "properties": {"cut_id": {"type": "string"},
                        "text": {"type": "string"},
                        "plan_seconds": {"type": "number"},
                        "engine": {"type": "string"}},
         "required": ["cut_id", "text", "plan_seconds"],
         "additionalProperties": False},
    ),
    "render_slide": (
        render_slide,
        "Render one cut's slide PNG via Remotion from the "
        "received slide draft + style guide. Max 3 renders per cut "
        "per run.",
        {"type": "object",
         "properties": {"cut_id": {"type": "string"}},
         "required": ["cut_id"], "additionalProperties": False},
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
        "Grant map/full rows on one entry (merged). You must hold a "
        "row on it; only Sam grants full (on Source). ref defaults "
        "to this order's Source entry.",
        {"type": "object",
         "properties": {"ref": {"type": "string"},
                        "map": {"type": "array",
                                "items": {"type": "string"}},
                        "full": {"type": "array",
                                 "items": {"type": "string"}}},
         "additionalProperties": False},
    ),
    "open_ref": (
        open_ref,
        "Open any stable pc:// ref verbatim with provenance. Refused "
        "without that PC's read grant or a recipient listing.",
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


TOOLS.update(MEDIA_TOOLS)


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

