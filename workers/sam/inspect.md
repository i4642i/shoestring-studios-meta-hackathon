# Inspection of worker sam

_2026-11-11 17:45, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The definition mixes an order-chat intake role/tools with an assigned save_output hand-off task, and it contains a conflicting retry instruction and a depth-value mismatch.

## 1. [warning] The persona and in-worker tools instruct a live order chat collecting four answers and a PDF, while the mission/outputs/checker define only an assigned task that copies a completed run input into request and pdf outputs.

- parts: persona, tools, mission, outputs, checker
- where: persona 'In the order chat...' and tools update_form/finalize_and_send vs mission/outputs/checker assigned task
- fix: Remove or clearly scope the order-chat persona/tools for this assigned-task worker, or add an explicit separate chat mission/phase.

## 2. [warning] save_output notes say to change exactly what any refusal names and save again, but the mission/checker say order-problem refusals are invalid run-input values the worker cannot fix.

- parts: tools, mission, checker
- where: given-by-program save_output tool note vs mission paragraph 3 and checker order-problem code
- fix: Add an exception to the save_output notes: if a refusal is an order problem, do not invent or change run-input values; report or stop.

## 3. [warning] The chat wording lists depth options as 'key points' and 'in depth', but the required output schema and checker accept only underscore forms 'key_points' and 'in_depth'.

- parts: persona, tools, outputs, checker
- where: persona and update_form description depth options vs request schema enum and checker DEPTHS
- fix: Use the canonical underscore depth values consistently in persona/tool notes or state that the site/run input canonicalizes them before saving.
