# v8 fix round report (2026-11-01)

## 요약 (한국어)

- v8 수정 5단계를 전부 끝내고 커밋했습니다 (푸시는 안 함, 직접 해주세요).
- Remy가 이제 SVG 대신 Remotion PNG 스틸을 뽑습니다. 미설치면 정직하게 스킵합니다.
- Vera는 진짜 재료만 씁니다: Max 값을 그대로 복사, 사진/그림은 실파일 확인, 박스 비율 검사.
- 영상 조립 단계가 컷마다 props+PNG+음성을 기록으로 남깁니다.
- 테스트 6종 + 브라우저 2종 전부 통과. 모델 호출·MP4 렌더·설치는 일절 안 했습니다.
- PC에서 할 일: 푸시 → setup_video.ps1 실행 → 스위트 재실행 → 화면 확인 (아래 순서 참고).

## Scope

Fix round for the v8 workflow (storyboard team + video production
team), after commit `43acfac`. Five steps, one commit per step, no
push. Rules kept for the whole round: no MP4 and no live runs of
any kind (no LLM/TTS/image/speech calls — zero model calls were
made), no package installs (setup script written for the owner
instead), never print or commit keys, never touch or commit `shk/`,
branch `main`, commit only.

Commits (all on `main`, ahead of `origin/main`):

- `d40bf29` STEP 1: drop probe/cache leftovers, ignore them
- `58904e9` Studio: responsive full-viewport office (done between
  STEP 1 and STEP 2 per owner message)
- `26e9984` STEP 2: Remotion CutSlide stills + slide v2 layout +
  honest skip
- `f7c5f35` STEP 3: Vera real materials (anim v2, exact data copy,
  aspect)
- `bfa43ba` STEP 4: code node records props + PNG + voice per cut
- (this report) STEP 5

## What is built and tested

STEP 1 — cleanup. Probe/cache folders deleted, git-ignored.

STEP 2 — Remotion for Remy.

- `video/remotion/`: one 1280x720 `CutSlide` composition (props
  only, no free code): `cutId, seconds, preset, blocks,
  onScreenText, guide`. Blocks: photo/generated/source_figure
  (contain fit), table (row reveal), formula (KaTeX, line by
  line), chart (bar/line SVG), steps (arrow chain), text.
- `render_slide` shells to `npx remotion still` into
  `slides/<cut>.png` (last frame of the cut). Without the
  install it skips honestly: ok + `status remotion_unavailable`
  + `renders_n 0` + install hint; the 3-render cap still
  applies. The video node records an empty slide instead of
  failing.
- `slide_draft` v2: preset + 1–4 boxed blocks.
  `validate_cut_layout` checks: boxes inside the 64px safe area,
  no overlap, fonts ≥20px, reveal steps finish inside the cut,
  kind-shaped data. Registry `slide_draft` v2; `render_log`
  gains `status`.
- `tools/setup_video.ps1`: installs/checks Node, Remotion deps,
  ffmpeg, espeak-ng, Kokoro (syntax-checked, never executed
  here). README + third-party credits list Remotion (marked
  proprietary), KaTeX, React.

STEP 3 — Vera real materials.

- `anim_picks` v2: use picks carry template
  (bar|line|table|formula|steps) + structured values + refs[]
  ({ref, quote}). The writer checks every ref is a CHECKED
  source table/formula quoted verbatim, and traces every data
  scalar to the quotes (steps items exempt: Max's own
  compression, refs still required).
- Vera data blocks (table/formula/chart/steps) copy Max's use
  pick for their cut exactly: matching template, equal values.
- photo/generated blocks must be backed AND readable from the
  stored entry; source_figure blocks must point at figure
  passages. Image boxes must match the material aspect within
  50% (dims stored on image/generated entries; parser w/h for
  source figures; unknown dims skip quietly).
- Text-card code removed (`render_text_card`, dead constants).
  Vera persona rewritten for blocks.

STEP 4 — code node records.

- `render_slide` writes `slides/<cut>.props.json` (exact render
  inputs, guide included) on render AND on skip.
- `build_cut_records`: per-cut `{cut_id, at_s, dur_s, props,
  slide, slide_status, audio, voice_ref}`; assembly segments
  ARE the records. Gaps record null, never a guess.
- No flow-line change: the owner design gives the code node
  Penn's storyboard but no style_guide line (verified against
  `shk/design.json`, not quoted), so the guide travels inside
  Remy's sidecar instead of a new transfer.

STEP 5 — this report. All suites re-run green (below).

## Choices I made

- One `CutSlide` composition for all materials (not one
  template each): the layout check and the renderer share one
  block contract. Reason: a single contract cannot drift.
- Layout numbers: 64px safe area (5%), 20px min font, max 4
  blocks, reveal steps 0.5/1.0/0.8s. Reason: readable at 720p,
  reveal always fits a 10–30s cut.
- A skipped render consumes one of the 3 tries. Reason: the cap
  counts attempts, and the log shows renders_n 0 anyway.
- Unavailable slides record `""` in the assembly; the
  ffmpeg command then carries an empty input. Reason: honest —
  the command visibly cannot run until Remy renders.
- anim values-trace exempts steps items. Reason: step labels
  are Max's compression and cannot be verbatim; refs still
  ground them.
- Aspect tolerance 50%, unknown dims skip. Reason: catch
  portrait-box-for-landscape-photo mistakes without failing
  old entries that never stored dims.
- Props sidecar instead of a new Penn→video style_guide line.
  Reason: the owner design has no such line; the sidecar
  captures byte-exact render inputs with no flow change.
- Text blocks need no helper backing. Reason: they are Vera's
  short labels, not source data.

## Needs owner

- `git push origin main` (5 fix commits + this report are local
  only).
- Run `powershell -ExecutionPolicy Bypass -File
  tools/setup_video.ps1` (needs Node.js 16+ and ffmpeg on
  PATH first; espeak-ng + `pip install "kokoro>=0.9.4"` for
  local TTS).
- After the install, re-run the six suites + headless (one real
  `npx remotion still` smoke happens only inside your own
  runs, never in the checks).
- CutSlide.jsx/index.js are logic-reviewed only (brace
  balance + config `node --check` pass); the first real still
  render proves them.
- Jetson index: press REBUILD INDEX yourself (never indexed
  from the sandbox).
- Visual confirms below (Ctrl+F5).

## Check results

All green at `bfa43ba`, stubs + fixtures only, no model calls:

- `flow_check.py`, `results_check.py`, `video_check.py`,
  `pc_check.py`, `pick_check.py`, `order_check.py`: ALL PASS
- `flow_headless.py` (Edge): ALL PASS
- `studio_check.py` (1280x720, 1920x1080, 390x844): ALL PASS
- `validate_agent.py` on `board_vera`, `anim_max`: PASS
- `node --check` on `remotion.config.js`: OK;
  `package.json` parses; `setup_video.ps1` tokenizes with 0
  errors
- No MP4 rendered, nothing installed, `shk/` untouched
  (`git status` shows no `shk/` entry), no keys printed or
  committed.

## What to check first on your PC (in order)

1. `git push origin main`, then `git log --oneline -7` shows
   the six commits above.
2. `tools/setup_video.ps1` output table: node/npm/Remotion
   deps yes; ffmpeg/espeak-ng/Kokoro per your installs.
3. Six suites + headless re-run: all ALL PASS.
4. Flow tab after Ctrl+F5: default flow loads, lines draw.
5. Studio tab: full-viewport office, chat collapse works.
6. Start a real run in step mode (see
   `docs/REPORT_2026-11-01_V8_EN.md` "first run" steps);
   expect `remotion_unavailable` logs until STEP 2's install
   is done, then real PNGs in `slides/`.
