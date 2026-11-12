# layouts/ — the screen layout library (project-owned)

`layouts.json` holds every layout the screen designer may choose (L01-L13) on a 1280x720 frame: slots with
position, size, kind (visual, text, number, card), role (main, support), the material kinds a slot accepts, and
order (together, or sequence = items appear in turn at narration words). People add layouts here; workers never
invent one. `preview.html` and `theme_preview.html` are pictures for people (regenerate after changes).

Material count and capacity (2026-11-11, computed by `tools/_layouts.py` material_range / layouts_for)
- A content cut takes 1, 2 or 3 candidate materials (ph-, gn-, ch-). Text the designer writes (use "lines") is no
  material.
- A layout's material capacity is counted over its material slots (every slot whose kind is not "text"): a slot
  shown together holds exactly 1; a sequence slot holds 1 up to what the 3-material limit leaves after the
  layout's other material slots. The designer must choose a layout whose capacity holds her count.

| layout | material slots              | capacity |
| L01    | main                        | 1        |
| L02    | none (text only)            | 0 (not usable for a content cut) |
| L03    | main (number)               | 1        |
| L04    | main                        | 1        |
| L05    | main                        | 1        |
| L06    | left, right                 | 2        |
| L07    | main, sub1, sub2            | 3        |
| L08    | main, sub1, sub2            | 3        |
| L09    | a, b, c (cards)             | 3        |
| L10    | main (sequence)             | 1-3      |
| L11    | main + side (sequence 1-2)  | 2-3      |
| L12    | none of the kinds made here | not choosable |
| L13    | section cover               | added by the program, never chosen |

How the parts use it
- `tools/layout_fit.py` (designer's tool): for a cut + layout + materials, computes slot fit (how much of a slot the
  material fills when scaled), the text size it needs, whether the layout holds the material count, and better
  layouts with the same capacity. Uses `tools/_layouts.py` (library, capacity, fit, placing slots, the
  program-added section cover L13, `cover_seconds`).
- `workers/designer`: picks 1-3 materials and a layout of matching capacity per cut, and writes the final slot text
  and highlight words; checks.py refuses unknown layouts/slots, a count the layout does not hold (naming the layouts
  that do), unmeasured choices, and low fit when a better layout exists.
- `workers/editor`: places what was decided in the chosen layout's slots (layers carry `"slot"`, never
  coordinates); it changes only placement (size, weight tier, line breaks, position, spacing, scaling/cropping,
  timing), never words or materials. Locked cuts/layers from decision feedback must stay unchanged (checks.py).
- `workers/reviewer`: looks at the finished screens and lists problems per content cut with the ids P1/P2 (pass),
  B1-B5 (minor, to the editor) and D1-D6 (severe, to the designer); the program's measured problems must be listed.
- `functions/check_layout.py` (decision, 3 branches): measures the scene (also for the reviewer), merges the
  reviewer's checklist and decides: any D -> redesign, else any B -> rebuild, else pass; MAX_ITERATIONS 5; feedback
  items carry where, now, change_to, why, cut, layers and `locked`.
  Measured limits: smallest text 22 px (source line 24 px; B1), 16 px (D2); screen height 55 % (B2) and 45 % (D3);
  slot fit 70 % (D1); overlap inside one slot up to 40 px (B3), more or between slots (D4).
- `tools/_layout.py`, `tools/_review.py`: measurement rules (screen use, smallest text, overlaps, blank start,
  font-weight tiers, chips), review locking, stable review and the measured-items cache for the reviewer.

Rules for changing things here: the program computes, the LLM judges only what cannot be measured; every refusal
says where, the measured value, the target and how to fix it; no bans written for one symptom.
