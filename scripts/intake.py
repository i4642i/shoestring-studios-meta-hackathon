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
START_DONE = "Production started \u2014 watch it in Studio."
CONFIRM_AGAIN = ("Just to confirm \u2014 shall I start "
                   "production now?")
CHAT_UNREADABLE = ("Sam's reply could not be read, "
                   "please send again.")
START_LINE = "Great — starting production now."
RECEIVED_LINE = "Thanks! Your order is in. The crew has started."

NO_PROMISE_RULE = ("Never promise to do anything or claim anything is "
                   "done or already underway (starting production, "
                   "parsing, uploading, writing, running, preparing): "
                   "only ask questions, confirm what you have so far, "
                   "and say what happens after the client confirms.")

_HEADING_RE = re.compile(r"^(\d+\.)+\s*\S")
_CONTROL_RE = re.compile(r"<\|.*?\|>", re.DOTALL)
_PREAMBLE_RE = re.compile(r"<\|start\|>\s*assistant\s+to=\S.*?<\|message\|>",
                             re.DOTALL | re.IGNORECASE)
_FUNC_BLOCK_RE = re.compile(r"<function\b.*?</function\s*>",
                             re.DOTALL | re.IGNORECASE)
_FUNC_SOLO_RE = re.compile(r"<function\b[^>]*/>",
                            re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")

_YES = frozenset([
    "yes", "yes start", "start", "go ahead", "go", "ok", "okay",
    "sure", "yeah", "yep", "do it", "please start",
    "start production",
    "\ub124", "\uc608", "\uc751", "\uc5b4", "\uc2dc\uc791",
    "\uc2dc\uc791\ud574", "\uc88b\uc544", "\uadf8\ub798",
])
_NO = frozenset([
    "no", "no not yet", "not yet", "nope", "wait", "hold on",
    "not now", "later",
    "\uc544\ub2c8", "\uc544\ub2c8\uc694", "\uc544\uc9c1",
    "\uae30\ub2e4\ub824", "\uc7a0\uae50", "\ub098\uc911\uc5d0",
])


def _norm_confirm(text):
    t = (text or "").strip().lower()
    t = re.sub(r"[,\s]+", " ", t).strip()
    return t.strip(".!?\u2026")


def classify_confirm(text):
    """Clear yes/no to Sam's start question, else None.
\r\n    Strict: the whole message must be the confirmation (extra
    words make it unclear, so Sam asks again)."""
    t = _norm_confirm(text)
    if not t:
        return None
    if t in _YES:
        return "yes"
    if t in _NO:
        return "no"
    return None


def confirm_step(ready, user_text):
    """Conversation-only start decision (no buttons).
\r\n    Returns "chat" (normal model turn), "start" (run confirm +
    start now), "keep" (client said no, consultation stays open)
    or "ask" (unclear: ask once more in one sentence)."""
    if not ready:
        return "chat"
    v = classify_confirm(user_text)
    if v == "yes":
        return "start"
    if v == "no":
        return "keep"
    return "ask"


def clean_chat_reply(raw):
    """Strip imitated model control/function blocks from a reply.
\r\n    The chat call has no tools, but a model may still emit
    "<|start|>..." control blocks or "<function ...>...</function>"
    text. Remove all of them and keep only the plain message.
    Returns "" when no plain text is left."""
    t = _PREAMBLE_RE.sub("", raw or "")
    t = _CONTROL_RE.sub("", t)
    t = _FUNC_BLOCK_RE.sub("", t)
    t = _FUNC_SOLO_RE.sub("", t)
    t = _WS_RE.sub(" ", t)
    t = _BLANK_RE.sub("\n\n", t)
    return t.strip()


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
