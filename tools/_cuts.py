"""Cut helpers shared by the material makers' checkers (photo, gene, anim) and the readers of their reports.
A helper, not a tool (the file name starts with _).

- content_cuts(visuals): the cuts that get materials (every visuals cut whose layout is not "title" or "end").
- material_cuts(reports): {material id: [cut ids]} from the makers' reports. One material may be listed in several
  cuts (made once, put in every cut it fits); it belongs to every cut whose report lists it, not only to the cut
  named in its id.
- run_material_cuts(ctx): the same map, read from this run's latest photo/gene/anim outputs of the same scene copy.
"""

from __future__ import annotations

import json
import pathlib

SPECIAL = ("title", "end")
REPORTS = ("photo_candidates", "gen_candidates", "chart_candidates")
MAKERS = {"photo": "photo_candidates", "gene": "gen_candidates", "anim": "chart_candidates"}


def content_cuts(visuals) -> list[str]:
    """Cut ids of the scene's visuals whose layout is not title or end, in visuals order."""
    out = []
    for c in (visuals or {}).get("cuts") or []:
        if isinstance(c, dict) and c.get("cut_id") and c.get("layout") not in SPECIAL:
            out.append(str(c["cut_id"]))
    return out


def material_cuts(reports) -> dict[str, list[str]]:
    """{material id: cut ids that list it, in report order} from an iterable of maker reports {part_id, cuts}."""
    out: dict[str, list[str]] = {}
    for rep in reports or []:
        for c in (rep or {}).get("cuts") or [] if isinstance(rep, dict) else []:
            if not isinstance(c, dict):
                continue
            m = c.get("material")
            if isinstance(m, dict) and m.get("id"):
                cuts = out.setdefault(str(m["id"]), [])
                cid = str(c.get("cut_id") or "")
                if cid and cid not in cuts:
                    cuts.append(cid)
    return out


def _latest_output(block_dir: pathlib.Path) -> dict | None:
    """The newest finished output.json of a block (iterations first, then attempts)."""
    def num(p):
        try:
            return int(p.name.split("-")[1])
        except (IndexError, ValueError):
            return -1
    iters = sorted(block_dir.glob("iter-*"), key=num) or [block_dir]
    for d in reversed(iters):
        for a in sorted(d.glob("attempt-*"), key=num, reverse=True):
            st = a / "status.json"
            try:
                if st.is_file() and json.loads(st.read_text(encoding="utf-8")).get("status") == "done":
                    return json.loads((a / "output.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    return None


def run_material_cuts(ctx) -> dict[str, list[str]] | None:
    """material_cuts of this scene copy's maker reports in this run, or None when none can be read."""
    try:
        run_dir = pathlib.Path(ctx["project"]) / "runs" / str(ctx["run_id"])
    except (KeyError, TypeError):
        return None
    _, _, k = str(ctx.get("block") or "").partition("@")
    reports = []
    for block, name in MAKERS.items():
        out = _latest_output(run_dir / "blocks" / (block + (f"@{k}" if k else "")))
        if isinstance(out, dict) and isinstance(out.get(name), dict):
            reports.append(out[name])
    return material_cuts(reports) if reports else None


def input_of(inputs, name):
    """The value of terminal `name` among a checker's inputs (short key first, then any "<block>/<name>" key)."""
    if not inputs:
        return None
    if name in inputs:
        return inputs[name]
    for k, v in inputs.items():
        if str(k).rpartition("/")[2] == name:
            return v
    return None


def check_report(report: dict, inputs, prefix: str, allow_null: bool) -> tuple[list[str], list[dict]]:
    """The shared shape rules of a maker report {part_id, cuts: [{cut_id, material}]}:
    every content cut listed once, in scene order, no other cuts; material required (or null when allow_null);
    id <prefix>-<cut_id>-1 named after the first cut the material is listed in; a material listed in several cuts is
    the identical object everywhere. Returns (errors, the distinct materials in order of first appearance)."""
    errors: list[str] = []
    cuts = [c for c in (report or {}).get("cuts") or [] if isinstance(c, dict)]
    listed = [str(c.get("cut_id") or "") for c in cuts]
    want = content_cuts(input_of(inputs, "visuals"))
    if want:
        missing = [x for x in want if x not in listed]
        extra = [x for x in dict.fromkeys(listed) if x not in want]
        twice = [x for x in dict.fromkeys(listed) if listed.count(x) > 1]
        if missing:
            errors.append(f"cuts misses the content cut(s) {', '.join(missing)}; list every content cut once "
                          f"({', '.join(want)}), each with its material.")
        if extra:
            errors.append(f"cuts lists {', '.join(extra)}, which is not a content cut of this scene (title and end "
                          f"cuts get no material); remove it. Content cuts: {', '.join(want)}.")
        if twice:
            errors.append(f"cuts lists {', '.join(twice)} more than once; list each content cut once.")
        if not (missing or extra or twice) and listed != want:
            errors.append(f"cuts must be in scene order: {', '.join(want)} (got {', '.join(listed)}).")
    first: dict[str, tuple[str, dict]] = {}
    materials: list[dict] = []
    for c in cuts:
        cid = str(c.get("cut_id") or "")
        m = c.get("material")
        if m is None:
            if not allow_null:
                errors.append(f"{cid}: material is empty; every content cut gets exactly one material.")
            continue
        if not isinstance(m, dict):
            errors.append(f"{cid}: material must be one object" + (" or null" if allow_null else "") + ".")
            continue
        mid = str(m.get("id") or "")
        if mid in first:
            fc, fm = first[mid]
            if m != fm:
                errors.append(f"{cid}: material {mid} is already used in {fc} with different contents. A material put "
                              f"in several cuts must be the identical object in each; otherwise give this cut its own "
                              f"material {prefix}-{cid}-1.")
            continue
        if mid != f"{prefix}-{cid}-1":
            errors.append(f"{cid}: material id must be {prefix}-{cid}-1 (got {mid or 'none'}). The middle is the first "
                          f"cut the material is listed in; the same material in later cuts keeps that id.")
        first[mid] = (cid, m)
        materials.append(m)
    return errors, materials
