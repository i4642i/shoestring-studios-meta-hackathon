# Employee File Standard

- Status: STANDARD (binding for every employee added from now on)
- Date: 2026-10-28
- Updated: 2026-10-30 (flow I/O contracts + category registry; see section 9)
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
  "title": "Structure writer",
  "model": "meta-models/muse-spark-open-1026",
  "tools": ["read_md_section", "write_structure"],
  "bounds": { "max_steps": 6 },
  "io": { "inputs": ["brief.json", "input.md"], "output": "result.json" },
  "done": ["2-4 key ideas", "every scene has >=1 source ref"]
}
```

Rules:

- All fields above are REQUIRED. Two OPTIONAL fields exist: `flow` (section 9) and `stage` (integer 0-99, crew-plan stage for Crew-page sorting; unstaged agents go last).
  Anything else unknown is rejected.
- `frame_version`: integer; the runner refuses versions it does not support.
- `id` MUST equal the parent folder name.
- `model` MUST be on the allowlist (D15): `meta-models/muse-spark-open-1026`
  (default, served via Baseten), `muse-spark-1.3`, `muse-wonder-1.0`,
  `muse-glimmer-*`, `muse-spark-open-*`.
- Every name in `tools` MUST exist in the registry (`agents/_frame/tools.py`)
  or in the employee's own `tools.py` (custom tools take precedence on collision).
- `bounds.max_steps`: integer 1–20 (D11: bounded ReAct, no unbounded loops).
- `io.output`: single filename; the runner validates it against
  `agents/_frame/schemas.py` when a schema exists.
- Builtin writers (`OUTPUTS` in `agents/_frame/tools.py`): `write_draft`
  → `draft.json`; `write_structure` and `write_request` → `result.json`
  (Q6 cutover: one result JSON per run, categories inside; the
  standalone `structure.json` / `request.json` / `request.md` are
  retired). Every writer also emits `report.md` via `render_report`.
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

## 9. Flow participation (OPTIONAL)

Why: the Flow tab wires crew into pipelines (Sam → Marty →
Cleo, Rex → Ash → Penn, Wren → Final storyboard). Connections live
ONLY in the flow file
(`data/flows/<id>.json`): an agent declares what it consumes and
produces, never where results go. This section is the contract that
makes lines checkable and handoffs safe.

`agent.json` gains one optional key:

```json
"flow": {
  "inputs": [
    {"category": "brief", "required": true,
     "description": "Order answers (audience, length, depth, theme).",
     "accept": [1]}
  ],
  "outputs": [
    {"category": "request",
     "description": "Video production request for PD/production."}
  ]
}
```

Rules:

- `inputs[]`: `category` (registry name, snake), `required` (bool),
  `description` (non-empty), optional `accept` (non-empty int list:
  category versions this agent takes; default is the registry
  version). A flow must deliver every required input.
- `outputs[]`: `category`, `description`. No destinations, no
  filenames: every run writes `result.json`.
- Every named category MUST exist in `agents/_frame/categories.json`.
  Agents without `flow` cannot join a flow; agents without a writer
  tool are drafts (display only, never run).
- The runner is unchanged: a flow run composes one `INPUTS.md` (order
  brief, sections labeled by sender/category, recipients-gated PC input)
  plus an `INPUTS.json` manifest and calls the normal bounded loop.
  Agents with no required inputs may start a flow.

Category registry (`agents/_frame/categories.json`): one entry per
result category: `version` (integer, starts at 1), `description`, and a
JSON `schema` for the `data`. Bump the version on any breaking change;
a handoff refuses a version the receiver does not accept.

Result JSON (one per agent run, stored at
`runs/<run_id>/<producer>/result.json`):

```json
{"producer": "sales_sam", "format_version": 1,
 "order_id": "...", "run_id": "...", "created_at": "2026-10-30T03:00:00",
 "status": "unverified|checked|reviewed|verified",
 "reviewed_by": null, "reviewed_at": null,
 "verified_by": null, "verified_at": null,
 "categories": {"request": {"version": 1, "data": {}}}}
```

`status`: `unverified` at write time, `checked` after a code check
passes, `reviewed` by a reviewer agent, `verified` by the developer
only (UI confirm). A verified result is read-only; any change starts
a new run.

Handoff check (flow engine, before the consumer runs): header shape,
accepted category versions, then `data` against the registry schema
with the stdlib subset: `type` (object, array, string, integer, number,
boolean), `properties`, `required`, `items` (one schema),
`additionalProperties` (bool), `enum`. Anything outside this subset in
a registry schema is ignored. On failure the flow stops and the run log
records why. Deeper input-relative rules (e.g. Marty's heading
coverage) stay enforced by the writer tools at creation time; the
handoff re-checks the static shape.
