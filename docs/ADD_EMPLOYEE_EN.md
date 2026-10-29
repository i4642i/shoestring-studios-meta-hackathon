# Adding an Employee

How crew members are added to Shoestring Studios. Two paths: the Crew tab
(recommended) or by hand. Both end at the same validator gate, so a member
that exists on disk always meets `AGENT_STANDARD_EN.md`.

## Path 1 — Crew tab (recommended)

1. Run `start_server.bat`, open `http://localhost:8000`, go to the Crew tab.
2. Fill in ADD EMPLOYEE: id, name, title, model, 3D variant.
   - id: `lowercase_snake`, e.g. `research_ria`. No leading underscore.
   - variant: leave on Auto — the server picks the first unused Kenney
     variant (`character-{male,female}-{a..f}.glb`).
3. CREATE. The server scaffolds the folder, validates it, and shows the
   new member in the roster. Failures arrive as plain errors (409 exists,
   400 bad shape, 422 validation with details) and nothing is left behind.

No server restart is needed: roster, chat, and the 3D office read the
folder on every request.

## What the server scaffolds

`agents/<id>/` with:

- `agent.json` — frame_version 1, your id/name/title/model, tools
  `["read_md_section", "write_structure"]`, bounds max_steps 6,
  inputs `brief.json` + `input.md`, output `structure.json`, three done lines.
- `persona.md` — `# Name — Title` plus the four required sections
  (intro, Persona, Voice, Rules), pre-filled for structure mapping.
- `handbook/notes.md` — one seed file. Replace with real training notes.
- `appearance.json` — `{variant, tint}` for the 3D crew viewer and office.

## Path 2 — by hand

```bat
mkdir agents\<id>\handbook
```

Create the same four files (copy `agents/pd_marty/` as a template, then
change id/name/title and rewrite the persona), then gate it:

```bat
python scripts/validate_agent.py agents/<id>
```

`PASS` means the roster, chat, and office pick the member up immediately.

## Rules that reject bad input

Enforced by `scripts/validate_agent.py` on every create AND every edit.
A failed edit rolls back; no half-written member is ever kept.

- id matches `^[a-z][a-z0-9_]*$` (UI caps input at 32 chars);
  folder `agents/<id>/` must not exist yet.
- model is `meta-models/muse-spark-open-1026` (default, via Baseten),
  `muse-spark-1.3/1.2/1.1`, `muse-wonder-1.0`, or a
  `muse-glimmer-` / `muse-spark-open-` prefixed id.
- every tool exists in the frame registry (`read_md_section`,
  `write_structure`, `write_draft`, `write_request`, `query_graph`)
  or `tools/*.py`.
- persona.md keeps `# Name` plus `## Persona` / `## Voice` / `## Rules`.
- done is a non-empty list; max_steps is int 1–20; variant ends `.glb`.

## After adding

- **Teach**: Crew detail → handbook UPLOAD (.md/.txt/.pdf), or drop .md
  files into `handbook/` (needs an `# H1` title). Click a filename to preview.
- **Tune**: Details tab edits name, title, model, tools, max_steps, done,
  persona, and 3D look. SAVE re-validates; invalid input is refused.
- **Output follows the writer**: `io.output` is read-only in the UI. Change
  the `write_*` tool and the server rewrites it (`write_structure` →
  `structure.json`, `write_draft` → `draft.json`, `write_request` →
  `request.md`).
- **Roster/chat/office**: automatic. Chat member picker and office seats
  (`DESKS`, in roster order) pick up new members with no code change.
- **Remove**: DELETE EMPLOYEE (with confirm) deletes the whole folder.
  This cannot be undone.

## Specification links

- Schema and layout: `docs/AGENT_STANDARD_EN.md`
- Run layout and crew table: `docs/AGENT_PLAN_EN.md`
- Employee lifecycle decision: `docs/MEETING_05_STUDIO_PLATFORM_EN.md` (D53)
