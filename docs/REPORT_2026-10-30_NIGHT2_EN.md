# Night report 2026-10-30 (night 2) — Cleo/Rex pipeline, PC pages, Ash/Penn/Wren designs

Summary (English):
- End to end now: PC overview → per-PC entries → entry detail (Original + What-agents-receive tabs, View-as Marty/Cleo/Rex/Ash) and Flow Order→Sam→Marty→Cleo,Rex→Final with dotted PC lines; all 5 check suites pass.
- Click: PC tab cards → entry → tabs → SHOW; Flow tab default flow + dotted lines + Ash preview link; Crew tab stage order.
- Built but untested on your PC: all browser UI (no browser here), live Cleo/Rex runs, live flow runs, Tavily search, Jetson indexing.
- Skipped: live Cleo/Rex runs (no TAVILY_API_KEY), permissions UI (parked for your 6-1/6-2 review), Ash/Penn/Wren code (design-only), duration code (designed, not built).
- Check tomorrow: (1) PC tab click-through + View-as, (2) approve item 5 + 7 designs, (3) add TAVILY key, press REBUILD INDEX, push when ready.
- Model calls tonight: 3 Marty runs (2 ok, 1 fail), 81,513 prompt + 14,730 completion = 96,243 tokens total.

요약 (한국어):
- 끝까지 됨: PC 개요 → PC별 목록 → 항목 상세(원문/에이전트 수신 탭, Marty·Cleo·Rex·Ash 미리보기), Flow Order→Sam→Marty→Cleo,Rex→Final(점선 PC 연결). 5개 검사 전부 통과.
- 클릭: PC 탭 카드 → 항목 → 탭 → SHOW, Flow 탭 기본 플로우·점선·Ash 미리보기, Crew 탭 단계 순서.
- 만들었으나 당신 PC에서 미확인: 브라우저 UI 전부(여기 브라우저 없음), Cleo/Rex 실실행, 플로우 실실행, Tavily 검색, Jetson 색인.
- 건너뜀: Cleo/Rex 실실행(TAVILY 키 없음), 권한 UI(6-1/6-2 리뷰 대기), Ash/Penn/Wren 코드(설계만), duration 코드(설계만).
- 내일 확인할 3가지: (1) PC 탭 클릭 + View-as, (2) item 5·7 설계 승인, (3) TAVILY 키 입력, REBUILD INDEX, push.
- 오늘 모델 사용: Marty 3회(성공 2·실패 1), 입력 81,513 + 출력 14,730 = 총 96,243 토큰.

Branch: `result-flow`, 11 commits, no push. No new packages. No Baseten
deployments. No keys printed or committed. No Jetson indexing from the
sandbox.

## 1. Queue items 1–2 (already done, skipped)

- Marty wrap-up (retries capped at 2/run, slim retry, stop-and-report,
  s2.3 omitted-by-text, terms top-15, Cleo preview from Marty-05):
  committed `b2d6ea4` + `85deec7`, reported in chat before this queue.
- Q11/Q12 decided + doc committed `9b5a42b`.
- Marty-05 (25.9k tokens) is superseded by Marty-08 below (doc shape).

## 2. Three small follow-ups (`a169591`)

- Sam: `intake.NO_PROMISE_RULE` (no action promises of any kind) used
  by the order chat; 2 new `order_check` cases.
- Marty title → "Structure writer"; new optional `agent.json` `stage`
  (standard + validator); `/api/crew` sorted by stage; roster shows
  S0–S7. Proven: Sam, Marty, Rex, Cleo, Ash, Penn, Vera, Wren, Iris.
- Credits: `data/third_party.json` + `scripts/gen_credits.py` write
  `THIRD_PARTY.md` and the About block (idempotent, includes LightRAG
  1.5.7, MiniLM, pdfplumber 0.11.10, three.js 0.186.1).

## 3. §14 step 3 — Marty concept + structure (`75a9179`, fixed `6234381`)

- `write_structure` saves `concept` v1 + `structure` v2 in one call;
  registry pretty-printed (8 categories); `marty_input` prints
  section refs for verbatim copy; default flow carries both.
- Marty-06: 20,800 + 4,166 tokens, 4 calls, 0 retries, 5 parts, all
  refs exact; Cleo preview rebuilt: 34,301 chars, 5 parts, 0 missing.
- Drift found and fixed: I first shipped `intent{overall,links}`;
  the doc says top-level `links` (overall already in concept).
  Realigned code + registry + checks + persona; registry :=
  doc schema minus `duration` (designed in item 5, code later).
- Marty-07 FAILED (49,817 + 7,290): empty covers + a shapeless retry
  (the retry prompt never restated the bundle shape), then the model
  wandered re-reading until steps ran out. Fix: retry prompt names
  the argument and its top-level keys; "do not read anything else"
  after a failed correction.
- Marty-08 OK: 10,896 + 3,274 = 14,170 tokens, 3 calls, 0 retries,
  doc shape, preview re-verified (34,301 chars, 0 missing).

## 4. §14 step 4 — Cleo/Rex writers (`414cc61`)

- `write_concepts` / `write_cases`: schema + verbatim quotes + every
  claim cited + report picks == run picks. Figure quotes match
  caption/image text/numbers only, never AI descriptions.
- Cleo/Rex un-drafted (flow I/O declared, `result.json` output).
- 15 new `results_check` cases against temp fixtures (accept +
  invented quote, whole-entry ref, citationless claim, wrong-PC
  pick, unpicked/dropped pick, part gap, bad kind/date, empty
  cases). No model calls (no Tavily key; direct tool tests).

## 5. §14 step 5 — retrieval behavior (`274d3da`)

- New `research_status` tool (searches/hits/picks/citations +
  per-part + STATUS line); writers log `citations` events per part
  on save; personas: need-list per part, short hits, status before
  writing. Needs stay in reasoning (no new store, per §13.3).

## 6. §14 step 6 — quality bars (`6535416`)

- Writer floors: `easy_explanation` ≥30 words, case `summary` ≥15.
- Refusal hints: §13.4.3 suggestions from the source map's omitted
  list (via run INPUTS → structure → map; silent in ad-hoc runs).
- Personas: Cleo's 4-point easy test, Rex's real-case test.

## 7. §14 step 7 — full flow (`cae5bdb`)

- Default flow: 6 nodes, 9 lines, Order→Sam→Marty→Cleo,Rex→Final;
  order→Marty `source` line; stubbed e2e green (cleo/rex checked,
  manifests, 9 line events).
- Marty gets the full-source preload in flow runs (same builder as
  the proven ad-hoc path, byte-identical via `pc.marty_input_text`).
- Fixed a real gap: the flow passed rendered markdown where the
  runner expects a path, so `read_md_section` and writer input
  validation could never work in flow runs. Flow now writes
  `INPUTS.md` to disk and passes the path (proven by new checks).
- Ash picks-only start prompt: `pc.picks_preview_for` + endpoint
  (200/409 proven) + Flow preview link on Ash. Proven on the real
  TWAP pick (map + reasons + full refs, 1,098 chars).
- Flow editor: PCs as dotted lines from catalog tools (wrapper keeps
  all 4 redraw call sites working); pick refs clickable in reports.

## 8. Queue 6-1 + 6-2 — PC pages (`e3ec5c5`, one commit)

- "PCs unavailable": routes exist in current code — your error was
  almost surely the stale server. The UI now names the failing call
  in the message so this is diagnosable next time.
- Overview: 3 true cards (computed state/entries/size/profile/index
  + real tool lists + computed grants), clickable to `#/pc/<id>`.
- Entry endpoints generalized to `<pc>` (list/detail/figures/build/
  index); detail adds paragraphs + web provenance; new picks
  endpoint (orders that picked an entry, newest first).
- Management view: entries + per-row INDEX; detail tabs Original
  (full text by section, figures/tables inline by page, ref-click
  jumps + flashes) and What-agents-receive (map + View-as select).
- View-as: source → Marty/Cleo/Rex (new Marty endpoint included);
  theory/article → Ash + picks table (latest picking order). Every
  preview uses the same code path as a real run. `js=0`, suites
  green, endpoints probed on real storage (Marty preview 49,012
  chars via the endpoint).

## 9. Queue 6-3 — permissions (doc only, `725fae4`)

- New §8.9: layer 1 tool grant per PC + layer 2 entry access
  `{read, edit}`; both required; refusal "no access to this item";
  defaults (Source: all order agents, Sam at ingest; picks: picker
  + later agents, edit = picker); UI parked for your 6-1/6-2
  review. No code.

## 10. Queue item 5 — Ash design (doc only, `07cef1b`)

- Structure v2 gains `duration {total_s, parts[]}`; sum check in
  the writer, exact-seconds match to the request in the handoff.
- New §5.3 `storyboard_draft` v1 (schema + 7 checks); crew table
  (Ash stage 3); `plan` retired; Q13 opened for Penn. All 15 JSON
  blocks parse. No code.

## 11. Queue item 7 — Penn/Wren design (doc only, `3f9e2be`)

- Scenes gain `handoff[]`; passing drafts grant Penn/Wren read
  access with `granted_by` + scene (§8.9 extended).
- New §5.4 `storyboard` v1 + §5.5 `narration` v1 (schemas + checks);
  crew table (both from Ash, parallel; Iris also reads
  `storyboard`); Q13 decided. All 17 JSON blocks parse. No code.

## 12. Choices (recommended option + one-line reason each)

- Single `write_structure` with `{result:{concept,structure}}`:
  the runner allows exactly one `write_*` tool per agent.
- Old structure-v1 results are legacy: a version bump must not
  re-validate the past.
- Evidence ref must sit inside its pick: strict reading keeps
  reports honest; relax later in one line if you disagree.
- ≥1 case per part, date needs a digit, ≥1 claim per part/case:
  mechanical teeth for "no evidence, no save".
- Part coverage vs the structure is the handoff's job: writers
  check p1..pn contiguity only.
- Floors (30/15 words) + self-test rules for §13.5: deeper style
  judgment belongs to reviewers, not writer gates.
- Need-list lives in model reasoning: §13.3 fixes the log format.
- Marty flow preload is full text: matches the proven ad-hoc run.
- `INPUTS.md` on disk in flow runs: makes tools and validation
  work identically in flow and ad-hoc runs.
- INPUTS.json → structure → map for refusal hints: reuses the
  flow's own artifacts, silent when absent.
- Dotted PC lines from catalog tools: grants already declared in
  `agent.json`, no second source.
- `_PC_JOBS` stays doc-id-keyed: content-hash collision across
  PCs is ~impossible; reap searches all PCs.
- 6-1+6-2 in one commit: the PC UI rewrite is inseparable.
- Duration designed, not built: item 5 said no code.
- `total_s` exact-seconds handoff rule: predictable, no tolerance
  tuning.
- Item 7 fill-ins (visuals = string list; scene sets exact; times
  copied; words counted; est ±15% of words/2.5 and ≤ scene;
  digit-lines cited; `notes_for_wren` read by Iris): smallest
  consistent completion of your spec.

## 13. Needs your decision

- Approve the item 5 + 7 designs before any Ash/Penn/Wren code.
- Review 6-1/6-2 in the browser before I build the permissions UI.
- Add `TAVILY_API_KEY` to `.env`, then I can run live Cleo/Rex and
  real search (smoke script ready; search code is built).
- §8.6 has stale rows (phantom `pc_add_*` tools, "all crew" list,
  Marty read grant): say whether I rewrite that table or leave it.
- `data-gym-cache/` (untracked, pre-existing, unknown origin):
  keep or delete?

## 14. Check first on your PC (in order)

1. `start_server.bat`, hard-refresh; the version banner must be gone
   (it proves fresh code — your "PCs unavailable" was the stale one).
2. PC tab: 3 cards → `#/pc/source` → entry → ORIGINAL tab figures →
   WHAT AGENTS RECEIVE → View-as Marty/Cleo/Rex SHOW.
3. `#/pc/theory`: TWAP entry → View-as Ash (shows "not picked by any
   order yet" until a flow run picks it).
4. Flow tab: default 6-node flow, dotted PC lines, Ash preview link.
5. Crew tab: S0–S7 order, Marty "Structure writer".
6. Press REBUILD INDEX on the chapter (sandbox cannot reach Jetson).
7. Add the Tavily key, run `tavily_smoke.py`, then say the word for
   live Cleo/Rex runs and `git push`.

## 15. Model usage tonight (this queue only)

- Marty-06: 20,800 + 4,166 = 24,966 (ok, intent shape).
- Marty-07: 49,817 + 7,290 = 57,107 (FAIL, see §3).
- Marty-08: 10,896 + 3,274 = 14,170 (ok, doc shape).
- Total: 81,513 prompt + 14,730 completion = 96,243 tokens.
- All other verification used checks and probes (no model calls).
