# Inspection of worker explainer

_2026-11-11 17:27, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The definition mostly agrees, but it has a hard contradiction between word-for-word quotations of foreign-language source text and the English-only checker, and it makes evidence seem required while the schema and checker do not enforce evidence.

## 1. [error] The mission requires quotes to be copied word for word but also says to replace Korean, Chinese, or Japanese characters with English, while the checker rejects any such characters in the output, so a source quote containing those characters cannot satisfy both instructions.

- parts: mission, checker
- where: mission step 4; checker check/_foreign
- fix: Remove the word-for-word requirement for foreign-language text or explicitly require a faithful English translation for such quotes and explain that translation replaces direct quoting when needed.

## 2. [warning] The persona and mission present evidence as essential, but the schema does not require each part to contain evidence and the checker does not check it, so the worker can pass while omitting evidence.

- parts: persona, outputs, mission, checker
- where: persona; outputs schema; mission steps 3-4
- fix: Either require evidence in the part schema and checker, or state in the persona and mission that evidence is optional rather than mandatory.
