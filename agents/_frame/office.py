"""Per-employee live states for the Studio office. Stdlib only.

build_office(run_id) reads real run files only (STATUS.json,
events.jsonl, per-stage events, results, memory STATUS) and returns
one card per crew member: stage, bubble text, red flag, seated flag.
Nothing is invented: an agent with no events yet says "Starting...",
not a guessed action.
"""
import json
import os
import re

from . import flow as _flow
from . import parts as _parts

CUT_RE = re.compile(r"^s(\d+)c(\d+)$")


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def _tail_tool_events(path):
    """(last tool event or None, count of pc_generate_image tools)."""
    last, gen = None, 0
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f.read().splitlines():
                try:
                    ev = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(ev, dict) or ev.get("ev") != "tool":
                    continue
                last = ev
                if ev.get("tool") == "pc_generate_image":
                    gen += 1
    except OSError:
        pass
    return last, gen


def _cut_label(cut_id):
    m = CUT_RE.match(str(cut_id or ""))
    if m:
        return "%s-%s" % (m.group(1), m.group(2))
    return str(cut_id or "")


def action_phrase(tool, detail, gen_n=0, quota=0):
    """Map one real tool event to a short plain phrase."""
    tool, detail = str(tool or ""), str(detail or "")
    if tool == "pc_read_source":
        return "Reading source %s" % detail if detail \
            else "Reading source"
    if tool == "open_ref":
        return "Reading %s" % detail if detail else "Reading a passage"
    if tool == "pc_search_images":
        return "Searching photos: %s" % detail if detail \
            else "Searching photos"
    if tool == "pc_search_theory":
        return "Searching theory: %s" % detail if detail \
            else "Searching theory"
    if tool == "pc_search_articles":
        return "Searching articles: %s" % detail if detail \
            else "Searching articles"
    if tool in ("pc_pick_theory", "pc_pick_article", "pc_pick_image"):
        return "Picking %s" % detail if detail else "Picking"
    if tool == "pc_generate_image":
        if quota and gen_n:
            return "Generating image %d/%d" % (gen_n, quota)
        if gen_n:
            return "Generating image %d" % gen_n
        return "Generating image"
    if tool == "render_slide":
        label = _cut_label(detail)
        return "Rendering cut %s" % label if label \
            else "Rendering a cut"
    if tool == "make_voice":
        label = _cut_label(detail)
        return "Recording %s" % label if label \
            else "Recording narration"
    if tool == "vera_view_image":
        return "Viewing %s" % detail if detail else "Viewing images"
    if tool == "pc_send_source":
        return "Sending source to the PC"
    if tool == "pc_set_recipients":
        return "Setting recipients"
    if tool.startswith("write_"):
        return "Writing report\u2026"
    plain = tool[3:] if tool.startswith("pc_") else tool
    plain = plain.replace("_", " ").strip().capitalize()
    if detail:
        return "%s %s" % (plain, detail)
    return plain or "Working\u2026"


def _memory_state(run_dir, base):
    """Item-9 contract, read here: memory/<agent>/STATUS.json."""
    st = _load_json(os.path.join(run_dir, "memory", base,
                                 "STATUS.json"))
    state = st.get("state")
    if state in ("building", "ready", "failed"):
        return state, str(st.get("error", "") or "")
    return "none", ""


def _failed_node(run_dir):
    """Last agent_start without a matching agent_done (flow log)."""
    started, done = [], set()
    try:
        with open(os.path.join(run_dir, "events.jsonl"),
                  encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("ev") == "agent_start" and ev.get("agent"):
            started.append(str(ev["agent"]))
        elif ev.get("ev") == "agent_done" and ev.get("agent"):
            done.add(str(ev["agent"]))
    for agent in reversed(started):
        if agent not in done:
            return agent
    return ""


def _result_ok(path):
    return os.path.isfile(path)


def build_office(run_id, runs_root=None):
    """One live card per crew member of a run."""
    runs_root = runs_root or _flow.RUNS_DIR
    run_dir = os.path.join(runs_root, run_id)
    st = _load_json(os.path.join(run_dir, "STATUS.json"))
    if not st:
        return {"ok": False, "error": "no such run: %r" % run_id}
    state = st.get("state", "unknown")
    if state == "failed":
        state = "error"
    current = str(st.get("current", "") or "")
    completed = st.get("completed", []) or []
    approved = set(st.get("approved") or [])
    run_error = str(st.get("error", "") or "")
    try:
        with open(os.path.join(run_dir, "flow.json"),
                  encoding="utf-8") as f:
            sequence = _flow.topo_order(json.load(f))
    except (OSError, ValueError, RuntimeError):
        sequence = [c for c in completed if c != "final"]
        if current and "@" not in current \
                and current not in sequence:
            sequence.append(current)
    crew = [n for n in sequence
            if n != _flow.FINAL_NODE and n != _parts.SPLIT_NODE
            and n != _flow.CODE_NODE
            and not _flow._is_draft(n)]
    for extra in ("sales_sam",):
        if extra not in crew:
            crew.insert(0, extra)
    plan = _parts.load_split(run_dir)
    prog = (plan or {}).get("parts") or []
    quotas = {}
    for p in prog:
        if isinstance(p, dict) and p.get("no") is not None:
            quotas[p["no"]] = p.get("quota", 0) or 0
    failed = _failed_node(run_dir) if state == "error" else ""
    failed_base = failed.split("@")[0] if failed else ""
    todo = [n for n in crew if n not in completed
            and n != current.split("@")[0]]
    next_up = todo[0] if todo else ""
    last_done = completed[-1] if completed else ""
    short_err = run_error[:80]
    if ": " in short_err:
        short_err = short_err.split(": ", 1)[-1][:80]

    employees = []
    for base in crew:
        mem, mem_err = _memory_state(run_dir, base)
        card = {"id": base, "stage": "waiting", "bubble": "",
                "red": False, "seated": False, "still": False}
        if base in _parts.CLONE_NODES and prog:
            parts_out = []
            all_ok, any_work = True, False
            for p in prog:
                no = p.get("no")
                cid = _parts.clone_id(base, no)
                cdir = os.path.join(run_dir, base, "p%d" % no)
                evp = os.path.join(cdir, "events.jsonl")
                has = _result_ok(os.path.join(
                    cdir, "result.json"))
                is_ok = has and (cid in approved
                                 or base in approved)
                if current == cid:
                    last, gen = _tail_tool_events(evp)
                    if last is None:
                        phrase = "Starting\u2026"
                    else:
                        phrase = action_phrase(
                            last.get("tool"), last.get("detail"),
                            gen, quotas.get(no, 0))
                    parts_out.append({"no": no, "stage": "working",
                                      "text": phrase})
                    any_work = True
                    all_ok = False
                elif is_ok:
                    parts_out.append({"no": no, "stage": "approved",
                                      "text": "Done \u2713"})
                elif has:
                    parts_out.append({"no": no,
                                      "stage": "done_wait",
                                      "text": "Report done"})
                    all_ok = False
                elif failed_base == base and \
                        failed.split("@")[1:] == ["p%d" % no]:
                    parts_out.append({"no": no, "stage": "error",
                                      "text": "Error"})
                    all_ok = False
                else:
                    parts_out.append({"no": no, "stage": "waiting",
                                      "text": "waiting"})
                    all_ok = False
            card["parts"] = parts_out
            if mem == "failed":
                card.update(stage="mem_failed",
                            bubble="Memory failed", red=True,
                            seated=True, still=True)
            elif mem == "ready":
                card.update(stage="mem_ready",
                            bubble="Done \u2713 \u00b7 Memory ready",
                            seated=True, still=True)
            elif mem == "building":
                card.update(
                    stage="mem_building",
                    bubble="Learning this project (LightRAG)\u2026",
                    seated=True)
            elif all_ok and parts_out:
                card.update(stage="approved", bubble="Done \u2713",
                            seated=True, still=True)
            elif any_work:
                card.update(
                    stage="working",
                    bubble=" \u00b7 ".join(
                        "P%d %s" % (p["no"], p["text"])
                        for p in parts_out),
                    seated=True)
            elif state == "error" and failed_base == base:
                card.update(stage="error",
                            bubble="Error: %s" % short_err,
                            red=True, seated=True)
            elif state == "done":
                card.update(stage="done", bubble="Done \u2713",
                            seated=True, still=True)
            elif state == "stopped":
                card.update(stage="done", bubble="Done \u2713",
                            seated=True, still=True)
            elif state == "paused" and \
                    (base == next_up or base == last_done):
                card.update(stage="paused", bubble="\u23f8 Paused",
                            seated=True)
            elif all(p["stage"] == "waiting" for p in parts_out):
                pass  # not started: roam like everyone waiting
            else:
                card.update(
                    stage="parts",
                    bubble=" \u00b7 ".join(
                        "P%d %s" % (p["no"], p["text"])
                        for p in parts_out),
                    seated=True)
            employees.append(card)
            continue
        adir = os.path.join(run_dir, base)
        has = _result_ok(os.path.join(adir, "result.json"))
        is_ok = has and base in approved
        last, gen = _tail_tool_events(os.path.join(
            adir, "events.jsonl"))
        if mem == "failed":
            card.update(stage="mem_failed", bubble="Memory failed",
                        red=True, seated=True, still=True)
        elif mem == "ready":
            card.update(stage="mem_ready",
                        bubble="Done \u2713 \u00b7 Memory ready",
                        seated=True, still=True)
        elif mem == "building":
            card.update(stage="mem_building",
                        bubble="Learning this project (LightRAG)\u2026",
                        seated=True)
        elif is_ok:
            card.update(stage="approved", bubble="Done \u2713",
                        seated=True, still=True)
        elif current == base:
            if last is None:
                phrase = "Starting\u2026"
            else:
                phrase = action_phrase(last.get("tool"),
                                       last.get("detail"), gen, 0)
            card.update(stage="working", bubble=phrase,
                        seated=True)
        elif state == "error" and failed_base == base:
            card.update(stage="error",
                        bubble="Error: %s" % short_err, red=True,
                        seated=True)
        elif state == "error" and has:
            card.update(stage="done", bubble="Done \u2713",
                        seated=True, still=True)
        elif state == "done" and has:
            card.update(stage="done", bubble="Done \u2713",
                        seated=True, still=True)
        elif state == "stopped" and has:
            card.update(stage="done", bubble="Done \u2713",
                        seated=True, still=True)
        elif state == "paused" and \
                (base == next_up or base == last_done):
            card.update(stage="paused", bubble="\u23f8 Paused",
                        seated=True)
        elif has:
            card.update(stage="done_wait",
                        bubble="Report done \u2014 waiting for "
                               "approval",
                        seated=True)
        employees.append(card)
    return {"ok": True, "run_id": run_id, "state": state,
            "employees": employees}
