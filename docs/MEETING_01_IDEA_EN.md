# Idea Meeting #1 — Minutes

- Date: 2026-10-27
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Lock the positioning and differentiation strategy for Shoestring Studios
- Context: Meta Global AI Developer Hackathon 2026, Indie Developer track, "Build for Your World." Shoestring Studios is an AI-agent video studio: dense source material in, narrated explainer video out.

---

## 1. Who benefits? (Impact framing)

Discussed candidates:

- Corporate L&D / onboarding teams (dense manuals to training videos)
- Solo video creators (research-to-video automation)
- Test-prep students, commuters, office workers wanting quick briefings
- Researchers needing public-facing videos of their work

Notes:

- Two already-validated markets were identified: corporate training-video outsourcing (AI training-video companies have already scaled to unicorn level selling text-to-training-video to enterprises) and per-video explainer outsourcing on freelance marketplaces.
- "Solo creator" was rejected as the primary framing: too generic and overused in hackathons.
- "AI for education" and student-as-hero framings were rejected: contest guidance lists educational AI products as overdone. House rule: present as a studio that produces cited explainer videos, not as an education product.
- Leading persona candidates: (a) researchers turning papers into public videos — open-access papers provide unlimited rights-cleared demo material, and accuracy is reputation survival; (b) office workers turning unread reports into 3-minute briefing videos — a fresh pitch with a universal pain; (c) domain experts with knowledge but no video skills.

## 2. Why verification? (Positioning of citations)

- Challenge raised: viewers never click citations, so "cited video" is weak as viewer-facing positioning. Accepted.
- Reframe agreed: verification serves the producer, not the viewer. The bottleneck in AI video is no longer generation but trust — producers must manually review every AI-written line. Verification means "publish without fear," and the claim-to-source report is a quality certificate for the producer.
- Headline direction: "not AI slop — a properly designed explainer." The agent crew's planning, writing, and reviewing is the craft; verification is the proof of that craft.

## 3. Topic regret / pivot question

- Concern raised: the topic feels cliché; the goal is to win a prize.
- Decision: no pivot. Rationale: judges score a 3-minute video on what they see and feel, not on topic novelty. Finished and surprising beats novel and unfinished. With 9 days left, a pivot is the highest-risk move. Differentiation will come from demo moments, not from the topic.

## 4. Differentiation: the cooking show

- Umbrella metaphor agreed: competing AI video tools are microwaves (input goes in, video comes out, middle is a black box). We are a cooking show (watch the crew make it).
- Candidate signature scenes: agent conflict drama (reviewer rejects, writer revises, v1 vs v3 side by side); audience-level dial (same source rendered for kids vs experts); self-caught hallucination (an agent deletes its own unsupported sentence); live production-cost counter ("this video cost $1.27 to make").
- Agreed: the agent conflict drama is the signature scene. The plan is to visualize the AI workers working.
- Screen concept ("studio window" — looking through glass at the crew): crew cards (name, role, status light, current task), a drama-style live feed of crew activity, a living script pane with version tabs and reject/revise highlighting, plus a thin progress bar and a cost counter. It must feel like a character show, not a metrics dashboard, since dashboard-centric products are penalized in this contest.

---

## Decisions

| ID | Decision |
|---|---|
| D1 | Topic stays: an AI-agent video production studio. No pivot. |
| D2 | Positioning: a studio producing properly designed explainer videos. Verification is producer QA ("publish without fear"), not a viewer feature. |
| D3 | Persona direction: specific over generic. Researcher (paper to public video) is the leading candidate; office briefing is the alternative. "AI for education" framing is out. |
| D4 | Core differentiator: process transparency ("cooking show, not microwave"). The agent conflict drama is the signature demo scene. |
| D5 | "Studio window" screen concept agreed in principle: crew cards, drama feed, living script, progress plus cost counter. Character show, not dashboard. |

## Open questions

1. Final persona choice and demo genre/material.
2. Screen composition details (add/remove).
3. Pipeline stage definitions and tech stack.
4. Meta model-to-role mapping and credit status.

## Next steps

1. Lock the persona and the demo material.
2. Define pipeline stages, agent roles, and the tech stack.
3. Verify Meta API credits and the self-hosted open-weights setup, then start building the end-to-end pipeline before polishing quality.
