# Stage 2 checklist — video verification 2026-11-03

Status: **BLOCKED on model billing — no full run yet.**
Crew agents call `meta-models/*` on Baseten; Baseten answers
`HTTP 402 Payment Required` (probed 2026-11-03 ~03:35 KST;
Meta-direct API answers 200, but the crew is Baseten-routed and
rerouting is an owner decision, not a night fix).

Attempted run: order `ord-20261103-002` (new, from the same client
PDF), run `flow-20261103-033309-8a91`. Sam's first model call
failed with the Baseten 402; the run stopped before any stage.
Nothing from it is reused except the empty order shell.

## Proven without models (measured, this night)

- Real 3-cut assembly: Remotion clips (20 s each) + sine WAVs
  (2.0/3.0/2.5 s) → `build_assembly` → full ffmpeg → `proof.mp4`
  **8.90 s** (2.8+3.8+3.3−2×0.5), 1280x720 h264 + AAC mono,
  audio/video stream durations equal. Caught and fixed live:
  audio indices, full-ffmpeg preference, `setpts` removal.
- Mid-crossfade frame at 2.55 s shows both cuts ghosted (0.5 s
  blend works); fade-in frame at 0.15 s is dim mid-rise.
- `scripts/video_check.py`, `flow_check.py`, `parts_check.py`,
  `board_check.py`, `pick_check.py` all green on the final tree.
- Items 2–6, 8, 12 render-verified on stills (Stage 1 checklist).

## Resume procedure (after Baseten top-up)

```bat
.\.venv\Scripts\python.exe scripts/stage2_run.py --src-order ord-20261102-030 --new-order ord-20261103-003
```

Repeat per fix-file iteration from the changed employee only:

```bat
.\.venv\Scripts\python.exe scripts/stage2_run.py --resume <run_id> --from <node>
```

When all rows below pass, do ONE final full run from a new PDF
order with nothing reused, verify that run, keep its MP4 + run
folder, and fill the measured column.

## Measurement rows (run id: TBD — final run)

| # | Measure (command / file) | Expected | Measured | Pass |
|---|---|---|---|---|
| 1 | `assembly.json` seg dur vs `wav_seconds` per cut; ffprobe audio dur == video dur; SRT end == seg end − 0.8 | equal, no crossing, no gap > 1.5 s | — | BLOCKED |
| 2 | Render log (Inter load) + PNG crop | style-guide Inter, no serif | pre-verified on stills (Stage 1) | PENDING final run |
| 3 | Script: onScreenText lines vs text-block lines in drafts + PNG | no sentence twice | — | BLOCKED |
| 4 | Sidecar `font_size` ≥ 32 (text); PNG | readable, box-filling | pre-verified on stills | PENDING final run |
| 5 | Render logs `renders_n`; sidecar vs viewed PNG | 1 when clean; overrides stick | — | BLOCKED |
| 6 | `slides/*.mp4` durations == cut seconds; joint frame; `xfade` in cmd | motion + 0.5 s blends | pre-verified (proof.mp4) | PENDING final run |
| 7 | Count image blocks vs cuts without photo/figure | blocks ≥ needy cuts | — | BLOCKED |
| 8 | Draft preset counts + card PNG | text-only cuts are cards | pre-verified on still | PENDING final run |
| 9 | Scan `on_screen_text` for `<->`/colon shorthand | plain sentences, quotes marked | — | BLOCKED |
| 10 | Max words per `captions.srt` block | ≤ 12 | — | BLOCKED |
| 11 | Cut durations in narration | mostly 10–15 s, all 10–30 s | — | BLOCKED |
| 12 | PNGs with bottom line + low blocks | translucent bar, readable | pre-verified on still | PENDING final run |

Also pending on the final run: `parallel_parts: true` timing,
Remy 1 render per clean cut, Commons-before-Openverse + skipped
transcribe in the logs, index backfill still backgrounded
(theory 25/42, article 0/124 at 03:50 — backfill itself needs the
model API, so it waits on the same top-up).
