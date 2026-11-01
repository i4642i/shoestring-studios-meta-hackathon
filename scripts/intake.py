"""Order intake helpers: readiness, confirm strings, PDF sections.

Readiness is decided by code (the missing list), never by the model.
Stdlib only; imported by scripts/server.py and tested by
scripts/order_check.py (no sockets, no model calls).
"""
import re

INTAKE_KEYS = ("audience", "length", "depth", "theme")
STARTED = ("complete", "in_production")

READY_QUESTION = ("I have everything I need. Anything else you'd like "
                  "to add? Shall I start?")

DECLINE_ACK = ("Of course — take your time. Tell me anything else "
               "you'd like, one thing at a time.")

YES_LINE = "Yes, start."
NO_LINE = "No, not yet."
START_LINE = "Great — starting production now."
RECEIVED_LINE = "Thanks! Your order is in. The crew has started."

NO_PROMISE_RULE = ("Never promise to do anything or claim anything is "
                   "done or already underway (starting production, "
                   "parsing, uploading, writing, running, preparing): "
                   "only ask questions, confirm what you have so far, "
                   "and say what happens after the client confirms.")

_HEADING_RE = re.compile(r"^(\d+\.)+\s*\S")


def missing_of(answers, files):
    """Missing intake items: blank answers count as missing; the
    attached source PDF is the fifth item (stored at upload, parsed
    by Sam after Yes)."""
    answers = answers if isinstance(answers, dict) else {}
    files = files if isinstance(files, dict) else {}
    missing = [k for k in INTAKE_KEYS
               if not isinstance(answers.get(k), str)
               or not answers[k].strip()]
    if not files.get("source"):
        missing.append("source PDF")
    return missing


def chat_reply_payload(reply, ready, missing):
    """Chat/upload reply envelope: the client needs the missing list
    with every reply (PDF button shows only when it is exactly
    ["source PDF"])."""
    return {"reply": reply, "ready": bool(ready),
            "missing": list(missing or [])}


def build_sections(parsed_md):
    """Turn parsed PDF markdown into sections: numbered heading lines
    ("1.1 ...") become markdown headings (depth follows the dot count),
    page markers become short notes. Returns (markdown, headings)."""
    out = []
    heads = []
    for ln in (parsed_md or "").splitlines():
        m = re.match(r"^## Page (\d+)\s*$", ln.strip())
        if m:
            out.append("*p. %s*" % m.group(1))
            continue
        s = ln.strip()
        if _HEADING_RE.match(s):
            depth = s.split()[0].count(".")
            heads.append(s)
            out.append("%s %s" % ("#" * (depth + 1), s))
            continue
        out.append(ln)
    return "\n".join(out) + "\n", heads
