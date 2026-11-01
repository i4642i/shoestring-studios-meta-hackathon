"""Order intake helpers: readiness, confirm strings, PDF sections.

Readiness is decided by code (the missing list), never by the model.
Stdlib only; imported by scripts/server.py and tested by
scripts/order_check.py (no sockets, no model calls).
"""
import json
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
CHAT_UNREADABLE = ("Sam's reply could not be read, "
                   "please send again.")
START_LINE = "Great — starting production now."
RECEIVED_LINE = "Thanks! Your order is in. The crew has started."


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
            elif ev == "progress" and type(r.get("pct")) is int:
                staged.append((at, "Parsing your PDF\u2026 %d%%"
                                % r["pct"], ""))
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


def chat_reply_payload(reply, ready, missing, form=None):
    """Chat/upload reply envelope: the client needs the missing list
    with every reply (PDF button shows only when it is exactly
    ["source PDF"]). The production request form rides along so the
    panel next to the chat fills up as Sam learns."""
    out = {"reply": reply, "ready": bool(ready),
           "missing": list(missing or [])}
    if form is not None:
        out["form"] = {k: (form.get(k) or "") for k in FORM_FIELDS}
        out["form_complete"] = form_complete(form)
    return out


FORM_FIELDS = ("audience", "length", "depth", "theme")
FORM_LABELS = {"audience": "Audience", "length": "Target length",
               "depth": "Depth", "theme": "Theme direction"}


def blank_form():
    """Empty production request form (source of truth for finalize)."""
    return {k: "" for k in FORM_FIELDS}


def form_complete(form):
    """Decided by code: every field holds non-blank text."""
    form = form if isinstance(form, dict) else {}
    return all(isinstance(form.get(k), str) and form[k].strip()
               for k in FORM_FIELDS)


def final_request_prompt(oid, form, pdf_name, pdf_bytes):
    """One-shot writer prompt: the final request from the form."""
    vals = {k: (form.get(k) or "") for k in FORM_FIELDS}
    return (
        "Write the final production request as ONE JSON object, no other "
        "text:\n"
        '{"order_id": "...", "client_answers": {"audience": "...", '
        '"length": "...", "depth": "...", "theme": "...", '
        '"source": "..."}, '
        '"production_notes": ["...", ...], "open_questions": [...]}\n'
        "Rules: client_answers.audience/length/depth/theme come from the "
        "FORM below, word for word; client_answers.source is the PDF file "
        "name. Never describe the source contents: the file is not "
        "parsed yet at your time; the Source PC map summarizes it. "
        "production_notes: 2-5 short crew instructions grounded in the "
        "form. open_questions: [] unless something is genuinely unclear.\n"
        "ORDER: %s\nFORM: %s\nSOURCE PDF: %s (%d bytes)"
        % (oid, json.dumps(vals, ensure_ascii=False),
           pdf_name, pdf_bytes))


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
