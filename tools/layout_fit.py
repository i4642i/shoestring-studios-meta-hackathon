"""The screen designer's ruler: for one cut, a layout from the library and which material goes into which slot, it
computes how well each material fits its slot (slot fit, text size) and which other layouts hold the same materials
better. Numbers are computed here; the designer only reads the sentences and judges. Every judged fill is recorded
(.cache/layout_fit/), so the designer's checker can see that the chosen fill was measured."""

import json
import pathlib

from tools import _layouts as L

NAME = "layout_fit"
DESC = ("Give one cut, a layout and the material for each slot. For every slot it computes how much of the slot the "
        "material fills (slot fill %) and how many px its text is drawn at, answers in sentences, and names 1-2 other "
        "layouts that hold the same materials better (only layouts whose material capacity equals the number of "
        "candidate materials in the fill). A material is a candidate id (ph-, gn-, ch-) or "
        "text you write yourself (use \"lines\" with lines). Always measure the fill you chose with this tool before you save.")
SCHEMA = {
    "type": "object",
    "properties": {
        "cut_id": {"type": "string"},
        "layout": {"type": "string", "description": "layout id (L01-L11)"},
        "fill": {"type": "array", "minItems": 1, "items": {
            "type": "object",
            "properties": {"slot": {"type": "string"}, "use": {"type": "string"},
                           "lines": {"type": "array", "items": {"type": "string"}}},
            "required": ["slot", "use"]}},
        "theme": {"type": "string"},
    },
    "required": ["cut_id", "layout", "fill"],
}


SERVERS = ("materials", "image", "generated")     # Max's animation values, photos, generated pictures


def _items(ctx) -> dict:
    """{title: file server item} over this run's materials, image and generated file servers (the newest item per
    title across the three)."""
    base = pathlib.Path(ctx["project"]) / "runs" / str(ctx["run_id"]) / "file_servers"
    found = []
    for server in SERVERS:
        for f in (base / server / "items").glob("*.json"):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if it.get("title"):
                found.append((f.stat().st_mtime, f.name, it))
    out = {}
    for _, _, it in sorted(found, key=lambda x: (x[0], x[1])):
        out[str(it["title"])] = it
    return out


def material(use: str, lines, items: dict) -> dict | str:
    """A material dict from a fill entry, or an error sentence."""
    if use == "lines":
        if not lines:
            return "When use is lines, put 1-3 lines of on-screen text in lines."
        return {"lines": [str(x) for x in lines]}
    it = items.get(use)
    if not it:
        near = sorted(items)[:20]
        return (f"Material {use} is not on the file servers materials/image/generated. Copy an id exactly from the "
                f"candidate lists (ids there: {', '.join(near)}).")
    path = str(it.get("path") or "")
    if str(it.get("format")) == "json":
        try:
            d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return f"Could not read the file of material {use} ({path})."
        return {"id": use, "template": d.get("template"), "values": d.get("values") or {}}
    return {"id": use, "file": path}


def run(ctx, args):
    lib = L.library()
    lay_id = str(args["layout"]).strip()
    layout = lib["layouts"].get(lay_id)
    if not layout or lay_id not in L.usable_layout_ids():
        ids = ", ".join(L.usable_layout_ids())
        return {"error": f"Layout {lay_id} is not in the list you can choose from. Use one of: {ids}."}
    theme = args.get("theme") or "shoestring"
    items = _items(ctx)
    fill, problems = [], []
    for f in args["fill"]:
        m = material(str(f["use"]), f.get("lines"), items)
        if isinstance(m, str):
            problems.append(m)
            continue
        slot = L.slot_of(layout, str(f["slot"]))
        if not slot:
            problems.append(f"{lay_id} has no slot {f['slot']} (its slots: {', '.join(s['id'] for s in layout['slots'])}).")
            continue
        if slot.get("kind") == "text" and m.get("template") == "text":    # a text card in a text slot is its lines
            lines = [str(x) for x in (m.get("values") or {}).get("lines") or [] if str(x).strip()][:3]
            m = material("lines", lines, items) if lines else m
        fill.append((str(f["slot"]), m))
    if problems:
        return {"error": " ".join(problems)}
    mats = [m for _, m in fill]
    n_mat = sum(1 for m in mats if L.kind_of(m) != "lines")
    # measure every json material / lines in one browser run (photos: file size)
    need = [m for m in mats if L.kind_of(m) != "photo"]
    boxes = L.measure_boxes([L.material_layer(m) for m in need], theme) if need else []
    nats = {}
    for m, b in zip(need, boxes):
        nats[id(m)] = L.natural(m, theme, b) if b else None
    for m in mats:
        if L.kind_of(m) == "photo":
            nats[id(m)] = L.natural(m, theme)
    rows = L.judge_fill(layout, fill, nats)
    sc = L.score(rows)
    ok = all(r["ok"] for r in rows)
    # other layouts that hold the same materials
    others = []
    for lid in L.layouts_for(n_mat, exclude=(lay_id,)):       # same material count only
        got = L.best_fills(lib["layouts"][lid], mats, nats)
        if got:
            others.append((got[0][0], lid, got[0][1], got[0][2]))
    others.sort(key=lambda x: -x[0])
    better = [o for o in others if o[0] > sc][:2] or others[:1]
    suggest = []
    for s2, lid, f2, rows2 in better:
        where = ", ".join(f"{sid}={m.get('id') or 'lines'}" for sid, m in f2)
        vs = "better than the current fill" if s2 > sc else "same as or worse than the current fill"
        suggest.append({"layout": lid, "name": lib["layouts"][lid]["name"], "fill": where, "score": f"{s2:.0%}", "vs_now": vs,
                        "say": f"In {lid} {lib['layouts'][lid]['name']} with {where}: " +
                               " ".join(r["say"] for r in rows2)})
    key = L.fill_key(str(args["cut_id"]), lay_id, fill)
    L.save_record(key, {"cut_id": args["cut_id"], "layout": lay_id, "ok": ok, "score": sc,
                        "rows": [{k: r[k] for k in ("slot", "material", "kind", "fit", "text_px", "ok")} for r in rows],
                        "better": [{"layout": o[1], "score": o[0]} for o in better if o[0] > sc]})
    verdict = (f"Every slot meets the targets (slot fill {L.FIT_OK:.0%} or more, text {L.TEXT_OK:g}px or more)." if ok else
               "Some slots miss the targets. Compare the other layouts below, or other materials.")
    lo, hi = L.material_range(layout)
    fits = L.layouts_for(n_mat)
    capacity = (f"{lay_id} holds {L.capacity_say(layout)} candidate material(s) and this fill has {n_mat}: "
                + ("the count fits." if lo <= n_mat <= hi else
                   f"the count does not fit. Layouts that hold {n_mat}: {', '.join(fits) or 'none'}"
                   f"{'' if L.MIN_MATERIALS <= n_mat <= L.MAX_MATERIALS else f' (a cut takes {L.MIN_MATERIALS}-{L.MAX_MATERIALS} materials)'}."))
    return {"layout": L.describe(layout), "capacity": capacity, "slots": [r["say"] for r in rows], "verdict": verdict,
            "worst_slot_score": f"{sc:.0%}", "other_layouts": suggest,
            "note": "The numbers are measured by the program. To compare, look at the verdict in the sentences (targets met or not) and the 'worst slot score'."}
