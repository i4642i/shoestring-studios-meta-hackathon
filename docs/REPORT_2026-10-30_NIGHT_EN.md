# Night report 2026-10-30 — lite removal, embedding profiles, Flow tab

Branch: `night-2026-10-30` (not pushed, per instructions).
Model calls during the night: zero. All tests are offline/stubbed.

## 1. What was done

### Step 1a — lite removal (approved list only, finished)
- `agents/_frame/graph.py` is LightRAG-only: lite index/query/helpers,
  constants and the `RAG_BACKEND` switch are gone.
- Deleted: `agents/*/graph_index/lite.json`,
  `experiments/lightrag/run_compare.py`,
  `experiments/lightrag/requirements-lightrag.txt` (pins merged into
  root `requirements.txt`: pdfplumber + 90 LightRAG pins).
- Crew map: LITE MAP button and lite branch removed; missing LightRAG
  shows `LightRAG unavailable: <reason>` plus fix steps.
- Order-chat hints now come from LightRAG (`_handbook_hints` rewritten;
  every chat turn fires one LightRAG query — real per-turn cost).
- Run log records tool error text and `profile/model/dim` passthrough.
- One deviation from the list: the local `.venv-lightrag/` directory
  was NOT deleted yet. It stays gitignored with a note and should be
  deleted after the first `start_server.bat` run with merged
  requirements succeeds (keeps a working fallback until the merge is
  proven on real hardware).

### Step 1b — embedding profiles + Settings tab (finished, LAN parts open)
- Profiles `local` (MiniLM, 384d, chunk 256) and `jetson` (bge-m3,
  1024d, chunk 512). Separate index per profile under
  `storage/<agent>/<profile>/`; model/dim recorded in per-profile
  markers; cross-model queries refused with a clear message.
- Found by reading the installed package: the old chunk size was the
  LightRAG default **1200**, silently truncating every MiniLM embedding.
  Migrated indexes keep an honest `chunk_size: 1200` in their markers.
- Jetson: `/health` before every operation, exact down message, no
  silent fallback to local. Token only in `.env`, never to the browser.
- Settings tab: profile radio, Jetson URL, token set/missing, test
  connection, per-agent×profile index table with Build buttons, plus
  LLM model list, query mode / top_k, and chunk sizes for new indexes.
- `start_server.bat` fixed twice: a `)` I added inside an echo broke
  parsing, then the file was found LF-only (cmd needs CRLF).
  Launcher now stays open, and `scripts/pip_install.py` installs with
  per-package `[i/N]` progress.
- Sam got an additive idle layer (head/arms move over the seat pose).

### Step 2 — Flow tab (built, live run untested)
- New `Flow` tab: canvas with draggable agent nodes, one output port
  per result category, single input port, drag green→blue to connect,
  click a line for the category popup (ALL or subset + delete),
  palette to add agents, live server validation with red highlights,
  save/load, run panel with order input, live log, run history.
- `agents/_frame/flow.py`: validation (unknown category, agent without
  input, missing required input, cycles, duplicates, order/final
  rules), topo order, envelope wrap/validate, whitespace-free runner
  integration (composed `input.md` + `INPUTS.json`, `runner.run`
  untouched), per-line transfer log, `runs/<run_id>/` layout.
- `agents/_frame/categories.json`: brief/source/request/structure, v1,
  with JSON schemas; hand-rolled stdlib validator for the documented
  subset (no new packages allowed).
- Default flow `Order -> Sam -> Marty -> Final` ships in
  `data/flows/default.json`.
- Endpoints: list, catalog, get, save, validate, run (background
  thread), runs, run status.

```
Order (brief, source) --*--> Sam --[request]--> Marty --[structure]--> Final
```

## 2. AGENT_STANDARD change (with reason)

Added section 9 "Flow participation (OPTIONAL)" plus the `flow` key in
`agent.json` (`inputs[]` with required flags, `outputs[]` with machine
filenames). Reason: flows need machine-checkable I/O contracts so lines
can be validated and handoffs schema-checked, while honoring the rule
that connections live only in flow files — agents declare *what*, never
*where*. `validate_agent.py` enforces the shape and registry membership;
new crew members get an explicit empty `flow` section.

## 3. Decisions made (no questions asked)

1. Wrapper, not writers: envelopes are created at the flow boundary;
   `write_request`/`write_structure` and standalone order runs are
   byte-identical to before.
2. Structure's input-relative rules (heading coverage/order) stay in the
   writer tool; handoff re-checks the static registry shape. Rationale:
   pure JSON schema cannot express "heading exists in input", and the
   payload already passed the writer at creation.
3. Envelope `verified` is reserved for future human/QA acceptance;
   flows use `unverified` → `checked`.
4. Flow aborts (fail fast) on: invalid flow, missing order/parsed PDF,
   missing producer file, envelope/schema failure, agent failure.
5. Strict input rule: every agent node needs ≥1 incoming line (all data,
   even the brief, arrives via lines). Duplicate same-pair lines are
   rejected — combine categories on one line.
6. RUN auto-saves first, so a run can never execute a stale canvas.
7. Background threads for flow runs (in-process runner, easy status);
   `STATUS.json` keeps status correct across server restarts.
8. No flow-delete endpoint (spec asked save/load only); no canvas
   pan/zoom (fixed 1160×480, scrolls); query `bypass` mode excluded.
9. `runs/` at repo root, gitignored, `fl-TIMESTAMP` ids with dedupe.
10. Zero model calls overnight; live flow run left for your PC.

## 4. Test results (all offline, all green)

- `scripts/flow_check.py`: 36/36 (registry, schema subset, envelopes,
  8 validation cases, topo, full stubbed end-to-end incl. envelopes,
  manifests, 3 line events, final collection, failure abort, both
  agents validate).
- Flow API probe (mock handler, deleted after): 18/18 incl. all
  refusal paths and zero spawned jobs on refusals.
- Settings probe: 24/24 (round-trip, 9 invalid values refused,
  precedence, fallback); `QueryParam(mode, top_k)` constructed in the
  real installed package.
- Seating: 23/23 (unchanged since green).
- `py_compile` on every touched Python file; `node --check` on both
  `index.html` scripts (module + classic).
- Live LightRAG query path proven earlier up to the sandbox socket
  block (graph + 384d embeddings loaded, then expected network fail).

## 5. Screenshots

None — the sandbox has no browser or LAN. Please capture on your PC:
Flow editor with the default flow, an open line popup, a finished run
log, the Settings tab, Sam `?seatdebug=1` on/off, one office sit
close-up.

## 6. Open issues / needs from you

1. PC: `start_server.bat` reinstall (~1GB) + `smoke_server.py` rerun.
2. Live flow run: create/approve an order, run the default flow, check
   `runs/<id>/` envelopes and the log. This exercises real model calls.
3. Jetson: test connection, build Marty's jetson index, same 3
   questions on both profiles.
4. Push when ready: 8 commits on `night-2026-10-30`, never pushed.
5. Delete `.venv-lightrag/` after the merged install works.
6. `data-gym-cache/` (one 3.6MB blob, unknown origin) left untracked —
   your call.
7. Future (not built): flow delete/duplicate, canvas pan/zoom,
   `verified` acceptance step, `/rerank` use, multi-seat sofa poses
   for office visitors.

## 7. Files changed (night branch, 8 commits)

- `af8b903` posed seating + drive clip + `?seatdebug` + probes
- `ba6e636` LightRAG-only backend, profiles, Settings, Sam motion
- `cbcab79` bat CRLF/pause + `scripts/pip_install.py`
- `3b081ee` lite-only file deletions
- `b5499af` registry, `flow.py`, `flow_check.py`, default flow,
  standard §9, validator, agent `flow` sections
- `8f3cbf4` flow API + `runs/` ignore
- `c6ae086` Flow tab UI + README tabs
- (this report)
