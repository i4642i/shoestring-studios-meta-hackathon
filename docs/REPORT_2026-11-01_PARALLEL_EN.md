# Parallel video team: part clones (STEPs 1-4)

## 요약 (한국어)

- Penn 승인 뒤 프로그램 단계 part_split이 파트별 클론(photo_pia@pN 등)을 만들고, 각 클론은 자기 파트 컷만 받아 병렬(최대 3워커) 또는 순차 실행됩니다.
- 승인/재실행/중단은 파트 단위이며, video_production은 모든 remy@pN 승인 전까지 대기합니다.
- Flow 탭은 비디오팀을 쌓인 카드+주황 점선 프레임+파트 상태 행으로 보여주고, Board API는 셀/단계 상태를 클론 단위로 반환합니다.
- 8개 스위트 742개 검사 전부 통과, 모델 호출 0회, MP4 렌더 없음.
- 남은 것: 브라우저 실측(Edge 승인이 막힘), Board 페이지 UI(별도 STEP 2/3 미착수), main 5개 커밋 push.

## What changed

Commits on `main` (no push; owner pushes):

- `ca64c58` STEP 1 — part split: code node `part_split` between Penn
  and the video team; clones `photo_pia@pN`, `image_gene@pN`,
  `anim_max@pN`, `board_vera@pN`, `slide_remy@pN` (`agents/_frame/parts.py`).
- `1d5205f` STEP 2 — parallel parts: thread pool (cap 3),
  per-entry PC locks, Openverse queue/rate limiter, pick dedup.
- `aeedbe7` STEP 3 — clone step mode: clone-keyed status/approve/
  re-run/STOP, video gate, Flow tab stacked cards + team frame,
  clone-aware Board API.

### STEP 1 — part split

- `part_split` cuts inputs by the chain cut -> scene_n -> Ash scene
  part_id: each clone gets only its part's Wren lines/cut times and
  Penn screen descriptions. Shared context for every clone: Marty's
  concept, Penn's style guide, one-line list of all parts with
  "you are Part N" marked. No "only do part N" text in prompts.
- PC rights reuse the existing recipient check (agent + order +
  parts); part_split only writes rows. Source rows go to
  `photo_pia@pN`, `anim_max@pN`, `board_vera@pN` (kind map + that
  part's items only); Voice rows hold only the part's cut clips;
  Pia/Gene picks grant only `board_vera@pN`, `slide_remy@pN`, and
  `video_production`. A clone never holds another part's rows.
- Gene's 6-image cap is split up front by cut count (largest
  remainder, min 1 per part); the same prompt reuses the stored
  image across parts and grants the reusing part.
- Results live in `runs/<run_id>/<node>/p<N>/`; a merge step joins
  parts in part order into the node's normal result, so
  video_production and older readers keep working. Writer check per
  clone: result cut IDs must equal exactly the given cut IDs.

### STEP 2 — parallel parts, safely

- Flow settings: `parallel_parts` (bool, default OFF for the first
  live run), `openverse_per_min` (default 20). Unknown settings and
  bad values are rejected by flow validation.
- Inside one part the order stays Pia/Gene/Max -> Vera -> Remy;
  parts never wait for each other. Sequential and parallel modes
  produce identical merged results and usage sums (fixture-tested).
- Every PC read-modify-write runs under a per-entry file lock (20
  parallel grants keep every row). Openverse calls share one
  queue/rate limiter. Same file + license reuses the first entry
  (deduped); same bytes under another license store separately.
- Usage/cost is logged per clone (`pN/usage.json`) and summed per
  member (`usage.json`).

### STEP 3 — step mode, Flow tab, Board

- Step status is keyed by clone (`photo_pia@p2`): per-clone
  result/approved/usage plus the node roll-up. APPROVE accepts a
  clone id (one part) or a base id (all parts at once, legacy runs
  included). RE-RUN (invalidate) of `pia@p2` drops only p2's
  downstream clones plus the uncloned video step — never other
  parts — and prunes only their approvals. Stepping to a clone id
  runs just that clone (owner note lands in that part only); on a
  fresh node it fails clean ("run the whole node first") instead
  of writing a partial merge. `video_production` waits until every
  `remy@pN` is approved. STOP parks the run at a stage boundary;
  the next step refuses until a stage is invalidated (resume).
- Flow tab: the five video nodes render as stacked cards with a
  "x N" badge, a dashed orange frame ("Video team — per part,
  parallel") around them, and a per-part status row
  (P1 ok / P2 ... / P3 -). A part selector narrows RUN STEP /
  APPROVE / RE-RUN / VIEW FILE to one part; a STOP button halts
  the run; the status table lists per-clone rows.
- Board API (`GET /api/flows/runs/<run_id>/board`): video-team
  cells take their own part's clone status (wait/run/done/ok/err,
  plus "none" when the helper skipped the cut); video stages
  carry per-part pills (`parts: [{no, clone, status}]`); every
  cut carries its part number; the step file endpoint resolves
  `node=base@pN` into the part folder (path-safe, inside the run
  only). Missing/partial stages still yield "wait", never a crash.

## Test results

No model calls, no MP4: stubs + fixtures only. 8 suites, 742
checks, 0 failures:

- parts_check 79 (split plan, clone inputs, PC rows, quotas, writer
  checks, parallel==sequential, locks, rate limiter, dedup,
  approve/re-run one part, part-only step + note, STOP/resume).
- flow_check 118 (incl. updated step-mode: final waits for every
  remy part approval, then finishes).
- pc_check 154, pick_check 34, order_check 18, results_check 90,
  video_check 81, board_check 68 (incl. mixed part states:
  ok/done/run/wait/none/err cells, per-part pills, clone files).
- Inline scripts in index.html pass `node --check` (the importmap
  block excluded: JSON, not JS).

One existing test was updated for the specified contract change:
stepping to final now refuses until every remy part is approved
(STEP 3 video gate), then finishes the run.

## The parallel switch

- `data/flows/default.json` settings:
  `{"parallel_parts": false, "openverse_per_min": 20}`.
- Keep it OFF for the first live run: the same clones run one part
  after another with identical results. Turn it ON only after the
  first stepped run is approved end to end.

## PC-rights rules (clones)

- Grant target is always the clone identity (`base@pN`), never
  the base id, for part-scoped rows.
- Source: map + only Ash's listed items for part N's scenes
  (Pia/Max/Vera clones). Voice: only part N's cut clips.
- Image / Generated Image picks: only `vera@pN`, `remy@pN`,
  `video_production` of the picking part (+ the reusing part on
  Gene reuse). Foreign-part reads fail with "no access to this
  item" (writer + view tools enforce it, not just prompts).
- Writer check: a clone's cut set must equal its given cuts;
  Gene's part quota is enforced at generate + write time.

## Choices I made

- Approving a base id approves all its parts at once (one click
  for the common case); per-part approve stays available.
- The merge stays strict: no partial merged results, so a
  part-first step on a fresh node fails with a message that names
  the missing part and says to run the whole node first.
- Board page UI (table, stage strip, side panel) was NOT built:
  that page is its own unfinished feature (Board STEP 2/3, never
  started — no Board tab exists in index.html). The API now
  returns everything the page needs; see Needs owner.

## Needs owner

- Push: `main` is 5 commits ahead of `origin/main`
  (`5d639fc`, `ca64c58`, `1d5205f`, `aeedbe7`, + this report).
- Browser proof: `scripts/flow_live_check.py` (server + headless
  Edge) could not run here — unsandboxed execution needs human
  approval and prompts are disabled. Please run it on your PC.
- Decide: build the Board page (Board STEP 2 table + side panel,
  STEP 3 screenshots) next, or run the first live order in step
  mode first. The API fields it needs (`parts[]` per stage,
  `cut.part`, clone cell statuses, `node=base@pN` file links)
  are all in place.
- First live run: keep `parallel_parts` OFF; approve story stages
  first; video_production unblocks after every remy part is ok.
- Still uncommitted, separate from this work: the Studio tab CSS
  fix (`#p-studio.active`), office bubble anchors, and the
  `studio_check.py` quote fix.

## Visual check needed

- Flow tab after Ctrl+F5: five video nodes as stacked orange
  cards with "x N" badges inside one dashed orange frame; per-part
  rows (P1/P2/...) with ok/run/wait marks; part selector +
  STOP button next to RUN STEP; clone rows under each video node
  in the step table.
- Step a fixture run to a clone (e.g. target photo_pia, part 2):
  only that part re-runs; other parts keep results + approvals.
- STOP mid-run: log shows "STOPPED: halted before ..."; the next
  step refuses; invalidate resumes.
- `GET /api/flows/runs/<run_id>/board`: video stages carry
  `parts[]`; cuts carry `part`; mixed part states show per-cell.
