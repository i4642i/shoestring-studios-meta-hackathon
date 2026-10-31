# V8 Video Plan (storyboard team + video production team)

Goal: automatic content generation ending in a narrated MP4.
The storyboard is an intermediate step. Source of truth for the
workflow is the owner's private drawing (design v8, git-ignored);
this file is the build plan derived from it. Sam's `source`
removal (Sam result = `request` only, old results still load)
stays in scope. Parser and source-figure improvements stay LATER.

## Goal

Thin end-to-end first (Phase A): cuts + local-TTS voice, cut
screen descriptions + style guide, text-card slides, joined
MP4 + subtitles + storyboard table. Then real helpers, vision
picking, the Remy visual loop, and speech checks (Phase B).
Step mode lets the owner review and approve every stage.

## Success Criteria

- Phase A: a fixture order runs Sam→…→video.mp4 + .srt +
  storyboard table with stubs for Pia/Gene/Max, all checks green.
- Phase B: real photo search (licensed+picks stored), image
  generation (<=6/run, prompt reuse), template animation from
  checked tables/formulas, Vera vision picks, Remy ≤3 re-renders.
- Step mode: run one node, show report + INPUTS + cost, approve /
  re-run with note / stop; re-run invalidates later stages.
- No live calls anywhere in this build; tests use stubs/fixtures.

## Approach

Reuse before invent: same recipients/list PC mechanism for the
three new PCs, same writer-tool + schema-check pattern for new
categories, same run_dir layout for step mode, flow.py executes
the video-production code node like today's final collector.
One material deviation from the drawing, forced by evidence:
Meta's transcribe API returns turn-level timestamps only (see
1b), so word timing = turn times + proportional split inside a
turn (the planned fallback becomes the design).

## Steps

### STEP 1b — verification results (official sources only)

1. Local TTS. RECOMMENDED: Kokoro (`kokoro` 0.9.4, Apache-2.0
   per PyPI classifier + license text, Python >=3.10,<3.13,
   needs torch + transformers + misaki + huggingface-hub, 82M
   params, CPU-capable, 24 kHz, EN quality good). Caveats:
   needs the espeak-ng system package for English fallback
   (espeak-ng is GPL-3.0, COPYING verified) and a manual
   Windows install. FALLBACK: Piper (`piper-tts` 1.8.0,
   GPL-3.0-or-later per PyPI metadata, needs onnxruntime,
   Windows CPU wheels, MIT/CC voices, lower quality).
   Decision: build `make_voice` against Kokoro with a
   stub-or-local engine switch; do NOT install toolchains in
   this build (see Needs owner in the final report).
2. Remotion. Free License covers individuals and companies up
   to 3 people, all features, unlimited commercial use
   (remotion.pro/license). Company License above that
   (Creators $25/seat/mo, Automators $0.01/render, $100/mo
   minimum). Node requirement: `engines.node >= 16` in the
   official package.json (local Node is v24, satisfied).
   WARNING: Remotion is proprietary source-available
   ("SEE LICENSE IN LICENSE.md"), NOT open source; credits
   must say so. Decision: Remotion templates for Remy +
   ffmpeg fallback. ffmpeg is NOT on local PATH (checked).
   Implemented (fix round): video/remotion/ holds the CutSlide
   composition (props: cutId, seconds, preset, blocks,
   onScreenText, guide); render_slide runs `npx remotion
   still` per cut into slides/<cut>.png; without the install
   it returns status remotion_unavailable (renders_n 0) and
   the video node records an empty slide instead of failing.
   No MP4 is rendered anywhere in tests or checks.
3. muse-voice-transcribe-1.0. Turn-level timestamps ONLY; no
   word-level timestamps, no confidence scores (official Meta
   speech-to-text docs, verbatim). Price $0.18/audio hour is
   secondary-source only (not confirmed on Meta's pricing
   page, which bills by audio second). Decision: subtitle
   timing = turn times + proportional word split; TTS-error
   check = transcript-vs-script text compare per turn.
4. muse-image-1.0. $0.01 per generated image, flat, built-in
   search included (official Meta pricing page). Decision:
   max 6 images/run stays; at most $0.06/run image cost.
5. Image search. Openverse API (`api.openverse.org/v1/`,
   official OpenAPI schema inspected): `/v1/images/` with
   `license`, `license_type`, `page_size` filters over
   openly-licensed media. Terms (official ToS): obey rate
   limits, no scraping, per-item license compliance, may
   charge commercial use later. Anonymous limits ~20/min,
   200/day are per a maintainer reply (semi-official); real
   limits come from response headers. Decision: query with
   `license_type=commercial` minus `by-nd` (we crop), store
   file + source URL + license + reason per pick, always
   credit.

### New agent folders (AGENT_STANDARD_EN.md layout)

- `agents/photo_pia` (Pia, photo search, stage 7)
- `agents/image_gene` (Gene, image generation, stage 7)
- `agents/board_vera` REPURPOSED (Vera, slide planner,
  stage 8; reviewer persona/handbook replaced)
- `agents/slide_remy` (Remy, slide builder, stage 9)
- `agents/anim_max` (Max, animation/formula/graph, stage 7)
- Wren stage stays 5→runs before Penn; Penn stage 6.
- Model for all AI steps: meta-models/muse-spark-open-1026.
- Video production is a code node (`video_production`,
  `"code": true` in the flow file), executed by flow.py via
  a new video module — never by the LLM runner.

### Schemas and code checks (all versioned, writer-checked)

- `narration` v2 (Wren, replaces v1 scenes): `cuts[]` with
  `cut_id, scene_n, start_s, end_s` (10–30 s), `lines[]`
  (text + citations), `words`, `audio {voice_pc_ref,
  seconds}`, `attempts`. Checks: cut times tile their scene
  (±15% vs Ash), audio seconds within ±15% of cut time,
  attempts ≤2/cut, facts cited verbatim.
- `storyboard` v2 (Penn, replaces v1 scenes): `cuts[]` with
  `cut_id, start_s, end_s, show_what, show_why,
  on_screen_text[≤3 lines]`. Checks: cut set/times equal
  Wren's exactly, text ≤3 lines, source-grounded claims.
- `style_guide` v1 (Penn, new): `palette, fonts,
  image_tone, rules[]`. Checks: all fields present.
- `photo_picks` v1 (Pia): per cut `pick|null|"none"` with
  `kind (source_figure|web), ref|file, source_url, license,
  reason`. Checks: license in allowlist
  (cc0/pdm/by/by-sa minus nd), unviewed never used.
- `gen_picks` v1 (Gene): per cut prompt or null + `images[]`
  (≤6/run, prompt reuse by hash). Checks: count cap,
  concept-only (no photoreal-fact look — persona rule).
- `anim_picks` v2 (Max): per cut `use|none` with template
  (bar|line|table|formula|steps) + structured `values` +
  `refs[]` ({ref, quote}). Checks: cut match; values shaped
  by template; every ref a CHECKED source table/formula
  quoted verbatim; every data scalar traced to the quotes
  (steps items exempt: Max's own compression, refs still
  required).
- `slide_draft` v2 (Vera): per cut `preset` +
  `blocks[1..4]` (kind, 1280x720 box, order, appear_s,
  reason + kind data), `on_screen_text, transitions[],
  why`. Checks: cut set + times match Wren; boxes inside
  the 64px safe area, no overlap, fonts ≥20px, reveal
  steps finish inside the cut; photo/generated backed by
  helper picks.
- `render_log` v1 (Remy): per cut `slide_file,
  adjustments[]` (layout values only), `renders_n ≤3`,
  `issues[]`, `status` (rendered|remotion_unavailable).
  Checks: content fields equal Vera's; unavailable cuts
  log renders_n 0 with an empty slide_file.
- Final: existing `video` + new `storyboard_table` v1
  (part, scene, cut, narration, screen, materials).

### Flow file + Flow tab (design v8)

- Nodes: add Pia, Gene, Max, Vera(active), Remy,
  `video_production` (code node, distinct style, never
  draggable-run by runner), Image/Generated/Voice PCs;
  Final takes `video` + `storyboard_table`.
- Solid: Ash→Wren, Ash→Penn; Marty concept→Wren/Penn;
  Wren→Penn, Wren→Vera, Wren→Remy, Wren→video;
  Penn descriptions→Pia/Gene/Max/Vera;
  Penn style_guide→Pia/Gene/Max/Vera/Remy;
  helpers→Vera; Vera→Remy; Remy→video;
  Ash/Penn/Vera/Marty-structure→video (table inputs);
  video→Final. Wren's two design ports merge into one
  `narration` v2 line (times embedded per cut).
- Dotted: Wren→Voice PC, Voice PC→video; Pia↔Image PC
  (search/pick/results-not-stored), Image PC→Vera/Remy;
  Gene→Generated PC, Generated PC→Vera/Remy;
  Source PC→Pia/Max/Vera/Remy (figures, checked
  tables/formulas, files); Ash recipient lists extended
  to Wren/Penn/Pia/Max/Vera.
- Tab: code-node rendering + step-mode controls (STEP 3).

### Cost caps per run and enforcement

- LLM: existing per-agent max_steps; counts/tokens already
  logged per run.
- Images: 6/run (Generated PC counts stored images per
  order_id; 7th tool call refused).
- Vision: Vera opens ≤4 candidate files/cut (counter in
  run_dir); Remy renders ≤3/cut (render tool counts).
- TTS: ≤2 attempts/cut (make_voice counts per cut).
- Searches: Tavily unchanged; Openverse ≤2 queries/cut
  (counter in run_dir).
- Every cap refuses with a clear error naming the cap;
  step mode shows spent cost before each approval.

### Build order

- Phase A: Sam source removal; agent folders + personas;
  categories + schemas + writer tools + checks; 3 new PCs
  (storage + recipients + read tools); make_voice
  (Kokoro adapter + stub engine + duration read);
  Pia/Gene/Max stubs ("none"); Vera layout drafts (v2
  boxed blocks); Remy Remotion stills (PNG per cut,
  honest skip without the install); video assembly
  (join + .srt + table over Remotion PNGs);
  flow v8 file + tab; step mode; fixtures + suites green.
- Phase B: real Pia (Openverse search+pick), Gene
  (muse-image + reuse), Max (templates + checked values),
  Vera vision picking, Remy visual loop (screenshot +
  Spark Open vision + layout-only adjust), speech checks
  (turn sync + transcript compare + proportional subs).

## Validation Plan

- New suites: voice/tts check (stub engine durations),
  video assembly check (fixture cuts → timing table + .srt
  exact), step-mode check (run/approve/re-run/invalidate),
  extended pc/flow/order/results checks. No live calls.
- One render smoke test max (fixture data, seconds long,
  file deleted) only to prove the toolchain; needs owner
  for installs/prompts, else skipped and logged.
- Manual: owner reviews step-mode first run (see report).

## Risks / Open Questions

- TTS install (torch+espeak-ng on Windows) may need owner
  → fallback: stub engine + everything else built.
- Remotion blocked → ffmpeg path (ffmpeg also not on
  PATH; Remotion downloads its own ffmpeg via npm).
- No word timestamps (confirmed) → proportional timing.
- Wren/Penn schema replacement retires v1: old results
  keep loading (version field), new runs write v2.
- Openverse commercial billing later → Image PC stores
  per-pick license so swaps stay possible.

## Sources

- https://pypi.org/pypi/piper-tts/json
- https://pypi.org/pypi/kokoro/json
- https://api.github.com/repos/espeak-ng/espeak-ng/license
- https://www.remotion.pro/license
- https://raw.githubusercontent.com/remotion-dev/remotion/main/packages/core/package.json
- https://raw.githubusercontent.com/remotion-dev/remotion/main/packages/docs/docs/getting-started.mdx
- https://raw.githubusercontent.com/remotion-dev/remotion/main/packages/create-video/package.json
- https://raw.githubusercontent.com/remotion-dev/remotion/main/package.json
- https://dev.meta.ai/docs/speech-to-text
- https://dev.meta.ai/docs/pricing-rate-limits
- https://api.openverse.org/v1/schema/
- https://docs.openverse.org/terms_of_service.html

## Audit note

Plan written and committed per explicit user order ("commit
it, then continue immediately"); execution follows in the
same session without a go gate.
