"""Validate one employee folder against docs/AGENT_STANDARD_EN.md.

Usage: python scripts/validate_agent.py agents/<id>
Exit 0 == PASS. Stdlib only. Also importable: validate(path) -> [errors].
"""
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ALLOW_MODELS = ("muse-spark-1.3", "muse-spark-1.2", "muse-spark-1.1",
                "muse-wonder-1.0", "meta-models/muse-spark-open-1026")
ALLOW_PREFIX = ("muse-glimmer-", "muse-spark-open-")
AGENT_REQUIRED = ("frame_version", "id", "name", "title", "model", "tools",
                  "bounds", "io", "done")
AGENT_OPTIONAL = ("flow",)


def validate(path):
    errs = []
    want_id = os.path.basename(os.path.normpath(path))
    agent_js = os.path.join(path, "agent.json")
    persona_md = os.path.join(path, "persona.md")
    handbook = os.path.join(path, "handbook")
    appearance = os.path.join(path, "appearance.json")
    tools_dir = os.path.join(path, "tools")

    if not ID_RE.match(want_id):
        errs.append("folder id breaks naming rule: %s" % want_id)
    for p in (agent_js, persona_md, appearance):
        if not os.path.isfile(p):
            errs.append("missing: %s" % p)
    if not (os.path.isdir(handbook)
            and [f for f in os.listdir(handbook) if f.endswith(".md")]):
        errs.append("handbook/ needs >=1 .md file")

    from agents._frame import tools as reg
    names = set(reg.TOOLS)
    if os.path.isdir(tools_dir):
        for fn in sorted(os.listdir(tools_dir)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            name = fn[:-3]
            if not ID_RE.match(name):
                errs.append("tool filename breaks naming rule: %s" % fn)
                continue
            spec = importlib.util.spec_from_file_location(
                "tool_" + name, os.path.join(tools_dir, fn))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                errs.append("tool %s import failed: %s" % (fn, exc))
                continue
            if getattr(mod, "NAME", None) != name:
                errs.append("tool %s: NAME != filename" % fn)
            if not callable(getattr(mod, "run", None)):
                errs.append("tool %s: run() not callable" % fn)
            if not isinstance(getattr(mod, "SCHEMA", None), dict):
                errs.append("tool %s: SCHEMA must be a dict" % fn)
            names.add(name)

    agent = {}
    if os.path.isfile(agent_js):
        try:
            with open(agent_js, encoding="utf-8") as f:
                agent = json.load(f)
        except ValueError as e:
            errs.append("agent.json invalid: %s" % e)
    if agent:
        unknown = [k for k in agent
                   if k not in AGENT_REQUIRED and k not in AGENT_OPTIONAL]
        if unknown:
            errs.append("agent.json unknown fields: %s" % unknown)
        if "flow" in agent:
            errs += _validate_flow(agent["flow"])
        missing = [k for k in agent if k not in agent]
        if missing:
            errs.append("agent.json missing: %s" % missing)
        if agent.get("id") != want_id:
            errs.append("id != folder name")
        model = agent.get("model", "")
        if not (model in ALLOW_MODELS or model.startswith(ALLOW_PREFIX)):
            errs.append("model not on allowlist: %s" % model)
        steps = (agent.get("bounds") or {}).get("max_steps")
        if not isinstance(steps, int) or not 1 <= steps <= 20:
            errs.append("bounds.max_steps must be int 1-20")
        if not isinstance(agent.get("done"), list) or not agent.get("done"):
            errs.append("done needs >=1 item")
        for t in agent.get("tools", []):
            if t not in names:
                errs.append("unknown tool: %s" % t)

    if os.path.isfile(appearance):
        with open(appearance, encoding="utf-8") as f:
            try:
                ap = json.load(f)
            except ValueError as e:
                errs.append("appearance.json invalid: %s" % e)
                ap = {}
        if ap and (not isinstance(ap, dict)
                   or not isinstance(ap.get("variant"), str)
                   or not ap["variant"].endswith(".glb")):
            errs.append("appearance.json needs {variant: '<file>.glb', tint?}")

    if os.path.isfile(persona_md):
        with open(persona_md, encoding="utf-8") as f:
            text = f.read()
        for section in ("## Persona", "## Voice", "## Rules"):
            if section not in text:
                errs.append("persona.md missing %s" % section)
        if not text.startswith("# "):
            errs.append("persona.md must start with '# <Name>'")
    return errs


def _validate_flow(flow):
    errs = []
    if not isinstance(flow, dict):
        return ["flow must be an object"]
    try:
        with open(os.path.join(ROOT, "agents", "_frame",
                               "categories.json"),
                  encoding="utf-8") as f:
            registry = json.load(f)
    except (OSError, ValueError) as exc:
        return ["cannot load category registry: %s" % exc]
    for side in ("inputs", "outputs"):
        items = flow.get(side, [])
        if not isinstance(items, list):
            errs.append("flow.%s must be a list" % side)
            continue
        for i, item in enumerate(items):
            where = "flow.%s[%d]" % (side, i)
            if not isinstance(item, dict):
                errs.append("%s must be an object" % where)
                continue
            cat = item.get("category", "")
            if not ID_RE.match(cat):
                errs.append("%s.category breaks naming rule" % where)
            elif cat not in registry:
                errs.append("%s.category unknown: %r" % (where, cat))
            if not isinstance(item.get("description"), str) \
                    or not item["description"].strip():
                errs.append("%s needs a non-empty description" % where)
            if side == "inputs":
                if not isinstance(item.get("required"), bool):
                    errs.append("%s.required must be a bool" % where)
            else:
                fn = item.get("file", "")
                if not isinstance(fn, str) or not fn \
                        or "/" in fn or "\\" in fn or fn.startswith("."):
                    errs.append("%s.file must be a plain filename" % where)
    return errs


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else ""
    errs = validate(d)
    if errs:
        print("FAIL", d)
        for e in errs:
            print(" -", e)
        return 1
    print("PASS", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
