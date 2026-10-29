# Result JSON draft (D8: definition first, code later)

- Status: DRAFT for decision. No code implements this yet.
- Date: 2026-10-30.
- Implements decisions D1–D9: one result JSON per agent run, split by
  category; lines pick categories; merges go through relay agents;
  video assembly is post-processing; no run-time missing-input requests.

## 1. Shape (one file per agent run)

```json
{
  "producer": "sales_sam",
  "format_version": 1,
  "order_id": "...",
  "run_id": "...",
  "created_at": "2026-10-30T03:00:00",
  "status": "unverified",
  "reviewed_by": null,
  "reviewed_at": null,
  "verified_by": null,
  "verified_at": null,
  "categories": {
    "request": {"version": 1, "data": {}}
  }
}
```

- `producer`: agent id that made this result. No destinations anywhere
  in the file (D1): the agent does not know where results go.
- `format_version`: envelope version, integer, starts at 1. Bump
  only when the header itself changes (producer, ids, status fields).
- `order_id`, `run_id`: the order and the run that produced this.
- `created_at`: local time `YYYY-MM-DDTHH:MM:SS`.
- `status`: `unverified` (just written) → `checked` (payload passed
  its category schema, code check) → `reviewed` (a reviewer agent —
  Vera for storyboard, Iris for narration — compared it with the
  sources via `open_ref` and passed it: every citation passes the
  verbatim check and no open fix remains; otherwise it stays
  `checked` and lists the problems) → `verified` (the developer
  confirmed it in the UI; any category, with or without a reviewer).
- `reviewed_by` / `reviewed_at`: reviewer agent id + time, set when
  the status becomes `reviewed`. `verified_by` / `verified_at`:
  developer id + time, set on confirm.
- A `verified` result is read-only; any change creates a new run
  (new `run_id`), never an edit in place.
- `categories`: `{<name>: {"version": <int>, "data": {...}}}`. Each
  category carries its own version; bump only that category's number
  when its schema changes. The schemas in §§2–4 below describe each
  category's `data`. An agent with one result has one key.
- A receiving agent's check names the category versions it accepts
  (e.g. `request` v1); anything else is refused at the line.

## 2. Sam (`sales_sam`)

Produces `{request}`. Consumes `brief` + `source` (delivered by lines).

`request` payload schema:

```json
{
  "type": "object",
  "required": ["order_id", "client_answers", "source_summary",
               "production_notes", "open_questions"],
  "properties": {
    "order_id": {"type": "string"},
    "client_answers": {
      "type": "object",
      "required": ["audience", "length", "depth", "theme", "source"],
      "properties": {
        "audience": {"type": "string"}, "length": {"type": "string"},
        "depth": {"type": "string"}, "theme": {"type": "string"},
        "source": {"type": "string"}
      }
    },
    "source_summary": {"type": "string"},
    "production_notes": {"type": "array", "items": {"type": "string"}},
    "open_questions": {"type": "array", "items": {"type": "string"}}
  }
}
```

Mirrors today's `request.json` (writer-validated). The human-readable
`request.md` render stays a sidecar, not part of the JSON (see Q6).

## 3. Marty (`pd_marty`)

Produces `{structure}`. Consumes `request` (required) and optionally
`source` (delivered by lines).

`structure` payload schema (static shape; input-relative rules such as
heading coverage and source order stay enforced by the writer tool at
creation time, because pure JSON schema cannot express "heading exists
in the input"):

```json
{
  "type": "object",
  "required": ["source", "common_theme", "parts", "intent"],
  "properties": {
    "source": {
      "type": "object", "required": ["book", "chapter"],
      "properties": {"book": {"type": "string"},
                     "chapter": {"type": "string"}}
    },
    "common_theme": {"type": "string"},
    "parts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "heading", "covers", "keywords"],
        "properties": {
          "id": {"type": "string"}, "heading": {"type": "string"},
          "covers": {"type": "string"},
          "keywords": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "intent": {
      "type": "object", "required": ["overall", "links"],
      "properties": {
        "overall": {"type": "string"},
        "links": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["from", "to", "why"],
            "properties": {
              "from": {"type": "string"}, "to": {"type": "string"},
              "why": {"type": "string"}
            }
          }
        }
      }
    }
  }
}
```

## 4. Order pseudo-producer (line inputs need schemas too)

`Order` is not an agent run, but its two categories ride lines, so they
are defined here with the same schema language.

`brief` payload schema:

```json
{
  "type": "object",
  "required": ["order_id", "answers", "source_file"],
  "properties": {
    "order_id": {"type": "string"},
    "answers": {
      "type": "object",
      "required": ["audience", "length", "depth", "theme"],
      "properties": {
        "audience": {"type": "string"}, "length": {"type": "string"},
        "depth": {"type": "string"}, "theme": {"type": "string"}
      },
      "additionalProperties": true
    },
    "source_file": {"type": "string"}
  },
  "additionalProperties": true
}
```

`source` payload schema (small pointer; full text stays in the sidecar
markdown file so envelopes never balloon to megabytes):

```json
{
  "type": "object",
  "required": ["file", "chars"],
  "properties": {
    "file": {"type": "string"},
    "chars": {"type": "integer"},
    "head": {"type": "string"}
  },
  "additionalProperties": true
}
```

## 5. Crew plan (stages 0–7): who makes and takes what

One result JSON per agent run (§1). Each role below lists the
categories it produces and the categories it receives. Receives are
delivered by flow lines (D1: no destinations in any JSON); a role may
take inputs from several senders (D4). Reviewers write a new
`*_checked` category instead of overwriting, so no two senders ever
emit the same category into one agent (see Q4). Full JSON schemas for
the new categories follow once the category set is approved.

| Stage | Role | Receives | Produces |
|---|---|---|---|
| 0 | Sales (Sam) | `brief`, `source` | `request` (§2) |
| 1 | Structure writer (Marty) | `request`, `source` | `structure` (§3) |
| 2 | Concept explainer | `structure`, `source` | `concepts` |
| 2 | Case researcher | `structure`, `source` | `cases` |
| 3 | Planning PD | `request`, `structure`, `concepts`, `cases` | `plan` |
| 4 | Storyboard writer | `plan`, `structure` | `storyboard` |
| 5 | Storyboard reviewer | `storyboard`, `source` | `storyboard_checked` |
| 6 | Narration writer | `storyboard_checked`, `plan` | `narration` |
| 7 | Narration reviewer | `narration`, `source` | `narration_checked` |

New category payloads (field sketches, schemas later):

- `concepts`: per part `{part_id, what, origin, simple_take,
  sources: [{title, url_or_ref, cited_for}]}` — what the concept is,
  why it came about, how to explain it simply.
- `cases`: `{part_id, cases: [{title, kind (event/company/person/
  film), summary, fit_why, sources: [...]}]}` — real cases viewers
  relate to, attached to parts.
- `plan`: `{audience, message, angle, fun_hooks[], flow: {intro,
  body[], conclusion}, page_budget}` — for whom, what, from which
  angle, how to make it fun; intro → body → conclusion.
- `storyboard`: `{pages: [{n, learn, screen, material, next_link}]}` —
  what the viewer learns, the screen, source/material used, link to
  the next page.
- `storyboard_checked`: `{pages: [...same shape, corrected...],
  fixes: [{page, was, now, why}]}` — facts fixed against source and
  materials.
- `narration`: `{pages: [{n, section (intro/body/outro), lines[],
  evidence: [{fact, source_ref}]}]}` — lines per page with evidence
  for each fact and number.
- `narration_checked`: `{pages: [...same shape, corrected...],
  fixes: [{page, was, now, why}]}` — lines fixed against source and
  materials.

Notes on the stage table:

- Stages 0–1 are exactly §§2–3 above, restated here for the full map.
- Planning PD receives `request` too, so audience/length/theme from
  the client interview survive into the plan (D4 multi-sender input).
- Storyboard writer takes `plan` + `structure` but not `concepts` /
  `cases` directly: the plan already folds them in, keeping the writer
  input small. If page detail suffers, add those two lines later.
- Reviewers also receive source/materials pointers via `source`; full
  material text stays in sidecars (cf. Q3).
- `narration_checked` is the last agent result; scene/video assembly
  from it is the post-processing page (D6, cf. Q5).

## 6. Rules this draft follows (from D1–D9)

- No destinations in any JSON (D1). No per-category files (D2): one
  JSON per run, categories inside.
- Lines filter categories; several senders may feed one agent (D3–D4).
- Merging is a relay agent's instructions, never a code block (D5).
- Scene/video assembly is a post-processing page, not an agent (D6).
- Every needed input must arrive by design; no run-time requests (D7).

## 8. Company computers (shared stores, not agents)

Two shared stores. They are not agents: they hold no opinions, run no
steps, and write no result JSON. Agents reach them only through tools
listed in their own `agent.json` — tools are the only permission
mechanism.

### 8.1 Source PC

Parsed results of the client's documents: markdown, images, section
list. Read: all crew. Write: intake only (Sam's parser step).

Entry format:

```json
{
  "doc_id": "a3f9c1d4e2b8",
  "title": "client document title",
  "origin_file": "upload original name.pdf",
  "order_id": "...",
  "parsed_at": "2026-10-30T03:00:00",
  "added_by": "sales_sam",
  "sections": [{"n": "1.1", "heading": "..."}],
  "paragraphs": [{"addr": "s1.1/p3", "text": "..."}],
  "images": [{"file": "...", "caption": "..."}]
}
```

- `doc_id`: content hash (§9), so re-parsing the same bytes yields the
  same id and address.
- Paragraphs carry short local addrs; the full stable address is
  `pc://source/<doc_id>#s<section>/p<paragraph>` (§9).
- Provenance on every entry: origin file, order, parse time, adder.

### 8.2 Article PC

External articles and materials found on the web. Read: external
researchers (Cleo, Rex) plus granted agents (Ash, Vera, Iris — they
must verify citations and facts). Write (add articles): external
researchers only.

Entry format:

```json
{
  "article_id": "7b2e…",
  "url": "https://…",
  "title": "…",
  "publisher": "…",
  "date": "2026-01-15",
  "fetched_at": "2026-10-30T03:00:00",
  "added_by": "case_rex",
  "text": "full text or excerpt (see Q9)",
  "paragraphs": [{"addr": "p12", "text": "..."}]
}
```

- `article_id`: content hash (§9). Full address:
  `pc://article/<article_id>#p<paragraph>`.
- Provenance on every entry: url, title, publisher, date, fetch time,
  adder. The model never copies these by hand (§9).

### 8.3 Indexing

LightRAG, one index per PC per embedding profile, reusing the agent
profile scheme (`local`, `jetson`): `storage/_pc/source/<profile>/`
and `storage/_pc/article/<profile>/`. Same rules as agent indexes: one
model+dim per index, cross-model queries refused, per-profile markers.

### 8.4 Duplicates

- Same content added twice → same id → add is a no-op returning the
  existing address. No duplicate entry is ever stored.
- Same url, changed content on re-fetch → a NEW entry (new id); the
  old entry is kept, so existing refs never rot. The entry notes
  `supersedes: <old_id>` (informational only).

### 8.5 Tools and grants

| Tool | PC | Effect | Granted to |
|---|---|---|---|
| `pc_read_source` | Source | read entry/section/paragraph | all crew |
| `pc_add_source` | Source | store a parsed document | `sales_sam` only |
| `pc_search_articles` | Article | web search (see Q8) | Cleo, Rex |
| `pc_read_article` | Article | read entry/paragraph | Cleo, Rex, Ash, Vera, Iris |
| `pc_add_article` | Article | store a fetched article | Cleo, Rex |
| `open_ref` | either | verbatim passage + provenance (§9) | whoever holds that PC's read grant |

- No web access except through `pc_search_articles`. All other agents
  are read-only on granted PCs.
- Writers (Penn, Wren) get no Article PC grant for now: they build
  from plan/storyboard, and reviewers re-verify against the PCs.

### 8.6 In the 3D office (idea only, no code)

Two computer desks against a wall: the Source PC near intake (Sam's
side), the Article PC in a research corner. Each with a monitor glow
tinted per PC. No behavior change: set dressing until the flow UI
needs live PC status.

## 9. Stable reference addresses

Every stored passage gets a stable address:

```text
pc://source/<doc_id>#s<section>/p<paragraph>
pc://article/<article_id>#p<paragraph>
```

- `<doc_id>` / `<article_id>`: first 12 hex chars of SHA-256 over the
  normalized content (whitespace-normalized, lowercased). Short to
  write, collision-safe at our scale; re-adding the same document
  gives the same address.
- The model writes only the short ref plus a verbatim quote. The
  system fills in full provenance (url, title, date, fetched_at) from
  the PC entry — the model never copies long URLs by hand.
- A citation in any result JSON:

```json
{"ref": "pc://article/7b2e…#p12", "quote": "<verbatim text>"}
```

- Tool `open_ref(ref)`: returns that passage verbatim with its
  provenance. The caller's PC read grant still applies: no grant, no
  passage.
- Citation check: a citation passes only if `quote` appears verbatim
  in the passage at `ref` (normalize whitespace only). Writer tools
  run this check at write time (same pattern as the existing
  writer-validated outputs); reviewers re-verify through `open_ref`
  and list any failures as problems (the result stays `checked`
  until clean).

## 10. Open questions

- Q1 DECIDED: version per category. The header keeps
  `format_version` for the envelope; every category is wrapped as
  `{"version", "data"}` with its own number; receivers name the
  versions they accept.
- Q2 DECIDED: `verified` is set only by the developer, via a
  confirm action in the UI (any category, with or without a
  reviewer). Four states: `unverified` → `checked` → `reviewed` →
  `verified`; see the header fields above.
- Q3 `source` payload: sidecar pointer (this draft) or full text
  inline? Sidecar keeps envelopes small; inline keeps one file.
- Q4 Same category from two senders into one agent: allowed with
  sender labels, or must it always go through a relay agent (D5)?
- Q5 Does the Final video node also write a result JSON, or is the
  post-processing page output (D6) outside this format?
- Q6 Transition: keep writing legacy sidecars (`request.md`,
  standalone `structure.json`) alongside the new JSON, or cut over?
- Q7 Stage 2 outside sources: which search tool, if any, do the
  concept explainer and case researcher use — a web search API, a
  curated source list, LightRAG over an internal corpus, or none
  (model knowledge only, citations unverifiable)? (Q8 narrows this
  to the API choice.)
- Q8 Which web search API backs `pc_search_articles` (if any)?
- Q9 Article PC: store full article text or excerpts only? Full text
  is easier to cite; excerpts are safer for copyright — and the repo
  will be public.
- Q10 Size limits for each PC (entries, chars per entry, total)?
