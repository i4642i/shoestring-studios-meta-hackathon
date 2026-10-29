"""Knowledge-graph interface. LightRAG only.

The server, tools, and run_index only ever call
index_corpus / query / summarize / get_status below.
Needs the LightRAG packages (requirements.txt, installed into .venv
by start_server.bat). When LightRAG is missing or broken, every call
below raises RuntimeError("LightRAG unavailable: ...") — results are
never faked.
"""
import importlib.util
import json
import os
import time
import xml.etree.ElementTree as ET

STATUS_NOT_INDEXED = "not_indexed"
STATUS_INDEXED = "indexed"

FIX_HINT = ("Fix: run start_server.bat (installs LightRAG into .venv), "
            "then build the index.")


_MOD = None


def _adapter():
    global _MOD
    if _MOD is not None:
        return _MOD
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(
        here, "..", "..", "experiments", "lightrag", "adapter.py"))
    spec = importlib.util.spec_from_file_location("rag_lightrag_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("LightRAG unavailable: adapter missing: %s. %s"
                           % (path, FIX_HINT))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        raise RuntimeError("LightRAG unavailable: %s. %s" % (e, FIX_HINT))
    _MOD = mod
    return mod


def get_status(agent_dir):
    """Honest status for the Crew tab. Never fakes an index."""
    idx = os.path.join(agent_dir, "graph_index")
    hb = os.path.join(agent_dir, "handbook")
    staged = sorted(f for f in os.listdir(hb) if f.endswith(".md")) \
        if os.path.isdir(hb) else []
    prof = _adapter().embed_settings()["profile"]
    marker = os.path.join(idx, "lightrag_%s.json" % prof)
    if os.path.isfile(marker):
        return {"state": STATUS_INDEXED, "path": idx, "staged": staged,
                "profile": prof}
    return {"state": STATUS_NOT_INDEXED, "staged": staged, "profile": prof,
            "reason": "no LightRAG index for profile '%s'; "
                      "index handbook/ first" % prof}


def index_corpus(agent_dir, profile=None):
    return _adapter().index_agent(agent_dir, profile)


def query(agent_dir, question, profile=None):
    return _adapter().query_agent(agent_dir, question, profile)


def summarize(agent_dir):
    """Learning-result summary for the graph panel.

    Contract: entities [{name, degree}], relations [{source, target}],
    communities []. Served from the LightRAG map (no second index).
    """
    m = map_lightrag(agent_dir)
    if m is None:
        st = get_status(agent_dir)
        note = ("LightRAG unavailable: no map storage yet. %s" % FIX_HINT
                if st["state"] == STATUS_INDEXED else "no index yet")
        return {"entities": [], "relations": [], "communities": [],
                "note": note}
    return {"entities": [{"name": e["name"], "degree": e.get("degree", 0)}
                         for e in m["entities"]],
            "relations": [{"source": r["source"], "target": r["target"]}
                          for r in m["relations"]],
            "communities": [],
            "note": "lightrag (%d entities, %d relations)" % (
                len(m["entities"]), len(m["relations"]))}


def _trim(s, n=600):
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def map_lightrag(agent_dir, profile=None):
    """Full LightRAG knowledge map for the Crew tab. Stdlib only.

    Reads experiments/lightrag/storage/<eid>/<profile>/ directly (no
    lightrag import, so the main server can serve it). Returns None when
    no LightRAG storage exists for this employee and profile.
    """
    mod = _adapter()
    prof = profile or mod.embed_settings()["profile"]
    eid = os.path.basename(os.path.normpath(agent_dir))
    here = os.path.dirname(os.path.abspath(__file__))
    store = os.path.normpath(os.path.join(
        here, "..", "..", "experiments", "lightrag", "storage", eid, prof))
    gml = os.path.join(store, "graph_chunk_entity_relation.graphml")
    if not os.path.isfile(gml):
        return None
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    try:
        root = ET.parse(gml).getroot()
    except ET.ParseError:
        return None
    key_of = {}
    for k in root.findall(ns + "key"):
        key_of.setdefault(k.get("attr.name"), k.get("id"))
    g = root.find(ns + "graph")
    if g is None:
        return None

    def data(el):
        out = {}
        for d in el.findall(ns + "data"):
            out[d.get("key")] = (d.text or "").strip()
        return out

    entities = []
    for n in g.findall(ns + "node"):
        dd = data(n)
        name = dd.get(key_of.get("entity_id", ""), "") or n.get("id", "")
        entities.append({
            "name": name,
            "type": dd.get(key_of.get("entity_type", ""), ""),
            "description": _trim(dd.get(key_of.get("description", ""), "")),
            "source": dd.get(key_of.get("source_id", ""), ""),
        })
    relations = []
    for e in g.findall(ns + "edge"):
        dd = data(e)
        try:
            weight = float(dd.get(key_of.get("weight", ""), "1") or 1)
        except ValueError:
            weight = 1.0
        relations.append({
            "source": e.get("source", ""),
            "target": e.get("target", ""),
            "weight": weight,
            "description": _trim(dd.get(key_of.get("description", ""), "")),
            "keywords": dd.get(key_of.get("keywords", ""), ""),
            "source_chunk": dd.get(key_of.get("source_id", ""), ""),
        })
    names = {e["name"] for e in entities}
    relations = [r for r in relations
                 if r["source"] in names and r["target"] in names]
    degree = {e["name"]: 0 for e in entities}
    for r in relations:
        degree[r["source"]] += 1
        degree[r["target"]] += 1
    for e in entities:
        e["degree"] = degree[e["name"]]
    entities.sort(key=lambda d: (-d["degree"], d["name"]))
    relations.sort(key=lambda d: (-d["weight"], d["source"], d["target"]))

    built = {"files": [], "index_seconds": 0.0}
    mark = mod.read_marker(agent_dir, prof)
    # Marker wins: it records what actually built this index, while the
    # config may have moved on. Config is fallback for legacy indexes.
    pcfg = mod.profile_config(prof)
    if mark:
        built["files"] = mark.get("files", [])
        built["index_seconds"] = mark.get("seconds", 0.0)
        built["profile"] = mark.get("profile", prof)
        built["model"] = mark.get("model", "")
        built["dim"] = mark.get("dim", 0)
        built["chunk_size"] = mark.get("chunk_size", 0)
        built["indexed_at"] = mark.get("indexed_at", "")
        marked_llm = {k: mark[k] for k in ("llm_model", "llm_base_url")
                      if mark.get(k)}
    else:
        built["profile"] = prof
        built["model"] = pcfg["model"]
        built["dim"] = pcfg["dim"]
        built["chunk_size"] = pcfg["chunk_size"]
        marked_llm = {}
    eff = mod.resolved_settings()
    cfg_path = os.path.normpath(os.path.join(
        here, "..", "..", "experiments", "lightrag", "config.json"))
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            built["llm_model"] = marked_llm.get("llm_model",
                                                eff["llm_model"])
            built["llm_base_url"] = marked_llm.get(
                "llm_base_url", cfg.get("llm_base_url", ""))
            built["embedding_model"] = built["model"]
            built["embedding_dim"] = built["dim"]
            built["mode"] = eff["query_mode"]
            built["top_k"] = eff["top_k"]
        except ValueError:
            pass
    calls, prompt_chars, reply_chars, llm_seconds = 0, 0, 0, 0.0
    log_path = os.path.join(store, "llm_log.jsonl")
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8") as f:
            for ln in f.read().splitlines():
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                calls += 1
                prompt_chars += rec.get("prompt_chars", 0) or 0
                reply_chars += rec.get("reply_chars", 0) or 0
                llm_seconds += rec.get("seconds", 0.0) or 0.0
    built["llm_calls"] = calls
    built["prompt_chars"] = prompt_chars
    built["reply_chars"] = reply_chars
    built["llm_seconds"] = round(llm_seconds, 1)
    if not built.get("indexed_at"):
        built["indexed_at"] = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(gml)))
    return {"available": True, "built": built, "entities": entities,
            "relations": relations}
