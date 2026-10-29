"""Knowledge-graph interface. One interface, two swappable backends:

lite (default): stdlib-only keyword/structure index over handbook/*.md.
lightrag: experiment backend (experiments/lightrag, separate venv).

RAG_BACKEND env selects ("lite" default). Server and tools only ever call
index_corpus / query / summarize / get_status below.
"""
import importlib.util
import json
import os
import re
import time
import xml.etree.ElementTree as ET

STATUS_NOT_INDEXED = "not_indexed"
STATUS_INDEXED = "indexed"

WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']{2,}")
ENT_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
STOP_WORDS = frozenset(
    "the and for are but not you all any can had her was one our out day "
    "get has him his how its may new now old see two way who did its with "
    "that this from they have what each every when which while".split())
STOP_ENT = frozenset(["The", "This", "That", "Each", "Every", "What", "When"])


def get_status(agent_dir):
    """Honest status for the Crew tab. Never fakes an index."""
    idx = os.path.join(agent_dir, "graph_index")
    hb = os.path.join(agent_dir, "handbook")
    staged = sorted(f for f in os.listdir(hb) if f.endswith(".md")) \
        if os.path.isdir(hb) else []
    if os.path.isdir(idx):
        return {"state": STATUS_INDEXED, "path": idx, "staged": staged}
    return {"state": STATUS_NOT_INDEXED, "staged": staged,
            "reason": "no index yet; index handbook/ first"}


def _backend():
    return os.environ.get("RAG_BACKEND", "lite").strip().lower() or "lite"


def _adapter():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(
        here, "..", "..", "experiments", "lightrag", "adapter.py"))
    spec = importlib.util.spec_from_file_location("rag_lightrag_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("lightrag adapter missing: %s" % path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        raise RuntimeError("lightrag backend needs the experiment venv: %s" % e)
    return mod


def index_corpus(agent_dir, backend=None):
    be = (backend or _backend()).strip().lower()
    if be == "lightrag":
        return _adapter().index_agent(agent_dir)
    if be != "lite":
        raise ValueError("unknown RAG backend: %r" % be)
    return _index_lite(agent_dir)


def query(agent_dir, question, top_k=5):
    be = _backend()
    if be == "lightrag":
        return _adapter().query_agent(agent_dir, question)
    if be != "lite":
        raise ValueError("unknown RAG backend: %r" % be)
    return _query_lite(agent_dir, question, top_k)


def summarize(agent_dir):
    """Learning-result summary for the graph panel.

    Contract: entities [{name, degree}], relations [{source, target}],
    communities [{title, size}]."""
    idx = os.path.join(agent_dir, "graph_index")
    lite = os.path.join(idx, "lite.json")
    if os.path.isfile(lite):
        with open(lite, encoding="utf-8") as f:
            d = json.load(f)
        return {"entities": d.get("entities", []),
                "relations": d.get("relations", []),
                "communities": d.get("communities", []),
                "note": "lite backend (%d chunks)" % len(d.get("chunks", []))}
    if os.path.isfile(os.path.join(idx, "lightrag.json")):
        return {"entities": [], "relations": [], "communities": [],
                "note": "lightrag backend: answers via query only"}
    return {"entities": [], "relations": [], "communities": [],
            "note": "no index yet"}


def _trim(s, n=600):
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def map_lightrag(agent_dir):
    """Full LightRAG knowledge map for the Crew tab. Stdlib only.

    Reads experiments/lightrag/storage/<eid>/ directly (no lightrag
    import, so the main server can serve it). Returns None when no
    LightRAG storage exists for this employee.
    """
    eid = os.path.basename(os.path.normpath(agent_dir))
    here = os.path.dirname(os.path.abspath(__file__))
    store = os.path.normpath(os.path.join(
        here, "..", "..", "experiments", "lightrag", "storage", eid))
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
    marker = os.path.join(agent_dir, "graph_index", "lightrag.json")
    marked_llm = {}
    if os.path.isfile(marker):
        try:
            with open(marker, encoding="utf-8") as f:
                m = json.load(f)
            built["files"] = m.get("files", [])
            built["index_seconds"] = m.get("seconds", 0.0)
            marked_llm = {k: m[k] for k in ("llm_model", "llm_base_url")
                          if m.get(k)}
        except ValueError:
            pass
    cfg_path = os.path.normpath(os.path.join(
        here, "..", "..", "experiments", "lightrag", "config.json"))
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            # Marker wins for the LLM: it records what actually built
            # this index, while the config may have moved on.
            built["llm_model"] = marked_llm.get("llm_model",
                                                cfg.get("llm_model", ""))
            built["llm_base_url"] = marked_llm.get("llm_base_url",
                                                  cfg.get("llm_base_url", ""))
            built["embedding_model"] = cfg.get("embedding_model", "")
            built["embedding_dim"] = cfg.get("embedding_dim", 0)
            built["mode"] = cfg.get("mode", "")
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
    built["indexed_at"] = time.strftime(
        "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(gml)))
    return {"available": True, "built": built, "entities": entities,
            "relations": relations}


def _chunks_of(text, fname):
    """Split markdown into (heading, body) sections in source order."""
    chunks, heading, buf = [], "intro", []
    for ln in text.splitlines():
        if ln.startswith("#"):
            if buf or heading != "intro":
                chunks.append((heading, "\n".join(buf).strip()))
            heading = ln.lstrip("#").strip() or "untitled"
            buf = []
        else:
            buf.append(ln)
    if buf or heading != "intro":
        chunks.append((heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in chunks if b]


def _entities(text, heading):
    found = set()
    for m in ENT_RE.finditer(text):
        name = " ".join(m.group(1).split())
        if " " in name and name.split()[0] not in STOP_ENT:
            found.add(name)
    if len(heading.split()) >= 1 and heading not in ("intro", "untitled"):
        found.add(heading)
    return found


def _index_lite(agent_dir):
    hb = os.path.join(agent_dir, "handbook")
    files = sorted(f for f in os.listdir(hb) if f.endswith(".md")) \
        if os.path.isdir(hb) else []
    if not files:
        raise RuntimeError("nothing to index: no .md in handbook/")
    chunks, in_chunk = [], {}
    for fname in files:
        with open(os.path.join(hb, fname), encoding="utf-8") as f:
            for i, (heading, body) in enumerate(_chunks_of(f.read(), fname)):
                cid = "%s#%d" % (fname, i)
                ents = sorted(_entities(heading + "\n" + body, heading))
                chunks.append({"id": cid, "file": fname,
                               "heading": heading, "text": body})
                in_chunk[cid] = ents
    entities = {}
    for cid, ents in in_chunk.items():
        for e in ents:
            entities.setdefault(e, set()).add(cid)
    ent_list = [{"name": e, "degree": len(c)} for e, c in entities.items()]
    ent_list.sort(key=lambda d: (-d["degree"], d["name"]))
    rels, seen_rel = [], set()
    for ents in in_chunk.values():
        for i in range(len(ents)):
            for j in range(i + 1, min(len(ents), i + 8)):
                a, b = sorted((ents[i], ents[j]))
                if (a, b) not in seen_rel:
                    seen_rel.add((a, b))
                    rels.append({"source": a, "target": b})
    parent = {e["name"]: e["name"] for e in ent_list}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in rels:
        ra, rb = find(r["source"]), find(r["target"])
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for e in ent_list:
        groups.setdefault(find(e["name"]), []).append(e["name"])
    degree = {e["name"]: e["degree"] for e in ent_list}
    comms = [{"title": max(m, key=lambda n: (degree[n], n)), "size": len(m)}
             for m in groups.values()]
    comms.sort(key=lambda d: (-d["size"], d["title"]))
    idx = os.path.join(agent_dir, "graph_index")
    os.makedirs(idx, exist_ok=True)
    with open(os.path.join(idx, "lite.json"), "w", encoding="utf-8") as f:
        json.dump({"backend": "lite", "files": files, "chunks": chunks,
                   "entities": ent_list, "relations": rels,
                   "communities": comms}, f, ensure_ascii=False, indent=1)
    return {"ok": True, "backend": "lite", "files": len(files),
            "chunks": len(chunks), "entities": len(ent_list)}


def _query_lite(agent_dir, question, top_k=5):
    lite = os.path.join(agent_dir, "graph_index", "lite.json")
    if not os.path.isfile(lite):
        raise RuntimeError("no lite index; run index_corpus first")
    with open(lite, encoding="utf-8") as f:
        d = json.load(f)
    words = {w.lower() for w in WORD_RE.findall(question or "")}
    words = {w for w in words if w not in STOP_WORDS}
    scored = []
    for c in d["chunks"]:
        hay = (c["heading"] + "\n" + c["text"]).lower()
        hits = sorted(w for w in words if w in hay)
        if hits:
            scored.append((len(hits), c["id"], c["heading"], c["text"], hits))
    scored.sort(key=lambda t: (-t[0], t[1]))
    out = [{"chunk": cid, "heading": h, "text": t, "hits": hits}
           for _, cid, h, t, hits in scored[:max(1, top_k)]]
    matched = sorted({e["name"] for e in d["entities"]
                      if any(w in e["name"].lower() for w in words)})
    return {"mode": "lite", "chunks": out, "entities": matched}
