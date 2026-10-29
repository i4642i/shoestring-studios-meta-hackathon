"""Tool registry + builtin tools. Stdlib only.

Each tool takes (ctx, args) and returns JSON-serializable data.
ctx: {"run_dir":..., "agent_dir":..., "input_md":...}
"""
import importlib.util
import json
import os

from . import graph
from . import results
from .schemas import (list_headings, validate_draft, validate_request,
                      validate_structure)


def read_md_section(ctx, args):
    path = args.get("path") or ctx.get("input_md")
    max_chars = int(args.get("max_chars", 4000))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    heads = [(i, ln) for i, ln in enumerate(lines) if ln.startswith("#")]
    sections = [t for _, t in list_headings(text)]
    want = (args.get("section") or "").strip().lower()
    if want:
        for idx, (li, ln) in enumerate(heads):
            if ln.lstrip("# ").strip().lower() == want:
                end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
                return {"section": ln.strip(),
                        "text": "\n".join(lines[li:end])[:max_chars]}
        return {"error": "section not found", "sections": sections}
    return {"sections": sections, "text": text[:max_chars],
            "truncated": len(text) > max_chars}


def write_draft(ctx, args):
    draft = args.get("draft")
    errors = validate_draft(draft)
    if errors:
        return {"ok": False, "errors": errors}
    out = os.path.join(ctx["run_dir"], "draft.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    return {"ok": True, "path": out, "output": "draft.json"}


def _save_category(ctx, category, obj):
    """Wrap one validated payload as the run's result.json (Q6 cutover)."""
    try:
        res = results.make_result(ctx["producer"], ctx["order_id"],
                                  ctx["run_id"], {category: obj})
    except (KeyError, RuntimeError) as exc:
        return {"ok": False, "errors": ["bad result context: %s" % exc]}
    problems = results.check_result(res)
    if problems:
        return {"ok": False, "errors": problems}
    try:
        out = results.save_result(ctx["run_dir"], res)
    except RuntimeError as exc:
        return {"ok": False, "errors": [str(exc)]}
    return {"ok": True, "path": out, "output": "result.json"}


def write_structure(ctx, args):
    obj = args.get("structure")
    errors = validate_structure(obj, ctx.get("input_md"))
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "structure", obj)


def write_request(ctx, args):
    obj = args.get("request")
    errors = validate_request(obj)
    if errors:
        return {"ok": False, "errors": errors}
    return _save_category(ctx, "request", obj)


def query_graph(ctx, args):
    st = graph.get_status(ctx["agent_dir"])
    if st["state"] != "indexed":
        return {"state": st["state"], "reason": st.get("reason", ""),
                "hint": "read input_md directly instead"}
    ans = graph.query(ctx["agent_dir"], args.get("question", ""))
    out = {"state": "indexed", "answer": ans}
    if isinstance(ans, dict):
        for k in ("profile", "model", "dim"):
            if ans.get(k) is not None:
                out[k] = ans[k]
    return out


# Writer tool -> run output file. The server keeps agent.json io.output
# in sync with the employee's single write_* tool. Since the Q6 cutover
# every run writes result.json (one envelope, categories inside).
OUTPUTS = {
    "write_draft": "draft.json",
    "write_structure": "result.json",
    "write_request": "result.json",
}

TOOLS = {
    "read_md_section": (
        read_md_section,
        "Read the input markdown file: lists sections, returns head or one section.",
        {"type": "object",
         "properties": {"path": {"type": "string"},
                        "section": {"type": "string"},
                        "max_chars": {"type": "integer"}},
         "additionalProperties": False},
    ),
    "write_draft": (
        write_draft,
        "Save the finished storyboard draft. Fails unless it passes validation.",
        {"type": "object",
         "properties": {"draft": {"type": "object"}},
         "required": ["draft"], "additionalProperties": False},
    ),
    "write_structure": (
        write_structure,
        "Save the input structure map as this run's result.json "
        "(structure category). Fails unless every section is mapped in "
        "source order with neighbour links.",
        {"type": "object",
         "properties": {"structure": {"type": "object"}},
         "required": ["structure"], "additionalProperties": False},
    ),
    "write_request": (
        write_request,
        "Save the video production request for an order as this run's "
        "result.json (request category). Fails unless all 5 intake "
        "answers and production notes validate.",
        {"type": "object",
         "properties": {"request": {"type": "object"}},
         "required": ["request"], "additionalProperties": False},
    ),
    "query_graph": (
        query_graph,
        "Ask the employee knowledge graph. Honest when no index exists yet.",
        {"type": "object",
         "properties": {"question": {"type": "string"}},
         "required": ["question"], "additionalProperties": False},
    ),
}


def get_tools(agent_dir):
    """Builtin registry + per-employee tools/<name>.py (D33, auto-discovered)."""
    merged = dict(TOOLS)
    tdir = os.path.join(agent_dir, "tools")
    if not os.path.isdir(tdir):
        return merged
    for fn in sorted(os.listdir(tdir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        spec = importlib.util.spec_from_file_location(
            "tool_" + name, os.path.join(tdir, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if (getattr(mod, "NAME", None) != name
                or not callable(getattr(mod, "run", None))
                or not isinstance(getattr(mod, "SCHEMA", None), dict)):
            raise ValueError("bad custom tool file: %s" % fn)
        merged[name] = (mod.run, getattr(mod, "DESC", "custom tool " + name),
                        mod.SCHEMA)
    return merged
