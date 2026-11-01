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
ACCEPT_LINE = "Order received \u2014 preparing production."
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
_FILLERS = frozenset([
    "okay", "ok", "yeah", "yep", "well", "sure", "fine",
    "please", "let's", "lets",
    "\ub124", "\uc608", "\uc751", "\uc5b4",
])
_CORE_YES = frozenset([
    "start", "go", "go ahead", "do it", "start production",
    "\uc2dc\uc791", "\uc2dc\uc791\ud574",
])
_CORE_NO = frozenset([
    "no", "not yet", "nope",
    "\uc544\ub2c8", "\uc544\ub2c8\uc694", "\uc544\uc9c1",
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
    words = t.split(" ")
    while words and words[0] in _FILLERS:
        words.pop(0)
    while words and words[-1] == "please":
        words.pop()
    core = " ".join(words)
    if core in _CORE_YES:
        return "yes"
    if core in _CORE_NO:
        return "no"
    return None


JUDGE_PROMPT = (
    'You classify a reply to "Shall I start production now?". '
    'Reply with exactly one word: YES if they agree to start, '
    'NO if they decline or want to wait, UNCLEAR otherwise. '
    'No other text.\n\nClient reply: "')


_QUESTION_WORDS = frozenset(
    "who what when where why how which whom whose".split() + 
    "is are was were can could do does did will would should may might".split()
    + "have has had shall".split())


def looks_like_question(text):
    """True when the client asks something (for a RAG lookup)."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if "?" in t:
        return True
    first = t.split(" ", 1)[0].strip(".,!")
    return first in _QUESTION_WORDS


def parse_confirm_word(text):
    '''One-word LLM verdict to yes/no/unclear (None).'''
    t = (text or "").strip().upper()
    if t == "YES":
        return "yes"
    if t == "NO":
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


def retry_line(reason):
    """Chat line after a failed start (no buttons)."""
    return ("Something went wrong while starting: %s. Say 'start' to try again." % (reason or "unknown reason"))


def progress_lines(tl_rows, entry_rows):
    """Plain-English start progress from raw log rows.

    tl_rows: timeline.jsonl rows; entry_rows: Source PC entry
    log.jsonl rows. Returns (lines, failed, reason): the last
    few lines for the progress card, whether any failed event
    was seen, and the short reason. Never raises."""
    staged = []
    try:
        for r in tl_rows or []:
            if not isinstance(r, dict):
                continue
            at = str(r.get("at", "")).replace("T", " ")
            src, ev = r.get("source", ""), r.get("ev", "")
            summ = str(r.get("summary", ""))
            if ev in ("failed", "error"):
                staged.append((at, "", summ[:200]))
            elif (src, ev) == ("sam", "start"):
                staged.append((at, "Sam is writing the production request", ""))
            elif (src, ev) == ("sam", "done"):
                staged.append((at, "Production request written", ""))
            elif (src, ev) == ("sam", "parse"):
                staged.append((at, summ[:200], ""))
            elif (src, ev) == ("pc_worker", "start"):
                staged.append((at, "Reading your PDF", ""))
            elif (src, ev) == ("pc_worker", "done"):
                staged.append((at, "Search index ready", ""))
            elif (src, ev) == ("order", "start"):
                staged.append((at, "Starting the crew flow", ""))
        for r in entry_rows or []:
            if not isinstance(r, dict):
                continue
            at = str(r.get("at", "")).replace("T", " ")
            ev = r.get("ev", "")
            if ev == "ingested" and isinstance(r.get("pages"), int):
                staged.append((at, "Reading your PDF (%d pages)"
                                % r["pages"], ""))
            elif ev == "transcribe_call" and not r.get("error"):
                if r.get("kind") == "table":
                    staged.append((at, "Reading the table on page %s"
                                    % r.get("page", "?"), ""))
                elif r.get("kind") == "formula":
                    staged.append((at, "Reading formulas on page %s"
                                    % r.get("page", "?"), ""))
            elif ev == "transcribe_call" and r.get("error"):
                staged.append((at, "", str(r["error"])[:120]))
            elif ev == "index_done":
                staged.append((at, "Building the search index", ""))
    except (AttributeError, TypeError, ValueError):
        return [], False, ""
    staged.sort(key=lambda x: x[0])
    lines, failed, reason = [], False, ""
    for _, text, prob in staged:
        if prob and not text:
            failed = True
            reason = prob
            lines.append("Problem: " + prob)
        elif text:
            if text.startswith("Parsing your PDF") and lines \
                    and lines[-1].startswith("Parsing your PDF"):
                lines[-1] = text
            else:
                lines.append(text)
    if any(l.startswith("Reading your PDF (") for l in lines):
        lines = [l for l in lines if l != "Reading your PDF"]
    keep, seen = [], set()
    for l in lines:
        if l not in seen:
            keep.append(l)
            seen.add(l)
    return keep[-4:], failed, reason


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
