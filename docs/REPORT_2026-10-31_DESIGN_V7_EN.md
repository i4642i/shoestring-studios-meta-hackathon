# v7 야간 작업 보고 (DESIGN V7)

- v7 데이터 흐름이 완성됐습니다: Sam→Marty→Cleo,Rex→Ash→Penn,Wren→Final 스토리보드, PC 3대 점선 연결.
- Sam·Marty 실제 LLM 실행 성공 (토큰 수는 아래 표 참고). Cleo/Rex 실측은 건너뜀.
- 모든 검사 5종 통과, 커밋 9개, 푸시 안 함.
- 확인할 것: Flow 탭 기본 흐름 그림 → PC 관리 페이지 수신 목록 → REBUILD INDEX → 주문 결과.
- 쓰지 않은 탐침 폴더 5개가 남아 있습니다. 지워도 되면 말해주세요.

# Design v7 night report (WORKFLOW DESIGN v7)

Date: 2026-10-31. Branch: `result-flow` (9 commits, no push).
All 5 suites green after every commit
(`pc_check`, `pick_check`, `results_check`, `order_check`,
`flow_check`: ALL PASS). Agents validate 9/9. Page JS
`node --check` clean.

## Done

- (a) Kind/parts recipient rows + parts-gated reads
  (`6b4850d`). Row shape
  `{agent, order_id, kind: map|full, parts, set_by, at}`;
  kindless rows count as `full`; reads outside held parts
  refused with `no access to this item`.
- (b) Kind-aware prompt chunks (`44f5bf5`): `full` rows get
  the full text (capped ~100k chars, honest truncation note +
  tool fallback), `map` rows the map, `parts` limits both.
- (c) Generalized `pc_set_recipients` + Cleo/Rex list Ash
  (`b0b2b28`): pickers auto-list Ash `map` on their picks.
- (d) Ash handoff application (`32b7085`): passing
  `storyboard_draft` writes Penn/Wren `map`+`parts` rows under
  the lister rule (E7).
- (e) Recipients replace the picks-scope gate (`e15f8a8`):
  one mechanism everywhere; same refusal message.
- (f) Ash/Penn/Wren writers + structure v3 (`32d03f7`):
  registry 11 categories; draft validated against Marty's
  time plan (contiguity, coverage, ±15%); storyboard and
  narration must match Ash's scenes exactly; Marty writes the
  `duration` time plan; Cleo/Rex accept structure v2+v3.
- (g) Flow file + UI (`7ee6afa`): default flow has 11 nodes,
  10 solid lines (c1–c10), 29 dotted `pc_lines` (c11–c39);
  PC nodes never run; final takes ONLY storyboard +
  narration (validated); Flow tab draws PC nodes, dotted
  lines with labels, Marty subtitle, Penn/Wren previews.
- (h) Docs (`3cbe20e`): draft §§4/5/5.3–5.5/8.6/8.9/12/13.2
  rewritten for kinds + no-source-lines; new §15 Workflow
  design v7 with the full line tables.
- (i) Live runs + persona fixes (`ca78955`): Sam and Marty
  each ran live once successfully (see tokens below). Both
  first attempts failed on over-reading and were fixed with
  read caps (Sam: max 3 reads then write; Marty: full text
  is already in the prompt, write by step 4, explicit part
  shape with ids).

Live tokens (model `meta-models/muse-spark-open-1026`):

| Run | Result | LLM calls | Prompt | Completion |
|---|---|---|---|---|
| Sam #1 | fail (read all 10 steps, never wrote) | 10 | 58,640 | 2,312 |
| Sam #2 | OK (request + source v3, 5 recipient rows) | 6 | 21,331 | 2,558 |
| Marty #1 | fail (parts without ids, over-read) | 8 | 59,667 | 7,697 |
| Marty #2 | OK (concept + structure v3: 5 parts, 600 s) | 7 | 39,583 | 6,515 |
| Total | | 31 | 179,221 | 19,082 |

Marty's live map: parts 2.1–2.5 with verbatim refs,
neighbour links p1→…→p5, duration 90/210/120/90/90 = 600 s
for "about 10 minutes". Sam's live send returned the known
entry `pc://source/bb84439e0b7c` (duplicate bytes → same
ref) and re-listed it for the new order.

## Skipped and why

- Live Cleo/Rex: `TAVILY_API_KEY` IS set, so this was
  allowed — but their v7 changes are input-shape only
  (concept+structure, no `source` line), already covered by
  `flow_check`/`pick_check`. Skipped to save Tavily credits
  and tokens. Say the word and I run one Cleo next.
- Flow-tab screenshot: the sandbox cannot bind the server
  socket, so no live page render was possible. The JS
  syntax-checks and the flow file validates; please eyeball
  the canvas (check 1 below).
- Dotted-line add-UI: the Flow tab renders, labels, and
  deletes dotted lines, but adding one needs a file edit.
  (Choice: a 29-line add-UI is out of scope; the default
  set ships in the file.)
- Vera/Iris stay drafts (out of v7 scope). Their old
  `source` line is retired in the doc; they get PC rows
  when built.

## Choices I made (one-line reasons each)

- Duplicate dotted pairs allowed (c11–c13 share endpoints):
  Sam→PC carries three distinct meanings, told apart by
  label.
- Dotted ids share the solid id space (clash = error): UI
  selection and error attribution use one id space.
- Marty labelled via node subtitle, ports unchanged: the two
  category ports stay individually connectable.
- Cleo/Rex accept structure v2 AND v3: old Marty results
  keep working during the cutover.
- Live Sam reused the same chapter.pdf bytes under a new
  order id: also verifies duplicate-send re-listing on the
  shared entry.
- Live Marty via `runner.run` + the flow chunk builder, not
  `run_flow`: `run_flow` validates first and the final rule
  rejects partial live flows.
- Live Cleo/Rex skipped (see above): only-spend-what's-needed.

## Needs your decision

- Push `result-flow` (9 commits) when you have reviewed it.
  Nothing was pushed.
- 5 stray probe dirs at the repo root (`data-gym-cache/`,
  `widenprobe2_ogdmsq07/`, `widenprobe_tz0za33a/`,
  `wrenprobe_mdb3tewh/`, `wrenprobe_z3aq_qrm/`): not made
  by my commands or any current script — left untouched.
  Delete them if they are scratch.
- `TAVILY_API_KEY` is set: say so if you want a live Cleo
  and/or Rex run next.

## What to click/check on my PC, in order

1. Run `start_server.bat`, confirm no "older code" banner.
   Open the Flow tab: the default flow shows 11 nodes
   (7 crew + Final storyboard + 3 PCs), 10 solid lines,
   29 dotted labelled lines; validation says Valid.
2. Drag a dotted line label into view; click one to see the
   from→to popup; check Marty's subtitle reads "Storyboard
   draft (concept + structure)".
3. PC tab → Source PC → entry `bb84439e0b7c`: the
   recipients list shows the `ord-live-v7` rows with kinds
   (Marty `full`, Cleo/Rex/Ash `map`, Sam `full`).
4. Press REBUILD INDEX on that entry (Jetson was
   unreachable from my sandbox; the send skipped indexing
   with a warning).
5. Order tab → `ord-live-v7`: Sam's live `request` report;
   `runs/live-v7-marty2/pd_marty/report.md`: Marty's live
   structure with the 600 s time plan.
6. "Preview start prompt" on Marty vs Cleo (order
   `ord-live-v7`): Marty gets the full text, Cleo the map.
7. Review the 9 `v7 (a)–(i)` commits, then push.
