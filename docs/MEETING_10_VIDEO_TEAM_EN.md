# Video Team Formation Meeting #10 — Minutes

- Date: 2026-10-31
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Settle the duties of the new video-production hires;
  close the open item from meeting #9
- Status: **Duties confirmed** — roster and responsibilities below
- Follows: MEETING_09_STORYBOARD_TEAM_EN.md (D87: video team next),
  docs/RESULT_JSON_DRAFT_EN.md §16 (v8 categories),
  docs/PLAN_V8_VIDEO_EN.md (build plan)

---

## Background (already settled)

- The product ends in a narrated MP4; the storyboard is an
  intermediate step. Storyboard team (Sam → Marty → Cleo/Rex →
  Ash) feeds the video team.
- New hires for video production: Pia (photo search), Gene
  (image generation), Max (animation planner), Remy (slide
  builder). Vera is repurposed from storyboard reviewer to
  slide planner. Wren and Penn take new stage duties (below).
- New shared stores: Image PC, Generated Image PC, Voice PC —
  same recipients mechanism as the other PCs.
- Iris (narration reviewer) is not part of the v8 flow; her
  agent folder is kept but unused.

## Decisions (confirmed 2026-10-31)

- D88: video team roster and order — Wren cuts + voices each
  Ash scene; Penn describes screens after Wren; Pia/Gene/Max
  prepare candidates once per order; Vera plans each cut's
  slide; Remy renders it; a program step (not an agent)
  assembles the video.
- D89: Wren (narration + voice) splits every scene into cuts
  of 10–30 s, writes the spoken lines with evidence, and
  voices each cut with free local TTS (`make_voice`). Audio
  off the plan by more than 15% → rewrite and redo, max 2
  attempts per cut. Clips are stored in the Voice PC.
- D90: Penn (screens + guide) runs AFTER Wren. Per cut: screen
  description (what to show, and why) + on-screen text (max 3
  lines). Plus ONE style guide (colors, fonts, image tone)
  for the whole video, based on Marty's concept.
- D91: helpers run ONCE per order and cover all cuts. Pia
  picks her own queries from Penn's descriptions — source
  figures first, else web search; search hits are never
  stored, picks are (file + source URL + license + reason);
  reuse-permitted images only, always credited. Gene picks
  only cuts needing a generated concept image, max 6 per
  run; the same prompt reuses the stored image. Max picks a
  template (bar/line chart, step arrows, formula line by
  line, table highlight) and fills values ONLY from checked
  source tables/formulas; "none" is allowed.
- D92: Vera (slide planner, repurposed) opens the candidates
  and picks as many materials as the cut needs: 1–4 blocks
  per screen, placed by space — layout preset, a box per
  block, appear times matched to Wren's words — plus
  on-screen text, cut time, and transition points.
  Table/chart/formula/steps blocks repeat Max's values
  character for character; image boxes fit the material's
  shape.
- D93: Remy (slide builder) renders each cut through Remotion
  data-only props (no free code), then looks at the still
  and adjusts ONLY layout values (position, size, font size,
  alignment, crop/zoom, padding, accent), never content. Max
  3 renders per cut; without the install he records an
  honest skip instead of a file.
- D94: assembly is a program step: join cut slides with Voice
  audio, subtitles from Wren's exact text (speech timing
  where available, proportional split otherwise),
  transcript-vs-script check to catch TTS errors. Outputs
  video.mp4 + .srt + storyboard table. No MP4 is rendered in
  tests or checks — fixtures only.
- D95: review process — the first real run goes in step mode:
  one stage at a time, each report reviewed (Korean summary
  first) before approving the next; re-running a stage
  invalidates later stages.
- D96: Ash decides per scene whether source figures, tables,
  or formulas are used and writes the recipient list; that
  list grants Wren, Penn, Pia, Max, and Vera access to the
  Source PC parts they need (same recipients mechanism).

## Scope (confirmed 2026-10-31)

In: duties of the five video members (Pia, Gene, Max, Vera,
Remy), Wren/Penn stage duties, the assembly step, review
process.
Out: parser/figure improvements (later), live runs (owner's
first step-mode run is still ahead).

Done means: this file records D88–D96; agent folders,
personas, and §16 categories already match.

## Next

- [ ] Owner runs `tools/setup_video.ps1`, then the first
  step-mode run with stage-by-stage review.
- [ ] Parser and source-figure improvements (separate step).
