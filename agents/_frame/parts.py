"""Part clones for the video team (STEP 1): split plan, per-part
clone inputs, merge. Stdlib only.

After Penn is approved, the part_split code node cuts the run into
one part per Marty part. Each video-team member then runs once per
part as a clone (photo_pia@p1, ...), seeing only its own part's
cuts plus the shared context (concept, style guide, parts list).
Merge joins the per-part results back into the node's normal
result so video_production and older readers keep working.
"""
import json
import os
import re
import shutil

from . import results

SPLIT_NODE = "part_split"
SPLIT_FILE = "split.json"
CLONE_NODES = ("photo_pia", "image_gene", "anim_max", "board_vera",
               "slide_remy")
CLONE_OUTPUTS = {"photo_pia": "photo_picks",
                 "image_gene": "gen_picks",
                 "anim_max": "anim_picks",
                 "board_vera": "slide_draft",
                 "slide_remy": "render_log"}
CUT_CATEGORIES = ("narration", "storyboard", "photo_picks",
                  "gen_picks", "anim_picks", "slide_draft",
                  "render_log")
GEN_BUDGET = 6
SOURCE_CLONE_READERS = ("photo_pia", "anim_max", "board_vera")
# Flow-intent readers per PC (default.json pc_lines): source
# figures to Pia/Vera and tables/formulas to Max (c75, c76,
# c80); theory/article to Penn/Wren (c36-c39); image/generated
# to Vera/Remy; voice to video_production only (c68).
PENN_WREN_CLONES = ("board_penn", "voice_wren")
IMAGE_CLONE_READERS = ("board_vera", "slide_remy")

_CLONE_RE = re.compile(r"^([A-Za-z0-9_]+)@p(\d+)$")


def clone_id(base, no):
    """Clone identity for part N (1-based): photo_pia@p1."""
    return "%s@p%d" % (base, no)


def parse_clone_id(cid):
    """(base, no) for a clone id, or (cid, None) for a plain id."""
    m = _CLONE_RE.match(cid or "")
    if not m:
        return cid, None
    return m.group(1), int(m.group(2))


def quotas_for(cut_counts, budget=GEN_BUDGET):
    """New-image quotas per part: largest remainder by cut count,
    at least 1 per part when the budget allows it. Sums to
    min(budget, parts) or less."""
    n = len(cut_counts)
    if n == 0:
        return []
    if n > budget:
        order = sorted(range(n), key=lambda i: (-cut_counts[i], i))
        out = [0] * n
        for i in order[:budget]:
            out[i] = 1
        return out
    total = sum(cut_counts) or 1
    exact = [budget * c / total for c in cut_counts]
    out = [int(x) for x in exact]
    rest = budget - sum(out)
    order = sorted(range(n),
                   key=lambda i: (exact[i] - out[i], -i),
                   reverse=True)
    for i in order[:rest]:
        out[i] += 1
    for i in range(n):
        while out[i] < 1:
            j = max(range(n), key=lambda k: (out[k], -k))
            if out[j] <= 1:
                break
            out[j] -= 1
            out[i] += 1
    return out


def _cut_line(cut):
    """One cut's spoken line (joined line texts)."""
    return " ".join(
        str((ln or {}).get("text", "")).strip()
        for ln in ((cut or {}).get("lines") or [])
        if isinstance(ln, dict) and str((ln or {}).get(
            "text", "")).strip())


def build_plan(structure, draft, narration, concept, guide):
    """Split plan data from Marty/Ash/Wren/Penn results. Raises
    ValueError naming the gap (unmapped scene, empty part). One
    part takes every cut without needing the scene map. Each part
    also carries boundary: the neighbor cuts' lines (read-only,
    for transitions)."""
    parts = [p for p in ((structure or {}).get("parts") or [])
             if isinstance(p, dict) and p.get("id")]
    if not parts:
        raise ValueError("part_split needs Marty's structure parts")
    scenes = [s for s in ((draft or {}).get("scenes") or [])
              if isinstance(s, dict)]
    scene_part = {}
    scene_mats = {}
    remy_by_scene = {}
    for sc in scenes:
        if isinstance(sc.get("n"), int):
            scene_part[sc["n"]] = sc.get("part_id")
            scene_mats[sc["n"]] = [
                m.get("ref") for m in (sc.get("materials") or [])
                if isinstance(m, dict) and m.get("ref")]
            refs = []
            for h in (sc.get("handoff") or []):
                if not isinstance(h, dict):
                    continue
                if "slide_remy" in (h.get("to") or []) \
                        and h.get("ref") and h["ref"] not in refs:
                    refs.append(h["ref"])
            remy_by_scene[sc["n"]] = refs
    cuts = [c for c in ((narration or {}).get("cuts") or [])
            if isinstance(c, dict) and c.get("cut_id")]
    if not cuts:
        raise ValueError("part_split needs Wren's narration cuts")
    secs = {}
    for dp in ((structure.get("duration") or {}).get("parts") or []):
        if isinstance(dp, dict) and dp.get("part_id"):
            secs[dp["part_id"]] = dp.get("seconds")
    plan_parts = []
    for no, p in enumerate(parts, 1):
        pid = p["id"]
        if len(parts) == 1:
            mine = list(cuts)
        else:
            mine = [c for c in cuts
                    if scene_part.get(c.get("scene_n")) == pid]
            for c in cuts:
                if c.get("scene_n") not in scene_part:
                    raise ValueError(
                        "cut %s names scene %r, missing from Ash's "
                        "draft" % (c.get("cut_id"),
                                   c.get("scene_n")))
        if not mine:
            raise ValueError("part %s has no cuts" % pid)
        sns = sorted({c.get("scene_n") for c in mine
                      if isinstance(c.get("scene_n"), int)})
        mats = []
        for sn in sns:
            for ref in scene_mats.get(sn, []):
                if ref not in mats:
                    mats.append(ref)
        rh, seen_rh = [], set()
        for sn in sns:
            for r in remy_by_scene.get(sn, []):
                if r not in seen_rh:
                    seen_rh.add(r)
                    rh.append(r)
        plan_parts.append({"no": no, "part_id": pid,
                           "title": p.get("heading") or "",
                           "seconds": secs.get(pid),
                           "scenes": sns,
                           "cuts": [c["cut_id"] for c in mine],
                           "materials": mats, "quota": 0,
                           "remy_handoff": rh,
                           "boundary": {"prev": None,
                                        "next": None}})
    quotas = quotas_for([len(p["cuts"]) for p in plan_parts])
    for p, q in zip(plan_parts, quotas):
        p["quota"] = q
    if len(plan_parts) > 1:
        order = [c["cut_id"] for c in cuts]
        by_id = {c["cut_id"]: c for c in cuts}
        for p in plan_parts:
            idx = [order.index(cid) for cid in p["cuts"]
                   if cid in order]
            if not idx:
                continue
            lo, hi = min(idx), max(idx)
            if lo > 0:
                pc = by_id[order[lo - 1]]
                p["boundary"]["prev"] = {
                    "cut_id": pc["cut_id"],
                    "line": _cut_line(pc)}
            if hi < len(order) - 1:
                nc = by_id[order[hi + 1]]
                p["boundary"]["next"] = {
                    "cut_id": nc["cut_id"],
                    "line": _cut_line(nc)}
    shared_parts = [{"no": p["no"], "part_id": p["part_id"],
                     "title": p["title"], "seconds": p["seconds"]}
                    for p in plan_parts]
    return {"version": 1, "parts": plan_parts,
            "shared": {"parts": shared_parts,
                       "concept": concept or {},
                       "style_guide": guide or {}}}


def load_split(run_dir):
    """The split plan for this run, or None (no part_split yet:
    video nodes run whole, as before)."""
    try:
        with open(os.path.join(run_dir, SPLIT_NODE, SPLIT_FILE),
                  encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(plan, dict) or not plan.get("parts"):
        return None
    return plan


def filter_data_for_cuts(data, cut_ids):
    """Copy of a cut-list category holding only cut_ids (cuts in
    input order, plus the matching gen images)."""
    want = set(cut_ids or [])
    out = dict(data or {})
    out["cuts"] = [c for c in (out.get("cuts") or [])
                   if isinstance(c, dict) and c.get("cut_id") in want]
    if isinstance(out.get("images"), list):
        out["images"] = [im for im in out["images"]
                         if isinstance(im, dict)
                         and im.get("cut_id") in want]
    return out


def slim_split_plan(plan, part_no, agent_id=None):
    """A clone's view of the split plan: its own part in full,
    every other part as one line (no, id, title, time), row log
    narrowed to its part. Nothing else from other parts. Pia and
    Max get no concept (Gene and Vera keep it)."""
    shared = dict((plan or {}).get("shared", {}))
    base = (agent_id or "").split("@")[0]
    if base and base not in CONCEPT_ROLES:
        shared.pop("concept", None)
    out = {"version": (plan or {}).get("version", 1),
           "parts": [], "shared": shared}
    for p in ((plan or {}).get("parts") or []):
        if not isinstance(p, dict):
            continue
        if p.get("no") == part_no:
            out["parts"].append(p)
        else:
            out["parts"].append(
                {"no": p.get("no"), "part_id": p.get("part_id"),
                 "title": p.get("title", ""),
                 "seconds": p.get("seconds")})
    rows = ((plan or {}).get("row_writes") or {})
    if isinstance(rows, dict):
        kept = {}
        for k in ("granted", "skipped"):
            items = []
            for e in (rows.get(k) or []):
                m = re.search(r" p(\d+)[\s(]", str(e))
                if m and int(m.group(1)) != part_no:
                    continue
                items.append(e)
            kept[k] = items
        out["row_writes"] = kept
    return out


def filter_clone_received(clone_dir, plan_part, agent_id=None):
    """Narrow a clone's received.*.json files to its part's cuts
    (writers then check cut sets against the part, not the run)
    and slim the split plan to the shared one-line list. Remy
    keeps only Vera's slide_draft: narration, storyboard and the
    split plan files are removed for him. Returns {category:
    kept cuts}."""
    no = (plan_part or {}).get("no")
    cut_ids = (plan_part or {}).get("cuts", [])
    kept = {}
    try:
        names = sorted(os.listdir(clone_dir))
    except OSError:
        return kept
    remy = (agent_id or "").split("@")[0] == "slide_remy"
    for fn in names:
        if not fn.startswith("received.") or not fn.endswith(".json"):
            continue
        core = fn[len("received."):-len(".json")]
        _sender, _dot, cat = core.partition(".")
        if not _dot:
            continue
        if remy and cat in ("narration", "storyboard",
                            "split_plan"):
            try:
                os.remove(os.path.join(clone_dir, fn))
            except OSError:
                pass
            continue
        if cat not in CUT_CATEGORIES and cat != "split_plan":
            continue
        path = os.path.join(clone_dir, fn)
        try:
            with open(path, encoding="utf-8") as f:
                wrapped = json.load(f)
        except (OSError, ValueError):
            continue
        data = wrapped.get("data")
        if not isinstance(data, dict):
            continue
        if cat == "split_plan":
            wrapped["data"] = slim_split_plan(data, no,
                                              agent_id)
        else:
            sub = filter_data_for_cuts(data, cut_ids)
            wrapped["data"] = sub
            kept[cat] = len(sub.get("cuts", []))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wrapped, f, ensure_ascii=False, indent=1)
    return kept


# Clone input sets (v8.2): who sees the concept and the
# boundary lines. Remy sees neither and no parts list either.
CONCEPT_ROLES = ("image_gene", "board_vera")
BOUNDARY_ROLES = ("photo_pia", "image_gene", "anim_max",
                  "board_vera")


def _parts_list_lines(shared, part_no):
    lines = ["Parts in this video:"]
    for p in shared.get("parts", []) or []:
        if not isinstance(p, dict):
            continue
        mark = " <-- YOU" if p.get("no") == part_no else ""
        lines.append("- Part %s: %s (%ss)%s"
                     % (p.get("no"), p.get("title") or
                        p.get("part_id"), p.get("seconds"),
                        mark))
    return lines


def _concept_lines(shared):
    concept = shared.get("concept") or {}
    if not concept:
        return []
    lines = ["Concept (Marty):"]
    for k in ("common_theme", "core_question",
              "viewer_takeaway", "intent_overall"):
        if concept.get(k):
            lines.append("- %s: %s" % (k, concept[k]))
    return lines


def _guide_lines(shared):
    guide = shared.get("style_guide") or {}
    if not guide:
        return []
    lines = ["Style guide (Penn):"]
    pal = guide.get("palette") or {}
    if pal:
        lines.append("- palette: %s"
                     % ", ".join("%s=%s" % (k, pal[k])
                                 for k in ("background", "text",
                                           "accent")
                                 if pal.get(k)))
    fonts = guide.get("fonts") or {}
    if fonts:
        lines.append("- fonts: heading=%s body=%s"
                     % (fonts.get("heading"),
                        fonts.get("body")))
    if guide.get("image_tone"):
        lines.append("- image tone: %s"
                     % guide["image_tone"])
    for r in (guide.get("rules") or [])[:6]:
        lines.append("- rule: %s" % r)
    return lines


def _boundary_lines(plan, part_no):
    for p in ((plan or {}).get("parts") or []):
        if isinstance(p, dict) and p.get("no") == part_no:
            bound = (p.get("boundary") or {})
            break
    else:
        return []
    prev, nxt = bound.get("prev"), bound.get("next")
    if not prev and not nxt:
        return []
    lines = ["Boundary lines (read-only, for transitions only):"]
    if prev:
        lines.append("- Previous part ends with (cut %s): %s"
                     % (prev.get("cut_id"), prev.get("line")))
    if nxt:
        lines.append("- Next part opens with (cut %s): %s"
                     % (nxt.get("cut_id"), nxt.get("line")))
    return lines


def shared_block(plan, part_no, agent_id=None):
    """Shared context markdown for a clone's INPUTS: the parts
    list with this part marked, Penn's guide, and per role
    Marty's concept (Gene, Vera) and the boundary lines
    (Pia, Gene, Max, Vera). Remy gets the part marker and the
    guide only. agent_id None keeps the legacy full block."""
    base = (agent_id or "").split("@")[0]
    shared = (plan or {}).get("shared") or {}
    if base == "slide_remy":
        lines = ["## Shared context (every part sees this)", "",
                 "You are Part %d." % part_no, ""]
        lines += _guide_lines(shared)
        lines += ["",
                  "Nothing else from other parts is visible here."]
        return "\n".join(lines)
    lines = ["## Shared context (every part sees this)", "",
             "You are Part %d." % part_no, ""]
    lines += _parts_list_lines(shared, part_no)
    if base in CONCEPT_ROLES or not base:
        concept = _concept_lines(shared)
        if concept:
            lines += [""] + concept
    lines += [""] + _guide_lines(shared)
    if base in BOUNDARY_ROLES:
        bound = _boundary_lines(plan, part_no)
        if bound:
            lines += [""] + bound
    lines += ["", "Nothing else from other parts is visible here."]
    return "\n".join(lines)


def merge_categories(node, part_datas):
    """Join per-part payloads into the node's normal result shape
    (cuts, plus images, in part order). Raises ValueError on
    duplicate cut ids."""
    cuts, images, seen = [], [], set()
    for data in part_datas:
        for c in ((data or {}).get("cuts") or []):
            if not isinstance(c, dict) or not c.get("cut_id"):
                continue
            if c["cut_id"] in seen:
                raise ValueError("%s: cut %r in two parts"
                                 % (node, c["cut_id"]))
            seen.add(c["cut_id"])
            cuts.append(c)
        for im in ((data or {}).get("images") or []):
            if isinstance(im, dict):
                images.append(im)
    out = {"cuts": cuts}
    if node == "image_gene" or images:
        out["images"] = images
    return out


def merge_node(node, run_dir, nparts, order_id=None):
    """Join p1..pN results into runs/<run>/<node>/result.json
    (+ report.md, summed usage.json, copied slides/). Returns
    {"ok": True, "cuts": n} or {"ok": False, "error": msg}."""
    cat = CLONE_OUTPUTS.get(node)
    if not cat:
        return {"ok": False, "error": "node %r never splits" % node}
    ndir = os.path.join(run_dir, node)
    datas, reports, usages = [], [], []
    for no in range(1, nparts + 1):
        pdir = os.path.join(ndir, "p%d" % no)
        try:
            res = results.load_result(
                os.path.join(pdir, results.RESULT_FILE))
        except (OSError, ValueError) as exc:
            return {"ok": False,
                    "error": "%s@p%d has no result.json (%s)"
                             % (node, no, exc)}
        wrapped = (res.get("categories") or {}).get(cat)
        if not isinstance(wrapped, dict) \
                or not isinstance(wrapped.get("data"), dict):
            return {"ok": False,
                    "error": "%s@p%d result holds no %s"
                             % (node, no, cat)}
        datas.append(wrapped["data"])
        order_id = order_id or res.get("order_id", "")
        try:
            with open(os.path.join(pdir, "report.md"),
                      encoding="utf-8") as f:
                reports.append((no, f.read()))
        except OSError:
            reports.append((no, ""))
        try:
            with open(os.path.join(pdir, "usage.json"),
                      encoding="utf-8") as f:
                usages.append(json.load(f))
        except (OSError, ValueError):
            pass
    try:
        merged = merge_categories(node, datas)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    info = []
    for p in ((load_split(run_dir) or {}).get("parts") or []):
        if not isinstance(p, dict):
            continue
        entry = {"no": p.get("no"), "part_id": p.get("part_id"),
                 "title": p.get("title") or "",
                 "cuts": [c for c in (p.get("cuts") or [])
                          if isinstance(c, str)]}
        if isinstance(p.get("seconds"), int) \
                and not isinstance(p.get("seconds"), bool):
            entry["seconds"] = p["seconds"]
        info.append(entry)
    try:
        res = results.make_result(node, order_id or "",
                                  os.path.basename(run_dir),
                                  {cat: merged,
                                   "part_info": {"parts": info}})
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    problems = results.check_result(res, where=node)
    if problems:
        return {"ok": False, "error": "%s: %s" % (node, problems[0])}
    results.promote_checked(res)
    try:
        results.save_result(ndir, res)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    with open(os.path.join(ndir, "report.md"), "w",
              encoding="utf-8") as f:
        for no, body in reports:
            f.write("# Part %d (%s@p%d)\n\n%s\n"
                    % (no, node, no, body.strip()))
    total = {"llm_calls": 0, "prompt_tokens": 0,
             "completion_tokens": 0, "tools": {}}
    for u in usages:
        if not isinstance(u, dict):
            continue
        for k in ("llm_calls", "prompt_tokens",
                  "completion_tokens"):
            total[k] += u.get(k, 0) or 0
        for t, n in ((u.get("tools") or {}).items()):
            total["tools"][t] = total["tools"].get(t, 0) + n
    total["parts"] = ["p%d" % no for no in range(1, nparts + 1)]
    with open(os.path.join(ndir, "usage.json"), "w",
              encoding="utf-8") as f:
        json.dump(total, f, ensure_ascii=False, indent=1)
    sdir = os.path.join(ndir, "slides")
    for no in range(1, nparts + 1):
        psrc = os.path.join(ndir, "p%d" % no, "slides")
        if not os.path.isdir(psrc):
            continue
        os.makedirs(sdir, exist_ok=True)
        for fn in sorted(os.listdir(psrc)):
            src = os.path.join(psrc, fn)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(sdir, fn))
    return {"ok": True, "cuts": len(merged["cuts"])}


def check_remy_handoff(order_id, plan, root=None):
    """Ash hands source figures to Remy per scene; part_split turns
    them into slide_remy@pN rows. Every ref must sit inside Ash's
    own rows, like apply_handoff. Returns [errors] (validate
    before writing anything)."""
    from . import pc
    errors = []
    for p in ((plan or {}).get("parts") or []):
        for ref in (p.get("remy_handoff") or []):
            try:
                rpc, rid, _frag = pc.parse_ref(ref)
                entry = pc.load_entry_by_ref(
                    pc.entry_ref(rpc, rid), root)
            except (OSError, ValueError, KeyError):
                errors.append("remy handoff: bad ref %r" % (ref,))
                continue
            mine = pc.entry_access(entry, "plan_ash", order_id)
            if mine is None:
                errors.append("remy handoff: plan_ash holds no row "
                              "for %s (order %s)"
                              % (pc.entry_ref(rpc, rid), order_id))
                continue
            held = pc.row_parts(mine)
            if held and not any(pc.ref_within(ref, part)
                                for part in held):
                errors.append("remy handoff: %r sits outside "
                              "plan_ash's listed parts" % (ref,))
    return errors


def _split_fig_tab(refs):
    # Source refs for clones: figures to Pia/Vera, tables and
    # formulas to Max. Sections and paragraphs are not grants:
    # the flow draws figures (c75, c80) and tables/formulas
    # (c76) only.
    figs, tabs = [], []
    for ref in refs or []:
        frag = ref.rsplit('#', 1)[-1] if '#' in ref else ''
        if frag.startswith('fig'):
            figs.append(ref)
        elif frag.startswith('tab') or frag.startswith('eq'):
            tabs.append(ref)
    return figs, tabs


def write_clone_rows(order_id, plan, root=None):
    """Recipient rows for every clone identity (the checks stay
    untouched; only rows are added). Returns {"granted": [...],
    "skipped": [...], "errors": [...]}; missing entries are
    skipped, never fatal, but a bad Remy handoff fails the whole
    split before anything is written."""
    from . import pc
    granted, skipped = [], []
    herr = check_remy_handoff(order_id, plan, root)
    if herr:
        return {"granted": granted, "skipped": skipped,
                "errors": herr}
    parts = (plan or {}).get("parts") or []
    by_entry = {}
    pw_rows = {}
    for p in parts:
        for ref in (p.get("materials") or []):
            try:
                rpc, rid, _frag = pc.parse_ref(ref)
            except ValueError:
                skipped.append(ref)
                continue
            by_entry.setdefault((rpc, rid), {}).setdefault(
                p["no"], []).append(ref)
    for (rpc, rid), per_no in by_entry.items():
        try:
            entry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid),
                                         root)
        except (OSError, ValueError, KeyError):
            skipped.append(pc.entry_ref(rpc, rid))
            continue
        for no, refs in per_no.items():
            refs = list(refs) + pc.twin_refs(entry, refs)
            if rpc == "source":
                figs, tabs = _split_fig_tab(refs)
                groups = [([clone_id("photo_pia", no),
                           clone_id("board_vera", no)], figs),
                          ([clone_id("anim_max", no)], tabs)]
            elif rpc in ("theory", "article"):
                for b in PENN_WREN_CLONES:
                    pw_rows.setdefault((rpc, rid, b),
                                      []).extend(refs)
                groups = []
            elif rpc in ("image", "generated"):
                groups = [([clone_id(b, no)
                           for b in IMAGE_CLONE_READERS], refs)]
            else:
                groups = []
            for agents, part_refs in groups:
                if not part_refs:
                    continue
                try:
                    pc.set_recipients(rpc, rid, order_id, agents,
                                      SPLIT_NODE, kind="map",
                                      parts=part_refs, root=root)
                except (OSError, ValueError) as exc:
                    skipped.append("%s p%d (%s)"
                                   % (pc.entry_ref(rpc, rid), no, exc))
                    continue
                granted.append("%s p%d (%s)"
                               % (pc.entry_ref(rpc, rid), no,
                                  ",".join(agents)))
    for (rpc, rid, b), part_refs in sorted(pw_rows.items()):
        seen = sorted(set(part_refs))
        if not seen:
            continue
        try:
            pc.set_recipients(rpc, rid, order_id, [b],
                              SPLIT_NODE, kind="map",
                              parts=seen, root=root)
        except (OSError, ValueError) as exc:
            skipped.append("%s %s (%s)"
                           % (pc.entry_ref(rpc, rid), b, exc))
            continue
        granted.append("%s %s (%s)"
                       % (pc.entry_ref(rpc, rid), b, b))

    remy_by_entry = {}
    for p in parts:
        for ref in (p.get("remy_handoff") or []):
            try:
                rpc, rid, _frag = pc.parse_ref(ref)
            except ValueError:
                skipped.append(ref)
                continue
            remy_by_entry.setdefault(
                (rpc, rid), {}).setdefault(
                    p["no"], []).append(ref)
    for (rpc, rid), per_no in remy_by_entry.items():
        try:
            rentry = pc.load_entry_by_ref(pc.entry_ref(rpc, rid),
                                          root)
        except (OSError, ValueError, KeyError):
            rentry = None
        for no, refs in per_no.items():
            agents = ["slide_remy@p%d" % no]
            if rentry is not None:
                refs = list(refs) + pc.twin_refs(rentry, refs)
            try:
                pc.set_recipients(rpc, rid, order_id, agents,
                                  SPLIT_NODE, kind="map",
                                  parts=refs, root=root)
            except (OSError, ValueError) as exc:
                skipped.append("%s p%d (%s)"
                               % (pc.entry_ref(rpc, rid), no, exc))
                continue
            granted.append("%s p%d (%s)"
                           % (pc.entry_ref(rpc, rid), no,
                              ",".join(agents)))
    try:
        vdoc = pc.content_id("voice:" + order_id)
        ventry = pc.load_entry_by_ref(
            pc.entry_ref("voice", vdoc), root)
        vref = ventry.get("ref", pc.entry_ref("voice", vdoc))
    except (OSError, ValueError, KeyError):
        skipped.append("voice entry for %s" % order_id)
        return {"granted": granted, "skipped": skipped,
                "errors": []}
    # Voice clips reach clones as the narration category; the
    # only Voice PC row goes to video_production (c68).
    try:
        pc.set_recipients("voice", vdoc, order_id,
                          ["video_production"],
                          SPLIT_NODE, kind="full", parts=[],
                          root=root)
    except (OSError, ValueError) as exc:
        skipped.append("voice video_production (%s)" % exc)
    else:
        granted.append("voice video_production")
    return {"granted": granted, "skipped": skipped, "errors": []}
