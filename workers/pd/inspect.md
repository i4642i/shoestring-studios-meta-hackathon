# Inspection of worker pd

_2026-11-11 17:28, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The worker definition is mostly consistent, but the parts schema does not require the source_refs and role fields that the mission and checker depend on.

## 1. [warning] The mission and checker require every part to include source_refs (empty for greeting/farewell, non-empty otherwise) and require greeting/intro/outro/farewell parts to have role values, but source_refs and role are not in parts.required, so a schema-valid brief could omit them and fail the checker.

- parts: outputs, mission, checker
- where: outputs schema: items of parts.required, fields source_refs and role
- fix: Add source_refs to parts.required (allowing empty arrays for greeting/farewell) and add role to parts.required (with null allowed for body parts), or otherwise make the schema enforce the fields that the checker requires.
