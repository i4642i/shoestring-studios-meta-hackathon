# Night report 2026-10-30 — lite removal, profiles, 7 agents, result draft

Branch: `night-2026-10-30` (not pushed, per instructions).
Model calls during the night: zero. All tests are offline/stubbed.

CORRECTION APPLIED: the Flow tab, category registry, handoff check
and output conversion were built, then fully reverted on your STOP
(revert commits `25ba329`, `3501b3c`, `e522878`). Only the finished
current task, the 7 agent folders, and the result-JSON draft remain.

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

### 7 new crew (stages 2–7), one commit each
- `explain_cleo` Cleo, Concept explainer → `concepts`
- `case_rex` Rex, Case researcher → `cases`
- `plan_ash` Ash, Planning PD → `plan`
- `board_penn` Penn, Storyboard writer → `storyboard`
- `board_vera` Vera, Storyboard reviewer → `storyboard_checked`
- `voice_wren` Wren, Narration writer → `narration`
- `voice_iris` Iris, Narration reviewer → `narration_checked`
- Each: agent.json (model `meta-models/muse-spark-open-1026`, read
  tools only), persona.md (4-section standard + draft-status line),
  one handbook craft seed, appearance.json (unique Mini variant +
  unique tint; all pass the office tint regex).
- Validator: 7/7 PASS. The validator does NOT block tool-less
  writers: `tools` holds two real frame tools and `io` is unchecked,
  so all 7 are standard-compliant *drafts* — they validate and show
  up, but cannot produce outputs until their writer tools exist. No
  code was changed for this; no runtime code was written for them.
- Crew page + 3D office: automatic. Both read the live `api/crew`
  roster (server scans `agents/` sorted); new members roam, chat, and
  take chat seats with no code change. Office chat lines already
  branch on titles: Ash→PD lines, Penn/Wren→writer, Vera/Iris→
  reviewer, Cleo/Rex→generic.
- Static `api/crew` fallback updated to all 9 members in roster order
  (was Marty-only with a stale title), so no-backend hosting still
  shows the full crew.

### Result JSON draft (D8/D9, document only, no code)
- `docs/RESULT_JSON_DRAFT_EN.md`: one JSON per agent run (header +
  `categories` map); schemas for Sam (`request`), Marty (`structure`),
  Order (`brief`, `source`); crew plan table stages 0–7 with
  produces/receives per role; company computers (§8: Source PC +
  Article PC formats, LightRAG indexing, duplicates, tool grants,
  office idea); stable refs (§9: `pc://` addresses, `open_ref`,
  citation check); open questions Q1–Q10.

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

- New agents: `validate_agent.py` 7/7 PASS (plus Sam/Marty still PASS).
- Roster scan replicated offline: 9 ids in server order; seat map
  computed (see §5.1).
- No-Korean and appearance-shape invariants hold for all new files
  (English-only, variants in the office list, tints match
  `^#[0-9a-f]{6}$`).
- Earlier: Settings 24/24, seating 23/23, `py_compile` clean,
  `node --check` on both `index.html` scripts.
- Live LightRAG query proven earlier up to the sandbox socket block.
- No browser in the sandbox: office/Crew visuals unverified, left for
  your PC (screenshots below).

## 4. Choices I made (recommended option each, one-line reason)

1. Built 7 agents, not "6" — your list named 7 roles and stages 2–7
   need 7.
2. Read tools (`read_md_section`, `query_graph`) on all 7 — real frame
   tools each role genuinely needs; writers stay missing → honest
   draft status.
3. `io` filenames mirror category names (`concepts.json`, …) — the
   draft has no filenames yet, so the obvious mapping keeps every
   file greppable.
4. Desks: REPORT, don't add — blind furniture surgery in the
   hand-tuned 10×7m room without screenshots risks overlap; seats are
   chat-only and roaming is unaffected.
5. Static `api/crew` updated to 9 — its README says it mirrors the
   roster, and it was already stale.
6. Article-PC read granted to Ash/Vera/Iris in the draft — planners
   and reviewers cannot verify citations without it; writers stay
   ungranted to keep their inputs small.
7. Duplicate add = idempotent no-op returning the existing address;
   changed content = new entry, old kept — refs must never rot.
8. ids = 12 hex chars of SHA-256 over normalized content — short to
   write, collision-safe at our scale.
9. PC indexes reuse `local`/`jetson` profiles at
   `storage/_pc/<pc>/<profile>/` — same no-mixing rules as agents,
   zero new concepts.
10. Citation check at writer-tool time + reviewer re-verify via
    `open_ref` — follows the existing writer-validated pattern.

## 5. Needs your decision

1. Q1–Q10 in `docs/RESULT_JSON_DRAFT_EN.md` (one at a time, per D9).
2. Desks: 9 crew share 6 chat seats by modulo — roster positions 7–9
   (Sam, Iris, Wren) sit at desks 0–2 when chatting. Say the word and
   I will add a third desk row (needs your screenshots to verify).
3. Push: branch `night-2026-10-30` holds 24 commits, never pushed.
4. PC: `start_server.bat` reinstall (~1GB) + `smoke_server.py` rerun.
5. Jetson: test connection, build Marty's jetson index, same 3
   questions on both profiles.
6. Screenshots: Settings tab, Crew roster with 9, office with 9
   roaming, Sam `?seatdebug=1` on/off, one office sit close-up.
7. Delete `.venv-lightrag/` after the merged install works.
8. `data-gym-cache/` (one 3.6MB blob, unknown origin) left untracked.

## 6. Decisions made without asking (kept work only)

1. Hints kept via LightRAG per your choice (flagging the per-turn cost).
2. Chunk sizes 256/512 from model limits; old indexes migrated, not
   rebuilt; query mode `bypass` excluded; `verified`/rerank untouched.
3. Single format `version` proposed in the draft (Q1 asks to confirm).
4. `source` payload as sidecar pointer (Q3 asks to confirm).
5. Zero model calls overnight; LAN/browser items left for your PC.
