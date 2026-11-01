"""Tool registry + builtin tools. Stdlib only.

Each tool takes (ctx, args) and returns JSON-serializable data.
ctx: {"run_dir":..., "agent_dir":..., "input_md":...}
"""
import importlib.util
import json
import os
import re
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
from . import readlog
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


_PUNCT_FOLD = {"\u2013": "-", "\u2014": "-", "\u2012": "-",
                "\u2011": "-", "\u2019": "'", "\u2018": "'",
                "\u201a": "'", "\u201b": "'", "\u201c": '"',
                "\u201d": '"', "\u201e": '"', "\u201f": '"',
                "\u2026": "..."}


def _norm_ws(s):
    """Whitespace-normalized with dash/quote marks folded to ASCII.
    Words must still match exactly; only punctuation equivalence."""
    t = str(s)
    for k, v in _PUNCT_FOLD.items():
        t = t.replace(k, v)
    return " ".join(t.split())


def _check_quote(errors, ref, quote, where):
    """One {ref, quote} pair passes only when the quote appears
    verbatim in the passage at the ref (whitespace normalized,
    dash/quote marks folded; words must match exactly)."""
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
        try:
            near = _nearest_para_hint(entry, quote,
                                      pc.entry_ref(rpc, rid))
        except (OSError, ValueError, KeyError):
            near = None
        if near:
            errors.append("%s: these words appear in %s" % (where, near))
        elif rpc in ("theory", "article"):
            base = pc.entry_ref(rpc, rid)
            errors.append("%s: cite %s passages as %s#pN "
                          "(paragraph N) or %s#g1 (whole text)"
                          % (where, rpc, base, base))
        return
    if _norm_ws(quote) not in _norm_ws(_verbatim_haystack(passage)):
        errors.append("%s: quote not found verbatim in %r" % (where, ref))
        hay = _verbatim_haystack(passage)
        if hay:
            errors.append("%s: quotable text at %r: %r"
                          % (where, ref, hay[:800]))
        try:
            near = _nearest_para_hint(
                entry, quote, pc.entry_ref(rpc, rid))
        except (OSError, ValueError, KeyError):
            near = None
        if near:
            errors.append("%s: these words appear in %s" % (where, near))


def _nearest_para_hint(entry, quote, base):
    """Best paragraph addr whose words match a run of the quote."""
    qw = _norm_ws(quote).lower().split()
    if len(qw) < 5:
        return None
    best, bestn = None, 0
    for p in entry.get("paragraphs", []):
        if not isinstance(p, dict):
            continue
        pw = _norm_ws(p.get("text", "")).lower().split()
        if not pw:
            continue
        runs = 0
        for i in range(len(qw)):
            for j in range(len(pw)):
                k = 0
                while (i + k < len(qw) and j + k < len(pw)
                       and qw[i + k] == pw[j + k]):
                    k += 1
                runs = max(runs, k)
        if runs > bestn:
            best, bestn = p.get("addr"), runs
    if best and bestn >= 5:
        return "%s#%s" % (base, best)
    return None


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
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except ValueError:
            obj = None
    if not isinstance(obj, dict):
        return {"ok": False,
                "errors": ["call with {%s: {...}} -- pass the object "
                           "itself, not a JSON string" % category]}
    errors = validator(obj)
    if errors:
        return {"ok": False,
                "errors": errors + _omitted_hints(ctx, errors)}
    cov = _coverage_errors(ctx, category, obj)
    if cov:
        return {"ok": False, "errors": cov}
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
    vs Wren's received narration, on-screen text ≤3 lines. Penn
    writes no timing; the writer copies scene_n/start_s/end_s per
    cut_id from the narration into the saved result."""
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
    own = {c.get("cut_id"): c for c in obj.get("cuts", [])
           if isinstance(c, dict)}
    filled = []
    for nc in (narr.get("cuts") or []):
        if not isinstance(nc, dict) or nc.get("cut_id") not in own:
            continue
        mine = own[nc["cut_id"]]
        filled.append({"cut_id": nc["cut_id"],
                       "scene_n": nc.get("scene_n"),
                       "start_s": nc.get("start_s"),
                       "end_s": nc.get("end_s"),
                       "show_what": mine.get("show_what"),
                       "show_why": mine.get("show_why"),
                       "on_screen_text": mine.get(
                           "on_screen_text")})
    saved = dict(obj)
    saved["cuts"] = filled
    return _save_categories(ctx, {"storyboard": saved,
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


def _structure_part_ids(run_dir):
    """Part ids from the run's received structure map, or None."""
    if not run_dir or not os.path.isdir(run_dir):
        return None
    try:
        names = sorted(os.listdir(run_dir))
    except OSError:
        return None
    for n in names:
        if n.startswith("received.") and n.endswith(".structure.json"):
            try:
                with open(os.path.join(run_dir, n),
                          encoding="utf-8") as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                return None
            data = rec.get("data", rec) if isinstance(rec, dict) else {}
            parts = data.get("parts") if isinstance(data, dict) else None
            if not isinstance(parts, list):
                return None
            return [p.get("id") for p in parts
                    if isinstance(p, dict)]
    return None


def _coverage_errors(ctx, category, obj):
    """Every structure part must be reported (cases/concepts)."""
    if category not in ("cases", "concepts"):
        return []
    want = _structure_part_ids((ctx or {}).get("run_dir", ""))
    if not want:
        return []
    got = [p.get("part_id") for p in obj.get("parts", [])
           if isinstance(p, dict)]
    missing = [i for i in want if i not in got]
    if not missing:
        return []
    return ["structure has parts %s but the report covers %s: cover "
            "every structure part in order (narrow with 1 pick per "
            "part and gaps if steps run low, never drop parts)"
            % (",".join(want), ",".join(got) or "none")]


def write_cases(ctx, args):
    return _write_report(ctx, args, "cases", validate_cases)


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


@readlog.logged("source")
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


@readlog.logged("source")
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
    Capped like any other read; truncation says how much is missing.
    Pass a section ref <entry>#sX[.Y] to read one section; cite
    passages as <entry>#s<section>/p<para>."""
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


@readlog.logged()
def open_ref(ctx, args):
    """Any-PC ref reader with grant enforcement: the caller must hold
    pc_read_<pc> plus a recipient row for this order. Grants are the
    tools listed in its agent.json. Cite shapes: source
    <entry>#s<section>/p<para>, theory/article <entry>#p<para>
    or <entry>#g<section>. A bare entry ref returns metadata only,
    never passage text: always open the full passage ref and copy
    quotes from the result."""
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


@readlog.logged("theory")
def pc_search_theory(ctx, args):
    """Web search for theory (Tavily basic). Hits stay in the run log;
    nothing is stored until picked."""
    return _pc_search(ctx, args, "pc_search_theory")


@readlog.logged("article")
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
           "supersedes": r["supersedes"],
           "cite": "cite paragraphs as %s#p1 .. %s#p%d; "
                   "verify each quote with open_ref before writing"
                   % (r["ref"], r["ref"], r["paras"])}
    try:
        pent = pc.load_entry_by_ref(r["ref"])
        p1t = (pent.get("paragraphs") or [{}])[0].get("text", "")
        tail = "..." if len(p1t) > 200 else ""
        out["p1_start"] = "p1 begins: " + p1t[:200] + tail
    except (OSError, ValueError, KeyError):
        pass
    if rec_err:
        out["recipients_error"] = rec_err
    return out


@readlog.logged("theory")
def pc_pick_theory(ctx, args):
    """Pick a search hit into the Theory PC (full ingest) and get its
    ref. Pick only what will be cited or read by later agents."""
    return _pc_pick(ctx, args, "theory")


@readlog.logged("article")
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
    if out.get("kind") == "entry" and pcname in ("theory", "article"):
        bits = []
        for p in entry.get("paragraphs", []) or []:
            if isinstance(p, dict) and p.get("text"):
                bits.append("[%s] %s" % (p.get("addr", "?"),
                                         p["text"]))
        out = {"kind": "passage", "ref": ref,
               "text": "\n\n".join(bits),
               "provenance": out.get("provenance")}
    try:
        cap = int(args.get("max_chars", 8000))
    except (TypeError, ValueError):
        cap = 8000
    text = out.get("text", "")
    if len(text) > cap:
        out["text"] = text[:cap]
        out["truncated"] = len(text) - cap
    return out


@readlog.logged("theory")
def pc_read_theory(ctx, args):
    """Read a Theory PC ref verbatim with provenance. Refused unless
    listed as a recipient for this order. Pass <entry>#pN for
    paragraph N (the pick result tells you how many paragraphs
    exist); a bare entry ref returns the whole text with [pN]
    markers -- cite the marker's paragraph."""
    return _pc_read_web(ctx, args, "theory")


@readlog.logged("article")
def pc_read_article(ctx, args):
    """Read an Article PC ref verbatim with provenance. Refused unless
    listed as a recipient for this order. Pass <entry>#pN for
    paragraph N (the pick result tells you how many paragraphs
    exist); a bare entry ref returns the whole text with [pN]
    markers -- cite the marker's paragraph."""
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


@readlog.logged("source")
def pc_send_source(ctx, args):
    """Send this order's attached PDF to the Source PC: parse, ingest,
    build the map, index. Returns the entry ref + counts. Sam only;
    idempotent (same PDF = same ref, finished stages are skipped)."""
    ctx = ctx or {}
    on_progress = ctx.get("on_progress")
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
    if callable(on_progress):
        on_progress(3, "PDF parsed")
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
    if (args or {}).get("build") == "async" \
            and not (map_done and indexed) and not warning:
        if jetson_down:
            mode = "noindex"
        else:
            mode = "index" if map_done else ("noindex" if indexed
                                             else "all")
        try:
            subprocess.Popen(
                [sys.executable, os.path.join("scripts",
                                              "pc_worker.py"),
                 r["doc_id"], mode, "source"],
                cwd=base, stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT)
        except OSError as exc:
            return {"error": "worker start failed: %s" % exc}
        worker_note = "mode %s spawned (async; map/index pending)" \
            % mode
    if not (map_done and indexed) and not warning \
            and (args or {}).get("build", "all") != "skip" \
            and (args or {}).get("build") != "async":
        if jetson_down:
            mode = "noindex"
        else:
            mode = "index" if map_done else ("noindex" if indexed
                                             else "all")
        try:
            proc = subprocess.Popen(
                [sys.executable, os.path.join("scripts",
                                              "pc_worker.py"),
                 r["doc_id"], mode, "source"],
                cwd=base, stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT)
        except OSError as exc:
            return {"error": "worker start failed: %s" % exc}
        log_path = os.path.join(pc.entry_dir("source", r["doc_id"]),
                                "log.jsonl")
        try:
            with open(log_path, encoding="utf-8") as f:
                f.seek(0, 2)
                log_off = f.tell()
        except OSError:
            log_off = 0
        rc, t0 = None, time.time()
        while True:
            if time.time() - t0 > SEND_TIMEOUT:
                rc = None
                break
            rc = proc.poll()
            if callable(on_progress):
                try:
                    with open(log_path, encoding="utf-8") as f:
                        f.seek(log_off)
                        chunk = f.read()
                        log_off = f.tell()
                except OSError:
                    chunk = ""
                for ln in chunk.splitlines():
                    try:
                        ev = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(ev, dict) \
                            and ev.get("ev") == "progress":
                        try:
                            on_progress(int(ev.get("pct", 0)),
                                        str(ev.get("stage", "")))
                        except (TypeError, ValueError):
                            pass
            if rc is not None:
                break
            time.sleep(2)
        if rc is None:
            try:
                proc.kill()
            except OSError:
                pass
            proc.wait()
            worker_note = "mode %s timed out after %ds" \
                % (mode, SEND_TIMEOUT)
            warning = ("worker timed out; map/index may still be "
                       "pending (REBUILD from the PC page)")
        else:
            worker_note = "mode %s exit %d" % (mode, rc)
        if not warning:
            mp = pc.load_map_by_ref(r["ref"])
            map_done = isinstance(mp, dict) \
                and mp.get("status") == "done"
            indexed = _indexed("source", prof, r["doc_id"])
            if rc != 0 and not map_done:
                return {"error": "map build failed: %s"
                                 % (_worker_reason(
                                     pc.entry_dir("source",
                                                  r["doc_id"]))
                                    or worker_note)}
            if rc != 0:
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


def _agents_root(ctx):
    """Folder holding the agent dirs (each with agent.json).

    ctx agent_dir points at the calling agent; its parent is the
    agents folder. A server-side call has no agent_dir: resolve
    against the repo checkout, never the process cwd (the cwd may
    be the repo root itself, which holds no agent.json files and
    made crew listing fail with "unknown agents")."""
    cands = [os.path.dirname(os.path.abspath(
        (ctx or {}).get("agent_dir", "") or "agents"))]
    try:
        cands.append(os.path.join(pc._base(None), "agents"))
    except Exception:  # noqa: BLE001 - next candidate covers it
        pass
    cands.append(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    for cand in cands:
        if os.path.isfile(os.path.join(cand, "sales_sam",
                                       "agent.json")):
            return cand
    return cands[0]


@readlog.logged()
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
    aroot = _agents_root(ctx)
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


# ---- Sam's order-chat tools (the chat LLM decides via these) ----

SAM_FORM_FIELDS = ("audience", "length", "depth", "theme")

SAM_SOURCE_GRANTS = {"full": ["pd_marty"],
                     "map": ["explain_cleo", "case_rex",
                             "plan_ash"]}


def _order_dir(order_id):
    d = os.path.join(pc._base(None), "orders", order_id or "")
    return d if os.path.isdir(d) else ""


def _load_form(odir, meta):
    """Production request form (source of truth). Missing file or
    keys fall back to the stored answers (old orders)."""
    try:
        with open(os.path.join(odir, "form.json"),
                  encoding="utf-8") as f:
            form = json.load(f)
    except (OSError, ValueError):
        form = None
    if not isinstance(form, dict):
        form = {}
    for k in SAM_FORM_FIELDS:
        if not isinstance(form.get(k), str) or not form.get(k):
            a = ((meta or {}).get("answers", {}) or {}).get(k, "")
            form[k] = a if isinstance(a, str) else ""
    return form


def _load_meta(odir):
    try:
        with open(os.path.join(odir, "meta.json"),
                  encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = None
    return meta if isinstance(meta, dict) else None


def _save_form_meta(odir, form):
    form = {k: (form.get(k, "") or "") for k in SAM_FORM_FIELDS}
    with open(os.path.join(odir, "form.json"), "w",
              encoding="utf-8") as f:
        json.dump(form, f, ensure_ascii=False, indent=1)
    meta = _load_meta(odir)
    if meta is None:
        raise OSError("no such order dir: %r" % odir)
    meta["answers"] = dict(form)
    with open(os.path.join(odir, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return form


def final_request_prompt(oid, form, pdf_name, pdf_bytes):
    """One-shot writer prompt: the final request from the form."""
    vals = {k: (form.get(k) or "") for k in SAM_FORM_FIELDS}
    return (
        "Write the final production request as ONE JSON object, no other "
        "text:\n"
        '{"order_id": "...", "client_answers": {"audience": "...", '
        '"length": "...", "depth": "...", "theme": "...", '
        '"source": "..."}, '
        '"production_notes": ["...", ...], "open_questions": [...]}\n'
        "Rules: client_answers.audience/length/depth/theme come from the "
        "FORM below, word for word; client_answers.source is the PDF file "
        "name. Never describe the source contents: the file is not "
        "parsed yet at your time; the Source PC map summarizes it. "
        "production_notes: 2-5 short crew instructions grounded in the "
        "form. open_questions: [] unless something is genuinely unclear.\n"
        "ORDER: %s\nFORM: %s\nSOURCE PDF: %s (%d bytes)"
        % (oid, json.dumps(vals, ensure_ascii=False),
           pdf_name, pdf_bytes))


def search_knowledge(ctx, args):
    """Look one question up in this employee's LightRAG index."""
    ctx = ctx or {}
    args = args or {}
    q = args.get("query", "")
    if not isinstance(q, str) or not q.strip():
        return {"error": "give query: {query: ...}"}
    try:
        rag = graph.query(ctx.get("agent_dir", "") or "",
                          q.strip()[:1000])
        ans = str((rag or {}).get("answer", "")).strip()
    except Exception as exc:  # noqa: BLE001 - a tool never raises
        return {"error": "knowledge index unavailable: %s" % exc}
    return {"answer": ans[:1500]}


def update_form(ctx, args):
    """Save what the turn revealed into the order's request form."""
    ctx = ctx or {}
    args = args or {}
    order_id = ctx.get("order_id", "")
    odir = ctx.get("order_dir") or _order_dir(order_id)
    if not odir:
        return {"error": "no such order: %r" % order_id}
    meta = _load_meta(odir)
    form = _load_form(odir, meta or {})
    changed = []
    for k in SAM_FORM_FIELDS:
        v = args.get(k, "")
        if isinstance(v, str):
            v = v.strip()[:500]
            if v and v != form.get(k, ""):
                form[k] = v
                changed.append(k)
    try:
        form = _save_form_meta(odir, form)
    except (OSError, ValueError) as exc:
        return {"error": "cannot save form: %s" % exc}
    return {"ok": True, "form": dict(form), "changed": changed}


def finalize_and_send(ctx, args):
    """Write the final request from the order's form and send the
    attached PDF to the Source PC (parse + map + index run async).
    Sam's job ends here. Only Sam; needs a full form and a stored
    PDF, else an error the model can act on."""
    ctx = ctx or {}
    args = args or {}
    order_id = ctx.get("order_id", "")
    if ctx.get("producer", "") != INTAKE_PRODUCER:
        return {"error": "finalize_and_send is Sam's tool"}
    odir = ctx.get("order_dir") or _order_dir(order_id)
    if not odir:
        return {"error": "no such order: %r" % order_id}
    meta = _load_meta(odir)
    meta_p = os.path.join(odir, "meta.json")
    if meta is None:
        return {"error": "no such order: %r" % order_id}
    form = _load_form(odir, meta)
    missing = [k for k in SAM_FORM_FIELDS
               if not (form.get(k) or "").strip()]
    if not (meta.get("files", {}) or {}).get("source"):
        missing = missing + ["source PDF"]
    if missing:
        return {"error": "intake incomplete",
                "missing": missing}
    agent_dir = ctx.get("agent_dir", "") or ""
    try:
        with open(os.path.join(agent_dir, "agent.json"),
                  encoding="utf-8") as f:
            model = json.load(f).get("model", "")
    except (OSError, ValueError):
        model = ""
    if not model:
        return {"error": "no model for Sam"}
    from . import runner as _runner
    files = meta.get("files", {}) or {}
    pdf_name = files.get("source", "source.pdf")
    try:
        pdf_bytes = os.path.getsize(os.path.join(odir, pdf_name))
    except OSError:
        pdf_bytes = files.get("bytes", 0) or 0
    run_dir = ctx.get("run_dir") or os.path.join(
        pc._base(None), "output", "runs", order_id)
    os.makedirs(run_dir, exist_ok=True)
    prompt = final_request_prompt(order_id, form, pdf_name,
                                 pdf_bytes)
    try:
        resp = _runner._chat(
            model, [{"role": "user", "content": prompt}],
            None, timeout=300, caller="sales_sam:finalize",
            log_path=os.path.join(run_dir, "llm_calls.jsonl"))
        text = ((resp.get("choices") or [{}])[0]
                .get("message", {}).get("content", ""))
        obj, status = _runner.parse_json_answer(text or "")
        if status != "ok" or not isinstance(obj, dict):
            raise ValueError("no request JSON in reply")
        obj["order_id"] = order_id
        errs = validate_request(obj)
        if errs:
            raise ValueError("; ".join(errs)[:300])
    except Exception as exc:  # noqa: BLE001 - returned, key never leaks
        return {"error": "request writing failed: %s" % exc}
    res = results.make_result("sales_sam", order_id, "",
                              {"request": obj})
    try:
        results.save_result(odir, res)
        with open(os.path.join(odir, "report.md"), "w",
                  encoding="utf-8") as f:
            f.write(results.render_report(res))
    except (OSError, ValueError, RuntimeError) as exc:
        return {"error": "cannot save request: %s" % exc}
    try:
        pout = pc_send_source(
            {"producer": "sales_sam", "order_id": order_id,
             "agent_dir": agent_dir, "run_dir": run_dir},
            {"build": "async"})
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return {"error": "parse not started: %s" % exc}
    if not isinstance(pout, dict) or pout.get("error"):
        err = (pout.get("error") if isinstance(pout, dict)
               else "bad tool result")
        return {"error": "parse not started: %s" % err}
    try:
        rout = pc_set_recipients(
            {"producer": "sales_sam", "order_id": order_id,
             "agent_dir": agent_dir},
            {"full": list(SAM_SOURCE_GRANTS["full"]),
             "map": list(SAM_SOURCE_GRANTS["map"]),
             "ref": pout["ref"]})
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return {"error": "crew listing failed: %s" % exc}
    if not isinstance(rout, dict) or rout.get("error"):
        err = (rout.get("error") if isinstance(rout, dict)
               else "bad tool result")
        return {"error": "crew listing failed: %s" % err}
    final_status = args.get("status", "in_production")
    if final_status not in ("complete", "in_production"):
        final_status = "in_production"
    intake_rec = {"order_id": order_id,
                  "answers": dict(form, source=files.get(
                      "source", "source.pdf")),
                  "files": {"source": files.get("source"),
                            "pc_ref": pout["ref"]},
                  "source": {"ref": pout["ref"],
                             "title": pout.get("title", ""),
                             "sections": pout.get("section_count",
                                                  "?"),
                             "chars": pout.get("chars", "?")}}
    try:
        with open(os.path.join(odir, "intake.json"), "w",
                  encoding="utf-8") as f:
            json.dump(intake_rec, f, ensure_ascii=False, indent=2)
        meta = (_load_meta(odir) or meta)
        meta["approved"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "answers": dict(form),
                            "via": "chat-form"}
        meta["status"] = final_status
        meta["starting"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        meta["parse_pending"] = {"doc_id": pout["doc_id"],
                                 "ref": pout["ref"]}
        with open(meta_p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    except (OSError, ValueError) as exc:
        return {"error": "cannot record handover: %s" % exc}
    return {"ok": True, "handed_over": True,
            "intake": intake_rec,
            "form": dict(form), "source": intake_rec["source"],
            "ref": pout["ref"], "doc_id": pout["doc_id"]}


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
    quota = (ctx or {}).get("gene_quota")
    if quota is not None:
        fresh = [im for im in (obj.get("images") or [])
                 if isinstance(im, dict) and not im.get("reused")]
        if len(fresh) > quota:
            return {"ok": False, "errors": [
                "part quota allows %d new images, got %d"
                % (quota, len(fresh))]}
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
    """Max's picks v2: cut match, template + structured values per
    use, every ref a CHECKED source table/formula quoted verbatim,
    every data value traced to the quotes."""
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
        where = "cuts[%d]" % i
        quotes = []
        for j, r in enumerate(cut.get("refs", []) or []):
            rw = "%s.refs[%d]" % (where, j)
            if not isinstance(r, dict):
                continue
            _readable_ref(errors, r.get("ref"), producer,
                          order_id, rw)
            _check_quote(errors, r.get("ref"), r.get("quote"), rw)
            _checked_table_formula(errors, r.get("ref"), rw)
            if isinstance(r.get("quote"), str):
                quotes.append(r["quote"])
        _values_trace(errors, cut.get("template"),
                      cut.get("values"), quotes, where)
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


_ANIM_TMPL_FOR = {"table": ("table",), "formula": ("formula",),
                  "chart": ("bar", "line"), "steps": ("steps",)}


def _cells_equal(a, b):
    """Normalized str-list compare (None-safe)."""
    if not isinstance(a, list) or not isinstance(b, list):
        return False
    if len(a) != len(b):
        return False
    return all(_norm_ws(x) == _norm_ws(y)
               for x, y in zip(a, b))


def _rows_equal(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        return False
    if len(a) != len(b):
        return False
    return all(_cells_equal(x, y) for x, y in zip(a, b))


def _nums_equal(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        return False
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        try:
            if float(x) != float(y):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _anim_backed(errors, maxp, cut_id, kind, block, where):
    """A data block copies Max's use pick for its cut exactly:
    matching template, equal values."""
    pick = maxp.get(cut_id)
    if pick is None:
        errors.append("%s: no anim pick for cut %r (data blocks "
                      "copy Max's values)" % (where, cut_id))
        return
    if pick.get("template") not in _ANIM_TMPL_FOR[kind]:
        errors.append("%s: Max's pick for cut %r is template %r, "
                      "need %s" % (where, cut_id,
                                   pick.get("template"),
                                   "/".join(_ANIM_TMPL_FOR[kind])))
        return
    data = block.get("data") if isinstance(block.get("data"), dict) \
        else {}
    pv = pick.get("values") if isinstance(pick.get("values"), dict) \
        else {}
    same = False
    if kind == "table":
        same = _cells_equal(data.get("headers"), pv.get("headers")) \
            and _rows_equal(data.get("rows"), pv.get("rows"))
    elif kind == "chart":
        same = data.get("subtype") == pick.get("template") \
            and _cells_equal(data.get("labels"), pv.get("labels")) \
            and _nums_equal(data.get("values"), pv.get("values"))
    elif kind == "formula":
        same = _cells_equal(data.get("lines"), pv.get("lines"))
    elif kind == "steps":
        same = _cells_equal(data.get("items"), pv.get("items"))
    if not same:
        errors.append("%s: data != Max's anim pick for cut %r"
                      % (where, cut_id))


def _figure_kind(errors, ref, where):
    """A source_figure block points at a figure passage, not a
    table or paragraph."""
    if not isinstance(ref, str) or not ref.strip():
        return  # missing refs are reported by readability
    try:
        rpc, rid, _frag = pc.parse_ref(ref)
        entry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid))
        passage = pc.open_ref(entry, ref)
    except (OSError, ValueError, KeyError):
        return  # open failures are reported by readability
    if passage.get("kind") != "figure":
        errors.append("%s: %r is a %s, not a figure"
                      % (where, ref, passage.get("kind")))


def _material_aspect(errors, ref, box, where):
    """Box aspect matches the stored material within 50%. Unknown
    dims (old entries, parser figures without w/h) skip quietly."""
    if not isinstance(ref, str) or not ref.strip():
        return
    try:
        rpc, rid, frag = pc.parse_ref(ref)
        entry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid))
    except (OSError, ValueError, KeyError):
        return
    w = h = None
    if rpc in ("image", "generated"):
        w, h = entry.get("width"), entry.get("height")
        if not (w and h):
            try:
                full, _e, _f = pc.resolve_material_file(ref)
                dims = pc.media_dims(full)
            except (OSError, ValueError, KeyError):
                dims = None
            if dims:
                w, h = dims
    elif rpc == "source" and frag:
        fig = next((f for f in entry.get("figures", [])
                    if f.get("addr") == frag), None)
        if fig is None:
            return
        w, h = fig.get("w"), fig.get("h")
        if not (w and h) and fig.get("file"):
            dims = pc.media_dims(os.path.join(
                pc.entry_dir(rpc, rid), "figures", fig["file"]))
            if dims:
                w, h = dims
    else:
        return
    if not all(isinstance(v, (int, float))
               and not isinstance(v, bool) and v > 0
               for v in (w, h)):
        return
    bw, bh = (box or {}).get("w"), (box or {}).get("h")
    if not all(isinstance(v, (int, float))
               and not isinstance(v, bool) and v > 0
               for v in (bw, bh)):
        return
    rel = abs(bw / bh - w / h) / (w / h)
    if rel > 0.5:
        errors.append("%s: box aspect %.2f vs material %.2f "
                      "(over 50%% off)" % (where, bw / bh, w / h))


def _values_trace(errors, template, values, quotes, where):
    """Every data scalar appears in the quoted source (numbers may
    match numerically: 2.5 finds "2.50"). Steps items are Max's own
    compression, so steps are exempt (refs still required)."""
    vals = values if isinstance(values, dict) else {}
    want = []
    if template == "table":
        want += [c for c in vals.get("headers", [])
                 if isinstance(c, str)]
        for r in vals.get("rows", []):
            if isinstance(r, list):
                want += [c for c in r if isinstance(c, str)]
    elif template in ("bar", "line"):
        want += [c for c in vals.get("labels", [])
                 if isinstance(c, str)]
        want += [v for v in vals.get("values", [])
                 if isinstance(v, (int, float))
                 and not isinstance(v, bool)]
    elif template == "formula":
        want += [c for c in vals.get("lines", [])
                 if isinstance(c, str)]
    else:
        return
    hay = _norm_ws("\n".join(q for q in quotes
                              if isinstance(q, str)))
    nums = set()
    for tok in re.findall(r"-?\d+(?:\.\d+)?", hay):
        try:
            nums.add(float(tok))
        except ValueError:
            pass
    for s in want:
        t = _norm_ws(s)
        if t and t in hay:
            continue
        try:
            f = float(str(s).replace(",", ""))
        except ValueError:
            errors.append("%s: value %r is not in the quoted "
                          "source" % (where, s))
            continue
        if f not in nums:
            errors.append("%s: value %r is not in the quoted "
                          "source" % (where, s))


def write_slide_draft(ctx, args):
    """Vera's slide plan v2: cut+time match vs Wren's narration,
    view budget (2 files per cut), layout-checked blocks,
    photo/generated backed by helper picks and readable, data
    blocks copying Max's values exactly, source figures readable,
    image boxes matching material aspect."""
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
    from . import media as _media
    views = {}
    try:
        with open(os.path.join((ctx or {}).get("run_dir", ""),
                               "vera_views.json"),
                  encoding="utf-8") as f:
            views = json.load(f)
    except (OSError, ValueError):
        views = {}
    if not isinstance(views, dict):
        views = {}
    for i, cut in enumerate(obj["cuts"]):
        cid = cut.get("cut_id")
        n = views.get(cid, 0)
        if isinstance(n, dict):
            n = n.get("views", 0)
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 0
        if n > _media.VERA_VIEW_CAP:
            errors.append("cuts[%d]: viewed %d files, budget is %d "
                          "per cut" % (i, n,
                                       _media.VERA_VIEW_CAP))
    if errors:
        return {"ok": False, "errors": errors}
    producer = (ctx or {}).get("producer", "")
    order_id = (ctx or {}).get("order_id", "")
    have = {"photo": _use_cuts(_received_data(ctx, "photo_picks")),
            "generated": _use_cuts(_received_data(ctx,
                                                  "gen_picks")),
            "animation": _use_cuts(_received_data(ctx,
                                                  "anim_picks"))}
    maxp = {}
    for mc in ((_received_data(ctx, "anim_picks") or {}).get("cuts")
               or []):
        if isinstance(mc, dict) and mc.get("decision") == "use" \
                and mc.get("cut_id"):
            maxp[mc["cut_id"]] = mc
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
                _readable_ref(errors, b.get("ref"), producer,
                              order_id, where)
                _material_aspect(errors, b.get("ref"),
                                 b.get("box") or {}, where)
            elif kind == "source_figure":
                _readable_ref(errors, b.get("ref"), producer,
                              order_id, where)
                _figure_kind(errors, b.get("ref"), where)
                _material_aspect(errors, b.get("ref"),
                                 b.get("box") or {}, where)
            elif kind in ("table", "formula", "chart", "steps"):
                _anim_backed(errors, maxp, cut.get("cut_id"), kind,
                             b, where)
            elif kind != "text":
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


@readlog.logged("voice")
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


def render_slide(ctx, args):
    """Render one cut's slide PNG via the Remotion CutSlide
    composition (last frame of the cut). Max 3 renders per cut per
    run. Every call records slides/<cut>.props.json (the exact
    render inputs, guide included) for the assembly records.
    Without Remotion the render is skipped honestly: ok True
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
    sdir = os.path.join(ctx["run_dir"], "slides")
    os.makedirs(sdir, exist_ok=True)
    props = video.cut_slide_props(cut, guide)
    sidecar = os.path.join(sdir, "%s.props.json" % cut_id)
    try:
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        return {"ok": False, "errors": ["props sidecar failed: %s"
                                        % exc]}
    if not _have_remotion():
        counts[cut_id] = n
        _counter_save(countp, counts)
        return {"ok": True, "slide_file": "",
                "status": "remotion_unavailable",
                "renders_n": 0,
                "props_file": "slides/%s.props.json" % cut_id,
                "note": "Remotion is not installed; run "
                        "tools/setup_video.ps1 to install it"}
    out = os.path.join(sdir, "%s.png" % cut_id)
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
            "renders_n": n,
            "props_file": "slides/%s.props.json" % cut_id}


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
        "use pick names a template with structured values quoted "
        "verbatim from CHECKED source tables/formulas.",
        {"type": "object",
         "properties": {"anim_picks": {"type": "object"}},
         "required": ["anim_picks"], "additionalProperties": False},
    ),
    "write_slide_draft": (
        write_slide_draft,
        "Save Vera's slide plan as this run's result.json "
        "(slide_draft category). Fails unless cuts match Wren's "
        "narration, images are backed and readable, and data "
        "blocks copy Max's values exactly.",
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
    "search_knowledge": (
        search_knowledge,
        "Look one question up in your LightRAG knowledge index "
        "before answering.",
        {"type": "object",
         "properties": {"query": {"type": "string"}},
         "required": ["query"], "additionalProperties": False},
    ),
    "update_form": (
        update_form,
        "Save what this turn revealed into the order's request "
        "form (clean professional third-person wording).",
        {"type": "object",
         "properties": {"audience": {"type": "string"},
                        "length": {"type": "string"},
                        "depth": {"type": "string"},
                        "theme": {"type": "string"}},
         "additionalProperties": False},
    ),
    "finalize_and_send": (
        finalize_and_send,
        "When the form is full, the PDF is attached and the client "
        "agrees: write the final request and send the PDF to the "
        "parser. Your job ends here.",
        {"type": "object", "properties": {},
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

