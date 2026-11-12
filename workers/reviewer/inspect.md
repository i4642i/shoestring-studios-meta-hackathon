# Inspection of worker reviewer

_2026-11-11 17:37, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

Most parts agree, but the note field for problems verdicts is underspecified, second-review handling is ambiguous about including all cuts, and the checker code does not fully enforce its stated measured-problem rules.

## 1. [warning] The schema says note is empty except for P2, but the mission only specifies it for P1 and P2, and the checker does not enforce an empty note when verdict is problems.

- parts: outputs, mission, checker
- where: outputs[].schema.properties.cuts.properties.note.description; mission step 2; checker.check()
- fix: State in the mission that note must be an empty string when verdict is problems, and optionally enforce that rule in the checker.

## 2. [warning] The mission tells the worker to judge only changed cuts and says unchanged entries are kept by the program, while the checklist rules and save_output note say the saved checklist must list every content cut once, creating ambiguity about whether to omit unchanged cuts.

- parts: mission, checker, tools
- where: mission section 'From the second check on'; checker RULES for checklist.cuts; save_output tool note
- fix: Clarify that the saved checklist must still contain every content cut by copying unchanged entries exactly, or explicitly document that the program auto-merges unchanged cuts before checking.

## 3. [warning] The RULES require every measured problem and its exact now to be listed, but the code only requires at least one problem per cut+what and only checks unit-number values, so duplicate measured problems can be omitted and non-numeric now text can be changed without refusal.

- parts: checker
- where: checker RULES item about measured problems; checker.check(); by_m; checker._problem()
- fix: Enforce one listed problem per measured problem and exact now copy, or relax the RULES to match what the checker actually enforces.
