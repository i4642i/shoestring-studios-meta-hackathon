# Inspection of worker anim

_2026-11-11 17:43, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The worker definition has several mismatches between the mission, output schema, checker rules, and tool descriptions, especially about source scope, total candidate limits, refs requirements, and allowed upload sources.

## 1. [warning] The mission says materials are built from only the narration line and screen visuals and must not contain anything absent from them, but then requires copying values from the source document and taking route stops from the brief.

- parts: mission, persona
- where: mission 'Common rules' bullets and later 'Steps' bullet 1
- fix: Clarify that the line and visuals decide what material to make, while exact values, formulas, steps, and route stops may be taken from the source or brief when needed.

## 2. [warning] The materials_upload description limits source to a web address, a book and page, or 'made here', while the mission and tool notes require source values such as fs source addresses and 'line <cut id>'.

- parts: tools, mission
- where: given tools materials_upload description vs materials_upload tool notes and mission upload paragraph
- fix: Update the materials_upload description to explicitly allow source document addresses and 'line <cut id>', or change the mission/notes to use only the allowed source values.

## 3. [warning] The schema allows up to 4 candidates in each cut's candidates array, but the mission and checker enforce at most 4 candidates for the whole scene.

- parts: outputs, mission, checker
- where: outputs[0].schema.properties.cuts.items.properties.candidates.maxItems; mission 'Make up to 4 candidates for the whole scene'; checker total candidate limit
- fix: Add a clear scene-wide total-candidate limit in the schema description or validation notes, since the per-array maxItems does not express the whole-scene limit.

## 4. [warning] The output schema does not require refs for chart or formula candidates, but the checker refuses candidates that omit refs even though such candidates can pass schema validation.

- parts: outputs, mission, checker
- where: outputs[0].schema.properties.cuts.items.properties.candidates.required and properties.refs; checker REFS_NEEDED
- fix: Add schema-level guidance or conditional validation stating that refs is required for numbers, bar, line, curve, scatter, and formula candidates.

## 5. [warning] The mission says every uploaded candidate text should include refs, but refs is not required or needed for steps and route in the output schema or checker.

- parts: mission, outputs, checker
- where: mission upload paragraph 'text = {"id", "template", "values", "refs"} as JSON text'; outputs candidate required fields; checker REFS_NEEDED
- fix: Specify that refs may be omitted or set to an empty array for steps and route candidates when uploading.
