# Inspection of worker cases

_2026-11-11 17:27, model qwen3.8-flash-next. Written by `nextop inspect`; files were not changed._

The worker definition is mostly consistent; the only gap is that the required output field 'address' is not described in the schema and its name alone is ambiguous.

## 1. [warning] The required field 'address' has no schema description, and its name alone could mean a web URL, file address, or postal address, while the mission defines it as the fs://article/<number> returned by article_upload.

- parts: outputs, mission
- where: outputs schema: cases.items.properties.address
- fix: Add a schema description for 'address', such as 'the fs://article/<number> returned by article_upload for the source article'.
