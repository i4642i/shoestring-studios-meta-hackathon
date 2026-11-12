RULES = [
    "checklist.cuts lists every content cut of the scene once (not the title or end cut).",
    "verdict P1 (good) has no problems and an empty note; P2 (a little off but fine to watch) has no problems and a note; problems has at least one problem.",
    "what is one of B1, B2, B3, B4, B5 (minor: the Slide Builder fixes it by placement) or D1, D2, D3, D4, D5, D6 (severe: the Screen Designer changes the layout, a material or her text).",
    "Every measured what id of inspect_screens is listed in its cut at least once with the same id; now copies the measured value. Measured ids (all but B4) are used only where the program measured them. You write no numbers of your own (px, %, scale).",
    "A minor (B) problem's change_to is a placement change only: size, weight tier, line breaks, alignment or position inside the slot, spacing, scaling or cropping of a material in its slot, appearance timing. It never changes words, a material, the layout or the narration.",
    "A severe (D) problem's change_to is exactly one thing the Screen Designer may change in that cut, with no other words: a bare layout id from designer_may_change (it holds the cut's material count), a bare unused candidate id of that cut, 'drop <candidate id>' of a material in the cut, 'another layout', or for D2 and D5 new text for one of her text slots (where = that slot). A copy of the measured change_to is also accepted.",
    "change_to is never the same as now.",
    "Something neither worker can change (narration, directions, the quality or content of a material, missing candidates, the layout library) is not a problem: write it in notes.",
    "Write English only.",
]

import importlib.util
import json
import pathlib
import re

MINOR = {"B1": "small text", "B2": "much empty space", "B3": "overlap inside one slot",
         "B4": "awkward alignment or line breaks", "B5": "a planned material does not show"}
SEVERE = {"D1": "material shape does not suit its slot", "D2": "text does not fit its slot",
          "D3": "most of the screen is empty", "D4": "overlap between slots", "D5": "a slot has nothing planned",
          "D6": "material count does not match the slots"}
OWN = {"B4"}                                     # judged by eye; every other id is measured by the program
PLACEMENT = ("size", "larger", "bigger", "smaller", "font", "weight", "bold", "line break", "break", "wrap", "align",
             "left", "right", "center", "centre", "top", "bottom", "middle", "position", "move", "shift", "spacing",
             "space", "margin", "padding", "gap", "scale", "enlarge", "grow", "crop", "fit", "timing", "appear",
             "start", "earlier", "later", "second", "place", "front", "visible", "layer", "lines")
CONTENT = ("remove", "delete", "rewrite", "reword", "rephrase", "shorten", "replace", "new text", "add text",
           "different text", "another word", "other words", "drop", "narration", "swap", "another material",
           "other layout", "another layout")
UNIT_NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:px|%|x\b|pt\b)", re.I)
LAYOUT_ID = re.compile(r"\bL\d{2}\b")
CAND_ID = re.compile(r"\b(?:ph|gn|ch)-[A-Za-z0-9_.-]+")
FOREIGN = re.compile("[ᄀ-ᇿ㄰-㆏가-힣぀-ヿ㐀-䶿一-鿿豈-﫿]+")


def _load(name):
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"naw_{name}", path)
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


def _nums(s) -> list[str]:
    return [re.sub(r"\s+", "", m.group(0)).lower() for m in UNIT_NUM.finditer(str(s or ""))]


def _words(value) -> set[str]:
    text = re.sub(r"<[^>]+>", " ", json.dumps(value, ensure_ascii=False))
    return {w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'%.-]*", text)}


def content_cuts(tl, plan) -> list[str]:
    lay = {str(c.get("cut_id")): str(c.get("layout") or "") for c in (plan or {}).get("cuts") or [] if isinstance(c, dict)}
    order = [str(c.get("cut_id")) for c in (tl or {}).get("cuts") or [] if isinstance(c, dict)] or list(lay)
    tl_lay = {str(c.get("cut_id")): str(c.get("layout") or "") for c in (tl or {}).get("cuts") or [] if isinstance(c, dict)}
    return [cid for cid in order if (lay.get(cid) or tl_lay.get(cid)) not in ("title", "end")]


def check(outputs, inputs=None):
    L, R = _load("_layouts"), _load("_review")
    ck = outputs["checklist"]
    tl = _input(inputs, "timeline") or {}
    plan = _input(inputs, "slide_plan") or {}
    want = content_cuts(tl, plan)
    may = R.allowed_changes(plan, L, R.load_members(tl) if tl else None)
    measured = R.load_measures(tl) if tl else None
    screen = {str(c.get("cut_id")): _words(c.get("layers")) for c in tl.get("cuts") or [] if isinstance(c, dict)}
    fill_of = {str(c.get("cut_id")): c.get("fill") or [] for c in plan.get("cuts") or [] if isinstance(c, dict)}
    errors = []
    got = [str(c["cut"]) for c in ck["cuts"]]
    if want:
        for cid in want:
            if cid not in got:
                errors.append(f"checklist has no entry for cut {cid}. Add {{cut: \"{cid}\", verdict, note, problems}} "
                              f"(content cuts of this scene: {', '.join(want)}).")
        for cid in sorted(set(got) - set(want)):
            errors.append(f"cut {cid} is not a content cut of this scene (content cuts: {', '.join(want)}; title and "
                          f"end cuts are not judged). Remove its entry.")
        for cid in sorted({x for x in got if got.count(x) > 1}):
            errors.append(f"cut {cid} is in the checklist {got.count(cid)} times. Keep one entry and put all its "
                          f"problems there.")
    by_m: dict = {}
    for x in measured or []:
        by_m.setdefault((str(x.get("cut")), str(x.get("what"))), []).append(x)
    for c in ck["cuts"]:
        cid, verdict, probs = str(c["cut"]), c["verdict"], c["problems"]
        note = str(c.get("note") or "").strip()
        if verdict in ("P1", "P2") and probs:
            errors.append(f"cut {cid}: verdict is {verdict} but it lists {len(probs)} problem(s). Fix: set verdict to "
                          f"problems, or move what is only a little off into note with verdict P2.")
        if verdict == "P2" and not note:
            errors.append(f"cut {cid}: verdict P2 needs a note saying what is a little off (e.g. \"margins slightly "
                          f"uneven\"). Fix: write it in note, or use P1 if nothing is off.")
        if verdict == "P1" and note:
            errors.append(f"cut {cid}: verdict P1 has a note (\"{note[:40]}\"). Fix: use P2 for a cut that is a little "
                          f"off, or empty the note.")
        if verdict == "problems" and not probs:
            errors.append(f"cut {cid}: verdict is problems but no problem is listed. Fix: list each with what, where, "
                          f"now, change_to, why, or set verdict P1/P2.")
        mine = {(cid, str(p["what"])) for p in probs}
        for (mc, mw), xs in by_m.items():
            if mc == cid and (mc, mw) not in mine:
                x = xs[0]
                errors.append(f"cut {cid}: the program measured {mw} ({(MINOR | SEVERE).get(mw, '')}) at "
                              f"{x.get('where')}: {x.get('now')}. A measured problem cannot be left out or given "
                              f"another id. Fix: add a problem with what \"{mw}\", where \"{x.get('where')}\", now "
                              f"\"{x.get('now')}\".")
        for p in probs:
            errors += _problem(cid, p, by_m, measured is not None, may.get(cid) or {}, screen.get(cid) or set(),
                               fill_of.get(cid) or [])
    bad = sorted(set(FOREIGN.findall(json.dumps(ck, ensure_ascii=False))))[:5]
    if bad:
        errors.append(f"write English only; replace these characters: {', '.join(bad)}.")
    return errors


def _problem(cid, p, by_m, have_measures, may, screen, fill) -> list[str]:
    out = []
    what, where = str(p["what"]), str(p["where"]).strip()
    now, change, why = str(p["now"]).strip(), str(p["change_to"]).strip(), str(p["why"]).strip()
    at = f"cut {cid} {what} ({where or 'no where'})"
    if not where or not change or not why:
        empty = [k for k, v in (("where", where), ("change_to", change), ("why", why)) if not v]
        out.append(f"{at}: {', '.join(empty)} is empty. Fix: write where (the slot or element), the concrete "
                   f"change_to and one sentence of why.")
        return out
    if change.lower() == now.lower():
        out.append(f"{at}: change_to equals now (\"{now}\"). Fix: write the value to change to.")
    prog = by_m.get((cid, what), [])
    if what not in OWN and have_measures and not prog:
        out.append(f"{at}: {what} ({(MINOR | SEVERE)[what]}) is measured by the program, and it measured no {what} in "
                   f"cut {cid}. Fix: remove this problem; if you see something uneven by eye use B4, or write it in "
                   f"notes.")
    allowed = {n for x in prog for n in _nums(x.get("now")) + _nums(x.get("change_to"))}
    invented = [n for n in _nums(now) + _nums(change) if n not in allowed]
    if invented:
        src = "the measured values" if prog else "no measured value; B4 has none"
        out.append(f"{at}: the numbers {', '.join(invented)} are not from the program ({src}). You do not measure "
                   f"numbers. Fix: copy now from the measured problem, or describe it in words (e.g. \"larger\", "
                   f"\"one line\").")
    if what in MINOR:
        if not (len(change) >= 3 and any(change.lower() in str(x.get("change_to") or "").lower() for x in prog)):   # copied program fix: ok
            used = {str(f.get("use")) for f in fill}
            out += _minor(at, change, screen, used)
    elif not (len(change) >= 3 and any(change.lower() in str(x.get("change_to") or "").lower() for x in prog)):  # copied program fix: ok
        out += _severe(at, what, where, change, may, fill)
    return out


def _minor(at, change, screen, used=()) -> list[str]:
    low = change.lower()
    out = []
    hits = ([w for w in CONTENT if w in low] + LAYOUT_ID.findall(change)
            + [x for x in CAND_ID.findall(change) if x not in used])      # placing a planned material is placement
    if hits:
        out.append(f"{at}: change_to \"{change}\" changes content ({', '.join(sorted(set(hits)))}). The Slide Builder "
                   f"only places what was decided: size, weight tier, line breaks, alignment or position inside the "
                   f"slot, spacing, scaling or cropping of a material, appearance timing. Fix: write one of these, or "
                   f"if the words, a material or the layout must change, it is a D problem for the Screen Designer.")
    elif not any(w in low for w in PLACEMENT):
        out.append(f"{at}: change_to \"{change}\" names no placement change. Fix: say which placement changes and to "
                   f"what (e.g. \"larger, fill the slot width\", \"break after 'returns'\", \"align left in the slot\", "
                   f"\"crop to keep the face\", \"appear at the start of the cut\").")
    for q in re.findall(r"[\"']([^\"']{2,})[\"']", change):
        new = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'%.-]*", q) if w.lower() not in screen]
        if new:
            out.append(f"{at}: change_to quotes \"{q}\", but {', '.join(new[:4])} is not on this cut's screen. The Slide "
                       f"Builder keeps every word. Fix: quote only words already on the screen (for line breaks), or "
                       f"make new words a D2 problem for the Screen Designer's text slot.")
    return out


def _severe(at, what, where, change, may, fill) -> list[str]:
    layouts, cands = may.get("layouts") or [], may.get("candidates") or []
    texts = may.get("text_slots") or []
    used = [str(f.get("use")) for f in fill if f.get("use") and f.get("use") != "lines"]
    low = change.lower().strip()
    if low == "another layout":
        return []
    if LAYOUT_ID.fullmatch(change):
        if change not in layouts:
            return [f"{at}: change_to layout {change} is not one the Screen Designer can use here: this cut has "
                    f"{may.get('materials', '?')} material(s) in {may.get('layout', '?')}, and the layouts that hold "
                    f"that count are {', '.join(layouts) or 'none'}. Fix: write one of these, or \"another layout\"."]
        return []
    if CAND_ID.fullmatch(change):
        if change not in cands:
            return [f"{at}: change_to {change} is not an unused candidate of this cut (unused candidates: "
                    f"{', '.join(cands) or 'none'}). Fix: write one of these, a layout id ({', '.join(layouts) or 'none'}) "
                    f"or \"another layout\"."]
        return []
    m = re.fullmatch(r"drop\s+((?:ph|gn|ch)-\S+)", low)
    if m:
        if m.group(1) not in [u.lower() for u in used]:
            return [f"{at}: change_to drops {m.group(1)}, which is not a material of this cut (materials: "
                    f"{', '.join(used) or 'none'}). Fix: drop one of these or name a layout id."]
        return []
    slot = next((s for s in texts if re.search(rf"\b{re.escape(s)}\b", where)), None)
    if what in ("D2", "D5") and slot:
        return []                                # new text for her own text slot
    choices = (f"a layout id ({', '.join(layouts) or 'none'}), an unused candidate of this cut "
               f"({', '.join(cands) or 'none'}), \"drop <candidate id>\" ({', '.join(used) or 'none'}), "
               f"\"another layout\"")
    if texts:
        choices += f", or new text for her text slot ({', '.join(texts)}; write that slot id in where)"
    return [f"{at}: change_to \"{change}\" is not something the Screen Designer can change. She can change only "
            f"{choices}. Fix: write one of these; if neither worker can change it, move it to notes."]
