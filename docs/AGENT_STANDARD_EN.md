# Employee File Standard

- Status: STANDARD (binding for every employee added from now on)
- Date: 2026-10-28
- Updated: 2026-10-28 (D45/D46: 2D portraits retired, appearance.json required)
- Implements: D14 (employee frame), D28 (folder layout), D45/D46 (3D appearance)
- Companion: AGENT_PLAN_EN.md

Every directory directly under `agents/` (except `agents/_frame/`) is one
employee and MUST follow this standard. A planned validator
(`scripts/validate_agent.py`) will enforce it mechanically.

---

## 1. Required layout

```text
agents/<id>/
  agent.json      # machine-readable definition (REQUIRED)
  persona.md      # persona + system prompt (REQUIRED)
  handbook/       # expertise corpus, >=1 .md file (REQUIRED, D12)
  appearance.json # 3D look: Mini variant + tint (REQUIRED, D46)
  tools/          # custom tools, one file per tool (OPTIONAL, D33)
```

No other top-level files are allowed without updating this standard.

## 2. Naming rules

- `<id>`: lowercase snake, `^[a-z][a-z0-9_]*$`, must equal the folder name.
- `agent.json`: exactly that filename. `persona.md`: exactly that filename.
- `handbook/*.md`: topic in snake case (`story_structure.md`), H1 title inside.
- `appearance.json`: exactly that filename. JSON object with `variant`
  (a `character-*.glb` filename from the D44 list in MEETING_04) and optional
  `tint` (`#rrggbb` whole-model multiplier, default `#ffffff`). Per-part tints
  are impossible — the Mini GLBs carry a single material (D44).

## 3. agent.json schema

```json
{
  "frame_version": 1,
  "id": "pd_marty",
  "name": "Marty",
  "title": "Documentary PD, showrunner",
  "model": "muse-spark-1.3",
  "tools": ["read_md_section", "write_structure"],
  "bounds": { "max_steps": 6 },
  "io": { "inputs": ["brief.json", "input.md"], "output": "structure.json" },
  "done": ["2-4 key ideas", "every scene has >=1 source ref"]
}
```

Rules:

- All fields above are REQUIRED. Unknown fields are rejected.
- `frame_version`: integer; the runner refuses versions it does not support.
- `id` MUST equal the parent folder name.
- `model` MUST be on the allowlist (D15): `muse-spark-1.3`,
  `muse-wonder-1.0`, `muse-glimmer-*`, `muse-spark-open-*`.
- Every name in `tools` MUST exist in the registry (`agents/_frame/tools.py`)
  or in the employee's own `tools.py` (custom tools take precedence on collision).
- `bounds.max_steps`: integer 1–20 (D11: bounded ReAct, no unbounded loops).
- `io.output`: single filename; the runner validates it against
  `agents/_frame/schemas.py` when a schema exists.
- `done`: human-readable completion checklist, >=1 item.

## 4. persona.md structure

REQUIRED sections, in order:

1. `# <Name>` — one-line role (e.g. `# Marty — PD, showrunner`).
2. `## Persona` — personality traits (3–6 bullets).
3. `## Voice` — how the employee writes/speaks (tone, banned words).
4. `## Rules` — hard rules, including "never invent source passages" and
   "ask for nothing; bounded tools only".

This file doubles as the system prompt: the runner sends it verbatim.

## 5. handbook/ rules (D12)

- At least ONE `.md` file. This is the employee's expertise corpus ("in-house
  training") indexed into its knowledge graph.
- Plain Markdown only: headings, bullets, short paragraphs. No HTML, no images.
- Each file starts with an H1 topic line. Keep files small (<200 lines);
  split by topic instead of growing one file.

## 6. tools/ rules (D13, D33)

- OPTIONAL directory. One file per custom tool: `tools/<name>.py`.
  Add a file = add a tool; delete the file = remove it. Auto-discovered.
- Each file MUST define: `NAME` (== filename), `run(ctx, args)` function,
  and `SCHEMA` (JSON schema for arguments).
- Tool names: same `^[a-z][a-z0-9_]*$` rule as ids.
- Functions take and return JSON-serializable values only. No network calls
  except through declared API wrappers reviewed with the team.
- Attach to the employee by listing the name in `agent.json` tools[].
  (Crew UI attach/detach comes with the backend.)

## 7. What employees get for free (frame-provided, not per-file)

- Bounded ReAct loop with tool calling (D11).
- Knowledge-graph build/query over `handbook/` (D12).
- Model calls on the Meta-only lineup (D15).
- Event emission to the studio window (one event per think/tool/done step).
- I/O validation against `schemas.py` where a schema exists.

## 8. Adding a new employee (checklist)

1. Copy the layout: `agents/<new_id>/` with the 4 required files.
2. Fill `agent.json` (validate: id == folder, model on allowlist, tools exist).
3. Write `persona.md` in the 4-section structure.
4. Seed `handbook/` with >=1 expertise file.
5. Pick a Mini variant + tint, save as `appearance.json` (D46; each
   employee gets a unique variant combo per D44).
6. Run `scripts/validate_agent.py agents/<new_id>` — must pass before use.
