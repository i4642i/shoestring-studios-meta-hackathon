"""The screen reviewer's eyes: renders the slide builder's saved timeline of this scene (same copy number) as
pictures and gives the program's measured items (checklist ids B1-B3, B5, D1-D6; functions/check_layout.py
measure_scene) as evidence. No arguments: it reads the saved timeline, slide_plan, timing and visuals from this run's
records. The measured items are also saved for the reviewer's checker (tools/_review.py save_measures)."""

import json
import pathlib

from tools import preview_slides

NAME = "inspect_screens"
DESC = ("Show the slide builder's saved screens of this scene as pictures (one per main layer), with the program's "
        "measured problems per cut (checklist ids and their numbers) and, per cut, what the screen designer may "
        "change (layouts that hold the cut's material count, unused candidates of the cut, her text slots). From the "
        "second check on, also 'last_review': the cuts that changed since the last check and your last checklist. "
        "Takes no arguments. Call it once before you fill in the checklist.")
SCHEMA = {"type": "object", "properties": {}}


def _latest_output(block_dir: pathlib.Path) -> dict | None:
    """The newest finished output.json of a block (iterations first, then attempts)."""
    num = lambda p: int(p.name.split("-")[1])
    iters = sorted(block_dir.glob("iter-*"), key=num) or [block_dir]
    for d in reversed(iters):
        for a in sorted(d.glob("attempt-*"), key=num, reverse=True):
            st = a / "status.json"
            if st.is_file() and json.loads(st.read_text(encoding="utf-8")).get("status") == "done":
                return json.loads((a / "output.json").read_text(encoding="utf-8"))
    return None


def _piece(run_dir: pathlib.Path, k: str) -> dict:
    """This scene's piece of the split (visuals, timing), {} when it cannot be read."""
    for a in sorted((run_dir / "blocks" / "split").glob("attempt-*/pieces.json"), reverse=True):
        try:
            pieces = json.loads(a.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if k and int(k) <= len(pieces):
            return pieces[int(k) - 1] or {}
    return {}


def run(ctx, args):
    from functions import check_layout as CL
    from tools import _layouts as L
    from tools import _review as R
    run_dir = pathlib.Path(ctx["project"]) / "runs" / ctx["run_id"]
    _, _, k = str(ctx["block"]).partition("@")
    at = lambda name: name + (f"@{k}" if k else "")
    out = _latest_output(run_dir / "blocks" / at("editor"))
    if not out or "timeline" not in out:
        return {"error": f"no saved timeline of {at('editor')} yet"}
    tl = out["timeline"]
    piece = _piece(run_dir, k)
    visuals, timing = piece.get("visuals") or {}, piece.get("timing") or {}
    plan = (_latest_output(run_dir / "blocks" / at("designer")) or {}).get("slide_plan") or {}
    notes, keep = [], {}
    items = CL.measure_scene(ctx, tl, timing, visuals, plan, notes, keep)
    res = keep.get("res")
    if not isinstance(res, dict) or res.get("error"):
        res = preview_slides.run(ctx, {"timeline": tl, "theme": str(visuals.get("theme") or "shoestring")})
    else:
        R.save_measures(tl, items)
    if not isinstance(res, dict) or res.get("error"):
        return res
    from tools._cuts import run_material_cuts
    members = run_material_cuts(ctx)                 # a material belongs to every cut whose maker report lists it
    R.save_members(tl, members)
    names = CL.MINOR | CL.SEVERE
    measured: dict = {}
    for x in items:
        measured.setdefault(str(x.get("cut")), []).append(
            {"what": x.get("what"), "name": names.get(str(x.get("what")), ""),
             "level": "severe" if x.get("what") in CL.SEVERE else "minor",
             "where": x.get("where"), "now": x.get("now"), "change_to": x.get("change_to")})
    view = {"pictures": res.get("pictures"), "_images": res.get("_images"),
            "measured_problems": measured or "the program measured no problem on these screens",
            "measurement_notes": notes,
            "designer_may_change": R.allowed_changes(plan, L, members),
            "note": ("These are the slide builder's screens as they will be rendered. measured_problems are measured by "
                     "the program: list every one of them in its cut with the same what id and copy its now; you "
                     "cannot drop one or change its id. Add only what you see yourself: B4 (awkward alignment, line "
                     "breaks, an important part of a photo cut off), without numbers. Anything neither worker can "
                     "change goes into notes.")}
    last = _last_review(run_dir, k, tl)
    if last:
        view["last_review"] = last
    return view


def _last_review(run_dir: pathlib.Path, k: str, timeline: dict) -> dict | None:
    """From iteration 2: which cuts changed since the last check, and the last checklist (stable review)."""
    from tools import _review as R
    me = run_dir / "blocks" / ("reviewer" + (f"@{k}" if k else ""))
    n = max((int(d.name.split("-")[1]) for d in me.glob("iter-*")), default=1)
    deciding = run_dir / "blocks" / ("check_layout" + (f"@{k}" if k else ""))
    basis = R.previous_basis(deciding / f"iter-{n}" / "attempt-1" / "files", n)
    if not basis:
        return None
    plan = _latest_output(run_dir / "blocks" / ("designer" + (f"@{k}" if k else ""))) or {}
    changed = R.changed_cuts(basis.get("timeline"), timeline, basis.get("plan"), plan.get("slide_plan"))
    cuts = [str(c.get("cut_id")) for c in timeline.get("cuts") or []]
    return {"changed_cuts": changed, "unchanged_cuts": [c for c in cuts if c not in changed],
            "last_checklist": basis.get("checklist"),
            "rule": ("Judge only the changed cuts. For an unchanged cut copy your last entry for that cut (the program "
                     "keeps it anyway and drops new remarks about unchanged cuts); measured problems are still listed.")}
