# Night report 2026-10-30 — lite removal, embedding profiles, result draft

Branch: `night-2026-10-30` (not pushed, per instructions).
Model calls during the night: zero. All tests are offline/stubbed.

CORRECTION APPLIED: the Flow tab, category registry, handoff check
and output conversion were built, then fully reverted on your STOP
(revert commits `25ba329`, `3501b3c`, `e522878`). Only the finished
current task plus the result-JSON draft below remain.

## 1. What was done (kept)

### Lite removal (approved list only)
- `agents/_frame/graph.py` is LightRAG-only: lite index/query/helpers,
  constants and the `RAG_BACKEND` switch are gone.
- Deleted: `agents/*/graph_index/lite.json`,
  `experiments/lightrag/run_compare.py`,
  `experiments/lightrag/requirements-lightrag.txt` (pins merged into
  root `requirements.txt`: pdfplumber + 90 LightRAG pins).
- Crew map: LITE MAP button and lite branch removed; missing LightRAG
  shows `LightRAG unavailable: <reason>` plus fix steps.
- Order-chat hints now come from LightRAG (your hints choice: keep via
  LightRAG — every chat turn fires one LightRAG query, real per-turn
  cost).
- Run log records tool error text and `profile/model/dim` passthrough.
- `.venv-lightrag/` kept until the merged install proves out on your
  PC (still gitignored, noted in `.gitignore`).

### Embedding profiles + Settings tab
- Profiles `local` (MiniLM, 384d, chunk 256) and `jetson` (bge-m3,
  1024d, chunk 512). Separate index per profile under
  `storage/<agent>/<profile>/`; model/dim in per-profile markers;
  cross-model queries refused.
- Found: the old chunk size was the LightRAG default **1200**, silently
  truncating MiniLM embeddings. Migrated markers honestly record 1200.
- Jetson: `/health` before every operation, exact down message, no
  silent fallback. Token only in `.env`, never to the browser.
- Settings tab: profile, Jetson URL, token set/missing, test
  connection, per-agent×profile index table with Build, LLM model
  list, query mode / top_k, chunk sizes for new indexes.
- `start_server.bat`: fixed LF-only parse failure and a paren-in-echo
  bug (both mine), launcher stays open, `scripts/pip_install.py`
  installs with per-package `[i/N]` progress.
- Sam: additive idle layer (head/arms move over the seat pose) and the
  posed-seating fix it rests on.

### Result JSON draft (D8, document only, no code)
- `docs/RESULT_JSON_DRAFT_EN.md`: one JSON per agent run (header +
  `categories` map), schemas for Sam (`request`), Marty (`structure`)
  and the Order pseudo-producer (`brief`, `source`), plus 6 open
  questions (Q1–Q6) for your decision.

## 2. What was reverted (built, then removed on STOP)

- `b5499af` Flow contracts/engine → `e522878`: `categories.json`,
  `flow.py`, `flow_check.py`, `data/flows/default.json`, agent `flow`
  sections, standard §9, validator flow support, crew-create template
  line.
- `8f3cbf4` Flow API → `3501b3c`: catalog/save/load/validate/run
  endpoints, run threads, `runs/` ignore.
- `c6ae086` Flow UI → `25ba329`: Flow tab editor, README tabs line.
- Verified after revert: zero Flow references in code, both agents
  validate, settings/graph endpoints intact (probe), all syntax green.

## 3. Test results (all offline, all green)

- Settings: 24/24 (round-trip, 9 invalid values refused, precedence,
  fallback); `QueryParam(mode, top_k)` built in the real package.
- Seating: 23/23. `py_compile` on every touched file; `node --check`
  on both `index.html` scripts.
- Post-revert integrity probe: settings GET shape, lite-free graph
  status, both agents validate — all pass.
- Live LightRAG query proven earlier up to the sandbox socket block.

## 4. Screenshots

None — the sandbox has no browser or LAN. On your PC: Settings tab,
Sam `?seatdebug=1` on/off, one office sit close-up.

## 5. Open issues / needs from you

1. PC: `start_server.bat` reinstall (~1GB) + `smoke_server.py` rerun.
2. Answer Q1–Q6 in `docs/RESULT_JSON_DRAFT_EN.md` (one at a time, per D9).
3. Jetson: test connection, build Marty's jetson index, same 3
   questions on both profiles.
4. Push when ready: 14 commits on `night-2026-10-30` (incl. this fix), never pushed.
5. Delete `.venv-lightrag/` after the merged install works.
6. `data-gym-cache/` (one 3.6MB blob, unknown origin) left untracked.

## 6. Decisions made without asking (kept work only)

1. Hints kept via LightRAG per your choice (flagging the per-turn cost).
2. Chunk sizes 256/512 from model limits; old indexes migrated, not
   rebuilt; query mode `bypass` excluded; `verified`/rerank untouched.
3. Single format `version` proposed in the draft (Q1 asks to confirm).
4. `source` payload as sidecar pointer (Q3 asks to confirm).
5. Zero model calls overnight; LAN/browser items left for your PC.
