# Studio & Platform Meeting #5 — Minutes (Final)

- Date: 2026-10-28
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Lock the Studio 3D office rules, Studio chat, Marty's new job, and full Crew management
- Status: **Final** — accepted 2026-10-28
- Follows: MEETING_04_CHARACTER_DESIGN_EN.md (D43–D47)

---

## Background (settled in Meetings #1–#4)

- D43/D44: Kenney 3D low-poly family (CC0); 1-of-12 Mini variant + whole-model tint per employee.
- D45/D46: Crew tab goes 3D; appearance.json required; 2D portraits retired.
- D47: Office renderer = Three.js (MIT), vendored locally with the Kenney GLBs. No CDN.
- D11/D14/D15: Bounded ReAct frame, Meta-only models; D28 employee folder layout.

## Agenda (agreed 2026-10-28)

1. Studio 3D office: placement bugs, scale, seating, lighting.
2. Studio chat with a chosen member + office speech bubbles.
3. Marty's job: drop the storyboard, map structure instead.
4. Crew tab: see everything, edit everything, add employees consistently.

## Decisions

| ID | Decision | Status |
|---|---|---|
| D48 | Office scene rules: orthographic (isometric-feel) camera, sky-blue background, furniture Box3-recentered (FURNITURE x/z = item center, ry spins in place), A* on 10cm grid with furniture blocks + 0.15m margin, 10x7m floor map. | Decided 2026-10-28 |
| D49 | Real-world scale: furniture x1.9 (desk ~1.4m wide, ~0.73m tall), crew 1.15m tall via per-model Box3; SIT_Y seat lift (0.2); desk chairs 0.3m from the desk front edge; DESKS seats match chair positions. | Decided 2026-10-28 |
| D50 | Office lighting (no tone mapping, sRGB): HemisphereLight #fff4e0/#3a3040 1.6 + one DirectionalLight #ffe2b8 2.2 with soft shadows. No environment map, no point lights. Fog + sky kept. | Decided 2026-10-28 |
| D51 | Studio chat: member picker, LLM reply in chat and in that member's office bubble. On chat the member walks to its own desk, sits, shows CHATTING, resumes roaming after 25s idle. Service is English-only: no Korean in UI, LLM forced to answer in English. | Decided 2026-10-28 |
| D52 | Marty repurposed to structure mapping only: reads input, writes structure.json via write_structure (coverage = every one-dot section in source order, deeper sections folded into parents, neighbour links). Storyboard retired. Runner safety: max 2 tools-off JSON retries per run, truncation guard (never fragment-mine), tool results wrapped as external data, tool closed after 5 consecutive failures. | Decided 2026-10-28 |
| D53 | Crew platform owns the employee lifecycle: detail shows every field (identity, model, tools, bounds, io, done, appearance, persona, handbook, graph); all editable with validator gate + rollback on failure; io.output auto-follows the single write_* tool; add-employee scaffold (template + first-unused variant + validate); delete with confirm. | Decided 2026-10-28 |

## Next

- [ ] Live structure-map run on the real book chapter (needs the input .md path; inputs/outputs stay out of git).
- [ ] Multi-crew office test (second employee via the new add form).
- [ ] Commit the session (office_3d.html, frame, Crew UI, vendor packs, these minutes).
