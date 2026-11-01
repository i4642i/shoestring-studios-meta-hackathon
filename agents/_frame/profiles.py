"""Employee profile cards + plain-text prompt parts (J22).

Every employee folder keeps a profile.md (name, team, title, duties,
flow neighbours, PC rights, tools). The runner and both chats put the
profile card and the tiny handbook files into the system prompt as
plain text; no RAG is used for this. Also the exact no-memory
sentences for the Studio interview chat.
"""
import json
import os

TEAM_NAMES = {"story": "Storyboard team",
              "video": "Video team",
              "sales": "Sales", "program": "Program"}

PC_NAMES = {"source": "Source PC", "theory": "Theory PC",
            "article": "Article PC", "image": "Image PC",
            "generated": "Generated Image PC", "voice": "Voice PC"}

PC_TOOLS = {"source": ("pc_list_source", "pc_read_source"),
            "theory": ("pc_search_theory", "pc_pick_theory",
                       "pc_read_theory"),
            "article": ("pc_search_articles", "pc_pick_article",
                        "pc_read_article"),
            "image": ("pc_search_images", "pc_pick_image"),
            "generated": ("pc_generate_image",),
            "voice": ("make_voice",)}

ADD_TOOLS = ("pc_send_source", "pc_pick_theory", "pc_pick_article",
             "pc_pick_image", "pc_generate_image", "make_voice")

MAX_HANDBOOK_CHARS = 24000

NO_MEMORY = {
    "building": "My memory of this project is still building.",
    "failed": "My memory of this project failed to build: %s.",
    "none": "I have not worked on this project yet.",
    "closed": "My memory of this project was deleted when the "
              "project closed.",
}


def refusal_for(state, error=""):
    """Exact interview sentence for a missing project memory."""
    if state == "failed":
        reason = (error or "unknown reason").strip()
        if reason.endswith("."):
            reason = reason[:-1].strip() or "unknown reason"
        return NO_MEMORY["failed"] % reason
    return NO_MEMORY.get(state, NO_MEMORY["none"])


def read_profile(agent_dir):
    with open(os.path.join(agent_dir, "profile.md"),
              encoding="utf-8") as f:
        return f.read()


def handbook_text(agent_dir):
    """All handbook/*.md joined (capped, with a note when cut)."""
    hb = os.path.join(agent_dir, "handbook")
    try:
        names = sorted(f for f in os.listdir(hb)
                       if f.endswith(".md"))
    except OSError:
        return ""
    parts = []
    for n in names:
        try:
            with open(os.path.join(hb, n),
                      encoding="utf-8") as f:
                parts.append("## %s\n%s" % (n, f.read()))
        except OSError:
            continue
    text = "\n\n".join(parts).strip()
    if len(text) > MAX_HANDBOOK_CHARS:
        text = text[:MAX_HANDBOOK_CHARS] + "\n[handbook truncated]"
    return text


def system_base(agent_dir):
    """Profile card + persona + handbook for a system prompt.

    Raises OSError (missing profile/persona) with the path."""
    profile = read_profile(agent_dir)
    with open(os.path.join(agent_dir, "persona.md"),
              encoding="utf-8") as f:
        persona = f.read()
    hb = handbook_text(agent_dir)
    out = ("# PROFILE CARD (who you are — answer interviews "
           "from this)\n%s\n\n---\n%s"
           % (profile.strip(), persona.strip()))
    if hb:
        out += ("\n\n---\n# HANDBOOK (your craft notes, plain "
                "text)\n%s" % hb)
    return out


def _job_line(persona):
    lines = persona.splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.lower().startswith("your job:"):
            para = [s]
            for cont in lines[i + 1:]:
                if not cont.strip():
                    break
                para.append(cont.strip())
            return " ".join(para)
    return ""


def _flow_links(flow, agent_id):
    """(receives, hands) as {category: description} from agent.json."""
    flow = flow or {}
    rec = {}
    for item in flow.get("inputs", []) or []:
        if isinstance(item, dict) and item.get("category"):
            rec[item["category"]] = item.get("description", "")
    out = {}
    for item in flow.get("outputs", []) or []:
        if isinstance(item, dict) and item.get("category"):
            out[item["category"]] = item.get("description", "")
    return rec, out


def _neighbours(flow_file, agent_id):
    """{category: [from ids]} and {category: [to ids]} from the
    default flow's solid lines."""
    frm, to = {}, {}
    try:
        with open(flow_file, encoding="utf-8") as f:
            flow = json.load(f)
    except (OSError, ValueError):
        return frm, to
    for ln in flow.get("lines", []) or []:
        if not isinstance(ln, dict):
            continue
        cats = ln.get("categories") or ([ln.get("category")]
                                        if ln.get("category")
                                        else [])
        for cat in cats:
            if ln.get("to") == agent_id:
                frm.setdefault(cat, []).append(ln.get("from",
                                                      "?"))
            if ln.get("from") == agent_id:
                to.setdefault(cat, []).append(ln.get("to", "?"))
    return frm, to


def _display(eid, names):
    if eid in ("part_split", "video_production"):
        return "%s (program step)" % eid
    if eid == "final":
        return "Final storyboard"
    if eid in names:
        return "%s (%s)" % (names[eid], eid)
    return eid


def _pc_lines(tools):
    have = [t for t in tools if t in (
        "open_ref", "pc_list_source", "pc_read_source",
        "pc_search_theory", "pc_pick_theory", "pc_read_theory",
        "pc_search_articles", "pc_pick_article",
        "pc_read_article", "pc_search_images", "pc_pick_image",
        "pc_generate_image", "make_voice", "pc_send_source",
        "pc_set_recipients")]
    if not have:
        return []
    by_pc = {}
    for pcn, names in PC_TOOLS.items():
        mine = [t for t in have if t in names]
        if mine:
            by_pc[pcn] = mine
    if "open_ref" in have:
        for pcn in by_pc:
            if "open_ref" not in by_pc[pcn]:
                by_pc[pcn].append("open_ref")
    if "pc_send_source" in have:
        by_pc.setdefault("source", []).append("pc_send_source")
    lines = []
    for pcn in PC_NAMES:
        if pcn not in by_pc:
            continue
        verbs = []
        mine = by_pc[pcn]
        if any(t not in ADD_TOOLS and t != "make_voice"
               for t in mine):
            verbs.append("read")
        if any(t in ADD_TOOLS or t == "make_voice"
               for t in mine):
            verbs.append("add")
        lines.append("- %s — %s (%s)"
                     % (PC_NAMES[pcn], ", ".join(verbs),
                        ", ".join(mine)))
    if "pc_set_recipients" in have:
        lines.append("- grant lists (pc_set_recipients)")
    return lines


def build_profile(agent_dir, flow_file=None, names=None):
    """Profile card markdown from agent.json + persona + the flow."""
    with open(os.path.join(agent_dir, "agent.json"),
              encoding="utf-8") as f:
        agent = json.load(f)
    with open(os.path.join(agent_dir, "persona.md"),
              encoding="utf-8") as f:
        persona = f.read()
    names = names or {}
    eid = agent.get("id", os.path.basename(agent_dir))
    team = TEAM_NAMES.get(agent.get("team", ""),
                          "Unassigned")
    head = "# %s — %s\nTeam: %s" % (
        agent.get("name", eid), agent.get("title", "?"), team)
    if isinstance(agent.get("stage"), int):
        head += " · Stage: S%d" % agent["stage"]
    duties = []
    job = _job_line(persona)
    duties.append(job if job else agent.get("title", "?"))
    for d in (agent.get("done") or [])[:3]:
        if isinstance(d, str) and d.strip():
            duties.append(d.strip())
    rec, out = _flow_links(agent.get("flow"), eid)
    frm, to = _neighbours(flow_file, eid) if flow_file else (
        {}, {})
    flow_sec = []
    if "flow" not in agent:
        flow_sec.append("Not in the current flow.")
    elif rec:
        flow_sec.append("Receives:")
        for cat, desc in rec.items():
            srcs = ", ".join(_display(x, names)
                             for x in frm.get(cat, []))
            flow_sec.append("- %s%s — %s" % (
                cat, (" from " + srcs) if srcs else "",
                desc or "see flow"))
    else:
        flow_sec.append("Receives: nothing (starts the work).")
    if "flow" in agent:
        if out:
            flow_sec.append("Hands to:")
            for cat, desc in out.items():
                dsts = ", ".join(_display(x, names)
                                 for x in to.get(cat, []))
                flow_sec.append("- %s%s — %s" % (
                    cat, (" to " + dsts) if dsts else "",
                    desc or "see flow"))
        else:
            flow_sec.append(
                "Hands to: nobody (end of the line).")
    pcs = _pc_lines(agent.get("tools", []) or [])
    tools = ", ".join(agent.get("tools", []) or [])
    return ("%s\n\n## Duties\n%s\n\n## Flow\n%s\n\n"
            "## PCs\n%s\n\n## Tools\n%s\n"
            % (head, "\n".join("- " + d for d in duties),
               "\n".join(flow_sec),
               "\n".join(pcs) if pcs else "None.",
               tools or "None."))
