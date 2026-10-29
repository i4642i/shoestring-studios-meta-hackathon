"""Crew flow engine: validate, order, and run multi-agent flows. Stdlib only.

A flow (data/flows/<id>.json) wires agents with category-carrying lines.
Connections live ONLY here: agents declare input/output categories in
agent.json "flow", never destinations. Results travel as envelopes
(see categories.json + AGENT_STANDARD_EN.md section 9); every handoff
validates envelope + payload schema and stops the flow on failure.
"""
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CATEGORIES = os.path.join(HERE, "categories.json")
FLOWS_DIR = os.path.join(ROOT, "data", "flows")
RUNS_DIR = os.path.join(ROOT, "runs")
ORDERS_DIR = os.path.join(ROOT, "orders")

ORDER_NODE = "order"
FINAL_NODE = "final"
ORDER_OUTPUTS = [
    {"category": "brief",
     "description": "Order answers + source ref (brief.json)",
     "file": "brief.json"},
    {"category": "source",
     "description": "Parsed source document (source.md)",
     "file": "source.md"},
]
STATUSES = ("unverified", "checked", "verified")

_registry = None


def registry():
    """Category registry {name: {version, description, schema}}."""
    global _registry
    if _registry is None:
        with open(CATEGORIES, encoding="utf-8") as f:
            _registry = json.load(f)
    return _registry


def validate_schema(value, schema, where="payload"):
    """Minimal JSON-schema check. Supported subset: type (object, array,
    string, integer, number, boolean), properties, required, items (one
    schema), additionalProperties (bool), enum. Returns [errors]."""
    errors = []

    def walk(val, sch, path):
        if not isinstance(sch, dict):
            return
        if "enum" in sch and val not in sch["enum"]:
            errors.append("%s: not one of %r" % (path, sch["enum"]))
        typ = sch.get("type")
        if typ == "object":
            if not isinstance(val, dict):
                errors.append("%s: must be an object" % path)
                return
            for k in sch.get("required") or []:
                if k not in val:
                    errors.append("%s: missing %r" % (path, k))
            props = sch.get("properties") or {}
            for k, sub in props.items():
                if k in val:
                    walk(val[k], sub, "%s.%s" % (path, k))
            if sch.get("additionalProperties") is False:
                for k in val:
                    if k not in props:
                        errors.append("%s: unknown key %r" % (path, k))
        elif typ == "array":
            if not isinstance(val, list):
                errors.append("%s: must be an array" % path)
                return
            items = sch.get("items")
            if isinstance(items, dict):
                for i, item in enumerate(val):
                    walk(item, items, "%s[%d]" % (path, i))
        elif typ == "string":
            if not isinstance(val, str):
                errors.append("%s: must be a string" % path)
        elif typ == "integer":
            if not isinstance(val, int) or isinstance(val, bool):
                errors.append("%s: must be an integer" % path)
        elif typ == "number":
            if (not isinstance(val, (int, float))
                    or isinstance(val, bool)):
                errors.append("%s: must be a number" % path)
        elif typ == "boolean":
            if not isinstance(val, bool):
                errors.append("%s: must be a boolean" % path)

    walk(value, schema, where)
    return errors


def make_envelope(category, producer, order_id, run_id, payload):
    """Wrap a payload. Raises RuntimeError for unknown categories."""
    reg = registry()
    if category not in reg:
        raise RuntimeError("unknown category: %r" % category)
    return {"category": category, "version": reg[category]["version"],
            "producer": producer, "order_id": order_id, "run_id": run_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": "unverified", "payload": payload}


def check_envelope(env, where="envelope"):
    """Validate envelope shape + registry version + payload schema."""
    if not isinstance(env, dict):
        return ["%s: must be an object" % where]
    errors = []
    for k in ("category", "version", "producer", "order_id", "run_id",
              "created_at", "status", "payload"):
        if k not in env:
            errors.append("%s: missing %r" % (where, k))
    if errors:
        return errors
    reg = registry()
    cat = env["category"]
    if cat not in reg:
        return ["%s: unknown category %r" % (where, cat)]
    if env["version"] != reg[cat]["version"]:
        errors.append("%s: version %r != registry v%d"
                      % (where, env["version"], reg[cat]["version"]))
    if env["status"] not in STATUSES:
        errors.append("%s: bad status %r" % (where, env["status"]))
    if not isinstance(env["payload"], dict):
        errors.append("%s: payload must be an object" % where)
        return errors
    errors += validate_schema(env["payload"], reg[cat]["schema"],
                              where + ".payload")
    return errors


def load_flow(flow_id):
    """Read data/flows/<id>.json. Raises FileNotFoundError/ValueError."""
    if not flow_id or "/" in flow_id or "\\" in flow_id \
            or flow_id.startswith("."):
        raise ValueError("bad flow id: %r" % (flow_id,))
    path = os.path.join(FLOWS_DIR, flow_id + ".json")
    with open(path, encoding="utf-8") as f:
        flow = json.load(f)
    if not isinstance(flow, dict):
        raise ValueError("flow %r is not an object" % flow_id)
    return flow


def load_catalog():
    """Agents with flow sections + pseudo nodes. Never raises."""
    agents = []
    adir = os.path.join(ROOT, "agents")
    if os.path.isdir(adir):
        for eid in sorted(os.listdir(adir)):
            if eid.startswith("_") or eid in (ORDER_NODE, FINAL_NODE):
                continue
            path = os.path.join(adir, eid)
            if not os.path.isdir(path):
                continue
            agent = {"id": eid, "name": eid, "title": "",
                     "flow": None}
            try:
                with open(os.path.join(path, "agent.json"),
                          encoding="utf-8") as f:
                    aj = json.load(f)
                agent["name"] = aj.get("name", eid)
                agent["title"] = aj.get("title", "")
                if isinstance(aj.get("flow"), dict):
                    agent["flow"] = aj["flow"]
            except (OSError, ValueError):
                pass
            agents.append(agent)
    return {"agents": agents,
            "order": {"outputs": ORDER_OUTPUTS},
            "final": {}}


def _sender_outputs(node_id, catalog):
    if node_id == ORDER_NODE:
        return catalog["order"]["outputs"]
    for a in catalog["agents"]:
        if a["id"] == node_id:
            return (a.get("flow") or {}).get("outputs") or []
    return []


def validate_flow(flow, catalog=None):
    """Live validation. Returns [{message, node?, line?}] (empty == valid)."""
    catalog = catalog if catalog is not None else load_catalog()
    errs = []

    def err(message, node=None, line=None):
        e = {"message": message}
        if node is not None:
            e["node"] = node
        if line is not None:
            e["line"] = line
        errs.append(e)

    if not isinstance(flow, dict):
        return [{"message": "flow must be an object"}]
    nodes = flow.get("nodes")
    lines = flow.get("lines")
    if not isinstance(nodes, list):
        return [{"message": "flow.nodes must be a list"}]
    if not isinstance(lines, list):
        return [{"message": "flow.lines must be a list"}]
    ids = []
    for n in nodes:
        nid = n.get("id") if isinstance(n, dict) else None
        if not nid or not isinstance(nid, str):
            err("node without a string id")
            continue
        if nid in ids:
            err("duplicate node id: %r" % nid, node=nid)
        ids.append(nid)
    known = set(ids)
    if ORDER_NODE not in known:
        err("flow needs an Order node")
    if FINAL_NODE not in known:
        err("flow needs a Final node")
    agent_ids = {a["id"] for a in catalog["agents"]}
    for nid in ids:
        if nid in (ORDER_NODE, FINAL_NODE):
            continue
        if nid not in agent_ids:
            err("unknown agent: %r" % nid, node=nid)
            continue
        outs = _sender_outputs(nid, catalog)
        flow_sec = None
        for a in catalog["agents"]:
            if a["id"] == nid:
                flow_sec = a.get("flow")
        if not isinstance(flow_sec, dict):
            err("agent %r declares no flow inputs/outputs" % nid, node=nid)
        elif not outs and not (flow_sec.get("inputs") or []):
            err("agent %r has an empty flow section" % nid, node=nid)
    seen_lines, seen_pairs = set(), set()
    for ln in lines:
        if not isinstance(ln, dict):
            err("line must be an object")
            continue
        lid = ln.get("id")
        if not lid or lid in seen_lines:
            err("line without a unique id", line=lid)
            continue
        seen_lines.add(lid)
        a, b = ln.get("from"), ln.get("to")
        if a not in known:
            err("line %r: unknown sender %r" % (lid, a), line=lid)
            continue
        if b not in known:
            err("line %r: unknown target %r" % (lid, b), line=lid)
            continue
        if a == b:
            err("line %r: sender == target" % lid, line=lid)
            continue
        if (a, b) in seen_pairs:
            err("duplicate line %r -> %r (combine categories on one line)"
                % (a, b), line=lid)
            continue
        seen_pairs.add((a, b))
        if a == FINAL_NODE:
            err("line %r: Final video sends nothing" % lid, line=lid)
            continue
        cats = ln.get("categories")
        sender_cats = [o["category"] for o in _sender_outputs(a, catalog)
                       if isinstance(o, dict) and o.get("category")]
        if cats == "*":
            if not sender_cats:
                err("line %r: sender declares no outputs" % lid, line=lid)
        elif (not isinstance(cats, list) or not cats
                or any(not isinstance(c, str) for c in cats)):
            err("line %r: categories must be \"*\" or a non-empty list"
                % lid, line=lid)
        else:
            for c in cats:
                if c not in sender_cats:
                    err("line %r: unknown category %r for %r"
                        % (lid, c, a), line=lid)
    incoming = {nid: [] for nid in ids}
    for ln in lines:
        if isinstance(ln, dict) and ln.get("to") in incoming:
            incoming[ln["to"]].append(ln)
    if incoming.get(ORDER_NODE):
        err("Order node takes no input", node=ORDER_NODE)
    for nid in ids:
        if nid == ORDER_NODE:
            continue
        if not incoming[nid]:
            what = "Final video" if nid == FINAL_NODE else "agent %r" % nid
            err("%s has no input" % what, node=nid)
    for nid in ids:
        if nid in (ORDER_NODE, FINAL_NODE):
            continue
        flow_sec = {}
        for a in catalog["agents"]:
            if a["id"] == nid:
                flow_sec = a.get("flow") or {}
        required = [i["category"] for i in flow_sec.get("inputs", [])
                    if isinstance(i, dict) and i.get("required")
                    and i.get("category")]
        for cat in required:
            if not _delivers(incoming[nid], cat, catalog):
                err("agent %r: missing required input %r" % (nid, cat),
                    node=nid)
    cyc = _find_cycle(ids, seen_pairs)
    if cyc:
        err("cycle not allowed: %s" % " -> ".join(cyc))
    return errs


def _delivers(incoming, category, catalog):
    for ln in incoming:
        cats = ln.get("categories")
        if cats == "*":
            sender_cats = [o["category"]
                           for o in _sender_outputs(ln["from"], catalog)
                           if isinstance(o, dict)]
            if category in sender_cats:
                return True
        elif isinstance(cats, list) and category in cats:
            return True
    return False


def _find_cycle(ids, pairs):
    nxt = {}
    for a, b in pairs:
        nxt.setdefault(a, []).append(b)
    color = {}

    def visit(n, stack):
        color[n] = 1
        for m in nxt.get(n, []):
            if color.get(m) == 1:
                return stack + [m]
            if color.get(m) is None:
                hit = visit(m, stack + [m])
                if hit:
                    return hit
        color[n] = 2
        return None

    for nid in ids:
        if color.get(nid) is None:
            hit = visit(nid, [nid])
            if hit:
                return hit
    return None


def topo_order(flow):
    """Node ids in dependency order. Raises RuntimeError on cycles."""
    ids = [n["id"] for n in flow.get("nodes", [])]
    pairs = [(ln["from"], ln["to"]) for ln in flow.get("lines", [])]
    cyc = _find_cycle(ids, set(pairs))
    if cyc:
        raise RuntimeError("cycle not allowed: %s" % " -> ".join(cyc))
    ins = {nid: 0 for nid in ids}
    nxt = {}
    for a, b in set(pairs):
        nxt.setdefault(a, []).append(b)
        ins[b] = ins.get(b, 0) + 1
    ready = sorted(n for n in ids if ins.get(n, 0) == 0)
    out = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in sorted(nxt.get(n, [])):
            ins[m] -= 1
            if ins[m] == 0:
                ready.append(m)
        ready.sort()
    return out


def expand_line(line, catalog):
    """Concrete categories a line carries ("*" -> all sender outputs)."""
    cats = line.get("categories")
    if cats != "*":
        return list(cats)
    return [o["category"] for o in _sender_outputs(line["from"], catalog)
            if isinstance(o, dict) and o.get("category")]


def _new_run_id():
    base = time.strftime("fl-%Y%m%d-%H%M%S")
    rid, n = base, 2
    while os.path.exists(os.path.join(RUNS_DIR, rid)):
        rid = "%s-%d" % (base, n)
        n += 1
    return rid


def run_flow(flow, order_id, run_agent_fn, run_id=None, flow_id="adhoc"):
    """Run a validated flow. Returns run_id. Raises RuntimeError on failure.

    run_agent_fn(agent_dir, run_dir, brief, input_md) follows the
    runner.run contract ({"ok": bool, ...}); tests inject a stub.
    Layout: runs/<run_id>/{flow.json, events.jsonl, STATUS.json,
    order/*, <agent>/*, final/*}. Order materializes brief.json +
    source.md; agents run in topo order; every handoff validates.
    """
    errs = validate_flow(flow)
    if errs:
        raise RuntimeError("invalid flow: %s"
                           % "; ".join(e["message"] for e in errs))
    catalog = load_catalog()
    rid = run_id or _new_run_id()
    rdir = os.path.join(RUNS_DIR, rid)
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "flow.json"), "w", encoding="utf-8") as f:
        json.dump(flow, f, ensure_ascii=False, indent=1)
    events_path = os.path.join(rdir, "events.jsonl")

    def emit(ev):
        ev["t"] = time.strftime("%H:%M:%S")
        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def fail(message):
        emit({"ev": "flow_error", "error": message})
        with open(os.path.join(rdir, "STATUS.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"state": "error", "error": message}, f,
                      ensure_ascii=False, indent=1)
        raise RuntimeError(message)

    emit({"ev": "flow_start", "flow": flow_id, "order": order_id,
          "run": rid})
    try:
        _materialize_order(rdir, order_id, rid, emit)
        order = topo_order(flow)
        by_to = {}
        for ln in flow["lines"]:
            by_to.setdefault(ln["to"], []).append(ln)
        for nid in order:
            if nid in (ORDER_NODE, FINAL_NODE):
                continue
            _run_agent_node(flow_id, rdir, order_id, rid, nid,
                            by_to.get(nid, []), catalog, run_agent_fn, emit)
        _collect_final(rdir, order_id, rid, by_to.get(FINAL_NODE, []),
                       catalog, emit)
    except RuntimeError as exc:
        fail(str(exc))
    with open(os.path.join(rdir, "STATUS.json"), "w", encoding="utf-8") as f:
        json.dump({"state": "done"}, f, ensure_ascii=False, indent=1)
    emit({"ev": "flow_done", "run": rid})
    return rid


def _materialize_order(rdir, order_id, run_id, emit):
    d = os.path.join(ORDERS_DIR, order_id)
    meta_p = os.path.join(d, "meta.json")
    parsed_p = os.path.join(d, "parsed.md")
    if not os.path.isfile(meta_p):
        raise RuntimeError("no such order: %r" % order_id)
    if not os.path.isfile(parsed_p):
        raise RuntimeError("order %r has no parsed PDF yet" % order_id)
    with open(meta_p, encoding="utf-8") as f:
        meta = json.load(f)
    with open(parsed_p, encoding="utf-8") as f:
        source_text = f.read()
    odir = os.path.join(rdir, ORDER_NODE)
    os.makedirs(odir, exist_ok=True)
    brief = {"order_id": order_id, "answers": meta.get("answers", {}),
             "source_file": meta.get("files", {}).get("source",
                                                      "source.pdf")}
    with open(os.path.join(odir, "brief.json"), "w", encoding="utf-8") as f:
        json.dump(make_envelope("brief", ORDER_NODE, order_id, run_id,
                                brief),
                  f, ensure_ascii=False, indent=1)
    with open(os.path.join(odir, "source.md"), "w", encoding="utf-8") as f:
        f.write(source_text)
    payload = {"file": "source.md", "chars": len(source_text),
               "head": source_text[:1000]}
    with open(os.path.join(odir, "source.json"), "w", encoding="utf-8") as f:
        json.dump(make_envelope("source", ORDER_NODE, order_id, run_id,
                                payload),
                  f, ensure_ascii=False, indent=1)
    emit({"ev": "order_ready", "files": ["brief.json", "source.md"]})


def _read_envelope(rdir, sender, category):
    path = os.path.join(rdir, sender, category + ".json")
    if not os.path.isfile(path):
        raise RuntimeError("producer %r has no %r yet" % (sender, category))
    with open(path, encoding="utf-8") as f:
        try:
            env = json.load(f)
        except ValueError:
            raise RuntimeError("%s is not valid JSON" % path)
    return env, path


def _transfer(rdir, order_id, run_id, line, catalog, emit):
    """Validate one line's handoffs. Returns [(sender, category, content)]."""
    got = []
    files, total = [], 0
    for cat in expand_line(line, catalog):
        env, path = _read_envelope(rdir, line["from"], cat)
        problems = check_envelope(env, "%s/%s" % (line["from"], cat))
        if problems:
            raise RuntimeError("handoff %s -> %s (%s) invalid: %s"
                               % (line["from"], line["to"], cat,
                                  "; ".join(problems)))
        if env["status"] == "unverified":
            env["status"] = "checked"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(env, f, ensure_ascii=False, indent=1)
        payload = env["payload"]
        sidecar = payload.get("file") if isinstance(payload, dict) else None
        side_p = os.path.join(rdir, line["from"], sidecar) \
            if isinstance(sidecar, str) else None
        if side_p and os.path.isfile(side_p):
            with open(side_p, encoding="utf-8") as f:
                content = f.read()
            files.append("%s/%s" % (line["from"], sidecar))
            total += len(content)
        else:
            content = json.dumps(payload, ensure_ascii=False, indent=2)
            files.append("%s/%s.json (inline)" % (line["from"], cat))
            total += len(content)
        got.append((line["from"], cat, env["version"], content))
    emit({"ev": "line", "line": line.get("id"), "from": line["from"],
          "to": line["to"],
          "categories": [c for _, c, _, _ in got],
          "files": files, "bytes": total, "status": "ok"})
    return got


def _run_agent_node(flow_id, rdir, order_id, run_id, nid, incoming,
                    catalog, run_agent_fn, emit):
    adir = os.path.join(rdir, nid)
    os.makedirs(adir, exist_ok=True)
    emit({"ev": "agent_start", "agent": nid})
    parts, manifest = [], []
    for ln in sorted(incoming, key=lambda l: str(l.get("id"))):
        for sender, cat, ver, content in _transfer(
                rdir, order_id, run_id, ln, catalog, emit):
            parts.append("## From %s / %s\n\n%s\n" % (sender, cat, content))
            manifest.append({"sender": sender, "category": cat,
                             "version": ver,
                             "envelope": "%s/%s.json" % (sender, cat)})
    input_md = os.path.join(adir, "input.md")
    with open(input_md, "w", encoding="utf-8") as f:
        f.write("# Flow inputs for %s (order %s, run %s)\n\n%s"
                % (nid, order_id, run_id, "\n".join(parts)))
    with open(os.path.join(adir, "INPUTS.json"), "w", encoding="utf-8") as f:
        json.dump({"inputs": manifest}, f, ensure_ascii=False, indent=1)
    brief = {"order_id": order_id, "flow_id": flow_id,
             "flow_run_id": run_id, "agent": nid,
             "inputs": [{"sender": m["sender"], "category": m["category"],
                         "version": m["version"]} for m in manifest]}
    agent_dir = os.path.join(ROOT, "agents", nid)
    result = run_agent_fn(agent_dir, adir, brief, input_md)
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError("agent %r failed: %s"
                           % (nid, (result or {}).get("error", "unknown")
                              if isinstance(result, dict) else result))
    wrapped = []
    for out in _sender_outputs(nid, catalog):
        cat, legacy = out["category"], out.get("file", "")
        if not legacy or "/" in legacy or "\\" in legacy \
                or legacy.startswith("."):
            raise RuntimeError("agent %r: bad output file %r"
                               % (nid, legacy))
        src = os.path.join(adir, legacy)
        if not os.path.isfile(src):
            raise RuntimeError("agent %r did not write %r"
                               % (nid, legacy))
        if legacy.endswith(".json"):
            with open(src, encoding="utf-8") as f:
                try:
                    payload = json.load(f)
                except ValueError:
                    raise RuntimeError("agent %r: %r is not valid JSON"
                                       % (nid, legacy))
            if not isinstance(payload, dict):
                raise RuntimeError("agent %r: %r must hold an object"
                                   % (nid, legacy))
        else:
            with open(src, encoding="utf-8") as f:
                text = f.read()
            payload = {"file": legacy, "chars": len(text),
                       "head": text[:1000]}
        env = make_envelope(cat, nid, order_id, run_id, payload)
        with open(os.path.join(adir, cat + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False, indent=1)
        wrapped.append(cat)
    emit({"ev": "agent_done", "agent": nid, "outputs": wrapped})


def _collect_final(rdir, order_id, run_id, incoming, catalog, emit):
    fdir = os.path.join(rdir, FINAL_NODE)
    os.makedirs(fdir, exist_ok=True)
    collected = []
    for ln in sorted(incoming or [], key=lambda l: str(l.get("id"))):
        for sender, cat, ver, _ in _transfer(
                rdir, order_id, run_id, ln, catalog, emit):
            dest = "%s_%s.json" % (sender, cat)
            shutil.copyfile(os.path.join(rdir, sender, cat + ".json"),
                            os.path.join(fdir, dest))
            collected.append({"sender": sender, "category": cat,
                              "version": ver, "file": dest})
    with open(os.path.join(fdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"inputs": collected}, f, ensure_ascii=False, indent=1)
    emit({"ev": "final_ready", "inputs": len(collected)})
