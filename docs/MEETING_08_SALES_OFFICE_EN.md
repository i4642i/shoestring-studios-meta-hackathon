# Sales Office Space Meeting #8 — Minutes

- Date: 2026-10-29
- Attendees: Sangho KIM, Muse Code (AI collaborator, powered by Meta Muse Spark)
- Purpose: Redesign Sam's consultation room as a warm first-meeting space
- Status: **Design accepted** — implementation pending `go`
- Follows: MEETING_06_SALES_EN.md (D66 reception corner)

---

## Background (already settled)

- D66: free-chat mode shows a 3D reception corner with speech bubbles,
  not a chat window.
- Chat UI and bubbles stay exactly as they are; only the 3D scene changes.
- Kenney Furniture Kit (CC0) + Mini Characters at office scale
  (furniture 1.9x, crew 1.15m).

## Decisions

- D76: room shell — small room about 4m x 3.5m; floor fits exactly
  inside the walls (no overhang, no corner gaps); back wall + left
  wall, open front/right for the camera like the main office; light
  wood floor, warm off-white walls, skirting board. Settled 2026-10-29.
- D77: window on the back wall, procedural (no model file): white
  frame box, light-blue emissive glass 1cm proud of the wall, thin
  cross bars, soft curtains on both sides; warm directional
  "sunlight" from the window side. Settled 2026-10-29.
- D78: furniture layout (Kenney kit): round rug center with coffee
  table on it; sofa behind the table facing the camera side as the
  client seat; armchair at the table side angled toward the sofa —
  Sam sits here facing the client (sit animation, raised to seat
  height); two cups + laptop/papers on the table; 2 big corner
  plants about 1.0-1.2m + 1 small plant on a side table; floor lamp
  with soft warm glow next to the armchair; low bookcase/cabinet on
  the left wall with a few objects; framed poster or Shoestring
  Studios sign on the back wall. Settled 2026-10-29.
- D79: look and light match the main office: no tone mapping, sRGB
  output, HemisphereLight("#fff4e0", "#3a3040", 1.6), warm
  DirectionalLight ~2.2 with soft PCFSoft shadows; camera frames
  the whole room with Sam clearly visible; drag-to-spin kept with
  azimuth limits so the open sides never show from behind. Settled
  2026-10-29.
- D80: "Drag to spin" hint moves out of the scene so it never
  overlaps the 3D view. Settled 2026-10-29.

## Scope (accepted 2026-10-29)

In: reception scene rebuild inside `index.html` (room, window,
furniture, seated Sam, lights, camera limits, hint move);
screenshot verification.
Out: chat/bubble logic, any other tab, new model files
(procedural geometry where the kit has no model).

Done means: room matches D76–D80 on a screenshot; no console
errors; bubbles still track Sam's head.

## Next

- [ ] Implement on `go` (plan presented 2026-10-29).
- [ ] Screenshot verify (headless run; user opens Order → FREE CHAT
  if the sandbox blocks browser automation).
