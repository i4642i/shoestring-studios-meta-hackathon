# Sales Employee Meeting #6 — Minutes (Final)

- Date: 2026-10-28
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Define the sales employee (frontline customer response) and how it plugs into the platform
- Status: **Final** — accepted 2026-10-28
- Follows: MEETING_05_STUDIO_PLATFORM_EN.md (D53 employee lifecycle)

---

## Background (already settled)

- D53: employees are added via scaffold + validator gate (see `docs/ADD_EMPLOYEE_EN.md`).
- Runner needs exactly one `write_*` tool per employee; chat works with any tools.
- Available writers: `write_structure` (structure.json), `write_draft` (draft.json).
  A new output needs a new writer tool + schema in the frame.
- Knowledge tools: `read_md_section` (input file), `query_graph` (handbook index).

## Decisions

- D55: sales intake asks exactly 5 questions: (1) audience level,
  (2) target video length, (3) depth (comprehensive vs key concepts),
  (4) theme direction, (5) source-material PDF. Settled 2026-10-28.
- D56: sales consultation happens on the Order page (not Studio chat).
  The Order form grows a consultation step: 5 questions + PDF upload.
  Settled 2026-10-28.
- D57: REVOKED (was: intern stays). Intern dropped — sales owns consult
  + request.md end to end, with its own output writer. Revoked 2026-10-28.
- D58: two files per order — `intake.json` (5 answers + pdf/md/image
  paths, machine-readable for Marty) + human-readable request (see D59).
  Settled 2026-10-28.
- D59: the second file is NOT an "intern summary". It is a video
  production request (영상제작 의뢰서) summarizing the consultation for
  PD/production. File: `request.md`. Settled 2026-10-28.
- D60: pipeline — sales Order consultation → auto-parse → sales writes
  request.md → orders/<id>/{intake.json,request.md} → Marty produces.
  Settled 2026-10-28.
- D61: Order page shows assignee + consultation chat + PDF attach AND
  a mini-3D sales seat. Settled 2026-10-28.
- D62: the PC fleet gets its own top-nav tab on the homepage (separate
  from Crew). Settled 2026-10-28.
- D63: PC tab is a fleet registry — PC list + materials each holds +
  owner + tool-connection state. Live monitoring deferred. Settled 2026-10-28.
- D64: Order consultation has two modes — GUIDED (5-question form) and
  FREE CHAT (conversation only; COMPLETE extracts the 4 answers from the
  chat transcript via one LLM call, then runs as usual). Settled 2026-10-28.
- D65: one button per mode — START PRODUCTION saves answers (guided),
  uploads the PDF if chosen, completes the order, and queues it.
  Guided shows no 3D, chat, or rep picker. Settled 2026-10-28.
- D66: free-chat mode is a 3D reception corner (sofa, coffee table,
  rug, lamp, plants, visitor chair, standing rep) with speech bubbles
  instead of a chat window: rep replies float from the head, client
  lines stack bottom-right. Replaces the D61 mini seat. Settled 2026-10-28.
- D67: Sam's handbook gains intake_examples.md (worked 5Q examples),
  indexed into LightRAG (37 entities, 46 relations) plus the lite
  index so both backends answer. Adapter fix: one ainsert per
  handbook (multi-insert hits a LightRAG event-loop bug). Settled 2026-10-28.
- D68: production is consent-gated — REVIEW & APPROVE appears when
  guided intake is filled, APPROVE enables START PRODUCTION (which
  calls the new start tool: approval check + pipeline). Editing
  answers after approval asks again. Free chat is talk-only, no
  START button. Settled 2026-10-28.
- D69: order chat consults the handbook index every turn
  (_handbook_hints: top-2 chunks into context, capped 1200 chars).
  Live-served from the lite index; the LightRAG index holds the same
  knowledge and answers from the experiment venv (main server cannot
  import the LightRAG venv). Verified: vague "students" got the
  indexed example back. Settled 2026-10-28.
- D70: no more amnesia — order chat context is the server transcript
  (chat.jsonl, ~8000 chars) plus the latest line; client cap 12→40;
  reload resumes the same consulting order with transcript (stored
  oid, cleared on START). Verified: "pineapple" recalled after
  reload. Settled 2026-10-28.

## Design notes (user-stated, shape the build)

- PDFs arrive THROUGH CHAT (file attachment in the consultation chat),
  landing in the order-scoped folder — not the Crew handbook form.
- Parse: pdfplumber 0.11.10 endpoint (MIT; swapped from pypdf 6.21.3
  on 2026-10-28 per user request — better table/layout-aware extraction.
  Earlier: PyMuPDF was proposed but is AGPL, which fails the
  CC0/MIT/BSD rule);
  pdf → `parsed.md` + `images/` on arrival, automatic, no manual step.
- Company PCs are a fleet SEPARATE from crew. Multiple PCs coming
  (shared PC, parser host, ...); each carries embedding and/or LightRAG
  serving for its own materials.
- Employees reach PC materials THROUGH A TOOL (no direct mounts).
  The tool is the access layer; the PC tab shows the fleet behind it.

## Scope (accepted 2026-10-28)

In: sales employee (consult + request.md writer); Order page (assignee +
chat + PDF + mini-3D sales seat); order backend (`orders/<id>/`, pdfplumber
parse, `intake.json` + `request.md`); PC fleet registry tab.
Out: intern (D57 revoked), START PRODUCTION wiring, OCR, live PC monitoring.

Done means: validator + smoke green; one Order consult → complete order
folder; shared PC registered on the PC tab.

## Next

- [x] Interview finished, record accepted as Final.
- [x] Scaffold sales employee and build the accepted scope (built
  2026-10-28: sales_sam + write_request, Order consult + backend, PC tab;
  validator + smoke + live order E2E green).
