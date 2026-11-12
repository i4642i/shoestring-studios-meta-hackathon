# Inspection of worker designer

_2026-11-11 17:43, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The worker is broadly consistent, but there are schema, mission, checker, and tool-note gaps that can confuse the worker or allow mission-required values to be omitted.

## 1. [warning] The required dropped field has no schema description, so its meaning is not clear from the field name alone even though the mission later explains it.

- parts: outputs, mission
- where: outputs: slide_plan.cuts.dropped
- fix: Add a schema description stating that dropped lists unused scene candidate ids in the first content cut and is empty for other cuts.

## 2. [warning] The schema says why_layout is based on the layout_fit verdict and why_in explains candidate materials, but title/end cuts have empty fill, no materials, and are not measured, yet the mission still requires one-sentence values.

- parts: outputs, mission
- where: outputs: why_layout and why_in descriptions; mission: Fixed cuts
- fix: Add an exception for title/end cuts to those schema descriptions, or revise the mission to say their why_layout and why_in are not based on layout_fit.

## 3. [warning] The mission tells the worker to give a source line for chosen materials, but source is optional and the checker only rejects fs:// addresses, so a valid output can omit source.

- parts: mission, outputs, checker
- where: mission: source instruction; outputs: source field
- fix: Make source required for content cuts or add a checker rule, or state in the mission that source may be omitted when there are no materials.

## 4. [warning] The checker requires at for every sequence-slot entry after the first, including use lines, but the mission describes at as applying to later materials and says lines are not materials, leaving ambiguity for lines in sequence slots.

- parts: mission, checker, tools
- where: mission: sequence fill and at; checker: _cues; layout_fit tool notes
- fix: State whether lines may appear in sequence slots and, if so, require at for them when they are not first, or forbid lines in sequence slots.

## 5. [warning] The layout_fit notes say the saved fill must be exactly the one measured, but the measured fill cannot include required sequence at fields while the saved fill can and must include them.

- parts: tools, mission, checker
- where: tools: layout_fit tool notes; mission and checker: fill measurement
- fix: Clarify that layout_fit measures only slot, use, and lines and that adding or changing at does not count as a fill change, or include at in the measurement API.

## 6. [warning] The tool notes rely on a vs_now field of other_layouts, but the tool description only says it names other layouts and does not describe vs_now.

- parts: tools
- where: tools: layout_fit description and tool notes
- fix: Describe vs_now in the layout_fit tool description or remove the tool-note reference to it.

## 7. [warning] With no maximum number of narration cuts given, 40 total calls may not cover 2-3 layout_fit calls for every content cut plus saves and any redesign remeasures.

- parts: limits, mission
- where: limits: max_calls=40; mission: compare 2-3 layouts per content cut with layout_fit
- fix: Raise max_calls, state a cuts-per-scene limit that fits 40 calls, or allow fewer comparison calls.
