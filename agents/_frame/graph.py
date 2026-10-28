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
