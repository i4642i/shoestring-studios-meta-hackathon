"""Board API builder: one run's storyboard progress as a table model.

Stdlib only. Reads a run folder (stage result.json files, STATUS.json,
events.jsonl, assembly.json) plus the media PC entries the results
point at, and returns the dashboard payload. A missing or partial
stage yields "wait" cells; nothing here raises on partial runs.
"""
import json
import os
import re
import time
from urllib.parse import quote

from . import parts as _parts
from . import pc as _pc

VIDEO_COLUMNS = ("photo", "image", "anim", "slide_plan",
                 "slide_build")

STAGES = (
    ("sam", "sales_sam", "Sam", "story", "Request"),
    ("marty", "pd_marty", "Marty", "story", "Part"),
    ("cleo", "explain_cleo", "Cleo", "story", "Concepts"),
    ("rex", "case_rex", "Rex", "story", "Cases"),
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

_KEY_NODE = {key: node for key, node, _w, _t, _l in STAGES}

_WHO_BY_NODE = {node: who for _k, node, who, _t, _l in STAGES}

_STAGE_FILES = ("report.md", "result.json", "INPUTS.md", "INPUTS.json",
                "inputs_log.json", "llm_calls.jsonl")

_VERIFY_FILES = ("report.md", "result.json", "INPUTS.md",
                 "INPUTS.json", "inputs_log.json",
                 "inputs_check.json", "reads_log.jsonl",
                 "events.jsonl", "usage.json", "llm_calls.jsonl")

_MAX_VERIFY_ROWS = 500

_RUN_PATH_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".json",
                  ".jsonl", ".md", ".txt", ".srt", ".mp4", ".webm")

_NODE_RE = re.compile(r"[A-Za-z0-9_\-]+")


def clone_run_dir(node):
    """Run-folder subpath for a stage id: base@pN -> base/pN.

    Plain ids pass through; anything else (bad clone base or part)
    is None. Only the file endpoints use this."""
    base, no = _parts.parse_clone_id(node or "")
    if no is None:
        return node if _NODE_RE.fullmatch(node or "") else None
    if base not in _parts.CLONE_NODES or no < 1:
        return None
    return os.path.join(base, "p%d" % no)


def run_id_ok(run_id):
    """Same rule as the server: a plain folder name, never a path."""
    return bool(run_id) and "/" not in run_id \
        and "\\" not in run_id and not run_id.startswith(".")


def sam_order_dir(order_id, sam_root=None):
    """Sam's order-run folder (output/runs/<order_id>), or None.

    Sam's canonical files (INPUTS.md, events.jsonl, llm_calls.jsonl,
    result.json, report.md) live there, not under the flow run."""
    from . import flow as _flow
    if not order_id or not isinstance(order_id, str):
        return None
    if "/" in order_id or "\\" in order_id \
            or order_id.startswith("."):
        return None
    root = sam_root or os.path.join(_flow.ROOT, "output", "runs")
    d = os.path.join(root, order_id)
    return d if os.path.isdir(d) else None


def stage_dir(run_dir, node, order_id="", sam_root=None):
    """Folder holding a stage's files. Sam resolves to his order-run
    folder when it holds a finished result.json (the flow run only
    keeps reuse copies); otherwise the run folder (live flow runs,
    fixtures)."""
    if node == "sales_sam" and order_id:
        sdir = sam_order_dir(order_id, sam_root)
        if sdir and os.path.isfile(
                os.path.join(sdir, "result.json")):
            return sdir
    return os.path.join(run_dir, node)


def sam_file(runs_root, run_id, name, sam_root=None):
    """Sam's file for the step file endpoint (same rule)."""
    run_dir = os.path.join(runs_root, run_id)
    status = _load_json(os.path.join(run_dir, "STATUS.json")) or {}
    full = os.path.join(
        stage_dir(run_dir, "sales_sam",
                  status.get("order_id", ""), sam_root), name)
    return full if os.path.isfile(full) else None


_LLM_SUM_ROWS = 2000
_LLM_KEEP_ROWS = 25


def _llm_section(ndir):
    """LLM calls for the verify view: sums plus the last rows in
    full. Sums cover at most the last _LLM_SUM_ROWS calls."""
    if not ndir or not os.path.isfile(
            os.path.join(ndir, "llm_calls.jsonl")):
        return {"present": False}
    rows = _read_jsonl(os.path.join(ndir, "llm_calls.jsonl"),
                       cap=_LLM_SUM_ROWS)
    pt, ct, secs = 0, 0, 0.0
    for r in rows:
        if type(r.get("prompt_tokens")) is int:
            pt += r["prompt_tokens"]
        if type(r.get("completion_tokens")) is int:
            ct += r["completion_tokens"]
        if type(r.get("seconds")) in (int, float):
            secs += r["seconds"]
    return {"present": True, "calls": len(rows),
            "prompt_tokens": pt, "completion_tokens": ct,
            "seconds": round(secs, 1), "rows": rows[-_LLM_KEEP_ROWS:]}


def safe_run_path(runs_root, run_id, node, rel):
    """An existing file inside a stage folder, or None.

    Rejects absolute paths, drive letters, ".." escapes, and
    non-dashboard extensions. Used by the step file endpoint to
    serve Remy slide PNGs (path mode). An empty node means the
    run folder itself (flat names only: STATUS.json,
    events.jsonl, flow.json).
    """
    if node:
        sub = clone_run_dir(node)
    else:
        sub = ""
    if not run_id_ok(run_id) or sub is None:
        return None
    if not rel or not isinstance(rel, str):
        return None
    if os.path.isabs(rel) or ":" in rel.split("/")[0]:
        return None
    clean = rel.replace("\\", "/")
    norm = os.path.normpath(clean)
    if norm.startswith("../") or norm == "..":
        return None
    if not node and "/" in clean:
        return None
    if os.path.splitext(norm)[1].lower() not in _RUN_PATH_EXTS:
        return None
    base = os.path.realpath(os.path.join(runs_root, run_id, sub))
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


def _clone_have(run_dir, node, no):
    return os.path.isfile(os.path.join(
        run_dir, node, "p%d" % no, "result.json"))


def _clone_approved(approved, node, no):
    cid = _parts.clone_id(node, no)
    return cid in approved or node in approved


def build_board(run_id, runs_root=None, pc_root=None, running=False,
                sam_root=None):
    """Dashboard payload for one run. Never raises on partial runs."""
    from . import flow as _flow
    runs_root = runs_root or _flow.RUNS_DIR
    if not run_id_ok(run_id):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    run_dir = os.path.join(runs_root, run_id)
    if not os.path.isdir(run_dir):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    status = _load_json(os.path.join(run_dir, "STATUS.json")) or {}
    order_id = status.get("order_id", "")
    approved = set(status.get("approved") or [])
    run_state = status.get("state", "unknown")
    started, done_ev = _events(run_dir)
    pending = []
    for agent in started:
        if agent not in done_ev and agent not in pending:
            pending.append(agent)
    cats, usage, have = {}, {}, {}
    for _key, node, _who, _team, _label in STAGES:
        ndir = stage_dir(run_dir, node, order_id, sam_root)
        cats[node] = _categories(ndir) if os.path.isdir(ndir) else {}
        have[node] = bool(cats[node])
        usage[node] = _load_json(os.path.join(ndir, "usage.json"))
    live = bool(running) or run_state == "running"
    split = _parts.load_split(run_dir)
    split_nos = [p.get("no") for p in ((split or {}).get("parts")
                                       or [])]

    def _missing(node):
        if node in _parts.CLONE_NODES and split_nos:
            return any(not _clone_have(run_dir, node, no)
                       for no in split_nos)
        return not have[node]

    failed_node = ""
    if run_state == "failed":
        board_nodes = [node for _k, node, _w, _t, _l in STAGES]
        pend_base = []
        for a in pending:
            b, _n = _parts.parse_clone_id(a)
            if b in board_nodes and _missing(b) \
                    and b not in pend_base:
                pend_base.append(b)
        if pend_base:
            failed_node = pend_base[-1]
        else:
            for node in board_nodes:
                if _missing(node):
                    failed_node = node
                    break
    failed_clones = set()
    if failed_node in _parts.CLONE_NODES:
        cands = [_parts.clone_id(failed_node, no)
                 for no in split_nos
                 if _parts.clone_id(failed_node, no) in pending
                 and not _clone_have(run_dir, failed_node, no)]
        if cands:
            failed_clones.add(cands[-1])
        else:
            for no in split_nos:
                if not _clone_have(run_dir, failed_node, no):
                    failed_clones.add(_parts.clone_id(
                        failed_node, no))
                    break
    stages = []
    by_key = {}
    clone_status = {}
    for key, node, who, team, label in STAGES:
        node_approved = node in approved
        if node in _parts.CLONE_NODES and split_nos:
            node_approved = all(
                _clone_approved(approved, node, no)
                and _clone_have(run_dir, node, no)
                for no in split_nos)
        if have[node] and node_approved:
            st = "ok"
        elif have[node]:
            st = "done"
        elif node == failed_node:
            st = "err"
        elif live and node in pending:
            st = "run"
        else:
            st = "wait"
        ndir = stage_dir(run_dir, node, order_id, sam_root)
        files = {}
        for name in _STAGE_FILES:
            if os.path.isfile(os.path.join(ndir, name)):
                files[name] = _run_file_url(run_id, node, name)
        entry = {"key": key, "who": who, "team": team,
                 "label": label, "status": st,
                 "cost": usage[node], "files": files}
        if node in _parts.CLONE_NODES and split_nos:
            per = []
            for no in split_nos:
                cid = _parts.clone_id(node, no)
                if _clone_have(run_dir, node, no) \
                        and _clone_approved(approved, node, no):
                    cst = "ok"
                elif _clone_have(run_dir, node, no):
                    cst = "done"
                elif cid in failed_clones:
                    cst = "err"
                elif live and cid in pending:
                    cst = "run"
                else:
                    cst = "wait"
                clone_status[cid] = cst
                per.append({"no": no, "clone": cid,
                            "status": cst})
            entry["parts"] = per
        stages.append(entry)
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
    scene_part = {}
    for sc in draft.get("scenes", []) or []:
        if isinstance(sc, dict):
            scene_part[sc.get("n")] = sc.get("part_id")
    part_no = {}
    if split:
        for p in split.get("parts") or []:
            if isinstance(p, dict):
                part_no[p.get("part_id")] = p.get("no")
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
                cut_part = part_no.get(
                    scene_part.get(ncut.get("scene_n")))
                cell = {}
                for col in COLUMNS:
                    key = _COLUMN_STAGE[col]
                    if col in VIDEO_COLUMNS and cut_part in \
                            split_nos:
                        node = _KEY_NODE[key]
                        cid2 = _parts.clone_id(node, cut_part)
                        cell[col] = clone_status.get(
                            cid2, by_key[key])
                    else:
                        cell[col] = by_key[key]
                if cell["photo"] in ("done", "ok") and not pia \
                        and (pia_map.get(cid) or {}).get(
                            "decision") == "none":
                    cell["photo"] = "none"
                if cell["image"] in ("done", "ok") \
                        and gene is None and (gen_map.get(cid)
                                              or {}).get(
                            "decision") == "none":
                    cell["image"] = "none"
                if cell["anim"] in ("done", "ok") \
                        and (max_map.get(cid) or {}).get(
                            "decision") == "none":
                    cell["anim"] = "none"
                cuts.append({
                    "cut_id": cid, "line": line, "sec": sec,
                    "t0": st_s, "part": cut_part,
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
            "order_id": status.get("order_id", ""),
            "stages": stages, "parts": parts,
            "style_guide": guide,
            "summary": _summary_of(run_dir, status, run_state)}


def _iter_stage_dirs(run_dir):
    """(node, part|None, dir) for every board node dir on disk."""
    out = []
    nodes = set(_KEY_NODE.values())
    try:
        names = sorted(os.listdir(run_dir))
    except OSError:
        return out
    for name in names:
        if name not in nodes:
            continue
        ndir = os.path.join(run_dir, name)
        if not os.path.isdir(ndir):
            continue
        out.append((name, None, ndir))
        if name in _parts.CLONE_NODES:
            try:
                subs = sorted(os.listdir(ndir))
            except OSError:
                continue
            for sub in subs:
                if len(sub) < 2 or sub[0] != "p" \
                        or not sub[1:].isdigit():
                    continue
                sdir = os.path.join(ndir, sub)
                if os.path.isdir(sdir):
                    out.append((name, int(sub[1:]), sdir))
    return out


def _read_jsonl(path, cap=_MAX_VERIFY_ROWS):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return rows
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
        if len(rows) >= cap:
            break
    return rows


def _run_cost_total(run_dir):
    """Summed usage over the same dirs flow._run_cost walks
    (memory builds + every stage dir, clones included), so the
    Board summary matches the Studio control bar."""
    cost = {"llm_calls": 0, "prompt_tokens": 0,
            "completion_tokens": 0}
    mdir = os.path.join(run_dir, "memory")
    dirs = []
    if os.path.isdir(mdir):
        try:
            subs = sorted(os.listdir(mdir))
        except OSError:
            subs = []
        for agent in subs:
            adir = os.path.join(mdir, agent)
            if os.path.isdir(adir):
                dirs.append(adir)
    dirs.extend(d for _n, _p, d in _iter_stage_dirs(run_dir))
    for d in dirs:
        u = _load_json(os.path.join(d, "usage.json")) or {}
        for k in cost:
            if isinstance(u.get(k), int) \
                    and not isinstance(u.get(k), bool):
                cost[k] += u[k]
    return cost


def _elapsed_s(run_dir, state, status_mtime):
    """Run length from file times (no timestamps are stored):
    oldest entry in the run folder to STATUS.json's change, or
    to now while the run is live. Seconds, or None."""
    try:
        names = os.listdir(run_dir)
    except OSError:
        return None
    marks = []
    for n in names:
        try:
            marks.append(os.path.getmtime(
                os.path.join(run_dir, n)))
        except OSError:
            pass
    if not marks:
        return None
    start = min(marks)
    if state in ("running", "pausing"):
        end = time.time()
    else:
        end = status_mtime or max(marks)
    return max(0, int(end - start))


def _scan_errors(run_dir, status):
    """Failed tool calls and run_fail rows, per node/part."""
    errs = []
    for node, part, d in _iter_stage_dirs(run_dir):
        for row in _read_jsonl(os.path.join(d, "events.jsonl")):
            if row.get("ev") == "run_fail":
                errs.append((node, part,
                             str(row.get("reason", ""))))
            elif row.get("ev") == "tool" \
                    and row.get("ok") is False:
                reason = row.get("error") or ""
                if not reason and isinstance(
                        row.get("errors"), list) \
                        and row["errors"]:
                    reason = str(row["errors"][0])
                errs.append((node, part, "%s: %s" % (
                    row.get("tool", "tool"),
                    reason or "failed")))
    if status.get("state") == "failed" and status.get("error"):
        errs.append(("", None, str(status["error"])))
    return [{"node": n, "part": p, "reason": r[:160]}
            for n, p, r in errs]


def _scan_spec(run_dir):
    """inputs_check.json rows with ok False, per node/part."""
    fails = []
    for node, part, d in _iter_stage_dirs(run_dir):
        chk = _load_json(os.path.join(d, "inputs_check.json"))
        if isinstance(chk, dict) and chk.get("ok") is False:
            item = {"node": node, "part": part}
            for k in ("missing", "extra", "wrong_part",
                      "wrong_kind"):
                vals = chk.get(k) or []
                item[k] = [str(v) for v in vals[:10]]
                item["n_" + k] = len(vals)
            fails.append(item)
    return fails


def _current_label(status):
    """(current id, short who label) from STATUS.json."""
    cur = status.get("current", "") or ""
    if not cur:
        return "", ""
    base, no = _parts.parse_clone_id(cur)
    who = _WHO_BY_NODE.get(base, "")
    if not who:
        return cur, cur
    if no is None:
        return cur, who
    return cur, "%s P%d" % (who, no)


def _summary_of(run_dir, status, state):
    try:
        smtime = os.path.getmtime(
            os.path.join(run_dir, "STATUS.json"))
    except OSError:
        smtime = None
    cur, who = _current_label(status)
    return {"state": state, "current": cur,
            "current_who": who,
            "elapsed_s": _elapsed_s(run_dir, state, smtime),
            "cost": _run_cost_total(run_dir),
            "errors": _scan_errors(run_dir, status),
            "spec_failures": _scan_spec(run_dir)}


def build_summary(run_id, runs_root=None):
    """One-run verify summary. Never raises on partial runs."""
    from . import flow as _flow
    runs_root = runs_root or _flow.RUNS_DIR
    if not run_id_ok(run_id):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    run_dir = os.path.join(runs_root, run_id)
    if not os.path.isdir(run_dir):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    status = _load_json(os.path.join(run_dir, "STATUS.json")) or {}
    out = _summary_of(run_dir, status,
                      status.get("state", "unknown"))
    out.update(ok=True, run_id=run_id)
    return out


def _ev_time(row):
    return row.get("t") or row.get("at") or ""


def build_verify(run_id, node, part=None, runs_root=None,
                 sam_root=None):
    """Everything the Board needs to verify one employee/part:
    inputs manifest, PC reads, spec check, merged events with
    plain phrases, LLM calls, cost, and file links. Unknown nodes
    fail; a stage that has not run yet returns empty sections."""
    from . import flow as _flow
    from . import office as _office
    runs_root = runs_root or _flow.RUNS_DIR
    if not run_id_ok(run_id):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    run_dir = os.path.join(runs_root, run_id)
    if not os.path.isdir(run_dir):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    base, no = _parts.parse_clone_id(node or "")
    if no is not None and part is None:
        part = no
    node = base or ""
    nodes = set(_KEY_NODE.values())
    if node not in nodes:
        return {"ok": False,
                "error": "no such node: %r" % (node,)}
    if part is not None and (node not in _parts.CLONE_NODES
                             or not isinstance(part, int)
                             or isinstance(part, bool)
                             or part < 1):
        return {"ok": False,
                "error": "no such part: %r" % (part,)}
    if part is None:
        status0 = _load_json(
            os.path.join(run_dir, "STATUS.json")) or {}
        ndir = stage_dir(run_dir, node,
                         status0.get("order_id", ""), sam_root)
    else:
        ndir = os.path.join(run_dir, node, "p%d" % part)
    ndir = ndir if os.path.isdir(ndir) else None
    label = node if part is None else "%s@p%d" % (node, part)
    inputs = _load_json(os.path.join(ndir, "inputs_log.json")) \
        if ndir else None
    spec = _load_json(os.path.join(ndir, "inputs_check.json")) \
        if ndir else None
    reads = _read_jsonl(os.path.join(ndir, "reads_log.jsonl")) \
        if ndir else []
    want = {node, label}
    run_rows = [r for r in _read_jsonl(
        os.path.join(run_dir, "events.jsonl"), cap=2000)
        if r.get("agent") in want]
    node_rows = _read_jsonl(os.path.join(ndir, "events.jsonl")) \
        if ndir else []
    all_rows = run_rows + node_rows
    order = sorted(range(len(all_rows)),
                   key=lambda i: _ev_time(all_rows[i]))
    gen = 0
    events = []
    for i in order:
        row = dict(all_rows[i])
        if row.get("ev") == "tool":
            if row.get("tool") == "pc_generate_image":
                gen += 1
            row["phrase"] = _office.action_phrase(
                row.get("tool"), row.get("detail"), gen, 0)
        events.append(row)
    usage = _load_json(os.path.join(ndir, "usage.json")) \
        if ndir else None
    times = [_ev_time(r) for r in events if _ev_time(r)]
    files = {}
    if ndir:
        for name in _VERIFY_FILES:
            if os.path.isfile(os.path.join(ndir, name)):
                files[name] = _run_file_url(run_id, label, name)
    return {"ok": True, "run_id": run_id, "node": node,
            "part": part, "clone": label,
            "inputs": inputs if isinstance(inputs, dict)
            else {"present": False},
            "llm": _llm_section(ndir),
            "reads": reads,
            "spec": spec if isinstance(spec, dict)
            else {"present": False},
            "events": events,
            "cost": {"usage": usage,
                     "started": times[0] if times else None,
                     "finished": times[-1] if times else None},
            "files": files}


def list_run_files(run_id, runs_root=None):
    """Every file under one run folder, for the read-only
    run-folder listing. Sorted relative paths with sizes."""
    from . import flow as _flow
    runs_root = runs_root or _flow.RUNS_DIR
    if not run_id_ok(run_id):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    run_dir = os.path.join(runs_root, run_id)
    if not os.path.isdir(run_dir):
        return {"ok": False, "error": "no such run: %r" % (run_id,)}
    out = []
    for dirpath, _dirs, files in os.walk(run_dir):
        for fn in sorted(files):
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            rel = os.path.relpath(full, run_dir).replace(
                "\\", "/")
            if "/" in rel:
                first, rest = rel.split("/", 1)
            else:
                first, rest = "", rel
            out.append({"path": rel, "size": size,
                        "node": first, "rel": rest})
            if len(out) >= 2000:
                break
        if len(out) >= 2000:
            break
    out.sort(key=lambda e: e["path"])
    return {"ok": True, "run_id": run_id, "files": out}
