"""Board API builder: one run's storyboard progress as a table model.

Stdlib only. Reads a run folder (stage result.json files, STATUS.json,
events.jsonl, assembly.json) plus the media PC entries the results
point at, and returns the dashboard payload. A missing or partial
stage yields "wait" cells; nothing here raises on partial runs.
"""
import json
import os
import re
from urllib.parse import quote

from . import pc as _pc

STAGES = (
    ("marty", "pd_marty", "Marty", "story", "Part"),
    ("ash", "plan_ash", "Ash", "story", "Scene"),
    ("wren", "voice_wren", "Wren", "story", "Lines \u00b7 voice"),
    ("penn", "board_penn", "Penn", "story", "Screen"),
    ("pia", "photo_pia", "Pia", "video", "Photo search"),
    ("gene", "image_gene", "Gene", "video", "Image gen"),
    ("max", "anim_max", "Max", "video", "Anim \u00b7 formula \u00b7 graph"),
    ("vera", "board_vera", "Vera", "video", "Slide plan"),
    ("remy", "slide_remy", "Remy", "video", "Slide build"),
    ("video", "video_production", "Program", "video", "Video"),
)

COLUMNS = ("part_time", "part", "scene", "line", "cut_time", "screen",
           "photo", "image", "anim", "slide_plan", "slide_build",
           "video")

_COLUMN_STAGE = {"part_time": "marty", "part": "marty", "scene": "ash",
                 "line": "wren", "cut_time": "wren", "screen": "penn",
                 "photo": "pia", "image": "gene", "anim": "max",
                 "slide_plan": "vera", "slide_build": "remy",
                 "video": "video"}

_STAGE_FILES = ("report.md", "result.json", "INPUTS.md", "INPUTS.json")

_RUN_PATH_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".json",
                  ".md", ".txt", ".srt")


def run_id_ok(run_id):
    """Same rule as the server: a plain folder name, never a path."""
    return bool(run_id) and "/" not in run_id \
        and "\\" not in run_id and not run_id.startswith(".")


def safe_run_path(runs_root, run_id, node, rel):
    """An existing file inside a stage folder, or None.

    Rejects absolute paths, drive letters, ".." escapes, and
    non-dashboard extensions. Used by the step file endpoint to
    serve Remy slide PNGs (path mode).
    """
    if not run_id_ok(run_id) \
            or not re.fullmatch(r"[A-Za-z0-9_\-]+", node or ""):
        return None
    if not rel or not isinstance(rel, str):
        return None
    if os.path.isabs(rel) or ":" in rel.split("/")[0]:
        return None
    norm = os.path.normpath(rel.replace("\\", "/"))
    if norm.startswith("../") or norm == "..":
        return None
    if os.path.splitext(norm)[1].lower() not in _RUN_PATH_EXTS:
        return None
    base = os.path.realpath(os.path.join(runs_root, run_id, node))
    full = os.path.realpath(os.path.join(base, norm))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full if os.path.isfile(full) else None


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _categories(node_dir):
    res = _load_json(os.path.join(node_dir, "result.json"))
    if isinstance(res, dict) and isinstance(res.get("categories"), dict):
        return res["categories"]
    return {}


def _cat_data(cats, name):
    wrapped = cats.get(name)
    if isinstance(wrapped, dict) and isinstance(wrapped.get("data"),
                                                dict):
        return wrapped["data"]
    return {}


def _cut_map(cuts):
    out = {}
    for c in cuts or []:
        if isinstance(c, dict) and c.get("cut_id"):
            out[c["cut_id"]] = c
    return out


def _events(run_dir):
    started, done = [], set()
    ep = os.path.join(run_dir, "events.jsonl")
    if not os.path.isfile(ep):
        return started, done
    try:
        with open(ep, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return started, done
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("ev") == "agent_start" and ev.get("agent"):
            started.append(ev["agent"])
        elif ev.get("ev") == "agent_done" and ev.get("agent"):
            done.add(ev["agent"])
    return started, done


def _run_file_url(run_id, node, name):
    return "/api/flows/runs/%s/file?node=%s&name=%s" % (
        quote(run_id, safe=""), quote(node, safe=""),
        quote(name, safe=""))


def _run_path_url(run_id, node, rel):
    return "/api/flows/runs/%s/file?node=%s&path=%s" % (
        quote(run_id, safe=""), quote(node, safe=""),
        quote(rel.replace("\\", "/"), safe="/"))


def _pc_media_url(pcname, doc_id, fname):
    return "/api/pcs/%s/entries/%s/media/%s" % (
        quote(pcname, safe=""), quote(doc_id, safe=""),
        quote(fname, safe=""))


def _figure_url(pcname, doc_id, fname):
    return "/api/pcs/%s/entries/%s/figures/%s" % (
        quote(pcname, safe=""), quote(doc_id, safe=""),
        quote(fname, safe=""))


def _voice_clip(ref, cut_id, root):
    """(file_url|None, engine|None) for a narration audio ref."""
    try:
        rpc, rid, _frag = _pc.parse_ref(ref)
        if rpc != "voice":
            return None, None
        entry = _pc.load_entry_by_ref(ref, root)
        clip = (entry.get("cuts") or {}).get(cut_id) or {}
        fname = clip.get("file")
        if not fname:
            return None, clip.get("engine")
        return (_pc_media_url("voice", rid, fname),
                clip.get("engine"))
    except (OSError, ValueError, KeyError):
        return None, None


def _pick_image_url(pick, root):
    """File URL for a Pia use-pick (web or source figure)."""
    try:
        rpc, rid, frag = _pc.parse_ref(pick.get("ref"))
    except (ValueError, AttributeError):
        return None
    if rpc == "image" and pick.get("file"):
        return _pc_media_url("image", rid, pick["file"])
    if rpc == "source" and frag:
        try:
            entry = _pc.load_entry_by_ref(pick["ref"], root)
        except (OSError, ValueError):
            return None
        for fig in entry.get("figures", []) or []:
            if isinstance(fig, dict) and fig.get("addr") == frag \
                    and fig.get("file"):
                return _figure_url("source", rid, fig["file"])
    return None


def _generated_url(prompt, fname):
    """File URL for a Gene image (one entry per prompt)."""
    try:
        if not prompt or not fname:
            return None
        doc_id = _pc.content_id("generated:" + prompt)
        return _pc_media_url("generated", doc_id, fname)
    except (ValueError, TypeError):
        return None


def _source_pages(refs, root):
    """Sorted page numbers behind Ash material refs (best effort)."""
    pages = set()
    for ref in refs:
        try:
            entry = _pc.load_entry_by_ref(ref, root)
            _rpc, _rid, frag = _pc.parse_ref(ref)
        except (OSError, ValueError):
            continue
        if not frag:
            continue
        for p in entry.get("paragraphs", []) or []:
            if not isinstance(p, dict):
                continue
            addr = p.get("addr") or ""
            if addr and (frag == addr or frag.startswith(addr + "/")
                         or addr.startswith(frag + "/")):
                for n in p.get("pages", []) or []:
                    if isinstance(n, int) and not isinstance(n, bool):
                        pages.add(n)
    return sorted(pages)


def _render_log_text(rlog):
    log = []
    for a in rlog.get("adjustments", []) or []:
        if isinstance(a, dict):
            log.append("%s: %s -> %s" % (a.get("field"),
                                         a.get("was"), a.get("now")))
    for issue in rlog.get("issues", []) or []:
        log.append(str(issue))
    return log


def _cut_voice(ncut, root):
    audio = ncut.get("audio") or {}
    url, engine = _voice_clip(audio.get("voice_pc_ref"),
                              ncut.get("cut_id"), root)
    return {"file": url, "attempts": ncut.get("attempts"),
            "engine": engine}


def _cut_pia(pcut, root):
    if not pcut or pcut.get("decision") != "use":
        return []
    pick = {"file": _pick_image_url(pcut, root),
            "source": pcut.get("source_url") or pcut.get("ref"),
            "license": pcut.get("license"),
            "reason": pcut.get("reason"),
            "kind": pcut.get("kind")}
    return [pick]


def _cut_gene(gcut, images):
    if not gcut or gcut.get("decision") != "generate":
        return None
    img = images.get(gcut.get("cut_id")) or {}
    return {"prompt": gcut.get("prompt"),
            "file": _generated_url(gcut.get("prompt"),
                                   img.get("file"))}


def _cut_max(mcut):
    if not mcut:
        return None
    if mcut.get("decision") == "use":
        return {"template": mcut.get("template"),
                "values": mcut.get("values"),
                "skipped_reason": None}
    return {"template": None, "values": None,
            "skipped_reason": mcut.get("reason")}


def _cut_vera(vcut):
    if not vcut:
        return None
    blocks = []
    reasons = []
    for b in vcut.get("blocks", []) or []:
        if not isinstance(b, dict):
            continue
        blocks.append({"type": b.get("kind"), "ref": b.get("ref"),
                       "box": b.get("box")})
        reasons.append(b.get("reason") or "")
    return {"preset": vcut.get("preset"), "blocks": blocks,
            "reasons": reasons, "why": vcut.get("why")}


def _cut_remy(run_id, runs_root, node_dir, rcut):
    if not rcut:
        return None
    png = None
    rel = rcut.get("slide_file")
    if rel and safe_run_path(runs_root, run_id,
                             os.path.basename(node_dir), rel):
        png = _run_path_url(run_id, os.path.basename(node_dir), rel)
    return {"png": png, "renders": rcut.get("renders_n"),
            "log": _render_log_text(rcut)}


def _cut_video(seg, line):
    if not seg:
        return None
    t0 = seg.get("at_s")
    dur = seg.get("dur_s")
    t1 = None
    if isinstance(t0, (int, float)) and isinstance(dur, (int, float)):
        t1 = round(t0 + dur, 3)
    return {"t0": t0, "t1": t1, "subtitle": line}


def build_board(run_id, runs_root=None, pc_root=None, running=False):
    """Dashboard payload for one run. Never raises on partial runs."""
    from . import flow as _flow
    runs_root = runs_root or _flow.RUNS_DIR
    if not run_id_ok(run_id):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    run_dir = os.path.join(runs_root, run_id)
    if not os.path.isdir(run_dir):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    status = _load_json(os.path.join(run_dir, "STATUS.json")) or {}
    approved = set(status.get("approved") or [])
    run_state = status.get("state", "unknown")
    started, done_ev = _events(run_dir)
    pending = []
    for agent in started:
        if agent not in done_ev and agent not in pending:
            pending.append(agent)
    cats, usage, have = {}, {}, {}
    for _key, node, _who, _team, _label in STAGES:
        ndir = os.path.join(run_dir, node)
        cats[node] = _categories(ndir) if os.path.isdir(ndir) else {}
        have[node] = bool(cats[node])
        usage[node] = _load_json(os.path.join(ndir, "usage.json"))
    failed_node = ""
    if run_state == "failed":
        board_nodes = [node for _k, node, _w, _t, _l in STAGES]
        pend_board = [a for a in pending if a in board_nodes
                      and not have[a]]
        if pend_board:
            failed_node = pend_board[-1]
        else:
            for node in board_nodes:
                if not have[node]:
                    failed_node = node
                    break
    live = bool(running) or run_state == "running"
    stages = []
    by_key = {}
    for key, node, who, team, label in STAGES:
        if have[node] and node in approved:
            st = "ok"
        elif have[node]:
            st = "done"
        elif node == failed_node:
            st = "err"
        elif live and node in pending:
            st = "run"
        else:
            st = "wait"
        ndir = os.path.join(run_dir, node)
        files = {}
        for name in _STAGE_FILES:
            if os.path.isfile(os.path.join(ndir, name)):
                files[name] = _run_file_url(run_id, node, name)
        stages.append({"key": key, "who": who, "team": team,
                       "label": label, "status": st,
                       "cost": usage[node], "files": files})
        by_key[key] = st
    struct = _cat_data(cats["pd_marty"], "structure")
    draft = _cat_data(cats["plan_ash"], "storyboard_draft")
    narr = _cat_data(cats["voice_wren"], "narration")
    board = _cat_data(cats["board_penn"], "storyboard")
    picks_photo = _cat_data(cats["photo_pia"], "photo_picks")
    picks_gen = _cat_data(cats["image_gene"], "gen_picks")
    picks_anim = _cat_data(cats["anim_max"], "anim_picks")
    slide = _cat_data(cats["board_vera"], "slide_draft")
    rlog = _cat_data(cats["slide_remy"], "render_log")
    assembly = _load_json(os.path.join(
        run_dir, "video_production", "assembly.json")) or {}
    secs = {}
    for dp in ((struct.get("duration") or {}).get("parts") or []):
        if isinstance(dp, dict) and dp.get("part_id"):
            secs[dp["part_id"]] = dp.get("seconds")
    narr_by_scene = {}
    for c in narr.get("cuts", []) or []:
        if isinstance(c, dict):
            narr_by_scene.setdefault(c.get("scene_n"), []).append(c)
    for group in narr_by_scene.values():
        group.sort(key=lambda c: (c.get("start_s") is None,
                                  c.get("start_s")))
    penn_map = _cut_map(board.get("cuts"))
    pia_map = _cut_map(picks_photo.get("cuts"))
    gen_map = _cut_map(picks_gen.get("cuts"))
    gen_images = {}
    for im in picks_gen.get("images", []) or []:
        if isinstance(im, dict) and im.get("cut_id"):
            gen_images[im["cut_id"]] = im
    max_map = _cut_map(picks_anim.get("cuts"))
    vera_map = _cut_map(slide.get("cuts"))
    remy_map = _cut_map(rlog.get("cuts"))
    seg_map = _cut_map(assembly.get("segments"))
    parts = []
    for i, p in enumerate(struct.get("parts", []) or []):
        if not isinstance(p, dict):
            continue
        pid = p.get("id") or "p%d" % (i + 1)
        scenes = []
        for sc in draft.get("scenes", []) or []:
            if not isinstance(sc, dict) or sc.get("part_id") != pid:
                continue
            mats = []
            for m in sc.get("materials", []) or []:
                if isinstance(m, dict) and m.get("ref"):
                    mats.append({"ref": m["ref"],
                                 "from": m.get("from")})
            cuts = []
            for ncut in narr_by_scene.get(sc.get("n"), []):
                cid = ncut.get("cut_id")
                line = " ".join(
                    str(ln.get("text", ""))
                    for ln in ncut.get("lines", []) or []
                    if isinstance(ln, dict))
                st_s, en_s = ncut.get("start_s"), ncut.get("end_s")
                sec = None
                if isinstance(st_s, (int, float)) \
                        and isinstance(en_s, (int, float)):
                    sec = en_s - st_s
                pcut = penn_map.get(cid) or {}
                pia = _cut_pia(pia_map.get(cid), pc_root)
                gene = _cut_gene(gen_map.get(cid), gen_images)
                cell = {col: by_key[_COLUMN_STAGE[col]]
                        for col in COLUMNS}
                if by_key["pia"] in ("done", "ok") and not pia \
                        and (pia_map.get(cid) or {}).get(
                            "decision") == "none":
                    cell["photo"] = "none"
                if by_key["gene"] in ("done", "ok") \
                        and gene is None and (gen_map.get(cid)
                                              or {}).get(
                            "decision") == "none":
                    cell["image"] = "none"
                if by_key["max"] in ("done", "ok") \
                        and (max_map.get(cid) or {}).get(
                            "decision") == "none":
                    cell["anim"] = "none"
                cuts.append({
                    "cut_id": cid, "line": line, "sec": sec,
                    "t0": st_s,
                    "voice": _cut_voice(ncut, pc_root),
                    "screen": pcut.get("show_what"),
                    "text": pcut.get("on_screen_text") or [],
                    "pia": pia, "gene": gene,
                    "max": _cut_max(max_map.get(cid)),
                    "vera": _cut_vera(vera_map.get(cid)),
                    "remy": _cut_remy(
                        run_id, runs_root,
                        os.path.join(run_dir, "slide_remy"),
                        remy_map.get(cid)),
                    "video": _cut_video(seg_map.get(cid), line),
                    "cell_status": cell,
                })
            scenes.append({"n": sc.get("n"),
                           "msg": sc.get("viewer_learns"),
                           "time": (sc.get("end_s") - sc.get("start_s"))
                           if isinstance(sc.get("start_s"),
                                         (int, float))
                           and isinstance(sc.get("end_s"),
                                          (int, float)) else None,
                           "materials": mats, "cuts": cuts})
        refs = [m["ref"] for sc in scenes for m in sc["materials"]]
        parts.append({"no": i + 1, "title": p.get("heading") or "",
                      "time": secs.get(pid),
                      "pages": _source_pages(refs, pc_root),
                      "scenes": scenes})
    guide = _cat_data(cats["board_penn"], "style_guide") or None
    return {"ok": True, "run_id": run_id, "run_state": run_state,
            "run_error": status.get("error", ""),
            "stages": stages, "parts": parts,
            "style_guide": guide}
