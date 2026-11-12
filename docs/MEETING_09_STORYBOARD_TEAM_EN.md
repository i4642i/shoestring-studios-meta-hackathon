# Storyboard Team Utilization Meeting #9 — Minutes

- Date: 2026-10-30
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Settle how the storyboard team members are utilized; note the
  upcoming video team creation
- Status: **Utilization confirmed** — follows the decided crew plan
- Follows: MEETING_03_CREW_EN.md (crew formation),
  docs/RESULT_JSON_DRAFT_EN.md §5 (stages 0–7), §8.6 (task inputs)

---

## Background (already settled)

- The crew runs stages 0–7 as one pipeline; each agent writes one
  result JSON per run, split by category (D1–D9).
- Live now: Sam (sales, stage 0) and Marty (structure, stage 1).
- Storyboard team exists as draft agents, no runtime yet: Cleo
  (concept explainer), Rex (case researcher), Ash (planning PD),
  Penn (storyboard writer), Vera (storyboard reviewer).
- Narration drafts (Wren, Iris) exist; the video team itself is not
  formed yet — that is the next meeting's topic.

## Decisions (confirmed 2026-10-30)

- D81: storyboard team pipeline order — Marty `structure` fans out to
  Cleo + Rex in parallel (`concepts`, `cases` per part); Ash folds
  `request` + `structure` + `concepts` + `cases` into `plan`; Penn
  writes `storyboard` from `plan` + `structure`; Vera writes
  `storyboard_checked` (corrected pages + fixes list) from
  `storyboard` + `source`.
- D82: Penn's inputs stay `plan` + `structure` only; `concepts` /
  `cases` reach him folded inside the plan, keeping his input small.
  Add direct lines later only if page detail suffers.
- D83: Vera never overwrites — she emits the new
  `storyboard_checked` category, so no two senders emit the same
  category into one agent. A result with open fixes stays `checked`;
  her clean pass moves it to `reviewed`; `verified` stays
  developer-only in the UI.
- D84: research duties — Cleo owns Theory PC search/add (easy
  explanations: posts, glossaries, lecture notes, Q&A; Wikipedia for
  definitions; arXiv/Semantic Scholar only for concept origins);
  Rex owns Article PC search/add (events, companies, people, films).
  Every used hit is added to its PC first to earn a ref; model
  knowledge alone is never cited.
- D85: reading duties — Ash reads Theory/Article entries; Penn and
  Wren carry citation refs forward from their inputs without PC
  text; Vera sees every cited passage next to each claim under
  review. Everyone gets the source section list; Marty also gets the
  source map.
- D86: evidence rule — no evidence, no save. Writer tools verify
  every `{ref, quote}` verbatim against the PCs at write time, and
  suggest a matching "omitted" ref from the map on refusal.
- D87: video team creation is next: members and pipeline after
  `storyboard_checked` (Wren narration → Iris check → postprocess
  assembly) will be settled in a separate meeting, not this one.

## Scope (confirmed 2026-10-30)

In: utilization order, inputs/outputs, review loop, PC duties,
evidence rule for the five storyboard members.
Out: video team formation, TTS/assembly choices, any runtime or Flow
code for stages 2–7 (still drafts by design).

Done means: this file records D81–D87; the draft (§§5, 8.6) already
matches and needs no change.

## Next

- [ ] Hold the video team formation meeting (members, narration →
  assembly pipeline).
- [ ] Keep stages 2–7 as drafts until the Source PC + Flow runtime
  work lands, then activate Cleo/Rex first (they unblock Ash).
