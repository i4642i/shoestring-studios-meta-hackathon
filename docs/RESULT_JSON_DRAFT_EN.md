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
  "version": 1,
  "order_id": "...",
  "run_id": "...",
  "created_at": "2026-10-30T03:00:00",
  "status": "unverified",
  "categories": {
    "request": {}
  }
}
```

- `producer`: agent id that made this result. No destinations anywhere
  in the file (D1): the agent does not know where results go.
- `version`: result-format version, integer, starts at 1. Bump on any
  breaking change to the header or to a category payload below.
- `order_id`, `run_id`: the order and the run that produced this.
- `created_at`: local time `YYYY-MM-DDTHH:MM:SS`.
- `status`: `unverified` (just written) → `checked` (payload passed its
  category schema) → `verified` (human/QA acceptance, see Q2).
- `categories`: `{<name>: <payload>}`. Only the payload differs per
  category. An agent with one result has one key.

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

## 5. Rules this draft follows (from D1–D9)

- No destinations in any JSON (D1). No per-category files (D2): one
  JSON per run, categories inside.
- Lines filter categories; several senders may feed one agent (D3–D4).
- Merging is a relay agent's instructions, never a code block (D5).
- Scene/video assembly is a post-processing page, not an agent (D6).
- Every needed input must arrive by design; no run-time requests (D7).

## 6. Open questions

- Q1 `version`: single format version (this draft) or one version per
  category so `request` can evolve without touching `structure`?
- Q2 `verified`: who sets it — a human QA click in a later UI, or the
  producer attesting its own writer validation?
- Q3 `source` payload: sidecar pointer (this draft) or full text
  inline? Sidecar keeps envelopes small; inline keeps one file.
- Q4 Same category from two senders into one agent: allowed with
  sender labels, or must it always go through a relay agent (D5)?
- Q5 Does the Final video node also write a result JSON, or is the
  post-processing page output (D6) outside this format?
- Q6 Transition: keep writing legacy sidecars (`request.md`,
  standalone `structure.json`) alongside the new JSON, or cut over?
