# Inspection of worker narrator

_2026-11-11 17:30, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

Most parts are consistent, but the mission's instruction to copy case wording unchanged conflicts with checker rules that forbid non-English text and brackets in cut text.

## 1. [error] The mission says to copy case names and summary wording unchanged, but the checker refuses any Korean, Chinese or Japanese characters and bracket characters in narration text, making cases with foreign names or parenthetical wording impossible to satisfy.

- parts: mission, checker
- where: mission Step 2 ('Use ... cases ... as they are'; 'Do not change the numbers or names in cases') and mission Flow ('Write English only...') vs checker RULES and code that reject Korean, Chinese, Japanese characters and bracket characters in a cut's text.
- fix: Clarify that foreign names and terms must be rendered in English (transliteration or official English form) and brackets removed while preserving the underlying facts, or relax the checker rules to allow the required source text.
