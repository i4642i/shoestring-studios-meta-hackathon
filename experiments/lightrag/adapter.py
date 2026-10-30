"""LightRAG backend behind the stable graph.py interface.

Needs the LightRAG packages (requirements.txt, installed into .venv
by start_server.bat).
Config: experiments/lightrag/config.json (LLM + per-profile embeddings).
Storage (gitignored): experiments/lightrag/storage/<eid>/<profile>/.
LLM calls are logged with chars/seconds to llm_log.jsonl next to the storage.

Embedding profiles ("jetson" default, "local"): one index per profile,
never mixed. Active profile: data/settings.json wins, .env EMBED_PROFILE
is the default. The Jetson server only computes embeddings (read-only
API use); the token lives in .env EMBED_REMOTE_TOKEN and is never
logged, committed, or sent to the browser.
"""
import asyncio
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(HERE, "config.json")
STORAGE = os.path.join(HERE, "storage")
SETTINGS = os.path.join(ROOT, "data", "settings.json")

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME",
                      os.path.join(HERE, "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

PROFILES = ("local", "jetson")
QUERY_MODES = ("local", "global", "hybrid", "naive", "mix")
DEFAULT_JETSON_URL = "http://192.168.0.4:8790"
TOP_K_MIN, TOP_K_MAX = 5, 100
CHUNK_MIN, CHUNK_MAX = 64, 1024


def _read_settings_file():
    if not os.path.isfile(SETTINGS):
        return {}
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def clean_settings(d):
    """Validate a settings dict; return the cleaned subset. Raises RuntimeError."""
    out = {}
    if "embed_profile" in d:
        v = str(d["embed_profile"] or "").strip().lower()
        if v not in PROFILES:
            raise RuntimeError("profile must be local|jetson")
        out["embed_profile"] = v
    if "jetson_url" in d:
        v = str(d["jetson_url"] or "").strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise RuntimeError("jetson_url must start with http(s)://")
        out["jetson_url"] = v
    if "llm_model" in d:
        from agents._frame.runner import LLM_MODELS
        v = str(d["llm_model"] or "").strip()
        if v not in LLM_MODELS:
            raise RuntimeError("unknown llm_model: %r" % v)
        out["llm_model"] = v
    if "query_mode" in d:
        v = str(d["query_mode"] or "").strip().lower()
        if v not in QUERY_MODES:
            raise RuntimeError("query_mode must be one of %s"
                               % "|".join(QUERY_MODES))
        out["query_mode"] = v
    if "top_k" in d:
        try:
            v = int(d["top_k"])
        except (TypeError, ValueError):
            raise RuntimeError("top_k must be an integer")
        if not TOP_K_MIN <= v <= TOP_K_MAX:
            raise RuntimeError("top_k must be %d..%d"
                               % (TOP_K_MIN, TOP_K_MAX))
        out["top_k"] = v
    for k in ("chunk_local", "chunk_jetson"):
        if k in d:
            try:
                v = int(d[k])
            except (TypeError, ValueError):
                raise RuntimeError("%s must be an integer" % k)
            if not CHUNK_MIN <= v <= CHUNK_MAX:
                raise RuntimeError("%s must be %d..%d"
                                   % (k, CHUNK_MIN, CHUNK_MAX))
            out[k] = v
    return out
JETSON_DOWN = ("Jetson embed server not reachable at %s. "
               "It may be off or in parser mode.")

_RAGS = {}
_ST = {}


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def _read_dotenv():
    vals = {}
    p = os.path.join(ROOT, ".env")
    if not os.path.isfile(p):
        return vals
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip("'\"")
    return vals


def load_key(key_env=None):
    vals = _read_dotenv()
    if key_env:
        key = vals.get(key_env) or os.environ.get(key_env) or ""
        if not key:
            raise RuntimeError("no %s in repo .env" % key_env)
        return key
    key = vals.get("MODEL_API_KEY") or vals.get("META_API_KEY") or ""
    if not key:
        raise RuntimeError("no key in repo .env")
    return key


def embed_settings():
    """Active embedding profile: data/settings.json wins, .env are defaults."""
    prof, url = None, None
    if os.path.isfile(SETTINGS):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                d = json.load(f)
            prof = d.get("embed_profile") or None
            url = d.get("jetson_url") or None
        except ValueError:
            pass
    env = _read_dotenv()
    prof = (prof or env.get("EMBED_PROFILE")
            or os.environ.get("EMBED_PROFILE") or "jetson")
    prof = prof.strip().lower()
    if prof not in PROFILES:
        raise RuntimeError(
            "unknown embedding profile: %r (want local|jetson)" % prof)
    url = (url or env.get("JETSON_EMBED_URL")
           or os.environ.get("JETSON_EMBED_URL")
           or load_config().get("jetson_url")
           or DEFAULT_JETSON_URL).strip().rstrip("/")
    return {"profile": prof, "jetson_url": url}


def profile_config(profile=None):
    cfg = load_config()
    prof = (profile or embed_settings()["profile"]).strip().lower()
    if prof not in PROFILES:
        raise RuntimeError(
            "unknown embedding profile: %r (want local|jetson)" % prof)
    pcfg = (cfg.get("profiles") or {}).get(prof) or {}
    if not pcfg.get("model") or not pcfg.get("dim"):
        raise RuntimeError(
            "config.json has no usable profiles.%s entry" % prof)
    chunk = int(pcfg.get("chunk_size") or 256)
    over = _read_settings_file().get("chunk_" + prof)
    if over is not None:
        chunk = clean_settings({"chunk_" + prof: over})["chunk_" + prof]
    return {"profile": prof, "model": pcfg["model"],
            "dim": int(pcfg["dim"]), "chunk_size": chunk}


def llm_settings():
    """Effective LLM: settings choice wins, config.json is the default."""
    cfg = load_config()
    model = _read_settings_file().get("llm_model") or ""
    if model:
        from agents._frame.runner import LLM_MODELS, provider_of
        if model not in LLM_MODELS:
            raise RuntimeError("unknown llm_model: %r" % model)
        _, base_url, key_env = provider_of(model)
        return {"model": model, "base_url": base_url, "key_env": key_env}
    return {"model": cfg.get("llm_model", ""),
            "base_url": cfg.get("llm_base_url", ""),
            "key_env": cfg.get("llm_key_env", "")}


def query_settings():
    """Effective retrieval options: settings win, config/package default."""
    cfg = load_config()
    stored = _read_settings_file()
    mode = stored.get("query_mode") or cfg.get("mode") or "hybrid"
    if mode not in QUERY_MODES:
        raise RuntimeError("query_mode must be one of %s"
                           % "|".join(QUERY_MODES))
    top_k = stored.get("top_k", cfg.get("top_k", 40))
    try:
        top_k = int(top_k)
    except (TypeError, ValueError):
        raise RuntimeError("top_k must be an integer")
    if not TOP_K_MIN <= top_k <= TOP_K_MAX:
        raise RuntimeError("top_k must be %d..%d" % (TOP_K_MIN, TOP_K_MAX))
    return {"mode": mode, "top_k": top_k}


def resolved_settings():
    """All effective settings + problems list. Never raises (for the UI)."""
    probs = []
    try:
        st = embed_settings()
    except RuntimeError as e:
        st = {"profile": "jetson", "jetson_url": DEFAULT_JETSON_URL}
        probs.append(str(e))
    try:
        lm = llm_settings()["model"]
    except RuntimeError as e:
        lm = load_config().get("llm_model", "")
        probs.append(str(e))
    try:
        q = query_settings()
    except RuntimeError as e:
        q = {"mode": "hybrid", "top_k": 40}
        probs.append(str(e))
    chunks = {}
    for p, fb in (("local", 256), ("jetson", 512)):
        try:
            chunks[p] = profile_config(p)["chunk_size"]
        except RuntimeError as e:
            chunks[p] = fb
            probs.append(str(e))
    return {"profile": st["profile"], "jetson_url": st["jetson_url"],
            "llm_model": lm, "query_mode": q["mode"], "top_k": q["top_k"],
            "chunk_local": chunks["local"],
            "chunk_jetson": chunks["jetson"], "problems": probs}


def marker_path(agent_dir, profile):
    return os.path.join(agent_dir, "graph_index",
                        "lightrag_%s.json" % profile)


def read_marker(agent_dir, profile):
    p = marker_path(agent_dir, profile)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        return None


def _log_call(eid, profile, rec, wdir=None):
    d = wdir or os.path.join(STORAGE, eid, profile)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "llm_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _jetson_auth():
    """(base url, token) for the Jetson server. No I/O; raises if no token."""
    url = embed_settings()["jetson_url"]
    try:
        token = load_key("EMBED_REMOTE_TOKEN")
    except RuntimeError:
        raise RuntimeError("Jetson profile needs EMBED_REMOTE_TOKEN in "
                           "repo .env (token missing)")
    return url, token


def jetson_health(base=None, token=None):
    """GET /health. Raises JETSON_DOWN (never falls back silently)."""
    if base is None or token is None:
        base, token = _jetson_auth()
    req = urllib.request.Request(base + "/health", method="GET")
    req.add_header("X-Embed-Token", token)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        raise RuntimeError(JETSON_DOWN % base)
    if not isinstance(d, dict) or not d.get("ok"):
        raise RuntimeError(JETSON_DOWN % base)
    d["ms"] = round((time.time() - t0) * 1000)
    return d


def _batches(texts, n):
    return [texts[i:i + n] for i in range(0, len(texts), n)]


def jetson_embed(base, token, texts):
    """POST /embed in batches of 256. Vectors arrive normalized."""
    all_vecs = []
    for b in _batches(list(texts), 256):
        payload = json.dumps({"texts": b}).encode("utf-8")
        req = urllib.request.Request(base + "/embed", data=payload,
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Embed-Token", token)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:
            raise RuntimeError(JETSON_DOWN % base)
        vecs = d.get("vectors") if isinstance(d, dict) else None
        if not isinstance(vecs, list) or len(vecs) != len(b):
            got = len(vecs) if isinstance(vecs, list) else "no"
            raise RuntimeError("Jetson /embed returned %s vectors for %d "
                               "texts" % (got, len(b)))
        all_vecs.extend(vecs)
    import numpy as np
    return np.asarray(all_vecs, dtype=float)


def get_rag(eid, profile=None, working_dir=None):
    pcfg = profile_config(profile)
    prof = pcfg["profile"]
    key = (eid, prof, working_dir or "")
    if key in _RAGS:
        return _RAGS[key]
    try:
        from lightrag import LightRAG, QueryParam  # noqa: F401 (re-exported)
        from lightrag.llm.openai import openai_complete_if_cache
        from lightrag.utils import EmbeddingFunc
    except ImportError as e:
        raise RuntimeError(
            "LightRAG unavailable: %s. Fix: run start_server.bat "
            "(installs LightRAG into .venv), then build the index." % e)
    lm = llm_settings()
    llm_key = load_key(lm["key_env"])
    wdir = working_dir or os.path.join(STORAGE, eid, prof)
    os.makedirs(wdir, exist_ok=True)

    async def llm_func(prompt, system_prompt=None, history_messages=None, **kw):
        t0 = time.time()
        out = await openai_complete_if_cache(
            lm["model"], prompt,
            system_prompt=system_prompt, history_messages=history_messages or [],
            api_key=llm_key, base_url=lm["base_url"], **kw)
        _log_call(eid, prof, {"t": time.strftime("%H:%M:%S"),
                              "prompt_chars": len(prompt or ""),
                              "reply_chars": len(out or ""),
                              "seconds": round(time.time() - t0, 1)},
                  wdir if working_dir else None)
        return out

    if prof == "jetson":
        base, token = _jetson_auth()

        async def embed_func(texts):
            return jetson_embed(base, token, list(texts))
    else:
        mid = pcfg["model"]

        async def embed_func(texts):
            import numpy as np
            from sentence_transformers import SentenceTransformer
            if mid not in _ST:
                _ST[mid] = SentenceTransformer(mid, device="cpu")
            return np.asarray(_ST[mid].encode(
                texts, normalize_embeddings=True, show_progress_bar=False))

    rag = LightRAG(
        working_dir=wdir,
        llm_model_func=llm_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=pcfg["dim"],
            max_token_size=8192,
            func=embed_func),
        chunk_token_size=pcfg["chunk_size"],
    )
    _run(rag.initialize_storages())
    _RAGS[key] = rag
    return rag


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def index_agent(agent_dir, profile=None):
    pcfg = profile_config(profile)
    prof = pcfg["profile"]
    if prof == "jetson":
        jetson_health()  # fail fast, never silently local
    eid = os.path.basename(os.path.normpath(agent_dir))
    rag = get_rag(eid, prof)
    hb = os.path.join(agent_dir, "handbook")
    files = sorted(f for f in os.listdir(hb) if f.endswith(".md"))
    if not files:
        raise RuntimeError("nothing to index: no .md in handbook/")
    # One ainsert for the whole handbook: LightRAG's worker queue binds to
    # the first event loop, so a second _run(ainsert) dies with
    # "PriorityQueue is bound to a different event loop".
    parts = []
    for fn in files:
        with open(os.path.join(hb, fn), encoding="utf-8") as f:
            parts.append("# FILE: %s\n\n%s" % (fn, f.read()))
    t0 = time.time()
    _run(rag.ainsert("\n\n---\n\n".join(parts)))
    secs = time.time() - t0
    idx = os.path.join(agent_dir, "graph_index")
    os.makedirs(idx, exist_ok=True)
    lm = llm_settings()
    with open(marker_path(agent_dir, prof), "w", encoding="utf-8") as f:
        json.dump({"backend": "lightrag", "profile": prof,
                   "model": pcfg["model"], "dim": pcfg["dim"],
                   "chunk_size": pcfg["chunk_size"], "files": files,
                   "seconds": round(secs, 1),
                   "indexed_at": time.strftime("%Y-%m-%d %H:%M"),
                   "llm_model": lm["model"],
                   "llm_base_url": lm["base_url"]},
                  f, ensure_ascii=False, indent=1)
    calls = _count_log(eid, prof)
    return {"ok": True, "backend": "lightrag", "profile": prof,
            "model": pcfg["model"], "dim": pcfg["dim"],
            "files": len(files), "seconds": round(secs, 1),
            "llm_calls": calls}


def index_texts(text, log_id, profile, working_dir, entry_id=""):
    """Insert raw text into a LightRAG at an explicit working dir (PC
    indexes). One ainsert for the whole text; writes the index.json
    marker there, tracking indexed entry ids. Returns stats."""
    pcfg = profile_config(profile)
    prof = pcfg["profile"]
    if prof == "jetson":
        jetson_health()  # fail fast, never silently local
    rag = get_rag(log_id, prof, working_dir)
    t0 = time.time()
    _run(rag.ainsert(text))
    secs = time.time() - t0
    os.makedirs(working_dir, exist_ok=True)
    mp = os.path.join(working_dir, "index.json")
    entries, chars = [], 0
    if os.path.isfile(mp):
        try:
            with open(mp, encoding="utf-8") as f:
                old = json.load(f)
            entries = old.get("entries", [])
            chars = old.get("chars", 0)
        except ValueError:
            pass
    if entry_id and entry_id not in entries:
        entries.append(entry_id)
        chars += len(text)
    lm = llm_settings()
    with open(mp, "w", encoding="utf-8") as f:
        json.dump({"backend": "lightrag", "profile": prof,
                   "model": pcfg["model"], "dim": pcfg["dim"],
                   "chunk_size": pcfg["chunk_size"], "entries": entries,
                   "chars": chars, "seconds": round(secs, 1),
                   "indexed_at": time.strftime("%Y-%m-%d %H:%M"),
                   "llm_model": lm["model"],
                   "llm_base_url": lm["base_url"]},
                  f, ensure_ascii=False, indent=1)
    return {"ok": True, "profile": prof, "model": pcfg["model"],
            "dim": pcfg["dim"], "seconds": round(secs, 1),
            "chars": len(text)}


def query_agent(agent_dir, question, profile=None):
    pcfg = profile_config(profile)
    prof = pcfg["profile"]
    mark = read_marker(agent_dir, prof)
    if mark is None:
        raise RuntimeError("no LightRAG index for profile '%s'; build it "
                           "first" % prof)
    if mark.get("model") != pcfg["model"] or mark.get("dim") != pcfg["dim"]:
        raise RuntimeError(
            "LightRAG index was built with %s (%sd); active profile '%s' "
            "uses %s (%sd). Rebuild the index or switch profile."
            % (mark.get("model"), mark.get("dim"), prof,
               pcfg["model"], pcfg["dim"]))
    if prof == "jetson":
        jetson_health()  # fail fast, never silently local
    q = query_settings()
    eid = os.path.basename(os.path.normpath(agent_dir))
    rag = get_rag(eid, prof)  # raises "LightRAG unavailable" when unimportable
    from lightrag import QueryParam
    out = _run(rag.aquery(question, param=QueryParam(mode=q["mode"],
                                                    top_k=q["top_k"])))
    return {"mode": "lightrag", "profile": prof, "model": pcfg["model"],
            "dim": pcfg["dim"], "query_mode": q["mode"], "top_k": q["top_k"],
            "answer": str(out)}


def _count_log(eid, profile):
    p = os.path.join(STORAGE, eid, profile, "llm_log.jsonl")
    if not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as f:
        return sum(1 for _ in f)
