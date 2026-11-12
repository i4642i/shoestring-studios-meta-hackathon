"""Switch block after the screen reviewer (KIND = "switch"), with three cases:
  pass     -> render
  redesign -> back to the screen designer (a severe problem: layout, materials or the designer's text)
  rebuild  -> back to the slide builder (a minor problem: placement inside the same slots)
It measures the scene's screens, reads the reviewer's checklist and picks the case.
The level follows the level of the reviewer's checklist ids (2026-11-11): the reviewer lists, per content cut, the
problems of the finished screens by the ids below (she never judges materials or content). The program measures the
screens itself (the same browser measurement as tools/preview_slides.py), gives the reviewer these measured items as
evidence (tools/inspect_screens.py, cached in .cache/screen_measures/) and the reviewer's checker refuses a checklist
that leaves a measured item out, changes its id (level) or invents numbers.

The checklist ids (plain names in the reviewer's mission). Measured = the program measures it and gives the
number; the reviewer cannot leave it out or change its level. B4 is the reviewer's own (by eye).

| id | level -> branch          | what                                                              | measured by        |
| P1 | pass -> render           | text reads well, slots filled, nothing overlaps, no empty slot    | all within limits  |
| P2 | pass (note) -> render    | a little off but fine to watch (note kept in the run record only) | reviewer (eyes)    |
| B1 | minor -> rebuild         | smallest text < 22 px (source line < 24 px), it can grow in its slot | program        |
| B2 | minor -> rebuild         | screen use 45-55 %, or a material drawn smaller than its slot allows | program        |
| B3 | minor -> rebuild         | overlap inside one slot, <= 40 px                                 | program            |
| B4 | minor -> rebuild         | awkward alignment / line breaks / important part of a photo cut off | reviewer (eyes) |
| B5 | minor -> rebuild         | slide_plan fills the slot but the screen shows it empty / late    | program            |
| D1 | severe -> redesign       | material cannot fill 70 % of its slot and a better layout/material exists | program    |
| D2 | severe -> redesign       | text needs < 16 px in its slot, or the designer's lines are too long | program         |
| D3 | severe -> redesign       | screen use < 45 %, or the cut's opening screen is empty           | program            |
| D4 | severe -> redesign       | overlap between slots, or > 40 px                                 | program            |
| D5 | severe -> redesign       | slide_plan puts nothing in a slot, or its material cannot be shown | program           |
| D6 | severe -> redesign       | material count is not the layout's material capacity              | program            |
Limits: B1 smallest text < 22 px (SourceTag < 24 px); D2 < 16 px; B2 screen height 45-55 %, D3 < 45 %; slot fit
70 % (D1 below it, B2 drawn more than 15 points below what is possible); B3 overlap <= 40 px inside one slot, D4 above
40 px or between slots.
Not failures (notes only, never sent back): a low slot fit or too-small template text that no layout or candidate
fixes; the reviewer's checklist "notes".

The case: any D -> redesign; else any B -> rebuild; else pass. A measured item the reviewer did not list is still
used at its measured level (her checker normally refuses that). Rebuild items carry placement changes only (size, weight tier, line breaks, alignment or
position inside a slot, spacing, scaling/cropping of a material, appearance timing): the slide builder never
changes words, materials, the layout or the narration. Severe items name what the designer may change: a layout
that holds the cut's material count, another candidate of the cut, or the text lines the designer wrote.
Measured problems that neither worker can fix (no better layout or material) go into "notes", never back.

Converging loop (2026-11-11):
- every fix item names its "cut" and, when known, the "layers" (indexes in the measured timeline) that may change;
  the feedback carries "locked" (the rest); on rebuild the editor checker copies it back from the last version, on redesign the designer checker refuses changes to it (tools/_review.py). redesign goes back to the designer only (one back line per branch); the editor then builds the scene again from the new plan, with no feedback.
- stable review: from iteration 2, for every cut that did not change since the last iteration the reviewer's last
  verdict for that cut is used (the effective checklist is kept in files/review_basis.json for the next iteration).
- blank start is judged on the cut's opening screen (the first main layers), after the section cover if the cut has one.
The feedback lists every failed item as {where, now, change_to, why, cut, layers} plus cause. On the last allowed
iteration the scene passes with "left_unfixed" (render_part carries it on to the final output)."""

import json
import math
import pathlib

from functions._common import pick, pick_opt

NAME = "check_layout"
DESC = ("Measures the scene's screens and reads the reviewer's per-cut checklist; pass to render, or send the problems "
        "back by severity: severe to the screen designer (redesign), minor to the slide builder (rebuild)")
KIND = "switch"
CASES = ["pass", "redesign", "rebuild"]
MAX_ITERATIONS = 5

FIT_OK = 0.70
DRAWN_GAP = 0.15         # drawn this much below what is possible = drawn smaller
H_OK, H_MIN = 0.55, 0.45
TEXT_OK, TEXT_MIN = 22.0, 16.0   # B1 below 22 px (source line below SOURCE_OK); D2 below 16 px
SOURCE_OK = 24.0
CSS_MIN = 22             # the slide builder's own rule: no font-size below 22px in an HtmlSlide
OVERLAP_SLOT = 40
# the checklist ids (2026-11-11): B minor -> rebuild (slide builder), D severe -> redesign (screen designer)
MINOR = {"B1": "small text", "B2": "much empty space", "B3": "overlap inside one slot",
         "B4": "awkward alignment or line breaks", "B5": "a planned material does not show"}
SEVERE = {"D1": "material shape does not suit its slot", "D2": "text does not fit its slot",
          "D3": "most of the screen is empty", "D4": "overlap between slots", "D5": "a slot has nothing planned",
          "D6": "material count does not match the slots"}
MEASURED = set(MINOR) - {"B4"} | set(SEVERE)       # B4 is the reviewer's own (by eye)
LABEL_WORDS = {"Kicker": ("kicker", "label", "Kicker"), "SourceTag": ("source", "source line", "SourceTag"),
               "Caption": ("caption", "subtitle", "Caption")}


def _fb(kind, where, now, change_to, why, cut=None, layers=None, what=None):
    """One fix item. cut: the cut id; layers: indexes of the cut's layers that may change (None: the whole cut);
    what: the reviewer's category (layout, small_text, empty_space, overlap)."""
    out = {"to": kind, "where": where, "now": now, "change_to": change_to, "why": why}
    if cut:
        out["cut"] = str(cut)
        out["layers"] = sorted(set(layers)) if layers else None
    if what:
        out["what"] = what
    return out


def severity(item: dict) -> str:
    """The program's severity of a measured item: redesign = severe, rebuild = minor."""
    return "severe" if item.get("to") == "redesign" else "minor"


def measure_scene(ctx, tl, timing, visuals, plan, notes=None, keep=None) -> list[dict]:
    """The program's measured problems of a scene (shared with tools/inspect_screens.py): material count, slot fit,
    screen height, smallest text, overlap, blank start. keep: a dict that gets the preview result under "res"."""
    from tools import _layouts as L
    theme = str((visuals or {}).get("theme") or "shoestring")
    lib = L.library()
    plan_of = {c["cut_id"]: c for c in (plan or {}).get("cuts") or [] if isinstance(c, dict)}
    notes = notes if notes is not None else []
    items = _counts(plan_of, lib, L)
    items += _measured(ctx, tl, timing or {}, theme, plan_of, lib, L, notes, visuals, keep)
    return items


def run(ctx, inputs):
    from tools import _review as R
    tl = pick(inputs, "timeline")
    spec = pick_opt(inputs, "design_spec") or {}
    plan = pick_opt(inputs, "slide_plan") or {}
    checklist = pick_opt(inputs, "checklist") or {"cuts": []}
    timing = pick_opt(inputs, "timing") or {}
    visuals = pick_opt(inputs, "visuals") or {}
    plan_of = {c["cut_id"]: c for c in plan.get("cuts") or [] if isinstance(c, dict)}
    notes: list[str] = []
    # stable review: the reviewer's last verdict stays for cuts that did not change since the last iteration
    last = R.previous_basis(ctx["files_dir"], int(ctx.get("iteration") or 1))
    if last:
        changed = R.changed_cuts(last.get("timeline"), tl, last.get("plan"), plan)
        checklist, kept = R.stable_checklist(checklist, last.get("checklist"), changed)
        notes += kept
    _write_basis(ctx, {"checklist": checklist, "timeline": tl, "plan": plan})
    notes += [f"reviewer note: {n}" for n in checklist.get("notes") or [] if str(n).strip()]
    notes += [f"{c.get('cut')} P2 (fine to watch, a little off): {c.get('note')}" for c in checklist.get("cuts") or []
              if c.get("verdict") == "P2" and str(c.get("note") or "").strip()]
    measured = measure_scene(ctx, tl, timing, visuals, plan, notes)
    items = _route(checklist, measured, tl, spec, plan_of, notes)
    return decide(ctx, items, notes, tl, plan, spec)


def decide(ctx, items, notes, tl, plan, spec) -> dict:
    """The case from the routed items: any redesign -> redesign; else any rebuild -> rebuild; else pass."""
    from tools import _review as R
    keys = ("where", "now", "change_to", "why", "cut", "layers")
    failed = [{k: x[k] for k in keys if k in x} | {"cause": x["to"]} for x in items]
    severe = [x for x in failed if x["cause"] == "redesign"]
    minor = [x for x in failed if x["cause"] == "rebuild"]
    if not items:
        return {"pass": {"iteration": ctx["iteration"], **({"notes": notes} if notes else {})}}
    if ctx["iteration"] >= ctx["max_iterations"]:
        return {"pass": {"iteration": ctx["iteration"], "left_unfixed": failed, **({"notes": notes} if notes else {})}}
    if severe:
        moving = sorted(R.free_of(severe, ("redesign",)))
        keep = [str(c.get("cut_id")) for c in plan.get("cuts") or [] if str(c.get("cut_id")) not in moving]
        return {"redesign": {"fix_these": failed, "your_last_plan": plan, "your_last_timeline": tl,
                             "your_last_spec": spec, "locked_cuts": keep,
                             "locked": R.locked_summary(tl, R.free_of(failed)), "measurement_notes": notes,
                             "note": (f"Some problems are severe (the layout, the materials or the screen text cannot hold "
                                      f"the cut well), so the scene is back at the screen designer. The screen designer "
                                      f"changes only {', '.join(moving)}: to a layout named in change_to (it holds the "
                                      f"cut's material count), another candidate of that cut, or new lines for its text "
                                      f"slot; measure each change with layout_fit. The other cuts "
                                      f"({', '.join(keep) or 'none'}) are locked: keep them as in your_last_plan. After you, the "
                                      f"slide builder builds the scene again from your new plan, and the screen reviewer "
                                      f"checks it again.")}}
    return {"rebuild": {"fix_these": minor, "your_last_plan": plan, "your_last_spec": spec, "your_last_timeline": tl,
                        "locked": R.locked_summary(tl, R.free_of(minor)), "measurement_notes": notes,
                        "note": "These are minor problems, fixed by placement inside the slots of the same layout: size, "
                                "weight tier, line breaks, alignment or position inside a slot, spacing, scaling or "
                                "cropping of a material, appearance timing. Do not change the layout, the slots, the "
                                "materials or any words. Change only the cut and layers of each fix_these item (layer "
                                "numbers in your_last_timeline, from 0; null means the whole cut); the program copies every cut "
                                "and layer under locked back from your_last_timeline when you save."}}


def _write_basis(ctx, basis: dict) -> None:
    from tools import _review as R
    d = pathlib.Path(ctx["files_dir"])
    d.mkdir(parents=True, exist_ok=True)
    (d / R.BASIS).write_text(json.dumps(basis, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ reviewer problems + measured problems

def _layers_for(cid, element, tl_cut, spec_cut, plan_cut) -> list[int] | None:
    """The layer indexes of a cut that a reviewer's element names (a slot id, a design_spec element, a material id,
    a strip such as the Kicker), or None when it cannot be told (then the whole cut may change)."""
    lys = (tl_cut or {}).get("layers") or []
    el = str(element or "").strip()
    if not lys or not el:
        return None
    by_slot = lambda sid: [i for i, ly in enumerate(lys) if str(ly.get("slot") or "") == sid]
    by_type = lambda t: [i for i, ly in enumerate(lys) if ly.get("type") == t]
    slots = {str(ly.get("slot")) for ly in lys if ly.get("slot")}
    if el in slots:
        return by_slot(el)
    for e in (spec_cut or {}).get("elements") or []:
        name = str(e.get("name") or "")
        if name and (el == name or el.startswith(name) or name in el):
            where, role = str(e.get("where") or ""), str(e.get("role") or "")
            if where in slots:
                return by_slot(where)
            for t, words in LABEL_WORDS.items():
                if where in words or role in words:
                    return by_type(t) or None
    for f in (plan_cut or {}).get("fill") or []:
        if f.get("use") and f.get("use") != "lines" and str(f["use"]) in el and str(f.get("slot")) in slots:
            return by_slot(str(f["slot"]))
    for t, words in LABEL_WORDS.items():
        if el == t or any(el.startswith(w) for w in words):
            return by_type(t) or None
    return None


def layout_options(plan_cut) -> list[str]:
    """The layouts the designer may change a cut to: same material count, not the current one."""
    from tools import _layouts as L
    fill = (plan_cut or {}).get("fill") or []
    kinds = [L.id_kind(f.get("use")) for f in fill if f.get("use") and f.get("use") != "lines"]
    return L.layouts_for(L.material_count(fill), exclude=(str((plan_cut or {}).get("layout") or ""),), kinds=kinds)


def _options_say(plan_cut) -> str:
    from tools import _layouts as L
    n = L.material_count((plan_cut or {}).get("fill"))
    return f"another layout that holds {n} material(s): {', '.join(layout_options(plan_cut)) or 'none'}"


def _route(checklist, measured, tl=None, spec=None, plan_of=None, notes=None) -> list[dict]:
    """The reviewer's problems merged with the measured items. The level comes from the checklist id: B -> rebuild,
    D -> redesign. A measured item keeps the program's values (the numbers are the program's); a severe item takes
    the reviewer's change_to when it names a layout, a candidate or new lines (its checker validated it). A measured
    item the reviewer did not list is used as it is (her checker normally refuses that)."""
    plan_of = plan_of or {}
    cut_of = {str(c.get("cut_id")): c for c in (tl or {}).get("cuts") or [] if isinstance(c, dict)}
    spec_of = {str(x.get("cut_id")): x for x in (spec or {}).get("screens") or [] if isinstance(x, dict)}
    by: dict = {}
    for x in measured:
        by.setdefault((str(x.get("cut") or ""), str(x.get("what") or "")), []).append(x)
    out, covered = [], set()
    for c in checklist.get("cuts") or []:
        cid = str(c.get("cut") or "")
        for p in c.get("problems") or []:
            what = str(p.get("what") or "")
            if what not in MINOR and what not in SEVERE:
                continue
            to = "redesign" if what in SEVERE else "rebuild"
            prog = by.get((cid, what), [])
            if prog and (cid, what) in covered:
                continue                       # the measured items of this cut and id are in already
            covered.add((cid, what))
            label = f"Screen reviewer {what} ({(MINOR | SEVERE)[what]}): {p.get('why') or ''}"
            change = str(p.get("change_to") or "").strip()
            if prog:
                for x in prog:
                    y = {**x, "why": f"{x['why']} ({label})"}
                    if to == "redesign" and change and change.lower() != "another layout":
                        y["change_to"] = f"{change} (or {x['change_to']})" if change not in x["change_to"] else x["change_to"]
                    out.append(y)
                continue
            if to == "redesign":
                if not change or change.lower() == "another layout":
                    change = _options_say(plan_of.get(cid))
                out.append(_fb("redesign", f"{cid} {p.get('where') or 'cut'}", str(p.get("now") or ""), change,
                               label, cid, None, what))
            else:
                lys = _layers_for(cid, p.get("where"), cut_of.get(cid), spec_of.get(cid), plan_of.get(cid))
                out.append(_fb("rebuild", f"{cid} {p.get('where') or 'cut'}", str(p.get("now") or ""), change,
                               label, cid, lys, what))
    for key, prog in by.items():
        if key in covered:
            continue
        out += prog
        if notes is not None:
            notes.append(f"{key[0]}: the program measured {key[1]} ({(MINOR | SEVERE).get(key[1], '')}), which the "
                         f"reviewer did not list; it is used as measured.")
    return out


# ------------------------------------------------------------------ material count

def _counts(plan_of, lib, L) -> list[dict]:
    out = []
    for cid, c in plan_of.items():
        lay = lib["layouts"].get(str(c.get("layout") or ""))
        if not lay or lay["id"] == L.COVER:
            continue
        n = L.material_count(c.get("fill"))
        if not L.holds(lay, n):
            fits = layout_options(c)
            out.append(_fb("redesign", f"{cid} layout {lay['id']}", f"{n} candidate material(s)",
                           f"a layout that holds {n}: {', '.join(fits) or 'none'} (or {L.capacity_say(lay)} materials "
                           f"in {lay['id']})",
                           f"D6 material count does not match the layout: {lay['id']} holds "
                           f"{L.capacity_say(lay)} candidate material(s); add or drop materials from this cut's "
                           f"candidates, or change the layout.", cid, None, "D6"))
    return out


# ------------------------------------------------------------------ measured on the rendered screens

MATERIAL_SERVERS = ("materials", "image", "generated")   # Max's animation values, photos, generated pictures


def _materials(ctx) -> dict:
    """{candidate id: material} from this run's material file servers (materials, image, generated); the newest item
    per title wins across the three (photos ph- and generated pictures gn- are files, the others json values)."""
    base = pathlib.Path(ctx["project"]) / "runs" / str(ctx["run_id"]) / "file_servers"
    files = [f for s in MATERIAL_SERVERS for f in (base / s / "items").glob("*.json")]
    out = {}
    for f in sorted(files, key=lambda f: (f.stat().st_mtime, f.name)):
        try:
            it = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        t, path = str(it.get("title") or ""), str(it.get("path") or "")
        if not t:
            continue
        if str(it.get("format")) == "json":
            try:
                v = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
                out[t] = {"id": t, "template": v.get("template"), "values": v.get("values") or {}}
            except (OSError, ValueError):
                pass
        else:
            out[t] = {"id": t, "file": path}
    return out


def _possible(cid, plan_cut, lay, mats, theme, L) -> dict:
    """{slot id: judged row of the planned material} (what the slot could show at best), for the first material."""
    out = {}
    fill = []
    for f in plan_cut.get("fill") or []:
        m = {"lines": f.get("lines") or []} if f.get("use") == "lines" else mats.get(str(f.get("use")))
        if m and f.get("slot") not in out:
            fill.append((str(f["slot"]), m))
            out[str(f["slot"])] = None
    need = [m for _, m in fill if L.kind_of(m) != "photo"]
    boxes = L.measure_boxes([L.material_layer(m) for m in need], theme) if need else []
    nats = {id(m): L.natural(m, theme, b) for m, b in zip(need, boxes) if b}
    for _, m in fill:
        if L.kind_of(m) == "photo":
            nats[id(m)] = L.natural(m, theme)
    for sid, m in fill:
        s = L.slot_of(lay, sid)
        out[sid] = L.judge_slot(s, m, nats.get(id(m))) if s else None
    every = []                         # every planned material (sequence slots hold several)
    for f in plan_cut.get("fill") or []:
        m = {"lines": f.get("lines") or []} if f.get("use") == "lines" else mats.get(str(f.get("use")))
        if m:
            every.append((str(f["slot"]), m))
    for _, m in every:
        if id(m) not in nats:
            b = L.measure_boxes([L.material_layer(m)], theme)[0] if L.kind_of(m) != "photo" else None
            nats[id(m)] = L.natural(m, theme, b) if (b or L.kind_of(m) == "photo") else None
    return {"rows": out, "fill": every, "materials": [m for _, m in every], "nats": nats}


def _better(lay, pos, lib, L) -> str:
    """The best other layout for the same materials, as words ("" if none is better)."""
    mats, nats = pos["materials"], pos["nats"]
    now = L.score(L.judge_fill(lay, pos["fill"], nats)) if mats else 0.0
    best = None
    for lid, other in lib["layouts"].items():
        if lid in (lay["id"], L.COVER):
            continue
        got = L.best_fills(other, mats, nats)
        if got and got[0][0] > now and (best is None or got[0][0] > best[0]):
            best = (got[0][0], lid, got[0][1])
    if not best:
        return ""
    where = ", ".join(f"{sid}={m.get('id') or 'lines'}" for sid, m in best[2])
    return f"{best[1]} {lib['layouts'][best[1]]['name']}({where})"


def _better_material(cid, sid, slot, now_fit, used, mats, theme, L, members=None) -> str:
    """Another candidate of this cut (not used in it) that fills this slot better and meets the target, or "".
    members: {material id: [cut ids]} from the makers' reports (a material belongs to every cut listing it)."""
    best = None
    for mid, m in mats.items():
        mine = cid in members[mid] if members and mid in members else f"-{cid}-" in mid
        if not mine or mid in used or not L.accepts(slot, L.kind_of(m)) or L.kind_of(m) not in L.AREA_KINDS:
            continue
        if L.kind_of(m) == "photo":
            nat = L.natural(m, theme)
        else:
            ly = L.material_layer(m)
            b = L.measure_boxes([ly], theme)[0] if ly else None
            nat = L.natural(m, theme, b) if b else None
        if not nat:
            continue
        f = L.fit(nat, slot)["fill"]
        if f >= FIT_OK and f > now_fit and (best is None or f > best[0]):
            best = (f, mid)
    return f"material {best[1]} (fills {best[0]:.0%} of this slot)" if best else ""


def _measured(ctx, tl, timing, theme, plan_of, lib, L, notes, visuals=None, keep=None) -> list[dict]:
    from tools import preview_slides
    from tools._layout import active, blank_start, collect, opening, overlap_pairs, space
    secs = {c["cut_id"]: float(c["seconds"]) + 0.4 for c in timing.get("cuts") or [] if c.get("seconds") is not None}
    sc = (visuals or {}).get("section_card") or {}
    cover = {sc["cut_id"]: L.cover_seconds(secs.get(sc["cut_id"], 6.0))} if sc.get("cut_id") else {}
    out_dir = pathlib.Path(ctx["files_dir"])
    res = preview_slides.run({"files_dir": str(out_dir)}, {"timeline": tl, "seconds": secs, "theme": theme,
                                                           "cover": cover})
    if keep is not None:
        keep["res"] = res
    if not isinstance(res, dict) or res.get("error"):
        return []                                  # nothing measured: the reviewer's items still count
    try:
        raw = json.loads((out_dir / "preview" / "measures.json").read_text(encoding="utf-8"))
        props = json.loads((out_dir / "preview" / "props.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    mats = _materials(ctx)
    from tools._cuts import run_material_cuts
    members = run_material_cuts(ctx)               # a material belongs to every cut whose maker report lists it
    out, t = [], 0.0
    for c in tl.get("cuts") or []:
        cid = c.get("cut_id")
        lys = c.get("layers") or []
        dur = secs.get(cid) or max([float(x.get("end", 0)) for x in lys] + [3.0])
        t0, t1 = t, t + dur
        t = t1
        pc = plan_of.get(cid) or {}
        lay = lib["layouts"].get(str(c.get("layout") or pc.get("layout") or ""))
        mine = [m for m in raw if "layers" in m and t0 * 30 <= m["frame"] < t1 * 30]
        if not mine:
            continue
        whole = not lay or lay["id"] == L.COVER
        pos = _possible(cid, pc, lay, mats, theme, L) if lay and not whole else {"rows": {}, "fill": [], "materials": [], "nats": {}}
        alt = _better(lay, pos, lib, L) if pos["materials"] else ""
        opts = _options_say(pc) if pc and not whole else ""
        seen, frames = set(), []
        for m in mine:
            n_bg, layers = active(props, m["frame"])
            items = collect(m, n_bg, layers)
            frames.append(items)
            used = {str(f.get("use")) for f in pc.get("fill") or []}
            alt_mat = lambda sid, slot, fit, cid=cid, used=used: _better_material(cid, sid, slot, fit, used, mats, theme, L, members)
            for x in _cut_problems(cid, lay, items, layers, t0, pos, alt, whole, L, space, overlap_pairs,
                                   alt_mat, notes, opts):
                key = (x["where"], x["now"])
                if key not in seen:
                    seen.add(key)
                    out.append(x)
        out += _blank_start(cid, opening(frames), t0 + float(cover.get(cid) or 0), blank_start, opts)
        if lay and not whole:
            out += _empty_slots(cid, lay, pc, c, frames, mats, opts, L)
    return out


def _empty_slots(cid, lay, plan_cut, tl_cut, frames, mats, opts, L) -> list[dict]:
    """B5 / D5: a slot of the chosen layout that shows nothing. D5 when slide_plan decided nothing for it or the
    decided material cannot be shown (no file on the file servers); B5 when it was decided but the screen shows it
    in fewer than half of the measured pictures of the cut (layer missing, wrong slot, zero size, hidden, timing)."""
    out = []
    fill = (plan_cut or {}).get("fill") or []
    lys = (tl_cut or {}).get("layers") or []
    for s in lay.get("slots") or []:
        sid = s["id"]
        mine = [f for f in fill if f.get("slot") == sid]
        where = f"{cid} slot {sid} ({lay['id']}, {s['w']}x{s['h']})"
        if not mine:
            out.append(_fb("redesign", where, "slide_plan puts nothing in this slot",
                           f"a candidate of this cut or your lines for slot {sid}, or {opts or 'a layout with fewer slots'}",
                           "D5 a slot has no material to place: the slot stays empty on screen.", cid, None, "D5"))
            continue
        lost = [str(f.get("use")) for f in mine if f.get("use") != "lines" and str(f.get("use")) not in mats]
        if lost and mats:
            out.append(_fb("redesign", where, f"material {', '.join(lost)} has no file on the file servers",
                           f"another candidate of this cut for slot {sid}, or {opts or 'a layout with fewer slots'}",
                           "D5 a slot has no material to place: the decided material cannot be shown.", cid, None, "D5"))
            continue
        if not frames:
            continue
        seen = sum(1 for items in frames if any(it.get("slot") == sid for it in items))
        if seen * 2 < len(frames):
            idx = [i for i, ly in enumerate(lys) if str(ly.get("slot") or "") == sid]
            now = (f"visible in {seen} of {len(frames)} measured pictures" if idx else "no layer has this slot")
            out.append(_fb("rebuild", where, now,
                           f"place {', '.join(str(f.get('use')) for f in mine)} in slot {sid}: a layer with \"slot\": "
                           f"\"{sid}\", visible size, in front, from the start of the cut (or its at word)",
                           "B5 a decided material is not visible in its slot.", cid, idx or None, "B5"))
    return out


def _idx(x) -> int | None:
    """The cut's layer index of a measured item or an active layer (preview_slides tags them with _ref)."""
    ref = x.get("ref") if "ref" in x else x.get("_ref")
    return int(ref[1]) if isinstance(ref, (list, tuple)) and len(ref) > 1 else None


def _blank_start(cid, items, start, blank_start, opts="") -> list[dict]:
    """D3 (the cut's opening screen is empty), judged on the opening screen; start = cut start (+ the section
    cover's seconds)."""
    msgs, info = blank_start(items, start)
    return [_fb("redesign", f"{cid} cut opening", f"first thing visible at {info.get('first_visible_s', 0):g} s, main "
                f"content at {info.get('main_visible_s', 0):g} s",
                opts or "a layout or material whose main element shows from the start of the cut",
                f"D3 very much empty space: {msg}", cid, None, "D3")
            for msg in msgs]


def _cut_problems(cid, lay, items, layers, t0, pos, alt, whole, L, space, overlap_pairs,
                  alt_mat=None, notes=None, opts="") -> list[dict]:
    """The measured items of one screen, each tagged with its checklist id (B1-B3 minor, D1-D4 severe).
    Minor items carry placement changes only; severe items name a better layout or material (alt) or the layouts
    that hold the cut's material count (opts). What neither worker can fix becomes a note."""
    out = []
    lid = lay["id"] if lay else "card"
    other_layout = alt or opts or "another layout whose slots suit these materials better"

    def note(text):
        if notes is not None and text not in notes:
            notes.append(text)

    # slot fit: what each slotted layer covers vs what its material could cover
    for li, ly in enumerate(layers):
        box = ly.get("box")
        if not box or whole:
            continue
        sid = str(ly.get("slot"))
        row = (pos["rows"] or {}).get(sid)
        mine = [it["rect"] for it in items if it["li"] == li and it["kind"] in ("text", "img", "shape", "box")]
        if not mine or not row or row.get("kind") not in L.AREA_KINDS or row.get("fit") is None:
            continue
        x0, y0 = max(min(r[0] for r in mine), box["x"]), max(min(r[1] for r in mine), box["y"])
        x1, y1 = min(max(r[2] for r in mine), box["x"] + box["w"]), min(max(r[3] for r in mine), box["y"] + box["h"])
        drawn = max(0, x1 - x0) * max(0, y1 - y0) / (box["w"] * box["h"])
        possible = row["fit"]
        if possible < FIT_OK:
            # D1 counts only when a better layout or material exists (the designer can fix it); else a note
            other = alt or (alt_mat(sid, L.slot_of(lay, sid), possible) if alt_mat else "")
            if other:
                out.append(_fb("redesign", f"{cid} {lid} {row['material']} in slot {sid}", f"can fill only {possible:.0%} of the slot",
                               other, f"D1 material does not suit its slot: even scaled up, {1 - possible:.0%} of the slot stays empty (target {FIT_OK:.0%} or more).",
                               cid, None, "D1"))
            else:
                note(f"{cid} {lid}: {row['material']} fills only {possible:.0%} of slot {sid}, but no layout holds "
                     f"these materials better and no other candidate suits this slot better, so it is not a failure.")
        elif drawn < possible - DRAWN_GAP and drawn < FIT_OK:
            out.append(_fb("rebuild", f"{cid} {ly.get('type')} in slot {sid}", f"drawn over only {drawn:.0%} of the slot",
                           f"scale it up to fill {FIT_OK:.0%} or more of the slot (this material can fill up to {possible:.0%})",
                           "B2 much empty space: the material suits the slot but is drawn small.", cid,
                           [_idx(ly)] if _idx(ly) is not None else None, "B2"))
    # screen height use
    msgs, info = space(items)
    if info and not whole:
        uh = (info["content_box"][3] - info["content_box"][1]) / L.H
        if uh < H_MIN:
            out.append(_fb("redesign", f"{cid} whole screen ({lid})", f"content uses {uh:.0%} of the screen height",
                           other_layout, f"D3 very much empty space: less than {H_MIN:.0%} of the screen height is used "
                           f"(target {H_OK:.0%} or more).", cid, None, "D3"))
        elif uh < H_OK:
            out.append(_fb("rebuild", f"{cid} whole screen ({lid})", f"content uses {uh:.0%} of the screen height",
                           f"enlarge the text and elements in the slots (size, line breaks, position) to use {H_OK:.0%} "
                           f"({int(H_OK * L.H)}px) of the height or more",
                           "B2 much empty space: the slots are not filled, so the top and bottom look empty.", cid, None, "B2"))
    # smallest text
    smallest = {}                      # one entry per layer: its smallest text below its target
    for it in items:
        target = SOURCE_OK if it.get("layer") == "SourceTag" else TEXT_OK
        if it["kind"] == "text" and it["px"] < target and (it["li"] not in smallest or it["px"] < smallest[it["li"]]["px"]):
            smallest[it["li"]] = it
    for it in sorted(smallest.values(), key=lambda it: it["px"]):
        sid = str(it.get("slot") or "")
        row = (pos["rows"] or {}).get(sid) or {}
        possible = row.get("text_px")
        target = SOURCE_OK if it["layer"] == "SourceTag" else TEXT_OK
        scale = it["px"] / it["fs"] if it.get("fs") else 1.0
        need = max(CSS_MIN, math.ceil(target / scale - 0.01) if scale > 0 else int(target))
        where = f"{cid} {it['layer']} text \"{it['text'][:30]}\"{' in slot ' + sid if sid else ''}"
        mine = [_idx(it)] if _idx(it) is not None else None
        too_long = not whole and ((possible is not None and possible < TEXT_MIN)
                                  or (it["layer"] not in ("HtmlSlide", "SourceTag") and it["px"] < TEXT_MIN))
        if too_long and row.get("kind") == "lines":          # the designer's own text: she shortens it
            cut = max(10, round((1 - (it["px"] / target) ** 2) * 100))
            out.append(_fb("redesign", f"{cid} slot {sid} lines", f"{it['px']:g}px",
                           alt or f"shorter lines for slot {sid} (about {cut}% fewer words)",
                           f"D2 text does not fit its slot: it is drawn at {it['px']:g}px, below {TEXT_MIN:g}px.",
                           cid, None, "D2"))
        elif too_long and alt:
            out.append(_fb("redesign", where, f"{it['px']:g}px", alt,
                           f"D2 text does not fit its slot: it would need less than {TEXT_MIN:g}px.", cid, None, "D2"))
        elif too_long:
            note(f"{where}: drawn at {it['px']:g}px (below {TEXT_MIN:g}px), but no layout holds this material better; "
                 f"another candidate with less text would be the only fix.")
        elif it["layer"] in ("HtmlSlide", "SourceTag"):
            out.append(_fb("rebuild", where, f"font-size {it['fs']:g}px (drawn at {it['px']:g}px)", f"font-size {need}px or more",
                           f"B1 small text: smaller than {target:g}px on the screen; it can grow in its slot.", cid, mine, "B1"))
        elif it["layer"] == "BigText":
            out.append(_fb("rebuild", where, f"{it['px']:g}px",
                           f"line breaks (same words) so the text block matches the slot shape and is drawn at {target:g}px or more",
                           f"B1 small text: smaller than {target:g}px on the screen.", cid, mine, "B1"))
        else:
            note(f"{where}: drawn at {it['px']:g}px (target {target:g}px); the program scales this template to its "
                 f"slot, so only a different layout or material could make it larger.")
    # overlaps
    for a, b, w, h in overlap_pairs(items):
        name = lambda it: f"\"{it['text'][:14]}\"" if it["kind"] == "text" else it["tag"]
        both = [i for i in (_idx(a), _idx(b)) if i is not None]
        if whole or (a["li"] == b["li"] and max(w, h) <= OVERLAP_SLOT and a.get("slot")):
            out.append(_fb("rebuild", f"{cid} {name(a)} and {name(b)} in slot {a.get('slot')}", f"overlap {w}px wide x {h}px high",
                           f"move one of them {h + 8}px or more up/down or {w + 8}px or more sideways",
                           "B3 overlap inside one slot: the text and pictures cover each other.",
                           cid, both if len(both) == 2 else None, "B3"))
        else:
            between = "between slots" if a["li"] != b["li"] else "a large overlap inside one slot"
            out.append(_fb("redesign", f"{cid} {name(a)} and {name(b)} ({between})", f"overlap {w}px wide x {h}px high",
                           other_layout, f"D4 overlap {between}: too large to fix inside a slot.", cid, None, "D4"))
    return out
