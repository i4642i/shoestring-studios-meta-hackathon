# Crew Meeting #3 — Minutes (DRAFT)

- Date: 2026-10-27
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Decide what features/capabilities each AI employee gets
- Status: **DRAFT** — decisions are written as they settle; becomes Final only on explicit user acceptance
- Follows: MEETING_01_IDEA_EN.md (D1–D5), MEETING_02_POSITIONING_EN.md (D6–D9)

---

## Background (settled in Meetings #1–#2)

- D1: An AI-agent video production studio. No pivot.
- D2: Publish-grade explainer videos; verification is producer QA ("publish without fear").
- D4: Process transparency ("cooking show"); agent conflict drama is the signature scene.
- D6: Hero persona — a busy domain expert becoming a solo knowledge creator.
- D8: Brief-driven, QA-gated (accuracy + coverage), revise-until-pass.
- D9 (proposed): Figure-grounded video — the paper's own figures as scenes.
- Naming rule: each crew role gets an instantly recognizable real-world job title (e.g. the PDF→MD parser is still being named).

## Decisions

| ID | Decision | Status |
|---|---|---|
| D10 | Minimal employee-creation setup (name TBD — user says "platform" overstated it). Shape unconfirmed; awaiting user's own description. | Superseded by D14 |
| D14 | Build order: storyboard-team PD first; extract the reusable employee frame WHILE building the PD; later employees plug into that frame. (Plan only — no coding yet.) | Decided |
| D15 | Inference LLMs are Meta-only per contest rules: Spark 1.3 (workhorse), Wonder 1.0 (final judgments), Glimmer / Spark Open (open weights). TTS excepted — Meta offers no TTS, so narration voice must come from outside. | Decided |
| D16 | Employee appearances are Muse Image-generated portraits (one-time generation per employee), with diverse customizable looks (skin tone, age, style). Keep one consistent art style across the crew. | Decided |
| D17 | Crew space shape: a virtual office where employee characters roam/move around (user call; user asserts feasibility within schedule). Still open: free wandering vs movement driven by work events. | Decided (motion style open) |
| D18 | Office characters show speech bubbles with work chatter/status lines. | Decided |
| D19 | Free-only sourcing: libraries, assets, and services must be free (MIT/CC0/free tiers, hackathon credits). No paid packs or plans. | Decided |
| D20 | ALL deliverables in English (judges are non-Korean): homepage, demo video + narration, submission text, README, claim-to-source report, produced videos. Internal working docs may stay Korean. | Decided |
| D21 | The homepage (English) is the next build. | Decided |
| D22 | Homepage has top horizontal tabs, including a gallery page of past produced videos — watchable anytime (stream) and downloadable (save). | Decided |
| D23 | Tabs (left to right): Order + Studio + Gallery + Crew. Brief input and run results live inside the Studio tab (proposed). | Decided |
| D25 | Order tab: customer intake page where the customer uploads a PDF (arXiv URL also accepted, proposed). | Decided |
| D26 | Office is object-separated (floor/walls base + individual furniture objects composed in code) so the layout can change. Cohesion CONFIRMED by 2-piece test (desk + plant share outlines/palette/dithering via shared style suffix). | Decided |
| D27 | First agent: PD "Marty" (common American name, nods to Scorsese). MD in -> storyboard draft out. | Decided |
| D28 | Agent folders per AGENT_PLAN_EN.md: agents/_frame/ (runner/tools/graph/schemas) + agents/pd_marty/ (agent.json, persona.md, handbook/, tools.py, portrait.webp); runs under output/runs/ (gitignored). | Decided |
| D29 | Employee file standard adopted (AGENT_STANDARD_EN.md): required agent.json/persona.md/handbook/portrait.webp, naming + schema + validation rules, Meta-only model allowlist, max 20 steps. | Decided |
| D30 | GraphRAG mini: hand-rolled dict graph + LOCAL CPU embeddings (sentence-transformers MiniLM) for retrieval. Inference/generation stays 100% Meta (no Meta embedding product exists). networkx deferred. OSS allowed, minimal deps, license-checked, pinned. | Superseded by D31 |
| D31 | Use the microsoft/graphrag package (MIT): Meta LLM (Spark 1.3) via api_base + local CPU embedding shim (MiniLM) via api_base. api_base VERIFIED for both llm and embeddings (official docs + Ollama examples). Frame-level capability, attached per employee via tools (opt-in). | DEFERRED — no training yet; training corpus TBD later; no embeddings for now |
| D32 | Marty v1 built & verified while user away: frame (runner/tools/graph/schemas) + pd_marty instance + run_agent CLI + validator PASS + smoke run OK (storyboard draft.json, ~16.7K tokens); crew_data.js + Crew detail UI (portrait/persona/tools/graph status). | Decided |
| D33 | Custom tools managed as one-file-per-tool under agents/<id>/tools/ (auto-discovered; add/delete = file ops). Registry + validator wired. | Decided |
| D34 | Backend (stdlib, localhost) + managed Crew tab: crew view/edit (persona/model/tools), handbook upload-parse-delete (.md/.txt/.pdf via pypdf), graph status endpoint. No black-box background: runs stay inspectable. | Decided |
| D35 | Graph training-results panel in Crew detail: counts + SVG network + top lists, honest empty state until indexed; reader fills after first graphrag index. | Decided |
| D24 | Crew tab: create and delete employees (built on the D14 employee frame). | Decided |
| D11 | Employees are Lv2 bounded tool-users (think → tool → verify, capped steps). Lv3 self-planning employees explicitly REJECTED. Order/flow is fixed by code, not by employees. | Decided |
| D12 | GraphRAG capability is IN: each employee queries a knowledge graph holding that employee's expertise ("in-house training" then work). | Decided |
| D13 | Custom-made function tools are attachable per employee. | Decided |

## Unresolved questions

1. (PARTIAL → D15) Meta-only lineup locked. Key WORKS (smoke passed 2026-10-27: Spark chat + Image portrait). Remaining: B200 access?
2. (SETTLED → D12) GraphRAG: IN — each employee's graph holds that employee's expertise.
3. (SETTLED → D11/D13) Bounded tool-users with custom function tools. Lv3 self-planning REJECTED.
4. (PARTIAL → D32) PD hired (pd_marty). Remaining: Writer, Reviewer, Transcriber, Illustrator, Producer?
5. (PARTIAL → D32) PD features done (read_md_section, write_draft; query_graph deferred with D31). Remaining: other roles.
6. (PARTIAL → D32) PD = Marty. Remaining: other role names.
7. (PARTIAL → D32) PD = muse-spark-1.3. Remaining: other roles.
8. (SETTLED → D16/D17) Image portraits in a virtual office space.
9. (SETTLED → D14) Frame-first: PD first, extract the employee frame while building it.
10. Team structure: "storyboard-team PD" implies teams — how is the crew grouped? (open)
11. (PARTIAL → D22/D23/D24/D25/D34/D35) Tabs: Order + Studio + Gallery + Crew. Crew management DONE (view/edit/model/tools/handbook/train/graph panel). Remaining: gallery item contents? Order form fields? Crew create/delete form?

## Next steps

1. Settle the LLM lineup and availability FIRST (user redirect: employees need engines before roles).
2. Then settle the roster, then decide features employee by employee.
3. Confirm D9 (figure-grounded video) as part of the Illustrator scope.

## Milestones

- 2026-10-27: Meta API smoke passed (`scripts/meta_smoke.py`) — Spark chat OK, first PD portrait generated (`output/pd_test.webp`, 16-bit pixel-art style). Learning: Spark spends many reasoning tokens even on trivial calls (176 reasoning for a 2-word reply) — always budget generous max_tokens; check thinking-depth control later for cost.
- 2026-10-28: Chibi PD sprite generated (`output/pd_chibi.webp`) and embedded roaming in `office_mockup.html` (base64 + JS chroma-key). Learning: the Image API returns WebP bytes, not PNG — use .webp extensions and image/webp MIME.
- 2026-10-28: Office viz postponed; PD agent first. Agent plan written (AGENT_PLAN_EN.md, D27/D28).
- 2026-10-28: Marty v1 done (D32). Validator PASS, smoke run OK on an original sample. Crew tab shows live employee detail (portrait/persona/tools/graph NOT INDEXED). Found+fixed: misleading tool-ok event flag; Image API returns WebP.
- 2026-10-28: Backend + Crew management + graph panel built (D34/D35). Verified: py_compile, node --check, multipart unit, validator. Live server test pending on user terminal (sandbox blocks listen). Project .venv created (pip bootstrap in progress).
- 2026-10-28: Full verification green (handler + headless Edge). Sandbox blocks listen()/asyncio/remote-debug/pip; verified instead via real HTTP bytes through the real Handler plus a self-driving page copy (byte-identical JS) in real Edge: crew list/detail/edit/restore, md/txt/pdf-stub upload-delete, graph empty-state render, 3 screenshots (1280 pristine/operated, 390). Evidence: output/__verify_all.py, __verify_edge.py, __verify_pdfstub.py, verify_crew_*.png. pypdf install stalled (3 hung attempts); full-vendor pdf leg reruns via __verify_all.py on an open network.
- 2026-10-28: Narrow-viewport fix: 4 tabs clipped at 390px (Crew cut). Added max-width:560px query (equal-flex tabs, smaller marquee). Verified at true 390 CSS-px via iframe probe (headless Edge min window is ~500px, measured W=492): all 4 tabs on one row. DRIVE_DONE + BROWSER PASS re-confirmed.
- 2026-10-28: Repo hygiene for first push (D36): retired trials moved to attic/ (gitignored, local only); requirements.txt added (pypdf only — everything else is stdlib, verified by import scan; graphrag/st listed as commented planned deps); pasted chat screenshots + tool dirs + pip byproducts ignored. Dry-run: 34 files staged (office_mockup.html reinstated — Studio tab iframes it; an earlier literal-mode search had missed the reference). .env/output/attic/.venv excluded.
- 2026-10-28: Story tab added (D37, 5th tab appended after Crew): background (problem/answer), build log (meetings 01-03 + verification), developer card with contact placeholders. Verified via new ?shot=story evidence screenshot; DRIVE_DONE + BROWSER PASS re-confirmed.
- 2026-10-28: Homepage restyled Meta-clean (D38, per official event-page reference): top bar + text tabs, dotted hero with outline headline + blue pill CTA on Order, light cards/pills everywhere. Retro version backed up to attic/index_retro.html. All IDs/JS untouched; ?shot=order evidence added; DRIVE_DONE + BROWSER PASS re-confirmed.
- 2026-10-28: Tabs renamed/reordered/separated (D40): Story renamed to About; order is now Order, Crew, Studio, Gallery; About sits apart behind a divider (own row on narrow screens). Evidence renamed to ?shot=about; DRIVE_DONE + BROWSER PASS re-confirmed.
- 2026-10-28: Build-log entries link to original minutes + carry record datetimes (D41). Stamps from minutes-file records (01/02 compiled together Oct 27 23:24 KST; 03 started 23:35), consistent with Date headers. Serving leg added (GET docs/MEETING_01_IDEA_EN.md); HANDLER PASS + BROWSER PASS re-confirmed.
- 2026-10-28: Crew detail split into Model/Tools/Persona subtabs (D42, single SAVE below). Drive now clicks through all three tabs and asserts each activates; DRIVE_DONE + BROWSER PASS re-confirmed.
- 2026-10-28: First-push prep done: .gitignore extended (node_modules, more media exts), root README.md (EN) added, requirements pinned to installed-only lib, file/size/secret scan clean (only key is gitignored .env; largest file ~177KB). office_editor.html found unreferenced (user-made) — included, flagged for removal if unwanted. Commit + push left to user terminal (sandbox cannot auth).
- 2026-10-28: Working docs consolidated into docs/ (D39, 9 files); attic/README_EN.md stays with the attic. Cross-refs are bare filenames so they survive the move; validator docstring updated. File count unchanged (34).
