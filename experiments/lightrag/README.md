# LightRAG knowledge backend

LightRAG is the crew's knowledge backend, behind the stable
`agents/_frame/graph.py` interface (`index_corpus` / `query` /
`summarize` / `get_status`). There is no other backend: when LightRAG
is missing, calls fail with "LightRAG unavailable: ..." instead of
faking results.

## Install (Windows, CPU-only)

`start_server.bat` installs the root `requirements.txt` into the
project `.venv` (frozen pins: `lightrag-hku==1.5.7`,
`sentence-transformers==6.2.0`, `torch==2.14.1+cpu`, ...). The
`--extra-index-url` line keeps torch CPU-only (~200MB instead of
~2.5GB CUDA).

## Embedding profiles

Two profiles, one index each (`storage/<eid>/<profile>/`, never mixed):

- `jetson` (default): `BAAI/bge-m3`, 1024 dims, chunk 512 tokens,
  embedded by the LAN server (read-only API use: `GET /health`,
  `POST /embed`; token from `.env` `EMBED_REMOTE_TOKEN`, never logged
  or sent to browsers).
- `local`: `sentence-transformers/all-MiniLM-L6-v2`, 384 dims, chunk
  256 tokens, embedded on this PC. Models download into `models/`
  (gitignored) on first run.

Active profile: `data/settings.json` wins (Settings tab), `.env`
`EMBED_PROFILE` is the default. Querying an index built with another
model is refused — rebuild or switch profile instead.

The Settings tab also switches the LightRAG LLM (provider follows the
model name: `meta-models/*` → Baseten, else Meta API), the retrieval
mode / top_k (apply to the next query), and per-profile chunk sizes
(apply to newly built indexes only).

MiniLM was picked over local bge-m3 (1024 dims, ~9GB, 15min load,
72ms/sent vs 6ms/sent on this PC) because the handbook corpus is small
English text; see `bench_embed.py` for the bake-off.

LLM calls go to Baseten (`meta-models/muse-spark-open-1026`,
`https://inference.baseten.co/v1`, key `BASETEN_API_KEY` from repo
`.env`, never logged). Older indexes were built on the Meta Model API;
their markers record that — re-run `run_index.py` to rebuild on Baseten.

## Run

```bat
.venv\Scripts\python experiments/lightrag/smoke_meta.py   # LLM check
.venv\Scripts\python experiments/lightrag/run_index.py agents/pd_marty [local|jetson]
```

`run_index.py` indexes `handbook/*.md` and logs every LLM call
(chars/seconds) to `storage/<eid>/llm_log.jsonl`. Stop near $2 of
spend (one handbook file costs cents).

## What is committed

`adapter.py`, `config.json`, scripts, this README, run logs.
NOT committed: `.venv/`, `models/`, `storage/`, `graph_index/`
(all gitignored; rebuild with the steps above).
