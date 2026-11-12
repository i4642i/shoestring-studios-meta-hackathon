# Inputs v8.2 + Board page — report (2026-11-01)

## 한국어 요약

- 이번 라운드(STEP 0→6) 전부 완료. 체크리스트 28개 항목 모두 [x].
- 에이전트별 입력 정리: Marty 지도 우선, Penn 목록만, Ash 전문 제거, 복사 직원 3종 입력, 경계 대사.
- Vera 이미지 열기는 컷당 2개로 제한 (검사 포함).
- Ash handoff에 Remy 허용, 장면 10초 이상, PC 행 kind=map 확인.
- 영상 제작 테이블은 복사 직원 결과의 파트 정보로 조립 (Marty 직접선 제거).
- Flow 탭 전체화면 + Board 페이지 신규. 둘 다 headless 캡처로 직접 확인.
- 테스트: 8개 스위트 + Board/Flow live check 전부 통과. 모델 호출 0, MP4 없음.
- 내일 확인할 것: Board 탭에서 실제 run 열어보기, Flow 탭 390px에서 그래프 조작감.

## Scope

Round: inputs v8.2 + Board page. STEP 0 (leftover Studio commit) →
STEP 1 (per-agent inputs) → STEP 2 (Vera view budget) →
STEP 3 (Ash rules/handoff) → STEP 4 (video table via clones) →
STEP 4b (Flow tab fullscreen) → STEP 5 (Board page) →
STEP 6 (suites + this report). Leftover E3/B5 fixed before STEP 6.

Rules kept: no push, no model calls, no MP4, never touched or
committed shk/, no new packages, no keys printed.

## What changed per STEP

- STEP 0 (`e2f4e80`): Studio tab CSS, bubble anchors, check quote
  fix. Checklist file (`125fdf6`).
- STEP 1 (`b41e7ba`): Marty reads the Source PC map before full
  text; Penn gets figure/table/equation lists (ref + title only);
  Ash full-text preload removed (`pc_read_source` kept); Penn no
  longer gets Wren cut times (the writer copies them); three
  clone input blocks (Pia/Max without concept, Gene/Vera with
  concept, Remy cut times + style guide + Vera draft only);
  boundary lines for Pia/Gene/Max/Vera (last cut of prev part +
  first cut of next part, read-only; Remy excluded); checks
  compare IDs/keys.
- STEP 2 (`3c6c9c3`): Vera picks from candidate descriptions
  first and opens at most 2 images per cut (`vera_view_image`
  tool cap + writer check + persona note). Check: a 4-candidate
  cut opens at most 2.
- STEP 3 (`858e3a9`): `slide_remy` allowed in Ash handoff,
  part_split writes `slide_remy@pN` rows; scenes must be at
  least 10 s; handoff rows are kind=map. E3 closed later
  (`eb28911`): parts_check now asserts Source/Theory/Article
  rows are kind=map + parts with set_by=part_split, scoped to
  the right part only.
- STEP 4 (`900025e`): video_production drops the Marty
  structure line; part info travels on merged clone results;
  storyboard_table.json unchanged.
- STEP 4b (`c48c67f` + `eb28911`): Flow canvas fills the
  viewport height (ResizeObserver, tab-show refit, shrink loop
  so the page itself never scrolls); footer + body bottom
  padding hidden on the Flow tab; hint hidden under 700 px;
  Crew/Steps drawers overlay the canvas (default collapsed);
  Fit on both axes; wheel zoom 40–200% cursor-centered; drag
  pan; under 70% nodes show name + role and labels go
  hover-only. B5 closed in `eb28911`: flow_live_check asserts
  21 nodes, no overlap, no page scroll at 1920/1280/390, and
  saves three screenshots; the old "labels visible" assert is
  now zoom-conditional (below 70% hidden labels are correct).
- STEP 5 (`fb2a608`): Board tab — header (title, run picker,
  Run step / Approve / Re-run with note / Stop, part selector,
  6-item legend), stage strip (10 pills, per-part pills for
  the video team), 12-column cut table (2-row header,
  STORYBOARD blue / VIDEO orange, Part/Scene rowspan,
  6 status colors, thumbnails, pulsing run dot, 3 s refresh
  while running), side panel (per-column cards: voice audio,
  photo gallery, Vera layout minimap, Remy render log, cost +
  report.md/result.json/INPUTS.md links); under 1000 px the
  panel drops below the table. New scripts/board_live_check.py
  (fixture run + Image PC pick, 10 pills, 12 cols, per-part
  pills, cell/minimap/log/style-guide clicks, thumbnails,
  390 px stacking, zero console errors). Also fixed a real
  server bug: the runs list included plain files (logs, PNGs);
  it now lists directories only.

## Test results

- Fixture suites, all green: parts, flow, pc, pick, order,
  results, video (`ALL PASS` / `fails: 0`), board (`fails: 0`).
- scripts/board_live_check.py: ALL PASS (17 asserts, incl.
  3 cut rows x 12 cols, photo cell click, side-panel cards,
  thumbnails in cell + gallery, 390 px stacking, 0 console
  errors). Screenshots: runs/board_1920.png,
  runs/board_1280.png, runs/board_cell.png (looked at all
  three: merged cells line up, no overlap, colors match).
- scripts/flow_live_check.py: ALL PASS (47 solid + 44 dotted
  paths at their own dots, 21 nodes, no overlap, no page
  scroll at 1920/1280/390). Screenshots: runs/flow_1920.png,
  runs/flow_1280.png, runs/flow_390.png (looked at 1920 and
  390; 1280 layout numbers logged: scroller top 315 h 278
  docH=winH 720).
- Canvas vs viewport: Board is a normal scrolling page (no
  page h-scroll at 1920). Flow scroller: 1920 → fills below
  toolbar (zoom after Fit 52%); 1280x720 → scroller h 278,
  docH=winH; 390x844 → scroller h 249, docH=winH.
- Model calls: 0. MP4/video/audio renders: none. No Baseten
  deployments, no installs.

## Choices I made

- Runs list bug: list directories only (logs/PNGs in runs/
  are not runs). One-line server fix, covered by both live
  checks.
- Live-check Edge profiles moved to the OS temp dir so they
  never pollute runs/ or the run picker.
- Old flow label assert vs B4 far-zoom rule: made the assert
  zoom-conditional instead of weakening the rule.
- Flow page-scroll fix: hide footer + body bottom padding on
  the Flow tab, shrink loop in fitLayout, min scroller 200 px,
  hint hidden under 700 px. No DOM moves.
- Thumbnail fixture: a 1 px PNG in a throwaway Image PC entry
  (created + deleted by the check) so the cell/gallery img
  paths execute for real.

## Needs owner

- Push `main` when ready (several local commits, no push from
  here). Never push shk/ (still git-ignored).
- First real run is still done in step mode on your PC; then
  open the Board tab on that run id.
- Board "Running" pulse + auto-refresh and Remy PNG cards
  only light up with a real running run; fixtures cover the
  code paths, not the live look.

## Visual check needed

- Board tab on a real run: per-part pills while parts run,
  run-pulse dot, voice audio play, Remy PNG + log, Vera
  minimap vs the PNG.
- Flow tab at 390 px: pinch/wheel zoom and pan feel on a
  small screen (layout fits; handling is yours to judge).
- Flow tab: hover a solid line at Fit zoom and confirm the
  label appears (hover-only under 70%).
