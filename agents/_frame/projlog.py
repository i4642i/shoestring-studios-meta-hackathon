"""Per-order project log (item 12): LOG_INDEX.json + timeline.jsonl +
TIMELINE.md under orders/<order_id>/. Stdlib only, and a leaf module
(no _frame imports at module level) so flow, memory, server and
pc_worker can all call it. Every entry point is best-effort:
failures are swallowed so logging never breaks a run.

Layout per order:
  orders/<oid>/LOG_INDEX.json   every project file, grouped
  orders/<oid>/timeline.jsonl   one append-only line per event
  orders/<oid>/TIMELINE.md      the same lines, human-readable

Timeline rows: {at, source, run_id, node, part, ev, summary, file}.
Sources: order, sam, flow, agent, pc_worker, memory, video, owner.
"""
import json
import os
import re
import threading
import time

ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

ORDERS_OVERRIDE = None  # tests only
RUNS_OVERRIDE = None  # tests only
OUTPUT_OVERRIDE = None  # tests only (PC side uses pc.ROOT_OVERRIDE)

SOURCES = ("order", "sam", "flow", "agent", "pc_worker",
           "memory", "video", "owner")

PC_NAMES = ("source", "theory", "article", "image", "generated",
            "voice")

LOG_FILES = ("TIMELINE.md", "timeline.jsonl", "LOG_INDEX.json")

_ORDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

_CLONE_RE = re.compile(r"^(.+)@p(\d+)$")

_lock = threading.Lock()

_SECRET_RES = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{4,}"), "sk-[redacted]"),
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE),
     "Bearer [redacted]"),
    (re.compile(r"(api[_-]?key|token|secret|password)"
                r"\s*[:=]\s*\S+", re.IGNORECASE),
     r"\1=[redacted]"),
]


def orders_root():
    return ORDERS_OVERRIDE or os.path.join(ROOT, "orders")


def runs_root():
    return RUNS_OVERRIDE or os.path.join(ROOT, "runs")


def output_root():
    return OUTPUT_OVERRIDE or os.path.join(ROOT, "output", "runs")


def split_clone(node):
    """(base, part|None) for a node or clone id. Local regex so
    this module stays free of _frame imports."""
    m = _CLONE_RE.match(node or "")
    if not m:
        return node or "", None
    return m.group(1), int(m.group(2))


def scrub(text, limit=200):
    """Redact secret-looking values, flatten to one line, and
    cap the length (summaries stay one line in TIMELINE.md)."""
    out = str(text or "").replace("\r", " ").replace(
        "\n", " ")
    for rx, rep in _SECRET_RES:
        out = rx.sub(rep, out)
    return out[:limit]


def order_dir(order_id, root=None):
    """Validated order folder, or None for a bad id."""
    if not order_id or not _ORDER_RE.match(order_id):
        return None
    return os.path.join(root or orders_root(), order_id)


def order_of_run(run_id, root=None):
    """The order a run belongs to (STATUS.json), or ""."""
    if not run_id or "/" in run_id or "\\" in run_id:
        return ""
    try:
        with open(os.path.join(root or runs_root(), run_id,
                               "STATUS.json"),
                  encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return ""
    oid = st.get("order_id", "") if isinstance(st, dict) else ""
    return oid if isinstance(oid, str) else ""


def runs_for_order(order_id, root=None):
    """Run ids whose STATUS names this order, oldest first."""
    root = root or runs_root()
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for n in names:
        if not os.path.isdir(os.path.join(root, n)):
            continue
        if order_of_run(n, root) == order_id:
            out.append(n)
    return out


def entries_for_order(order_id):
    """PC entries created for this order: [{pc, doc_id, ref, dir}].
    Lazily imports pc so this module stays a leaf."""
    from . import pc as _pc
    out = []
    try:
        base = _pc._base(None)
    except (OSError, ValueError, AttributeError):
        return out
    for pcname in PC_NAMES:
        edir = os.path.join(base, "storage", "_pc", pcname,
                            "entries")
        try:
            docs = sorted(os.listdir(edir))
        except OSError:
            continue
        for doc in docs:
            ddir = os.path.join(edir, doc)
            if not os.path.isdir(ddir):
                continue
            try:
                with open(os.path.join(ddir, "entry.json"),
                          encoding="utf-8") as f:
                    entry = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(entry, dict) \
                    and entry.get("order_id") == order_id:
                out.append({"pc": pcname, "doc_id": doc,
                            "ref": entry.get("ref", ""),
                            "dir": ddir})
    return out


def log_event(order_id, source, ev, summary="", run_id="",
              node="", part=None, file="", root=None):
    """Append one timeline line. Writes only when the order
    folder exists, so fixture runs with fake orders stay silent."""
    if source not in SOURCES or not ev:
        return False
    try:
        with _lock:
            odir = order_dir(order_id, root)
            if not odir or not os.path.isdir(odir):
                return False
            row = {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "source": source, "ev": ev,
                   "summary": scrub(summary),
                   "run_id": run_id or "", "node": node or "",
                   "part": part,
                   "file": (file or "").replace("\\", "/")}
            with open(os.path.join(odir, "timeline.jsonl"), "a",
                      encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False)
                        + "\n")
        return True
    except (OSError, ValueError, TypeError):
        return False


def log_owner(order_id, run_id, ev, node="", part=None,
              summary="", file=""):
    """One owner-action line (approve, re-run, pause/resume/
    stop/step, memory retry, close)."""
    base, no = split_clone(node)
    if no is not None and part is None:
        part = no
        node = base
    return log_event(order_id, "owner", ev, summary,
                     run_id, node, part, file)


def _result_rel(run_id, node, part):
    if part is None:
        return "runs/%s/%s/result.json" % (run_id, node)
    return "runs/%s/%s/p%d/result.json" % (run_id, node, part)


def mirror_run_event(order_id, run_id, ev):
    """Mirror one run-level flow event into the project timeline.
    Stage boundaries and run end also refresh the index + TIMELINE.md.
    Returns True when a refresh ran. Never raises."""
    try:
        return _mirror(order_id, run_id, ev or {})
    except (OSError, ValueError, TypeError):
        return False


def _mirror(order_id, run_id, ev):
    name = ev.get("ev", "")
    if name in ("line", ""):
        return False
    refresh = False
    if name in ("agent_start", "agent_done", "agent_skip"):
        agent = ev.get("agent", "")
        node, part = split_clone(agent)
        if ev.get("code") and node == "video_production":
            source = "video"
        elif ev.get("code"):
            source = "flow"
        else:
            source = "agent"
        if name == "agent_start":
            tev, summary, path, refresh = (
                "start", "started", "", False)
        elif name == "agent_skip":
            tev, summary, path, refresh = (
                "skipped", "skipped (already approved)", "",
                False)
        else:
            tev, summary, path, refresh = (
                "done", "done",
                _result_rel(run_id, node, part), True)
        log_event(order_id, source, tev, summary, run_id,
                  node, part, path)
    elif name == "flow_start":
        log_event(order_id, "flow", "run_start",
                  "flow %s started" % ev.get("flow", ""),
                  run_id)
    elif name == "flow_done":
        log_event(order_id, "flow", "run_done",
                  "flow finished", run_id)
        refresh = True
    elif name == "step_start":
        log_event(order_id, "flow", "step_start",
                  "step to %s" % ev.get("target", ""),
                  run_id, node=ev.get("target", ""),
                  file="runs/%s/events.jsonl" % run_id)
    elif name == "flow_error":
        log_event(order_id, "flow", "error",
                  str(ev.get("error", "")), run_id,
                  file="runs/%s/events.jsonl" % run_id)
        refresh = True
    elif name == "step_stopped":
        log_event(order_id, "flow", "stopped",
                  "halted at a stage boundary", run_id,
                  file="runs/%s/events.jsonl" % run_id)
        refresh = True
    elif name in ("flow_paused", "flow_resumed", "flow_step",
                  "step_paused"):
        tev = {"flow_paused": "paused",
               "flow_resumed": "resumed", "flow_step": "step",
               "step_paused": "step_paused"}[name]
        log_event(order_id, "flow", tev,
                  "run %s" % tev, run_id)
    elif name == "final_ready":
        log_event(order_id, "flow", "final_ready",
                  "%s final inputs" % ev.get("inputs", ""),
                  run_id)
    else:
        log_event(order_id, "flow", name, "", run_id)
    if refresh:
        do_refresh(order_id)
    return refresh


def mirror_owner_event(run_id, ev, root=None):
    """Mirror a log_run_event row (run_pause/run_resume/run_step/
    run_stop, by owner) into the project timeline."""
    try:
        oid = order_of_run(run_id, root)
        if not oid:
            return False
        name = (ev or {}).get("ev", "")
        tev = {"run_pause": "pause", "run_resume": "resume",
               "run_step": "step", "run_stop": "stop"}.get(
                   name, name)
        return log_event(oid, "owner", tev, "", run_id)
    except (OSError, ValueError, TypeError):
        return False


def memory_event(run_id, agent_id, ev, summary="", root=None):
    """One memory-build line (start/done/failed). Done/failed
    also refresh, since memory files changed."""
    try:
        oid = order_of_run(run_id, root)
        if not oid:
            return False
        file = "runs/%s/memory/%s/%s" % (
            run_id, agent_id,
            "log.jsonl" if ev in ("done", "failed")
            else "STATUS.json")
        ok = log_event(oid, "memory", ev, summary, run_id,
                       node=agent_id, file=file)
        if ev in ("done", "failed"):
            do_refresh(oid)
        return ok
    except (OSError, ValueError, TypeError):
        return False


def pc_event(order_id, ev, summary="", ref="", root=None):
    """One pc_worker line (start/done/failed). Done/failed also
    refresh, since entry files changed."""
    try:
        ok = log_event(order_id, "pc_worker", ev, summary,
                       file=ref, root=root)
        if ev in ("done", "failed"):
            do_refresh(order_id)
        return ok
    except (OSError, ValueError, TypeError):
        return False


def _walk_files(top, rel_base, skip_prefixes=()):
    """Sorted repo-relative file paths under top (forward
    slashes): rel_base + the path inside top, so temp-root
    overrides still yield canonical "orders/…/runs/…" paths.
    Returns (files, skipped): skipped counts files hidden
    under generated-dir prefixes."""
    files, skipped = [], 0
    if not os.path.isdir(top):
        return files, skipped
    for dirpath, _dirs, names in os.walk(top):
        for fn in sorted(names):
            full = os.path.join(dirpath, fn)
            rel = rel_base + "/" + os.path.relpath(
                full, top).replace("\\", "/")
            if rel.startswith(skip_prefixes):
                skipped += 1
                continue
            files.append(rel)
    files.sort()
    return files, skipped


def rebuild_index(order_id):
    """Regenerate orders/<oid>/LOG_INDEX.json: every project
    file, grouped. Generated memory indexes are counted, not
    listed (see "skipped"). Returns the index, or None."""
    try:
        return _rebuild(order_id)
    except (OSError, ValueError, TypeError):
        return None


def _rebuild(order_id):
    odir = order_dir(order_id)
    if not odir or not os.path.isdir(odir):
        return None
    order_files, _ig = _walk_files(odir, "orders/" + order_id)
    # the three log files belong to the project by definition
    # (this write creates LOG_INDEX.json; the matching render
    # creates TIMELINE.md), so they are always listed.
    for name in LOG_FILES:
        rel = "orders/%s/%s" % (order_id, name)
        if rel not in order_files:
            order_files.append(rel)
    order_files.sort()
    sam_files, _ig = _walk_files(
        os.path.join(output_root(), order_id),
        "output/runs/" + order_id)
    runs, memory, video, skipped = [], [], [], []
    for rid in runs_for_order(order_id):
        rdir = os.path.join(runs_root(), rid)
        all_files, _ig = _walk_files(
            rdir, "runs/" + rid,
            ("runs/%s/memory/" % rid,))
        mem_files, _ig = _walk_files(
            os.path.join(rdir, "memory"),
            "runs/%s/memory" % rid)
        # memory/<agent>/index/ holds the generated vector
        # store: count it, do not list every blob file.
        mem_listed = [p for p in mem_files
                      if "/index/" not in p]
        mem_skipped = len(mem_files) - len(mem_listed)
        vid = [p for p in all_files
               if p.startswith("runs/%s/video_production/"
                               % rid)]
        rest = [p for p in all_files
                if not p.startswith("runs/%s/video_production/"
                                    % rid)]
        runs.append({"run_id": rid, "files": rest})
        for agent in sorted(
                {p.split("/")[3] for p in mem_listed
                 if len(p.split("/")) > 3}):
            memory.append({
                "run_id": rid, "agent": agent,
                "files": sorted(
                    p for p in mem_listed
                    if p.split("/")[3] == agent)})
        if vid:
            video.append({"run_id": rid, "files": vid})
        if mem_skipped:
            skipped.append(
                "runs/%s/memory/*/index/ (%d files, "
                "generated index)" % (rid, mem_skipped))
    pcs = []
    for e in entries_for_order(order_id):
        files, _ig = _walk_files(
            e["dir"], "storage/_pc/%s/entries/%s"
            % (e["pc"], e["doc_id"]))
        pcs.append({"pc": e["pc"], "doc_id": e["doc_id"],
                    "ref": e["ref"], "files": files})
    index = {"order_id": order_id,
             "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "order": order_files, "sam_run": sam_files,
             "runs": runs, "memory": memory, "video": video,
             "pc": pcs, "skipped": skipped}
    with open(os.path.join(odir, "LOG_INDEX.json"), "w",
              encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    return index


def render_timeline_md(order_id):
    """Regenerate orders/<oid>/TIMELINE.md from timeline.jsonl:
    one line per event. Returns the line count, or None."""
    try:
        odir = order_dir(order_id)
        if not odir or not os.path.isdir(odir):
            return None
        rows = []
        path = os.path.join(odir, "timeline.jsonl")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for ln in f.read().splitlines():
                    try:
                        row = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        lines = ["# Project timeline — %s" % order_id, ""]
        for r in rows:
            who = r.get("node", "")
            if r.get("part") is not None:
                who += "@p%s" % r["part"]
            if r.get("run_id"):
                who = (who + " " if who else "") + \
                    "[%s]" % r["run_id"]
            line = "- %s [%s] %s" % (r.get("at", ""),
                                     r.get("source", ""),
                                     r.get("ev", ""))
            if who:
                line += " %s" % who
            if r.get("summary"):
                line += " — %s" % r["summary"]
            if r.get("file"):
                line += " (%s)" % r["file"]
            lines.append(line)
        lines.append("")
        with open(os.path.join(odir, "TIMELINE.md"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(lines))
        return len(rows)
    except (OSError, ValueError, TypeError):
        return None


def do_refresh(order_id):
    """Rebuild the index + TIMELINE.md. Best effort."""
    try:
        rebuild_index(order_id)
        render_timeline_md(order_id)
        return True
    except (OSError, ValueError, TypeError):
        return False


def projectlog_path(order_id, name):
    """A servable project-log file, or None. Only the three log
    names; anything else (including traversals) is refused."""
    if name not in LOG_FILES:
        return None
    odir = order_dir(order_id)
    if not odir:
        return None
    full = os.path.join(odir, name)
    return full if os.path.isfile(full) else None
