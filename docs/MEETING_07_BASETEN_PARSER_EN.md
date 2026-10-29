# Cost & Parser Meeting #7 — Minutes (Final)

- Date: 2026-10-29
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Cut LLM spend by moving to Baseten; verify the PDF parser pipeline
- Status: **Final** — accepted 2026-10-29
- Follows: MEETING_06_SALES_EN.md (D70 order memory)

---

## Background (already settled)

- D70: order chat context is the server transcript; message-count caps
  removed (only the ~8000-char transcript budget and per-message 2000
  chars remain as API guards).
- All model calls (crew chat, order chat, extraction, runner) go
  through one function: `agents/_frame/runner.py::_chat`.
- PDF intake parses on arrival: PDF → `parsed.md` + `images/` via
  pdfplumber 0.11.10 (MIT), order-scoped under `orders/<id>/`.

## Decisions

- D71: Baseten is the second model provider (cost reduction).
  Base URL `https://inference.baseten.co/v1`, model exactly
  `meta-models/muse-spark-open-1026` (OpenAI-compatible), key
  `BASETEN_API_KEY` from repo `.env` (never printed, never logged).
  Routing lives in the runner: `meta-models/*` → Baseten, everything
  else → Meta Model API (unchanged). Missing-key errors name the
  right variable per model. Verified: live "Hello!" call answered.
  No Baseten deployment created. Settled 2026-10-29.
- D72: Baseten is the DEFAULT model. Marty and Sam run on it, new
  employees default to it, and it heads the model dropdowns (Crew
  tab + add-employee form). Meta `muse-spark-*` / `muse-wonder-1.0`
  stay selectable. Validator allowlist + standard + docs updated;
  smoke pins the default (`create defaults to baseten`). Settled
  2026-10-29.
- D73: LightRAG's LLM moves to Baseten too (`config.json` URL +
  model + `llm_key_env`). Embeddings stay local MiniLM (free, no
  re-index needed for that). Old indexes were Meta-built and their
  markers say so, so the Crew knowledge map stays honest; the
  adapter now records the build-time LLM on every new index.
  Re-run `run_index.py` to rebuild an index on Baseten. Settled
  2026-10-29.
- D74: the PDF parser is verified working: direct pdfplumber run
  extracts text; the upload pipeline (multipart → `source.pdf` →
  `parsed.md` + `images/` + meta) is green in smoke. Scanned
  (image-only) PDFs are rejected with "no extractable text" —
  expected, OCR stays out of scope. Verified 2026-10-29.
- D75: hidden file inputs MUST be label-activated. The free-chat
  "Attach PDF" button was dead because its `display:none` input sat
  in a `<span>` (guided "Choose PDF" worked only because it sits in
  a `<label>`). Both free-chat attach and Crew train upload are now
  `<label class="filebtn">`. Fixed 2026-10-29.

## Design notes (user-stated, shape the build)

- Cost first: Baseten serves the same Spark-class model cheaper,
  so it becomes the default everywhere an LLM is called.
- Keys live in `.env` only; the server refuses `.env` over HTTP
  (403) and no key value is ever printed or logged.
- Parser test uses a real text PDF through the chat attach button,
  not a fixture: success reads `Attached <name>: parsed N pages,
  M chars, K images.`

## Scope (accepted 2026-10-29)

In: Baseten provider + default (agents, LightRAG LLM, docs, tests);
PDF parser verification; attach-button fix.
Out: OCR, LightRAG re-index on Baseten (on demand), live PC monitoring.

Done means: validator green on both agents; smoke green incl. the
new default check; one real PDF attached through free chat.

## Next

- [ ] User live test: attach one text PDF in Order free chat.
- [ ] User live test: one LightRAG query on Baseten
  (`.venv-lightrag` + `RAG_BACKEND=lightrag`), then optional re-index.
- [ ] Rerun `python scripts/smoke_server.py` on the user PC (sandbox
  blocks socket bind here) and restart `:8000` via `start_server.bat`.
