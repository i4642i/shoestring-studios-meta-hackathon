"""Split function: one piece per scene of the planner's storyboard (its cuts with voice, word timings and what
the viewer sees, plus the part it belongs to), so photo, effects and slide work run in parallel copies, scene by scene."""

import json
import pathlib

OBJ = {"type": "object"}

from functions._common import pick, pick_opt
from functions.render_part import BREATH

NAME = "split_parts"
DESC = "One piece per scene from the brief (plan), the storyboard (scenes), the visuals (screens, cards) and the narration (cuts)"
KIND = "split"
# one piece per scene, cut into the reports it came from; each worker gets only the terminals its lines take
OUTPUTS = [{"name": "narration", "from": "narration", "schema": OBJ},     # the lines (what the viewer hears)
           {"name": "visuals", "from": "visuals", "schema": OBJ},         # what each cut shows, cards, theme
           {"name": "storyboard", "from": "storyboard", "schema": OBJ},   # the scene
           {"name": "brief", "from": "brief", "schema": OBJ},             # the part's heading and message
           {"name": "timing", "schema": OBJ}]                             # seconds, screen seconds, voice files, word times


def _words(audio: str) -> list:
    """Word timings saved by the narrator's voice_lines next to the audio file."""
    try:
        return json.loads(pathlib.Path(audio).with_suffix(".json").read_text(encoding="utf-8")).get("words", [])
    except (OSError, ValueError):
        return []


def run(ctx, inputs):
    # the plan (parts, audience, depth, core question, takeaway) comes from the PD's brief, the scenes per part from
    # the planner's storyboard, what is on screen and the first/last slide cards from the storyboard writer's
    # visuals, the cuts with their voice from the narration
    narration, visuals, brief = pick(inputs, "narration"), pick(inputs, "visuals"), pick(inputs, "brief")
    storyboard = pick_opt(inputs, "storyboard") or {}
    parts = [{"part_id": p["id"], "heading": p["heading"], "role": p.get("role") or "main", "covers": p.get("covers", ""),
              "question": p.get("question", ""), "message": p.get("message", "")}
             for p in brief.get("parts") or []]
    if not parts:
        return {"error": "the brief has no parts"}
    outline = [{"part_id": p["part_id"], "heading": p["heading"]} for p in parts]   # headings only: the TOC
    part_of = {p["part_id"]: p for p in parts}
    scene_of = {(sc.get("part_id"), sc.get("n")): {k: sc.get(k) for k in ("n", "role", "viewer_learns", "points", "screen_idea", "link")
                                                    if sc.get(k) not in (None, "")}
                for sc in storyboard.get("scenes") or []}
    see = {c["cut_id"]: c for c in visuals["cuts"]}
    total = len(narration["cuts"])
    groups: list[tuple[tuple, list]] = []          # (part_id, scene_n) in narration order
    for c in narration["cuts"]:
        key = (c["part_id"], c.get("scene_n"))
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(c)
    bad = sorted({k[0] for k, _ in groups} - set(part_of))
    if bad:
        return {"error": f"cuts belong to no part of the brief: {bad}"}
    pieces = []
    for (part_id, scene_n), cs in groups:
        part = part_of[part_id]
        pid = f"{part_id}-s{scene_n}"
        lines, screens, timing = [], [], []
        for c in cs:
            v = see.get(c["cut_id"], {})
            lines.append({"cut_id": c["cut_id"], "text": c["text"]})
            screen = {"cut_id": c["cut_id"], "show": v.get("show", ""), "form": v.get("form", ""), "draw": v.get("draw", "")}
            if v.get("photo_subject"):
                screen["photo_subject"] = v["photo_subject"]
            screens.append(screen)
            # screen_seconds: how long the cut's screen lasts (voice + the pause after it), so no worker adds it up
            timing.append({"cut_id": c["cut_id"], "seconds": c["seconds"],
                           "screen_seconds": round(float(c["seconds"]) + BREATH, 2),
                           "audio": c["audio"], "words": _words(c["audio"])})
        vis = {"piece_id": pid, "cuts": screens, "theme": visuals.get("theme", "shoestring"),
               "source_title": visuals.get("source_title", "")}
        brief_part = {"part_id": part_id, "heading": part["heading"], "message": part.get("message", ""),
                      "audience": brief.get("audience", "")}
        if any(x["form"] == "route" for x in screens):     # only a table-of-contents scene needs the outline
            brief_part["outline"] = outline
        pieces.append({"narration": {"piece_id": pid, "cuts": lines},
                       "visuals": vis,
                       "storyboard": scene_of.get((part_id, scene_n), {"n": scene_n}),
                       "brief": brief_part,
                       "timing": {"piece_id": pid, "cuts": timing}})
    # the title card goes on the PD's greeting part, the end card on its farewell part (the designer must use these
    # layouts); a brief without those parts (older plans) puts them on the first and last cut
    role_of = {(p["part_id"]): p["role"] for p in parts}
    greet = [x for x in pieces if role_of.get(x["brief"]["part_id"]) == "greeting"]
    bye = [x for x in pieces if role_of.get(x["brief"]["part_id"]) == "farewell"]
    if pieces:
        first, last = (greet or pieces)[0], (bye or pieces)[-1]
        for c in first["visuals"]["cuts"] if greet else first["visuals"]["cuts"][:1]:
            c["layout"] = "title"
        first["visuals"]["title_card"] = visuals.get("title_card", {})
        for c in last["visuals"]["cuts"] if bye else last["visuals"]["cuts"][-1:]:
            c["layout"] = "end"
        last["visuals"]["end_card"] = visuals.get("end_card", {})
    # section cover (layout L13, 2026-11-11): the first cut of every other part opens with its number, heading and
    # message for its first 3 s (render_part adds the cover; the cut keeps its own layout and materials after it);
    # the number counts those parts in order (01, 02, ...), computed here so no worker counts
    seen, n = set(), 0
    for x in pieces:
        part_id = x["brief"]["part_id"]
        if part_id in seen or role_of.get(part_id) in ("greeting", "farewell"):
            seen.add(part_id)
            continue
        seen.add(part_id)
        first_cut = x["visuals"]["cuts"][0] if x["visuals"]["cuts"] else None
        if not first_cut or first_cut.get("layout") in ("title", "end"):
            continue
        n += 1
        x["visuals"]["section_card"] = {"cut_id": first_cut["cut_id"], "number": f"{n:02d}",
                                        "title": part_of[part_id]["heading"], "subtitle": part_of[part_id].get("message", "")}
    missing = sorted({c["cut_id"] for c in narration["cuts"]} - {c["cut_id"] for p in pieces for c in p["narration"]["cuts"]})
    if missing:
        return {"error": f"cuts left out of every scene: {missing}"}
    return pieces
