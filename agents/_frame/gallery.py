"""Gallery cards: one per order with a final video or a storyboard
table (J20). Pure stdlib helpers over the orders/ and runs/ folders;
the server endpoint is a thin wrapper. No model calls.
"""
import json
import os
import re
from urllib.parse import quote

ORDER_RE = re.compile(r"^ord-[0-9]{8}-[0-9]{3}$")

VIDEO_NODE = "video_production"
VIDEO_NAMES = ("video.mp4", "video.webm")
TABLE_NAME = "storyboard_table.json"
SLIDE_NODE = "slide_remy"


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def latest_run_for_order(runs_root, oid):
    """Newest run dir whose STATUS.json names this order ("" if none)."""
    if not os.path.isdir(runs_root):
        return ""
    try:
        names = os.listdir(runs_root)
    except OSError:
        return ""
    names = sorted(
        names,
        key=lambda n: os.path.getmtime(os.path.join(runs_root, n)),
        reverse=True)
    for n in names:
        if n.startswith(".") or "/" in n or "\\" in n:
            continue
        if not os.path.isdir(os.path.join(runs_root, n)):
            continue
        st = _load_json(os.path.join(runs_root, n, "STATUS.json"))
        if isinstance(st, dict) and st.get("order_id") == oid:
            return n
    return ""


def order_title(meta, oid):
    """Best human title: Source PC entry title, else the uploaded file
    stem, else the order id."""
    files = {}
    if isinstance(meta, dict):
        files = meta.get("files", {}) or {}
    if isinstance(files, dict):
        pc_title = files.get("pc_title")
        if isinstance(pc_title, str) and pc_title.strip():
            return pc_title.strip()
        for key in ("upload_name", "source"):
            name = files.get(key)
            if isinstance(name, str) and name.strip():
                stem = os.path.basename(name.strip())
                stem = os.path.splitext(stem)[0].strip()
                if stem:
                    return stem
    return oid


def run_length_s(vdir):
    """Video seconds: result video.duration_s, else assembly total_s."""
    res = _load_json(os.path.join(vdir, "result.json"))
    if isinstance(res, dict):
        cats = res.get("categories", {}) or {}
        wrapped = cats.get("video", {}) or {}
        for cand in (wrapped, wrapped.get("data", {}) or {}):
            dur = cand.get("duration_s") if isinstance(cand,
                                                       dict) else None
            if isinstance(dur, (int, float)) and dur > 0:
                return int(dur)
    asm = _load_json(os.path.join(vdir, "assembly.json"))
    if isinstance(asm, dict):
        tot = asm.get("total_s")
        if isinstance(tot, (int, float)) and tot > 0:
            return int(tot)
    return None


def first_slide_png(run_dir):
    """First Remy slide PNG under slide_remy/ (forward slashes)."""
    base = os.path.join(run_dir, SLIDE_NODE)
    if not os.path.isdir(base):
        return None
    hits = []
    for root, _ds, fs in os.walk(base):
        for fn in fs:
            if fn.lower().endswith(".png"):
                rel = os.path.relpath(os.path.join(root, fn), base)
                hits.append(rel.replace("\\", "/"))
    if not hits:
        return None
    return sorted(hits)[0]


def _run_file_url(run_id, node, name):
    return "/api/flows/runs/%s/file?node=%s&name=%s" % (
        quote(run_id, safe=""), quote(node, safe=""),
        quote(name, safe=""))


def _run_path_url(run_id, node, rel):
    return "/api/flows/runs/%s/file?node=%s&path=%s" % (
        quote(run_id, safe=""), quote(node, safe=""),
        quote(rel.replace("\\", "/"), safe="/"))


def order_card(orders_root, runs_root, oid):
    """One gallery card dict, or None when the order has neither a
    final video nor a storyboard table in its latest run."""
    if not ORDER_RE.match(oid or ""):
        return None
    meta = _load_json(os.path.join(orders_root, oid, "meta.json"))
    if not isinstance(meta, dict):
        return None
    run_id = latest_run_for_order(runs_root, oid)
    if not run_id:
        return None
    vdir = os.path.join(runs_root, run_id, VIDEO_NODE)
    video_rel = None
    if os.path.isdir(vdir):
        for name in VIDEO_NAMES:
            full = os.path.join(vdir, name)
            try:
                if os.path.isfile(full) \
                        and os.path.getsize(full) > 0:
                    video_rel = name
                    break
            except OSError:
                continue
    has_table = os.path.isfile(os.path.join(vdir, TABLE_NAME))
    if not video_rel and not has_table:
        return None
    closed = bool(meta.get("closed"))
    if closed:
        status = "closed"
    elif video_rel:
        status = "video"
    else:
        status = "table"
    thumb = first_slide_png(os.path.join(runs_root, run_id))
    log_path = os.path.join(orders_root, oid, "TIMELINE.md")
    card = {"order_id": oid,
            "title": order_title(meta, oid),
            "created": meta.get("created", "")
            if isinstance(meta.get("created"), str) else "",
            "length_s": run_length_s(vdir),
            "closed": closed,
            "status": status,
            "run_id": run_id,
            "thumb_url": _run_path_url(run_id, SLIDE_NODE, thumb)
            if thumb else None,
            "video_url": _run_path_url(run_id, VIDEO_NODE, video_rel)
            if video_rel else None,
            "table_url": _run_file_url(run_id, VIDEO_NODE, TABLE_NAME)
            if has_table else None,
            "log_url": "/api/orders/%s/projectlog?name=TIMELINE.md"
            % quote(oid, safe="") if os.path.isfile(log_path)
            else None}
    return card


def gallery_cards(orders_root, runs_root):
    """Newest first. Skips orders without a qualifying latest run."""
    out = []
    try:
        names = os.listdir(orders_root)
    except OSError:
        return []
    for n in sorted(names):
        if not ORDER_RE.match(n):
            continue
        if not os.path.isdir(os.path.join(orders_root, n)):
            continue
        card = order_card(orders_root, runs_root, n)
        if card is not None:
            out.append(card)
    out.sort(key=lambda c: (c["created"], c["order_id"]),
             reverse=True)
    return out
