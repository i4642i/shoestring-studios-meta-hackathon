# Character Design Meeting #4 — Minutes (Final)

- Date: 2026-10-28
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Settle the crew character art direction and per-employee visual rules
- Status: **Final** — accepted 2026-10-28; D44 variant list filled in after pack inspection (same day)
- Follows: MEETING_03_CREW_EN.md (D10–D42)

---

## Background (settled in Meetings #1–#3)

- D4: Agent conflict drama is the signature scene — characters must be expressive enough to carry it.
- D5: Studio-window concept — a character show, not a dashboard.
- D16: Employee appearances are Muse Image-generated portraits (one-time per employee); diverse customizable looks, one consistent art style.
- D17/D18: Virtual office with roaming chibi characters + speech bubbles.
- D26: Office layout is object-separated; cohesion confirmed.
- Current look: 3-head-tall chibi, retro/pixel-art feel. First portrait exists (PD Marty, `agents/pd_marty/portrait.webp`).
- Office renderer deferred: Kaboom.js attempt failed on CDN; Phaser migration pending.

## Agenda (agreed 2026-10-28)

1. Lock the art style — pixel density, palette, outline rules.
2. Diversity scope — which traits vary per employee (skin tone, hair, outfit, ...).
3. Portrait vs office sprite — shared asset or separate generations.
4. Portrait generation procedure for each new employee.

## Decisions

| ID | Decision | Status |
|---|---|---|
| D43 | Office art style = Kenney 3D low-poly family (CC0): Mini Characters (animated, 25 files) for the crew, Furniture Kit (140 files) for the space. | Decided 2026-10-28 |
| D44 | Diversity = Mini variant pick (1 of 12 rigged characters) as the primary mechanism; per-part material tinting (skin/shirt/pants) REJECTED after inspection — all 12 GLBs carry a single "colormap" material, so only whole-model tint (appearance.json "tint") is possible. Exact list: character-male-a…f, character-female-a…f (12); the pack's other 14 GLBs are accessories (10 aid-*) + wheelchairs (4). | Decided 2026-10-28 (AI call) |
| D45 | Crew tab goes 3D too: employee detail shows a 3D viewer (same Three.js + Mini assets as the office). 2D portraits retired entirely, including Marty's portrait.webp (moves to attic/). D16 superseded. | Decided 2026-10-28 |
| D46 | New-employee 3D procedure: pick a Mini variant + tints, save as appearance.json in the employee folder; Crew 3D viewer and office spawn read it automatically. No more 2D portrait step. | Decided 2026-10-28 (AI call) |
| D47 | Office goes full 3D: renderer = Three.js (MIT, free). Deferred Phaser 2D plan dropped. | Decided 2026-10-28 |

## Next

- [x] Download Mini Characters 1.0 + Furniture Kit 2.0 (free, no login) into vendor/kenney/ (2026-10-28; CC0 confirmed in both License.txt files).
- [x] D44 variant list filled in (see row above).
- [x] Implement: Three.js office (Studio tab, office_3d.html) + 3D viewer (Crew tab, appearance.json per D46); office spawn + viewer both read appearance.json.
- [x] Retire 2D portraits: portrait.webp moved to attic/, dropped from the API + validator + file standard (D45 done). The viewer shows a message on load failure.
- Future decisions take IDs D48+.
