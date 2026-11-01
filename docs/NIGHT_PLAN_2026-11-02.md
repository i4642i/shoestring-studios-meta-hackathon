# NIGHT PLAN 2026-11-02 — one real MP4, driven like a customer

Goal: a real MP4 out of the app by morning, every step driven through
the real browser UI with the real model. No stubs, no direct API
shortcuts for the order itself.

## 0. Inspect (read-only, no changes)
- Read STATUS.json of the two live flow runs (orders 003/006) and the
  :8000 server state. If a run is healthy and close to the end, let it
  finish (a real MP4 from any order counts). If early or stuck, go on.
- Record the starting point in the final note.

## 1. Finish the Sam tool-calling rewrite (J45, uncommitted)
- tools.py: use the order dir for form/meta (hermetic tests), catch
  all search errors as dicts.
- order_check.py: replace keyword/judge/FORM-block asserts with tool
  asserts (registry, schemas, agent.json, update_form + finalize
  guard on temp dirs, no model calls).
- Suites green: order_check, order_chat, order_received,
  order_progress, flow_check, board_check.
- Commit + push. The bat serves the new code from here on.

## 2. Night driver: behave like a customer
- Start with start_server.bat (it stops old servers itself). Open the
  app in headless Edge over CDP (the same harness the check scripts
  use; browser closed ASAP after each step, CPU rule).
- Per order, through the real UI only:
  1. Order tab: type chat messages into the input box and Send.
     Answer Sam like a normal person (beginner, 10 min, key concepts,
     real-life examples — vary wording per order).
  2. When Sam asks for the PDF: attach via the file input
     (CDP setFileInputFiles), then confirm the "attached" line.
  3. When Sam asks to start: type yes naturally ("yes I did" style —
     this is the live proof that no hard-coding remains).
  4. Watch the handover popup + parse % in the Order tab.
- Never POST to /api/* directly for order steps (polling progress or
  reading logs via API/files is fine — a customer can't, but watching
  is not doing).

## 3. Follow the run through Studio + Board to the MP4
- After handover: poll the Order progress + Board stages; screenshot
  Studio and Board at each employee (view the PNGs myself).
- Per-stage checks: Sam handover (form 4/4, PDF ref) → parse done
  (map + sections) → Marty (concept + structure) → Cleo/Rex
  (reports + picks) → Ash (scenes + time sums) → Wren (cuts + voice
  files exist) → Penn (screens + style guide) → Pia/Gene/Max
  (picks/images, licenses) → Vera (slide plan) → Remy (PNG renders)
  → video_production (video.mp4 + .srt + storyboard table).
- MP4 acceptance: ffprobe shows video + audio streams with real
  duration; extract 3 frames across the timeline and look at them;
  subtitles match Wren's lines (spot-check 2 cuts).

## 4. Stuck = any of these, then the loop below
- An error message in chat / popup / Board cell.
- No new log line, no progress %, no stage change for 10 minutes
  (parse/map/index steps get 20 minutes; TTS/CPU steps get 30).
- A screen that shows nothing (empty Board, missing panel).
- Clearly wrong output (empty form started, missing parts, nonsense
  text, unplayed files).
- Loop: close the bat (stop the server) → read TIMELINE.md,
  llm_calls.jsonl, the run folder (events/usage/inputs_check),
  the server window output, then the code → fix the real cause
  (no symptom patching) → suite for the touched area → commit +
  push → bat again → a NEW order from the beginning.

## 5. Costs and limits
- Real model for everything; log calls/tokens per run (the app logs
  llm_calls.jsonl itself; I report totals).
- Model-call failures: at most 2 retries per step, then the stuck
  loop (fix or honestly record).
- Keys stay in .env (never printed, committed, or written to logs).
- Never touch shk/, never commit orders/runs/output/storage.

## 6. Morning note (chat reply)
- The order id that produced the video + MP4 path.
- One line per fix (with commit hash).
- Anything unfixed, with the reason.
