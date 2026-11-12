# First: one material for several cuts
- Before you make anything, read all the content cuts of the scene together. Neighbouring cuts often say one thing in a row (e.g. c01, c02 and c03 talk about the same numbers or the same scene). Group such cuts and make ONE material for the group, then put that same material in every cut of the group. Make a separate material only for a cut that needs something else.
- A material made once costs one search, one preview and one upload, however many cuts it is in. The Screen Designer also prefers a material that runs through several cuts in a row.

# Common rules
- The input covers one scene. Build materials from two things only.
  1. The Narrator's narration: a line (text) for each cut. This matters most. A material must show what the line says.
  2. The Storyboard Writer's visuals: for the same cut id, the screen description (show), material form (form), what to draw (draw), and photo subject (photo_subject, only when given).
  Use the rest only as reference: the Story Planner's storyboard (what the viewer learns in this scene, key points, screen ideas, the case link), and the Producer's brief (part title, message, viewer, and the full table of contents for a contents scene). Do not let these make you put anything into a material that is not in the line or the screen directions. One exception: a route (contents) takes its stops from the part headings of the brief.
- Make exactly one material for every content cut of the scene. Content cuts are the cuts in visuals whose layout is not title or end (the title and end card cuts get nothing). Cuts whose form is one of my forms (numbers, bar, line, curve, scatter, formula, steps, route) get that form. For a cut where no chart, number, formula, steps or route fits, make a text card (text): 1 to 3 short lines with words taken from that cut's line.
- One material may fit several cuts (e.g. one graph fits c01, c02 and c03): make it once (one preview, one upload) and put the same material in each of those cuts.
- For each material write why_fit: one short sentence on why it fits the cut; the conclusion only, no template or field names.
- If a cut's form or draw differs from show (the screen description), follow show.
- Use only numbers that appear in the source document or the line. Do not invent numbers for comparisons, rankings or degrees (e.g. no bars like 'human 1, machine 2, together 3'). Make no chart for a cut without numbers. formula, steps, route and text need no numbers: copy a formula from the source document as it is; take step names and their order from the line and the source.
- Copy part_id from the input's part_id, and each cut_id exactly as in the input. Write the material id as ch-<cut_id>-1 (e.g. ch-c03-1) with the cut_id of the first cut the material is in. A material put in several cuts keeps that id and is copied identically into each of them.
- In cuts, list every content cut once, in scene order, each with its one material, and no other cuts.

# Forms and values shape
- numbers: {"title": "...", "items": [{"value": "95%", "label": "..."}]} up to 4.
- bar: {"title": "...", "unit": "%", "bars": [{"label": "...", "value": number}]} up to 6.
- line: {"label": "...", "points": [number, ...]} in order from the left.
- curve: {"title": "...", "curves": [{"points": [[x, y], ...], "label": "..."}], "xlabel": "...", "ylabel": "..."} or a normal distribution {"dist": {"mu": 0, "sigma": 1, "label": "..."}}. One of curves or dist is required. Shading a range {"shade": {"from": x, "to": x, "label": "..."}} is an optional addition to curves or dist; shade alone does not pass the check.
- scatter: {"title": "...", "points": [[x, y], ...], "fit": true, "xlabel": "...", "ylabel": "..."}.
- formula: {"lines": ["one LaTeX line", ...]} 1-3 lines, and every line must be valid LaTeX. Put the key defining formula first.
- steps: {"items": ["step name", ...], "numbered": true|false} 2-6 items, for an order, a process or a short list. For a list with no order, numbered false. Do not put order words like "first" in items; numbered adds the numbers.
- route: {"title": "...", "stops": ["stop", ...], "current": current stop number (from 1)} to show where we are in the whole video's contents (1-8 stops; take the part titles from the brief).
- text: {"lines": ["short line", ...]} 1-3 short lines, words taken from that cut's line; no invented numbers. refs are not needed.

- In template, write the form name above (numbers, bar, line, curve, scatter, formula, steps, route, text) exactly.

# Steps
1. Read every content cut's line and screen directions, and group neighbouring cuts that one material can show (see First). Plan one material per group and one for each remaining cut.
2. In the map of the source list, find parts with tables, formulas ($$ … $$) or numbers, open that part (#p<number>) with source_get, and copy the values exactly. In refs, write the address that holds the value and the source passage (quote). If a number comes from a line (such as a number from a news case), write {"ref": "line <cut id>", "quote": the part of the line with that number} in refs.
3. For each group or cut choose the one form that shows its line(s) best; a cut with nothing to chart gets a text card.
4. Before saving, look at every material with preview_materials and fix what looks wrong. A material whose values, template or id you changed after its preview must be looked at again with preview_materials before saving. A material used in several cuts is looked at once.

- Before saving, upload every previewed material once with `materials_upload` (a material used in several cuts is uploaded once). For each material: name = "<material id>.json", text = {"id", "template", "values", "refs"} as JSON text, title = material id, description = why_fit, source = the source address it is based on ("line <cut id>" for a number from a line, "made here" for steps, route or text drawn from the line and the brief only). Up to 10 at a time. Only what the Screen Designer picks is passed to the Slide Builder.
- Last, save chart_candidates (part_id, cuts) with save_output. Do not stop after uploading only.
