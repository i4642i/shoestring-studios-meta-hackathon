# Inspection of worker board

_2026-11-11 17:29, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The worker definition is mostly aligned, but there are a few conditional contradictions between the mission, checker rules, and checker code.

## 1. [warning] The mission says title_card.title and end_card.message must be copied from the request and never empty, while also saying empty order fields must remain empty and the checker code does not enforce non-empty values when the request provides empty ones.

- parts: mission, checker, outputs
- where: mission step 9; checker RULES and _cards()
- fix: Clarify that the order must provide non-empty title/message values, or adjust the checker and RULES so they consistently allow or require those values.

## 2. [warning] Step 4 says draw may use only numbers and names found in the narration and source, while step 8 tells the worker to use article/theory materials that may add new names or facts used in cuts.

- parts: mission, outputs
- where: mission step 4 draw guidance and step 8 materials guidance
- fix: State explicitly that draw may use numbers and names from selected article/theory materials, or restrict those materials from being drawn in cuts.

## 3. [warning] The RULES claim exact source-title copying, exact card copying, non-empty title/message values, and no extra cut IDs in all cases, but the code only checks non-empty source_title, compares only card fields present in a dict request, skips extra cut IDs when the narration has no cuts, and does not reliably enforce the non-empty title/message rule.

- parts: checker, mission
- where: checker RULES versus checker code checks for source_title, cards, and cut IDs
- fix: Tighten the checker to enforce the stated rules, or soften the RULES to describe only what the code actually enforces.
