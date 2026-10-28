"""LightRAG backend behind the stable graph.py interface.

Only imported when RAG_BACKEND=lightrag (needs .venv-lightrag).
Config: experiments/lightrag/config.json. Storage (gitignored):
experiments/lightrag/storage/<eid>/. LLM calls are logged with
chars/seconds to llm_log.jsonl next to the storage.
"""
import asyncio
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(HERE, "config.json")
STORAGE = os.path.join(HERE, "storage")

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME",
                      os.path.join(HERE, "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

_RAGS = {}
_ST = {}


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def load_key():
    vals = {}
    with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip("'\"")
    key = vals.get("MODEL_API_KEY") or vals.get("META_API_KEY") or ""
    if not key:
        raise RuntimeError("no key in repo .env")
    return key


def _log_call(eid, rec):
    os.makedirs(os.path.join(STORAGE, eid), exist_ok=True)
    with open(os.path.join(STORAGE, eid, "llm_log.jsonl"),
              "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def get_rag(eid):
    if eid in _RAGS:
        return _RAGS[eid]
    from lightrag import LightRAG, QueryParam  # noqa: F401 (re-exported)
    from lightrag.llm.openai import openai_complete_if_cache
    from lightrag.utils import EmbeddingFunc
    cfg = load_config()
    key = load_key()
    wdir = os.path.join(STORAGE, eid)
    os.makedirs(wdir, exist_ok=True)

    async def llm_func(prompt, system_prompt=None, history_messages=None, **kw):
        t0 = time.time()
        out = await openai_complete_if_cache(
            cfg["llm_model"], prompt,
            system_prompt=system_prompt, history_messages=history_messages or [],
            api_key=key, base_url=cfg["llm_base_url"], **kw)
        _log_call(eid, {"t": time.strftime("%H:%M:%S"),
                        "prompt_chars": len(prompt or ""),
                        "reply_chars": len(out or ""),
                        "seconds": round(time.time() - t0, 1)})
        return out

    async def embed_func(texts):
        import numpy as np
        from sentence_transformers import SentenceTransformer
        mid = cfg["embedding_model"]
        if mid not in _ST:
            _ST[mid] = SentenceTransformer(mid, device="cpu")
        return np.asarray(_ST[mid].encode(
            texts, normalize_embeddings=True, show_progress_bar=False))

    rag = LightRAG(
        working_dir=wdir,
        llm_model_func=llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=cfg["embedding_dim"],
            max_token_size=8192,
            func=embed_func),
    )
    _RAGS[eid] = rag
    return rag


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def index_agent(agent_dir):
    eid = os.path.basename(os.path.normpath(agent_dir))
    rag = get_rag(eid)
    hb = os.path.join(agent_dir, "handbook")
    files = sorted(f for f in os.listdir(hb) if f.endswith(".md"))
    if not files:
        raise RuntimeError("nothing to index: no .md in handbook/")
    t0 = time.time()
    for fn in files:
        with open(os.path.join(hb, fn), encoding="utf-8") as f:
            _run(rag.ainsert(f.read()))
    secs = time.time() - t0
    idx = os.path.join(agent_dir, "graph_index")
    os.makedirs(idx, exist_ok=True)
    with open(os.path.join(idx, "lightrag.json"), "w", encoding="utf-8") as f:
        json.dump({"backend": "lightrag", "files": files,
                   "seconds": round(secs, 1)}, f, ensure_ascii=False, indent=1)
    calls = _count_log(eid)
    return {"ok": True, "backend": "lightrag", "files": len(files),
            "seconds": round(secs, 1), "llm_calls": calls}


def query_agent(agent_dir, question):
    from lightrag import QueryParam
    eid = os.path.basename(os.path.normpath(agent_dir))
    rag = get_rag(eid)
    cfg = load_config()
    out = _run(rag.aquery(question, param=QueryParam(mode=cfg.get("mode", "hybrid"))))
    return {"mode": "lightrag", "answer": str(out)}


def _count_log(eid):
    p = os.path.join(STORAGE, eid, "llm_log.jsonl")
    if not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as f:
        return sum(1 for _ in f)
