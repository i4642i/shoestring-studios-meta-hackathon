# Agent Plan — First Employee: PD Marty

- Status: PLAN ONLY (no product code yet)
- Date: 2026-10-28
- Implements: D11 (bounded tool-users), D12 (expertise graphs), D13 (custom tools),
  D14 (PD first + frame extraction), D15 (Meta-only inference), D27, D28

---

## 1. The first agent

- Role: PD (showrunner), storyboard team.
- Name: **Marty** — a common American first name; nods to Martin "Marty" Scorsese.
- Job: take handbook MD (converted from PDF by the user's parser) plus a brief,
  and produce a **storyboard draft (JSON)**: 2–4 key ideas, a scene list, and
  per-scene narration beats with figure/illustration slots and source refs.
- The frame supports everything from the employee definition: persona,
  GraphRAG expertise, LLM, custom tools, external APIs (via tools), bounded
  ReAct, JSON I/O, and event emission.

## 2. Folder layout

```text
agents/
  _frame/                 # reusable employee frame (grows out of PD per D14)
    runner.py             # bounded ReAct loop: think -> tool -> verify, max steps
    tools.py              # tool registry + builtin tools (read_md, query_graph, ...)
    graph.py              # GraphRAG interface over handbook/
    schemas.py            # JSON I/O contracts between crew
  pd_marty/               # employee #1
    agent.json            # id, name, title, model, tools, bounds, done-conditions
    persona.md            # persona + system prompt
    handbook/             # expertise corpus (*.md) -> indexed into Marty's graph
    tools.py              # Marty's custom tools (only if beyond builtins)
    portrait.webp         # face (Muse Image, D16)
output/
  runs/<run-id>/          # per-run: brief.json, input.md, events.jsonl, draft.json (gitignored)
scripts/
  run_agent.py            # CLI dev harness: run one employee on one input
```

Notes:

- `agent.json` (not YAML) keeps the project dependency-free (stdlib only).
- `output/` is gitignored; run artifacts are scratch, not deliverables.
- Portraits live with their employee so the Crew tab and office render them directly.

## 3. PD Marty — filled definition

| Field | Value |
|---|---|
| id / name | pd_marty / Marty |
| title | Documentary PD, showrunner |
| persona | Veteran showrunner. Decisive, allergic to jargon, protects the viewer |
| duties | MD + brief -> storyboard draft JSON |
| model | muse-spark-1.3 |
| graph | handbook/ story-design expertise (+ per-run paper index) |
| tools | read_md_section, query_graph, write_draft |
| apis | none direct (all external calls wrapped as tools) |
| inputs | brief.json, input.md |
| output | draft.json (storyboard schema v1) |
| bounds | max 6 steps per run |
| done | 2-4 key ideas; every scene has >=1 source ref; coverage list attached |

## 4. Build order (plan only)

1. Frame skeleton: runner + tool registry + I/O schemas (minimal for one employee).
2. PD instance files: agent.json, persona.md, handbook seed, portrait.
3. GraphRAG (D31: microsoft/graphrag + local embeddings) — DEFERRED. No training yet; corpus TBD later. Marty v1 reads MD directly (Spark 1M context).
4. CLI run on the demo paper (OPEN: which paper, D7) and verify draft.json by hand.
5. Refine the frame from lessons learned (D14); the writer comes next.

## 5. Open questions

1. (→ D31, DEFERRED) GraphRAG via microsoft/graphrag + local embeddings; no training yet.
2. (DONE → D32) Handbook seed: story_structure.md.
3. Which exact demo paper (D7)? (Smoke-tested on an original sample instead.)
4. (DONE → D32) Portrait: reused pd_test.webp.
