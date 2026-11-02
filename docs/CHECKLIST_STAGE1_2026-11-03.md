# Stage 1 checklist — video fixes 2026-11-03

One row per fix-file item. (a) file/function/persona changed,
(b) commit hash, (c) how to see the fix in a rendered slide or
the MP4. All 12 committed on `main` in item order.

| # | Changed (file / function / persona) | Commit | How to see it |
|---|---|---|---|
| 1 | `agents/_frame/video.py` (`wav_seconds`, `retime_narration`, `build_assembly` xfade/apad/clips); `agents/_frame/flow.py` (`_run_code_node` measures WAVs, prefers clips) | `daf1559` | `assembly.json` segments follow WAV lengths (+pad); `ffmpeg_cmd` has `xfade`+`acrossfade`+`apad`; audio length == video length, no trailing silence |
| 2 | `video/remotion/src/CutSlide.jsx` (`loadFont` Inter + `delayRender`, `mapGuideFont`); `video/remotion/src/index.js` (guide defaults); `package.json` (`@remotion/google-fonts`) | `a8e86c9` | Still render: sans letterforms, no Times serif; headless probe page reports `Inter loaded: true` |
| 3 | `CutSlide.jsx` (bottom line only without a text block); `agents/board_vera/persona.md` (anchor rule); `schemas.py` `validate_cut_layout` (dup reject) | `46e35d8` | Still with text block + `onScreenText`: bottom line absent; writer refuses a repeated sentence |
| 4 | `schemas.py` (`MIN_FONT_TEXT=32`, text min); `CutSlide.jsx` (`fitTextFont` 32–72, bottom line 36); Vera persona (box rule) | `72abb5d` | Text fills its box (72 px in the probe still); props sidecars never carry text under 32 |
| 5 | `agents/_frame/video.py` (`cut_slide_props`+`apply_overrides`); `agents/_frame/tools.py` (`render_slide` `overrides`); `agents/slide_remy/persona.md` (render→view→override→render); `CutSlide.jsx` (font/position/align) | `4cf96cd` | `slides/<cut>.props.json` carries Remy's values; still re-renders moved/centered |
| 6 | `CutSlide.jsx` (0.5 s fade+rise, image 1.0→1.06 zoom, row/item fades); `tools.py` (`render_slide` renders MP4 clip + PNG still); `video.py` (no 30 s clamp); `index.js` (no cap) | `531802b` | Clip frames at 0.15 s (dim, mid-fade) vs 4.5 s (full); per-cut `slides/<cut>.mp4` exists; assembly uses `xfade` |
| 7 | `agents/_frame/parts.py` (split budget = cut count); `schemas.py` (`validate_gen_picks` one-per-cut cap); `agents/image_gene/persona.md`, `agents/board_vera/persona.md` (quota + image-first rules) | `ab4cfbd` | `split.json` quotas equal part cut counts; run holds up to one image per cut |
| 8 | `schemas.py` (`LAYOUT_PRESETS` + `card`); `CutSlide.jsx` (`CARD_BOX` centered + fit font); Vera persona (text-only → card) | `aadbb06` | Card still: one centered full-screen line, no corner boxes, no bottom line |
| 9 | `agents/board_penn/persona.md` (plain-sentence rule) | `25c0d5d` | New storyboards: full sentences, no `<->`/colon shorthand, quotes marked |
| 10 | `agents/_frame/video.py` (`srt_blocks` ≤12 words, `_multipart_body` CRLF, `SKIP_TRANSCRIBE`); `agents/_frame/flow.py` (skip keeps proportional) | `8abf1e9` | `captions.srt` blocks ≤ 12 words; multipart body ends `CRLF--bound--CRLF` |
| 11 | `agents/voice_wren/persona.md` (10–15 s aim) | `244ec8a` | New narrations prefer 10–15 s cuts (10–30 s stays the hard range) |
| 12 | `CutSlide.jsx` (translucent bottom bar) | `16126b9` | Still with low block + bottom line: text sits on a dark band, readable |

Checks run per item: `scripts/video_check.py`, `scripts/flow_check.py`,
`scripts/parts_check.py` (plus `board/pick/results/office/gallery`)
green after each commit; still/clip renders viewed for items 2–6,
8, 12. Two maintained-test contracts moved with the spec on purpose:
`video_check.py`/`flow_check.py` assembly timing (measured voice +
crossfade instead of planned concat) and `parts_check.py` Vera
fixture (no repeated sentence); `video_check.py` gen-cap message
(one-per-cut instead of 6).

Deliberate deviations from the fix file:
- Item 1: segment = voice + 0.5 s fade tail of silence + 0.3 s breath
  (multi-cut), voice + 0.3 s (lone cut). The 0.5 s tail keeps the
  item-6 crossfade from ever dipping into speech.
- Item 10: `transcribe_file()` stays skipped (`SKIP_TRANSCRIBE=True`)
  until the audio API 400 is verified fixed; the multipart CRLF fix
  is in but unproven live.
- Item 11: persona nudge only (schema range untouched).
- Item 12: translucent bar (no validator 600-reservation), so old
  drafts keep validating.
