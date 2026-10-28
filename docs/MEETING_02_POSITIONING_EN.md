# Idea Meeting #2 — Minutes

- Date: 2026-10-27
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Converge on the hero persona, the enemy, and the hero feature
- Follows: MEETING_01_IDEA_EN.md (D1–D5 stand)

---

## 1. Hero persona: the user's own story

- The user stated the real motivation: a busy mechanical-engineering graduate who wants to become a solo knowledge creator and run a video team, sharing domain expertise with the public — but has no time and no crew.
- This was locked as the hero persona: **a busy domain expert becoming a solo knowledge creator.** Rationale: it is a personally experienced problem (the core of "Build for Your World"), it is specific rather than generic-creator cliché, and "running an AI video team" matches the studio concept literally.
- One-line positioning: "An AI video team that turns a busy expert into a solo knowledge creator."
- Background note: mechanical engineering major with broad intellectual curiosity. Default demo material comes from ME; a second sample from a curiosity field can later prove versatility.

## 2. The enemy: casual summarizers

- The user named the lived pain: Google NotebookLM's summary videos omit important content and fall below shareable/publishable quality.
- Agreed framing: NotebookLM-class tools are memo-grade summarizers; Shoestring Studios produces publish-grade videos. Quality bar: "good enough to upload to YouTube."
- Pipeline consequence: two QA gates, not one — accuracy (no hallucinations) AND coverage (no omitted key points). The coverage gate is the direct technical answer to the omission pain.

## 3. Novelty debate (resolved as direction)

- Concern raised twice: with many participants, the entry must be creative, novel, and eye-catching — an unprecedented item.
- Response accepted as working direction: the scoring criteria contain no novelty-of-category item (Impact 30%, Meta tooling 25%, Technical depth 20%, Demo 25%); judges remember "wow" moments from a 3-minute video, not category novelty. Differentiation comes from the combination plus execution, and from demo moments — not from inventing a product category.
- Rejected in this meeting (do not re-propose as heroes): studio logo animation plus staff credit roll, morning-meeting cold open, reject-stamp plus v1-vs-final visuals, "you are the CEO" mid-run intervention, cost counter. These were judged decorative rather than item-level differentiation. Some may return as minor demo garnish only.

## 4. Item-level differentiation (agreed direction)

Existing tools are one-shot pipelines: press a button, get one output, no QA, no revision. A team enables what they structurally cannot:

1. Brief-driven production — the crew takes a brief (audience, purpose, length) like real hires; the same paper yields different videos per purpose.
2. QA-gated release — accuracy plus coverage gates must pass before anything is published.
3. Revise-until-pass — reviewers reject and writers revise until the gates pass.

Summary line: "Not a button summarizer — a briefed, QA-passing production team."

## 5. Hero feature (PROPOSED, pending confirmation)

- Proposal: **figure-grounded video — the paper's own figures come alive on screen.** Instead of generic stock/AI visuals, the pipeline extracts the source paper's figures and uses them as scenes (with camera movement), narrated in sync ("as Figure 3 shows…"). AI illustrations fill only abstract-concept scenes.
- Why it qualifies as the hero: no competing product does it; it reads in 3 seconds on screen; it is feasible (figures plus captions from the arXiv HTML version, script-to-figure matching, ffmpeg camera moves, AI-illustration fallback); it exercises Spark multimodal, SAM, and Image together; and it adds a natural crew QA gate ("is this the right figure for this scene?").

---

## Decisions

| ID | Decision | Status |
|---|---|---|
| D6 | Hero persona: busy domain expert becoming a solo knowledge creator (the user's own story). | Decided |
| D7 | Demo material default: one ME arXiv paper (10–20 pp, visually interesting topic); second sample from a curiosity field. | Decided |
| D8 | Item differentiation: brief-driven, QA-gated (accuracy + coverage), revise-until-pass. | Decided |
| D9 | Hero feature: figure-grounded video. | Proposed, awaiting user call |

## Open questions

1. D9 confirmation: figure-grounded video as the hero feature?
2. Which exact demo paper?
3. Pipeline stage definitions, agent roles, and tech stack.
4. Screen composition details for the crew visualization.

## Next steps

1. User calls D9.
2. Pick the exact demo paper (test input for development).
3. Define pipeline stages, agent roles, and tech stack; then build end-to-end before polishing.
