# LightRAG experiment (D54)

Try LightRAG as Marty's knowledge backend, behind the stable
`agents/_frame/graph.py` interface (`index_corpus` / `query`).
`RAG_BACKEND=lite` (default, stdlib) or `lightrag` (this venv).

## Install (Windows, CPU-only)

```bat
python -m venv .venv-lightrag
.venv-lightrag\Scripts\python -m pip install -r experiments/lightrag/requirements-lightrag.txt
```

Pins are frozen in `requirements-lightrag.txt`
(`lightrag-hku==1.5.7`, `sentence-transformers==6.2.0`,
`torch==2.14.1+cpu`, ...). The file's `--extra-index-url` line keeps
torch CPU-only (~200MB instead of ~2.5GB CUDA).

## Embedding model (locked)

`sentence-transformers/all-MiniLM-L6-v2` — 384 dims, ~274MB on disk.
Picked over `BAAI/bge-m3` (1024 dims, ~9GB, 15min load, 72ms/sent vs
6ms/sent on this PC) because the handbook corpus is small English text.
Re-pick means re-index; see `bench_embed.py` for the bake-off.
Models download into `models/` (gitignored) on first run.

LLM calls go to the Meta Model API (`muse-spark-1.3`,
`https://api.meta.ai/v1`, key from repo `.env`, never logged).

## Run

```bat
set RAG_BACKEND=lightrag
.venv-lightrag\Scripts\python experiments/lightrag/smoke_meta.py   # LLM check
.venv-lightrag\Scripts\python experiments/lightrag/run_index.py agents/pd_marty
.venv-lightrag\Scripts\python experiments/lightrag/run_compare.py agents/pd_marty
```

`run_index.py` indexes `handbook/*.md` and logs every LLM call
(chars/seconds) to `storage/<eid>/llm_log.jsonl`. Stop near $2 of
spend (one handbook file costs cents). `run_compare.py` asks the same
3 questions through lite and LightRAG and prints answers side by side.

## What is committed

`adapter.py`, `config.json`, scripts, `requirements-lightrag.txt`,
this README, run logs. NOT committed: `.venv-lightrag/`, `models/`,
`storage/`, `graph_index/` (all gitignored; rebuild with the steps above).
