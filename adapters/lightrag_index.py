"""LightRAG index adapter for Nextop Agentic Workers: an example project adapter.
Copy it into a project as adapters/lightrag_index.py.

Needs: lightrag-hku, sentence-transformers (local embeddings), numpy. The core never imports this.

project.json
  "adapters": {"index": {"lightrag": {
      "class": "adapters.lightrag_index:LightRAGIndex",
      "options": {
        "base_url": "https://api.meta.ai/v1", "key_env": "MODEL_API_KEY", "env_file": ".env",
        "model": "muse-spark-1.3",                    # LLM that extracts entities and keywords
        "embed_model": "BAAI/bge-m3", "embed_dim": 1024, # runs on this computer (CPU)
        "mode": "mix", "top_k": 20, "chunk_top_k": 10,
        "gleaning": 0, "llm_async": 8, "chunk_tokens": 2048
      }}}}

How it keeps the Index contract
  - Every text part of an item is one LightRAG document whose id and file path are
    '<item address>#<part>' (an item without text parts: its index_text under the item address).
    chunk_tokens is large enough that a part is normally one chunk, so query() returns the
    part's original text under its address.
  - build()    a new index in workdir; the LLM cache in cache_dir is copied in first and copied
               back after, so items seen before cost no LLM calls.
  - assemble() a new index for fewer items, from the cache: no LLM calls (embeddings are
               computed again on this computer).
  - insert()/delete() change an existing index (domain knowledge quick adding).
  - query()    retrieval only (aquery_data); no answer is generated. Passages carry addresses.

Inside one process, LightRAG keeps data in memory per "workspace" name. Each index folder
gets its own workspace id (stored in workdir/nextop_lightrag.json); a copied folder that
meets its original in the same process is given a new id. All LightRAG work runs on one
background event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import re
import shutil
import threading
import time
import uuid
from typing import Any

from nextop.adapters import AdapterError, IndexStats, Passage

MARKER = "nextop_lightrag.json"
_CHUNK_SUFFIX = re.compile(r"-chunk-\d+$")
logging.getLogger("lightrag").setLevel(logging.WARNING)
CACHE_FILE = "kv_store_llm_response_cache.json"


# ---------------------------------------------------------------------------
# One event loop for all LightRAG work in this process
# ---------------------------------------------------------------------------
_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def _loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            _LOOP = asyncio.new_event_loop()
            threading.Thread(target=_LOOP.run_forever, name="nextop-lightrag", daemon=True).start()
        return _LOOP


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop()).result()


DEVICES = ("auto", "cpu", "cuda", "mps")


def pick_device(device: str = "auto") -> str:
    """auto: an NVIDIA GPU (cuda) when torch sees one, then Apple GPU (mps), else the CPU.
    A GPU needs the CUDA build of torch that fits the GPU driver (the CPU build never sees a GPU)."""
    if device not in DEVICES and not device.startswith("cuda:"):
        raise AdapterError(f"device must be one of {DEVICES} or cuda:<n> (got {device!r})")
    if device != "auto":
        return device
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    return "mps" if mps is not None and mps.is_available() else "cpu"


class LocalEmbed:
    """sentence-transformers on this computer: CPU, or a GPU (device "auto" picks one when present)."""

    _models: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, model: str = "BAAI/bge-m3", dim: int | None = None, cache_folder: str | None = None,
                 device: str = "auto", batch: int = 32):
        self.model, self.cache_folder = model, cache_folder
        self.device_setting = device
        self.device = pick_device(device)             # what is really used (shown by the studio TEST)
        self.batch = max(1, int(batch))
        self.dim = int(dim) if dim else None          # None: found out from the model on first use

    @property
    def identity(self) -> str:
        return f"LocalEmbed {self.model}"

    def _get(self):
        with self._lock:
            key = (self.model, self.device)
            m = self._models.get(key)
            if m is None:
                from sentence_transformers import SentenceTransformer
                m = SentenceTransformer(self.model, device=self.device, cache_folder=self.cache_folder)
                self._models[key] = m
            return m

    def embed(self, texts: list[str]):
        import numpy as np
        return np.asarray(self._get().encode(list(texts), batch_size=self.batch, normalize_embeddings=True,
                                             show_progress_bar=False))

    def health(self) -> dict:
        """For the studio TEST button: where it runs."""
        return {"device": self.device, "device_setting": self.device_setting}


class LightRAGIndex:
    def __init__(self, base_url: str, model: str, key_env: str = "MODEL_API_KEY", env_file: str | None = None,
                 embed: Any = None, embed_model: str = "BAAI/bge-m3", embed_dim: int | None = None,
                 embed_cache: str | None = None,
                 mode: str = "mix", top_k: int = 20, chunk_top_k: int = 10, gleaning: int = 0,
                 llm_async: int = 8, chunk_tokens: int = 2048, timeout: float = 180.0, llm=None):
        """embed: the name of an entry in project.json adapters.embed (any embedding: local, a LAN
        server, an API), or an embedding object. Without it, embed_model runs on this computer."""
        if llm is None:
            from nextop.adapters.openai_compat import OpenAICompatLLM
            llm = OpenAICompatLLM(base_url=base_url, key_env=key_env, env_file=env_file, timeout=timeout)
        self.llm, self.model = llm, model
        self.embed_name = embed if isinstance(embed, str) else None
        self.embedder = None if self.embed_name else (embed or LocalEmbed(embed_model, embed_dim, embed_cache))
        self._embed_dim = int(embed_dim) if embed_dim else None
        self.mode, self.top_k, self.chunk_top_k = mode, int(top_k), int(chunk_top_k)
        self.gleaning, self.llm_async, self.chunk_tokens = int(gleaning), int(llm_async), int(chunk_tokens)
        self._rags: dict[str, Any] = {}           # resolved workdir -> LightRAG
        self._owners: dict[str, str] = {}         # workspace id -> resolved workdir
        self._lock = threading.Lock()
        self._calls = 0

    def bind(self, adapters: dict) -> None:
        """Called by the framework after all adapters are built: find the named embedding."""
        if self.embed_name:
            got = (adapters.get("embed") or {}).get(self.embed_name)
            if got is None:
                raise AdapterError(f"embedding '{self.embed_name}' is not in project.json adapters.embed")
            self.embedder = got

    @property
    def embed_identity(self) -> str:
        e = self._embedder()
        return str(getattr(e, "identity", None) or getattr(e, "model", None) or type(e).__name__)

    def _embedder(self):
        if self.embedder is None:
            raise AdapterError(f"embedding '{self.embed_name}' is not bound (build adapters with the framework)")
        return self.embedder

    @property
    def embed_dim(self) -> int:
        """Vector size: given, or asked from the embedding once."""
        if self._embed_dim is None:
            d = getattr(self._embedder(), "dim", None)
            if not d:
                d = len(list(self._embedder().embed(["dimension check"]))[0])
            self._embed_dim = int(d)
        return self._embed_dim

    def _guard(self, workdir: str) -> None:
        """Refuse an index built with another embedding: vectors would not match."""
        mp = pathlib.Path(workdir) / MARKER
        if not mp.exists():
            return
        data = json.loads(mp.read_text(encoding="utf-8"))
        old_id, old_dim = data.get("embed"), data.get("embed_dim")
        if (old_id and old_id != self.embed_identity) or (old_dim and int(old_dim) != self.embed_dim):
            raise AdapterError(f"this index was built with embedding '{old_id}' ({old_dim} dims) but the setting "
                               f"is now '{self.embed_identity}' ({self.embed_dim} dims); build the index again")

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _docs(items) -> dict[str, str]:
        """{'<address>#<part>': text} for every text part ({address: text} for items without)."""
        out = {}
        for it in items:
            parts = {k: v for k, v in it.parts.items() if isinstance(v, str) and v.strip()}
            if parts:
                out.update({f"{it.address}#{k}": v for k, v in parts.items()})
            else:
                text = it.meta.get("text") or it.title
                if text:
                    out[it.address] = text
        return out

    def _workspace(self, workdir: pathlib.Path) -> str:
        mp = workdir / MARKER
        data = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
        ws = data.get("workspace")
        key = str(workdir.resolve())
        if ws and self._owners.get(ws, key) != key:        # a copy of a folder already open here
            new = "w" + uuid.uuid4().hex[:12]
            if (workdir / ws).exists():
                (workdir / ws).rename(workdir / new)
            ws = new
        if not ws:
            ws = "w" + uuid.uuid4().hex[:12]
        if data.get("workspace") != ws:
            data["workspace"] = ws
            workdir.mkdir(parents=True, exist_ok=True)
            mp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        self._owners[ws] = key
        return ws

    def _rag(self, workdir: str):
        wd = pathlib.Path(workdir)
        key = str(wd.resolve())
        with self._lock:
            if key in self._rags:
                return self._rags[key]
            from lightrag import LightRAG
            from lightrag.utils import EmbeddingFunc
            for name in ("lightrag", "nano-vectordb"):      # lightrag sets INFO when it is imported
                logging.getLogger(name).setLevel(logging.WARNING)
            ws = self._workspace(wd)
            me = self

            async def llm_func(prompt, system_prompt=None, history_messages=None, **kw):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages += list(history_messages or [])
                messages.append({"role": "user", "content": prompt})
                me._calls += 1
                reply = await asyncio.to_thread(me.llm.chat, me.model, messages, None)
                return reply.text or ""

            async def embed_func(texts):
                import numpy as np
                return np.asarray(await asyncio.to_thread(me._embedder().embed, list(texts)), dtype=float)

            async def make():
                rag = LightRAG(working_dir=str(wd), workspace=ws, llm_model_func=llm_func,
                               embedding_func=EmbeddingFunc(embedding_dim=self.embed_dim, max_token_size=8192,
                                                            func=embed_func),
                               chunk_token_size=self.chunk_tokens, entity_extract_max_gleaning=self.gleaning,
                               llm_model_max_async=self.llm_async)
                await rag.initialize_storages()
                logging.getLogger("lightrag").setLevel(logging.WARNING)   # LightRAG resets it on start
                return rag
            rag = _run(make())
            self._rags[key] = rag
            return rag

    def _close(self, workdir: str) -> None:
        key = str(pathlib.Path(workdir).resolve())
        with self._lock:
            rag = self._rags.pop(key, None)
        if rag is not None:
            _run(rag.finalize_storages())

    def _cache_path(self, workdir: str) -> pathlib.Path:
        wd = pathlib.Path(workdir)
        return wd / self._workspace(wd) / CACHE_FILE

    @staticmethod
    def _merge_cache(src: pathlib.Path, dst: pathlib.Path) -> None:
        if not src.exists():
            return
        data = json.loads(src.read_text(encoding="utf-8") or "{}")
        if dst.exists():
            old = json.loads(dst.read_text(encoding="utf-8") or "{}")
            old.update(data)
            data = old
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _insert_docs(self, workdir: str, docs: dict[str, str], on_progress=None, batch: int = 8) -> None:
        rag = self._rag(workdir)
        keys = list(docs)
        total = len(keys)
        for i in range(0, total, batch):
            ids = keys[i:i + batch]
            _run(rag.ainsert([docs[k] for k in ids], ids=ids, file_paths=ids))
            if on_progress:
                on_progress(min(i + batch, total), total)
        if on_progress and not total:
            on_progress(0, 0)

    def _record(self, workdir: str, docs: dict[str, str], replace: bool) -> None:
        mp = pathlib.Path(workdir) / MARKER
        data = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
        old = {} if replace else dict(data.get("docs", {}))
        for d in docs:
            old.setdefault(d.split("#", 1)[0], [])
            if d not in old[d.split("#", 1)[0]]:
                old[d.split("#", 1)[0]].append(d)
        data.update(docs=old, model=self.model, embed=self.embed_identity, embed_dim=self.embed_dim,
                    updated=time.strftime("%Y-%m-%d %H:%M:%S"))
        mp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------ contract
    def _fresh(self, workdir: str, items, cache_dir: str, on_progress=None) -> IndexStats:
        t0, before = time.time(), self._calls
        self._close(workdir)
        wd = pathlib.Path(workdir)
        if wd.exists():
            shutil.rmtree(wd)
        wd.mkdir(parents=True)
        cache = pathlib.Path(cache_dir) / CACHE_FILE
        self._merge_cache(cache, self._cache_path(workdir))
        docs = self._docs(items)
        self._insert_docs(workdir, docs, on_progress)
        self._record(workdir, docs, replace=True)
        _run(self._rag(workdir).llm_response_cache.index_done_callback())
        self._merge_cache(self._cache_path(workdir), cache)
        return IndexStats(items=len(items), llm_calls=self._calls - before, seconds=time.time() - t0)

    def build(self, workdir: str, items, cache_dir: str, on_progress=None) -> IndexStats:
        return self._fresh(workdir, items, cache_dir, on_progress)

    def assemble(self, workdir: str, items, cache_dir: str) -> IndexStats:
        return self._fresh(workdir, items, cache_dir)

    def insert(self, workdir: str, items, cache_dir: str, on_progress=None) -> IndexStats:
        self._guard(workdir)
        t0, before = time.time(), self._calls
        cache = pathlib.Path(cache_dir) / CACHE_FILE
        self._merge_cache(cache, self._cache_path(workdir))
        self._close(workdir)                      # reopen so the merged cache is read
        docs = self._docs(items)
        self.delete(workdir, [it.address for it in items])   # an update replaces the old parts
        self._insert_docs(workdir, docs, on_progress)
        self._record(workdir, docs, replace=False)
        _run(self._rag(workdir).llm_response_cache.index_done_callback())
        self._merge_cache(self._cache_path(workdir), cache)
        return IndexStats(items=len(items), llm_calls=self._calls - before, seconds=time.time() - t0)

    def delete(self, workdir: str, item_addresses) -> None:
        mp = pathlib.Path(workdir) / MARKER
        if not mp.exists():
            return
        data = json.loads(mp.read_text(encoding="utf-8"))
        known = data.get("docs", {})
        gone = [a for a in item_addresses if a in known]
        if not gone:
            return
        self._guard(workdir)
        rag = self._rag(workdir)
        for a in gone:
            for doc_id in known.pop(a):
                _run(rag.adelete_by_doc_id(doc_id))
        data["docs"] = known
        mp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def query(self, workdir: str, question: str) -> list[Passage]:
        from lightrag import QueryParam
        if not (pathlib.Path(workdir) / MARKER).exists():
            return []
        self._guard(workdir)
        rag = self._rag(workdir)
        param = QueryParam(mode=self.mode, top_k=self.top_k, chunk_top_k=self.chunk_top_k, enable_rerank=False)
        res = _run(rag.aquery_data(question, param=param))
        chunks = ((res or {}).get("data") or {}).get("chunks") or []
        out, seen = [], set()
        for rank, ch in enumerate(chunks):
            # LightRAG keeps only the last path piece of file_path; the chunk id is '<doc id>-chunk-<n>'
            addr = _CHUNK_SUFFIX.sub("", ch.get("chunk_id") or "") or ch.get("file_path") or ""
            text = ch.get("content") or ""
            if not addr or (addr, text) in seen:
                continue
            seen.add((addr, text))
            out.append(Passage(address=addr, text=text, score=float(len(chunks) - rank)))
        return out


__all__ = ["LightRAGIndex", "LocalEmbed", "pick_device"]
