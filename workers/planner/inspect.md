# Inspection of worker planner

_2026-11-11 17:49, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The worker definition is mostly consistent, but the checker's materials-address rule is not actually enforced as stated.

## 1. [warning] The RULES and mission require a numeric address format like fs://article/<number> or fs://theory/<number>, but the checker code only checks that the address starts with fs://article/ or fs://theory/ and would accept malformed or non-numeric addresses.

- parts: checker, mission, outputs
- where: checker.check materials address loop; RULES list; mission step 5; outputs.storyboard.materials.properties.address
- fix: Change the checker to require full addresses such as fs://article/<digits> and fs://theory/<digits>, and only reject non-numeric or malformed addresses.
