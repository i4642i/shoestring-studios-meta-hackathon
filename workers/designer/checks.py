RULES = [
    "Every narration cut appears in slide_plan.cuts once, in narration order, and there are no other cuts.",
    "The use of fill and the ids under dropped are candidate ids of this scene (use may also be lines), copied exactly from the candidate lists.",
    "layout is one of L01-L11 of the layout library (layouts/layouts.json; L12 takes only quote materials, which are not made). A cut that visuals marks title or end uses that value, with empty fill and considered. L13 (section cover) is added by the program; never choose it.",
    "The slot of each fill entry is a slot of that layout, and every slot of the layout is filled. A slot shown together (order together) holds one material; a sequence slot (order sequence) holds its materials one after another (L10 main 1-3, L11 side 1-2).",
    "Put in each slot only the material kinds it accepts. When use is lines, write 1-3 lines in lines, each 40 characters or less.",
    "From the second material of a sequence slot on, at holds a word of that cut's line (the first material shows from the start of the cut, so its at may be empty), in the order the line says them.",
    "A content cut takes 1, 2 or 3 candidate materials (ph-, gn-, ch-; text you write with use lines is no material), and its layout's material capacity holds exactly that count: 1 = L01, L03, L04, L05, L10; 2 = L06, L10, L11; 3 = L07, L08, L09, L10, L11. A candidate goes into one cut only, once, unless the candidate lists put it in several cuts: then it may go into each of those cuts.",
    "A content cut lists in considered 1-2 other layouts it compared (from the library and different from the chosen one).",
    "A content cut's fill (layout and the material in each slot) is exactly what layout_fit measured before saving.",
    "If layout_fit measured a slot under 70% slot fill or text under 16 px and a better layout exists, that fill is not used.",
    "Each highlight word is a word of that cut's lines (the text you wrote); a cut without lines has no highlight.",
    "source holds no fs:// address (viewers see it).",
    "With judgement feedback (redesign), only the cuts named by redesign items of fix_these change layout and fill; every other cut stays as in your_last_plan.",
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the output.",
]

import difflib
import importlib.util
import json
import pathlib
import re

PREFIXES = ("ph-", "gn-", "ch-")
CANDIDATES = ("photo_candidates", "gen_candidates", "chart_candidates")
LINE_MAX = 40
SPECIAL = ("title", "end", "L13")
# the material kinds made in this project, in message words (steps and contents use the slot kind "diagram")
KIND_NAMES = {"photo": "photo", "chart": "chart", "formula": "formula", "numbers": "number",
              "diagram": "steps or contents", "lines": "text (lines)", "figure": "figure"}


def _lib():
    """tools/_layouts.py, loaded by path (the checker may run without the project on sys.path)."""
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / "_layouts.py"
    spec = importlib.util.spec_from_file_location("naw_layouts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _input(inputs, name):
    """The value of terminal `name` among the inputs (short key first, then any "<block>/<name>" key)."""
    if not inputs:
        return None
    if name in inputs:
        return inputs[name]
    for k, v in inputs.items():
        if k.rpartition("/")[2] == name:
            return v
    return None


def _candidates(inputs) -> dict[str, dict]:
    """{candidate id: candidate (with "cut_id", the first cut listing it, and "cut_ids", every cut listing it)} of
    this scene, from the three candidate lists (one material per listed cut; a material may be listed in several)."""
    out = {}
    for name in CANDIDATES:
        for c in ((_input(inputs, name) or {}).get("cuts") or []):
            x = c.get("material") if isinstance(c, dict) else None
            if isinstance(x, dict) and x.get("id"):
                cut = str(c.get("cut_id") or "")
                had = out.get(str(x["id"]))
                cuts = (had["cut_ids"] if had else []) + ([cut] if had is None or cut not in had["cut_ids"] else [])
                out[str(x["id"])] = {**x, "cut_id": cuts[0], "cut_ids": cuts}
    return out


def _text_cards_to_lines(cuts, known, layouts) -> None:
    """A text card (a ch- material with template text) chosen for a text slot is not a material there: the program
    writes its lines into the slot as {use: "lines", lines}, in place (the platform saves the checked object), so it
    does not count toward the layout's material capacity."""
    for c in cuts:
        lay = layouts.get(str(c.get("layout") or "")) or {}
        text_slots = {s["id"] for s in lay.get("slots") or [] if s.get("kind") == "text"}
        for f in c.get("fill") or []:
            m = known.get(str(f.get("use") or ""))
            if f.get("slot") in text_slots and m and m.get("template") == "text":
                lines = [str(x) for x in (m.get("values") or {}).get("lines") or [] if str(x).strip()]
                if lines:
                    f["use"], f["lines"] = "lines", lines[:3]


def _list(xs) -> str:
    return ", ".join(xs) if xs else "none"


def _kind(k) -> str:
    return KIND_NAMES.get(k, k)


def _material(use, entry, known):
    if use == "lines":
        return {"lines": [str(x) for x in entry.get("lines") or []]}
    c = known.get(use) or {}
    if c.get("template"):
        return {"id": use, "template": c["template"], "values": c.get("values") or {}}
    return {"id": use, "file": str(c.get("file") or "")}          # photos (ph-) and generated pictures (gn-)


def check(outputs, inputs=None):
    L = _lib()
    lib = L.library()
    layouts = lib["layouts"]
    choosable = L.usable_layout_ids()
    errors = []
    plan = outputs["slide_plan"]
    cuts = plan["cuts"]
    scene_cuts = [c["cut_id"] for c in cuts]
    known = _candidates(inputs)
    _text_cards_to_lines(cuts, known, layouts)      # a text card in a text slot becomes that slot's lines (program)
    narration = _input(inputs, "narration")
    text_of = {c["cut_id"]: str(c.get("text") or "") for c in ((narration or {}).get("cuts") or []) if isinstance(c, dict)}
    errors += _scene(scene_cuts, narration)
    visuals = _input(inputs, "visuals") or {}
    source_title = str(visuals.get("source_title") or "")
    marked = {c.get("cut_id"): c.get("layout") for c in visuals.get("cuts") or [] if isinstance(c, dict) and c.get("layout")}

    for c in cuts:
        cid, lay, fill = c["cut_id"], c["layout"], c["fill"]
        for x in [f["use"] for f in fill if f["use"] != "lines"] + [d["id"] for d in c["dropped"]]:
            if not _is_candidate(x, known, scene_cuts):
                errors.append(_bad_id(cid, x, known))
        want = marked.get(cid)
        if want in ("title", "end") and lay != want:          # visuals never marks L13 (section_card is separate)
            what = {"title": "title card", "end": "end card"}[want]
            errors.append(f"{cid}: visuals made this the {what} cut (layout {want}). Change layout from {lay} to {want} "
                          f"and make fill and considered empty lists.")
            continue
        if lay in SPECIAL:
            if lay == "L13":
                errors.append(f"{cid}: layout is L13 (section cover). The program adds the section cover in the first 3 s "
                              f"of the part's first cut, so never choose it. Compare layouts that suit this cut "
                              f"({', '.join(choosable)}) with layout_fit and pick one.")
            elif want != lay:
                errors.append(f"{cid}: layout {lay} is used only when visuals marks the cut {lay}. Compare layouts that "
                              f"suit this cut ({', '.join(choosable)}) with layout_fit and pick one.")
            elif fill or c["considered"]:
                errors.append(f"{cid} is a {lay} cut, so its screen is fixed. Make fill and considered empty lists.")
            continue
        layout = layouts.get(lay)
        if not layout:
            near = difflib.get_close_matches(lay, choosable, n=1, cutoff=0.5)
            errors.append(f"{cid}: layout \"{lay}\" is not in the layout library. Change it to one of "
                          f"{', '.join(choosable)}{' (did you mean ' + near[0] + '?)' if near else ''}.")
            continue
        errors += _fill(cid, layout, fill, known, text_of.get(cid, ""), L)
        errors += _considered(cid, lay, c["considered"], choosable)
        errors += _capacity(cid, layout, fill, L)
        errors += _highlight(cid, c, fill)
        if not any(e.startswith(cid + " ") or e.startswith(cid + ":") for e in errors):
            errors += _measured(cid, layout, fill, known, L)
        src = c.get("source") or ""
        if "fs://" in src:
            errors.append(_source_msg(cid, src, source_title))
    used = [f["use"] for c in cuts for f in c["fill"] if f["use"] != "lines"]
    for x in sorted({x for x in used if used.count(x) > 1}):
        where = [c["cut_id"] for c in cuts if any(f["use"] == x for f in c["fill"])]
        if len(where) > 1 and not set(where) <= set((known.get(x) or {}).get("cut_ids") or []):
            errors.append(f"candidate {x} is in {', '.join(where)}. A candidate goes into one cut only: remove it from "
                          f"the fill of {', '.join(where[1:])}.")
    for c in cuts:
        bad = _foreign(c)
        if bad:
            errors.append(f"{c['cut_id']}: write English only; replace these Korean/Chinese/Japanese characters: "
                          f"{', '.join(bad)}.")
    errors += _locked(plan, inputs)
    return errors


def _locked(plan, inputs) -> list[str]:
    """Lock what passed: on redesign only the cuts named by a redesign item of fix_these may change their layout and
    fill; every other cut keeps them exactly as in your_last_plan."""
    fb = _input(inputs, "check_layout/redesign")
    if not isinstance(fb, dict) or not isinstance(fb.get("your_last_plan"), dict):
        return []
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / "_review.py"
    spec = importlib.util.spec_from_file_location("naw_review", path)
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    free = set(R.free_of(fb.get("fix_these") or [], ("redesign",)))
    return R.plan_lock_errors(plan, fb["your_last_plan"], free)


def _fill(cid, layout, fill, known, text, L) -> list[str]:
    out = []
    lid = layout["id"]
    slots = {s["id"]: s for s in layout["slots"]}
    names = ", ".join(f"{s['id']} ({'sequence' if s.get('order') == 'sequence' else 'one'})" for s in layout["slots"])
    for f in fill:
        s = slots.get(f["slot"])
        if not s:
            out.append(f"{cid}: fill has a slot \"{f['slot']}\" that {lid} does not have. The slots of {lid} are "
                       f"{names}. Change slot to one of these.")
            continue
        m = _material(f["use"], f, known)
        kind = L.kind_of(m)
        if f["use"] == "lines":
            lines = f.get("lines") or []
            if not 1 <= len(lines) <= 3:
                out.append(f"{cid} slot {f['slot']}: lines has {len(lines)} lines. Write 1-3 lines of screen text.")
            for i, ln in enumerate(lines):
                if len(ln) > LINE_MAX:
                    out.append(f"{cid} slot {f['slot']}: line {i + 1} has {len(ln)} characters (\"{ln}\"). Shorten it by "
                               f"about {len(ln) - LINE_MAX} characters to {LINE_MAX} or less (drop filler words).")
        elif f.get("lines"):
            out.append(f"{cid} slot {f['slot']} uses candidate {f['use']}, so leave lines empty (text goes only in "
                       f"slots whose use is \"lines\").")
        if f["use"] in known or f["use"] == "lines":
            if not L.accepts(s, kind):
                ok_here = [x for x in layout["slots"] if L.accepts(x, kind)]
                hint = (f" This material fits slot {', '.join(x['id'] for x in ok_here)}." if ok_here else
                        " No slot of this layout takes this material; compare other layouts with layout_fit.")
                out.append(f"{cid} slot {f['slot']} accepts only {', '.join(_kind(a) for a in s.get('accepts') or [] if a in KIND_NAMES)}, "
                           f"but {f['use']} is a {_kind(kind)}.{hint}")
    for sid, s in slots.items():
        mine = [f for f in fill if f["slot"] == sid]
        seq = s.get("order") == "sequence"
        if not mine:
            out.append(f"{cid}: slot {sid} of {lid} is empty ({s['w']}x{s['h']}). Put a fitting material or text "
                       f"(use \"lines\") in it, or compare a layout with fewer slots with layout_fit.")
        elif not seq and len(mine) > 1:
            out.append(f"{cid}: slot {sid} holds {len(mine)} materials ({_list([f['use'] for f in mine])}). It takes "
                       f"one: keep one, or to show them one after another compare L10 or L11.")
        elif seq:
            most = L.sequence_max(layout)
            if len(mine) > most:
                out.append(f"{cid}: slot {sid} of {lid} shows materials one after another and holds at most {most} "
                           f"(now {len(mine)}: {_list([f['use'] for f in mine])}). Drop {len(mine) - most}, or choose "
                           f"a layout that holds {L.material_count(fill)} materials.")
            out += _cues(cid, sid, mine, text)
    for f in fill:
        s = slots.get(f["slot"])
        if s and s.get("order") != "sequence" and f.get("at"):
            out.append(f"{cid} slot {f['slot']} shows from the start together with the others, so it takes no at. "
                       f"Remove at.")
    return out


def _capacity(cid, layout, fill, L) -> list[str]:
    """1-3 candidate materials per content cut, and the layout's material capacity holds exactly that count."""
    lid = layout["id"]
    mats = [f["use"] for f in fill if f["use"] != "lines"]
    n = len(mats)
    out = []
    twice = sorted({x for x in mats if mats.count(x) > 1})
    if twice:
        out.append(f"{cid}: fill uses {', '.join(twice)} more than once. A material goes into one slot only: put "
                   f"another candidate of this cut in the other slot, or choose a layout with fewer material slots.")
    if not L.MIN_MATERIALS <= n <= L.MAX_MATERIALS:
        lo, hi = L.MIN_MATERIALS, L.MAX_MATERIALS
        fix = (f"add the candidate of this cut that shows the line best and choose a layout that holds 1 "
               f"({', '.join(L.layouts_for(1))}); {lid} holds {L.capacity_say(layout)}" if n < lo else
               f"drop the {n - hi} least important and choose a layout that holds {hi} "
               f"({', '.join(L.layouts_for(hi))})")
        return out + [f"{cid}: the fill has {n} candidate materials ({_list(mats)}); a content cut takes "
                      f"{lo}-{hi} (text you write with use lines does not count). Fix: {fix}, then measure it with "
                      f"layout_fit."]
    if not L.holds(layout, n):
        fits = L.layouts_for(n, kinds=[L.id_kind(m) for m in mats])
        out.append(f"{cid}: you chose {n} candidate material(s) ({_list(mats)}) but {lid} holds "
                   f"{L.capacity_say(layout)}. Fix: choose a layout that holds {n} ({', '.join(fits) or 'none'}), or "
                   f"keep {lid} and change the materials to {L.capacity_say(layout)}; then measure it with layout_fit.")
    return out


def _highlight(cid, cut, fill) -> list[str]:
    """highlight words come from the text the designer wrote (lines) in this cut."""
    words = [str(w) for w in cut.get("highlight") or [] if str(w).strip()]
    if not words:
        return []
    text = " ".join(str(x) for f in fill if f["use"] == "lines" for x in f.get("lines") or [])
    if not text:
        return [f"{cid}: highlight is {_list(words)} but this cut has no text slot with lines. Make highlight an "
                f"empty list (what the screen points at in a material goes in focus)."]
    flat = _norm(text)
    bad = [w for w in words if _norm(w) not in flat]
    if bad:
        return [f"{cid}: highlight {_list(bad)} is not in this cut's lines (\"{text[:80]}\"). Copy the 1-2 words to "
                f"stress exactly from your lines, or make highlight empty."]
    return []


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _cues(cid, sid, mine, text) -> list[str]:
    """Each item of a sequence slot names a word of the narration, in narration order."""
    out, last, flat = [], -1, _norm(text)
    for k, f in enumerate(mine):
        at = str(f.get("at") or "").strip()
        if not at and k == 0:
            continue                    # the first item shows from the start of the cut
        if not at:
            out.append(f"{cid} slot {sid}: {f['use']} has no at. Copy into at the word of the line at which this "
                       f"material appears (e.g. \"{' '.join(text.split()[:2])}\" from the line).")
            continue
        pos = flat.find(_norm(at))
        if pos < 0:
            near = difflib.get_close_matches(at, text.split(), n=1, cutoff=0.4)
            hint = f" (did you mean \"{near[0]}\"?)" if near else ""
            out.append(f"{cid} slot {sid}: the at \"{at}\" of {f['use']} is not in this cut's line. Copy a word that "
                       f"is in the line{hint}.")
            continue
        if pos < last:
            out.append(f"{cid} slot {sid}: the materials are not in the order of the line: the at \"{at}\" of "
                       f"{f['use']} comes before the word of the material before it. Put the materials in the order "
                       f"the line says them.")
        last = max(last, pos)
    return out


def _considered(cid, lay, considered, choosable) -> list[str]:
    out = []
    if not considered:
        out.append(f"{cid}: considered is empty. List 1-2 other layouts you compared with layout_fit and why you did "
                   f"not choose them (compare the ones in other_layouts of layout_fit).")
    for x in considered:
        if x["layout"] == lay:
            out.append(f"{cid}: considered holds the chosen layout {lay}. List other layouts you compared but did not "
                       f"choose.")
        elif x["layout"] not in choosable:
            out.append(f"{cid}: considered holds \"{x['layout']}\", which is not in the library. Use one of "
                       f"{', '.join(choosable)}.")
    return out


def _auto_measure(cid, layout, fill, L):
    """The layout_fit record of this fill, with the materials read where layout_fit reads them (the newest items on
    the run's file servers; a candidate list may hold an older version). Measures the fill when it was not measured
    (the program measures, the worker need not). The checker gets no run id, so the run is found by the materials'
    titles. None when it cannot be done."""
    root = pathlib.Path(__file__).resolve().parents[2]
    ids = {str(f["use"]) for f in fill if f.get("use") and f["use"] != "lines"}
    try:
        from tools import layout_fit
    except Exception:
        return None
    runs = sorted((p for p in (root / "runs").glob("*/file_servers") if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for fs in runs[:20]:
        titles = set()
        for server in layout_fit.SERVERS:
            for f in (fs / server / "items").glob("*.json"):
                try:
                    titles.add(str(json.loads(f.read_text(encoding="utf-8")).get("title") or ""))
                except (OSError, ValueError):
                    continue
        if ids <= titles:
            ctx = {"project": str(root), "run_id": fs.parent.name}
            try:
                items = layout_fit._items(ctx)
                pairs = [(str(f["slot"]), layout_fit.material(str(f["use"]), f.get("lines"), items)) for f in fill]
                if any(isinstance(m, str) for _, m in pairs):
                    return None
                key = L.fill_key(cid, layout["id"], pairs)
                rec = L.load_record(key)
                if not rec:
                    args = {"cut_id": cid, "layout": layout["id"],
                            "fill": [{k: v for k, v in f.items() if k in ("slot", "use", "lines")} for f in fill]}
                    if "error" in layout_fit.run(ctx, args):
                        return None
                    rec = L.load_record(key)
                return rec
            except Exception:
                return None
    return None


def _measured(cid, layout, fill, known, L) -> list[str]:
    """The fill was measured with layout_fit (same layout, same materials in the same slots), and it holds."""
    pairs = [(f["slot"], _material(f["use"], f, known)) for f in fill]
    rec = L.load_record(L.fill_key(cid, layout["id"], pairs))
    args = json.dumps({"cut_id": cid, "layout": layout["id"],
                       "fill": [{k: v for k, v in f.items() if k in ("slot", "use", "lines")} for f in fill]},
                      ensure_ascii=False)
    if not rec:      # look the materials up where layout_fit does (the file servers), measuring if needed
        rec = _auto_measure(cid, layout, fill, L)
    if not rec:
        return [f"{cid}: there is no layout_fit record of this fill ({layout['id']}, "
                f"{', '.join(f['slot'] + '=' + f['use'] for f in fill)}) (it was changed and not measured again, or it "
                f"is new). Call layout_fit with these values before saving: {args}"]
    bad = [r for r in rec.get("rows") or [] if (r.get("kind") in L.AREA_KINDS and r.get("fit") is not None and r["fit"] < L.FIT_OK)
           or (r.get("text_px") and r["text_px"] < L.TEXT_MIN)]
    better = rec.get("better") or []
    if bad and better:
        what = "; ".join(
            f"{r['material']} in slot {r['slot']} fills only {r['fit']:.0%} of the slot" if r.get("fit") is not None and r["fit"] < L.FIT_OK
            else f"the text of {r['material']} in slot {r['slot']} is small ({r['text_px']:g} px)" for r in bad)
        alt = " or ".join(b["layout"] for b in better)
        return [f"{cid}: layout_fit measured the {layout['id']} fill: {what} (standard: slot fill {L.FIT_OK:.0%} or more, "
                f"text {L.TEXT_MIN:g} px or more). Change to {alt}, which holds the same materials better, and measure "
                f"again with layout_fit (changing a material is also a way)."]
    return []


def _scene(scene_cuts, narration) -> list[str]:
    """Every narration cut once, in order, and no other cut."""
    want = [c["cut_id"] for c in ((narration or {}).get("cuts") or []) if isinstance(c, dict) and c.get("cut_id")]
    if not want:
        return []
    out, scene = [], ", ".join(want)
    for cid in want:
        if cid not in scene_cuts:
            out.append(f"slide_plan has no cut {cid} (the cuts of this scene: {scene}). Decide its layout and fill and "
                       f"add it to cuts.")
    for cid in sorted(set(scene_cuts) - set(want)):
        out.append(f"cut {cid} is not a cut of this scene (the cuts of this scene: {scene}). Remove it from slide_plan.")
    for cid in sorted({x for x in scene_cuts if scene_cuts.count(x) > 1}):
        out.append(f"cut {cid} is in slide_plan {scene_cuts.count(cid)} times. Merge them into one.")
    kept = [x for x in scene_cuts if x in want]
    if not out and kept != want:
        out.append(f"the cut order differs from the narration (now: {', '.join(kept)}). Put them in the order {scene}.")
    return out


def _is_candidate(x, known, scene_cuts) -> bool:
    if known:
        return x in known
    return x.startswith(PREFIXES) and any(("-" + k + "-") in x for k in scene_cuts)


def _bad_id(cid, x, known) -> str:
    msg = f"{cid} has an id that is not a candidate of this scene: \"{x}\". "
    if known:
        near = difflib.get_close_matches(x, list(known), n=1, cutoff=0.6)
        hint = f" Did you mean {near[0]}?" if near else ""
        return msg + (f"Copy the id from the candidate lists without changing a character (candidates of this scene: "
                      f"{_list(sorted(known))}).{hint}")
    return msg + ("Candidate ids look like <prefix>-<cut id>-<number> (prefixes ph-, gn-, ch-); copy the "
                  "id from the candidate lists.")


def _source_msg(cid, src, source_title) -> str:
    addrs = re.findall(r"fs://[^\s\"'<>)\]]+", src)
    pages = sorted({int(p) for a in addrs for p in re.findall(r"#p(\d+)$", a)})
    if source_title and pages and all(a.startswith("fs://source/") for a in addrs):
        hint = f" E.g. \"{source_title}, p. {', '.join(map(str, pages))}\"."
    else:
        hint = (" For the source document use source_title from visuals plus the page; for web photos and articles, "
                "the site name; for generated pictures, \"AI-generated image\".")
    return (f"{cid}: source holds an fs:// address ({', '.join(addrs) or src}). Viewers see the source, so change it to "
            f"a source they can recognise.{hint}")


_FOREIGN = re.compile("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters anywhere in the value (LaTeX and file paths included)."""
    return sorted(set(_FOREIGN.findall(json.dumps(value, ensure_ascii=False))))[:5]
