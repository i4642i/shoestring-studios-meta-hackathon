"""JSON contracts between crew (v1). Stdlib only."""

import re

DRAFT_SCHEMA_V1 = "storyboard-draft/1"
STRUCTURE_SCHEMA_V1 = "structure-map/1"
REQUEST_SCHEMA_V1 = "production-request/1"

# A "numbered section" head: digits.digits, exactly one dot ("1.1", "10.3").
# "1.2.1" must NOT match: the char after the second number may not be . or digit.
ONE_DOT_RE = re.compile(r"^(\d+)\.(\d+)(?![\d.])")
DEEP_NUM_RE = re.compile(r"^(\d+(?:\.\d+){2,})(?![\d.])")


def list_headings(text):
    """Section headings exactly as read_md_section sees them.

    Returns [(level, title)] in source order; level = count of '#'."""
    out = []
    for ln in text.splitlines():
        if not ln.startswith("#"):
            continue
        stripped = ln.lstrip("#")
        level = len(ln) - len(stripped)
        out.append((level, stripped.strip()))
    return out


def _norm(s):
    return " ".join(str(s).split()).lower()


def expected_parts(text):
    """Headings Marty must map, in source order.

    Numbered mode: every one-dot section (1.1, 1.2, ...). Fallback (none
    found): headings at the top level under the document title.
    Returns (mode, [titles])."""
    heads = list_headings(text)
    numbered = [t for _, t in heads if ONE_DOT_RE.match(_num_prefix(t))]
    if numbered:
        return "numbered", numbered
    if not heads:
        return "fallback", []
    title_level = heads[0][0]
    rest = [(lv, t) for lv, t in heads[1:] if lv > title_level]
    if not rest:
        return "fallback", [heads[0][1]]
    top = min(lv for lv, _ in rest)
    return "fallback", [t for lv, t in rest if lv == top]


def _num_prefix(title):
    """Leading section number of a heading title ('' when none)."""
    m = re.match(r"^(\d+(?:\.\d+)*)", title.strip())
    return m.group(1) if m else ""


def deep_sections(text):
    """Deeper numbered headings (two+ dots) in source order: [(number, title)]."""
    out = []
    for _, t in list_headings(text):
        m = DEEP_NUM_RE.match(t.strip())
        if m:
            out.append((m.group(1), t.strip()))
    return out


def _title_words(title):
    return [w for w in re.findall(r"[A-Za-z]+", title) if len(w) > 3]

REQUIRED_TOP = ("title", "key_ideas", "scenes")


def validate_draft(obj):
    """Return a list of error strings (empty == valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["draft must be an object"]
    for k in REQUIRED_TOP:
        if k not in obj:
            errors.append("missing: %s" % k)
    ideas = obj.get("key_ideas")
    if isinstance(ideas, list):
        if not 2 <= len(ideas) <= 4:
            errors.append("key_ideas must have 2-4 items (got %d)" % len(ideas))
        for i, idea in enumerate(ideas):
            if not isinstance(idea, dict):
                errors.append("key_ideas[%d] must be an object" % i)
            elif not idea.get("id") or not idea.get("title"):
                errors.append("key_ideas[%d] needs id + title" % i)
    elif "key_ideas" in obj:
        errors.append("key_ideas must be a list")
    scenes = obj.get("scenes")
    if isinstance(scenes, list):
        if not scenes:
            errors.append("scenes must be non-empty")
        for i, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                errors.append("scenes[%d] must be an object" % i)
                continue
            if not sc.get("narration"):
                errors.append("scenes[%d] needs narration" % i)
            srcs = sc.get("sources")
            if not isinstance(srcs, list) or not srcs:
                errors.append("scenes[%d] needs >=1 source" % i)
    elif "scenes" in obj:
        errors.append("scenes must be a list")
    if "title" in obj and not isinstance(obj["title"], str):
        errors.append("title must be a string")
    return errors


REQUIRED_STRUCT_TOP = ("source", "common_theme", "parts", "intent")


def validate_structure(obj, input_md_path):
    """Return a list of error strings (empty == valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["structure must be an object"]
    for k in REQUIRED_STRUCT_TOP:
        if k not in obj:
            errors.append("missing: %s" % k)
    src = obj.get("source")
    if isinstance(src, dict):
        for k in ("book", "chapter"):
            if not isinstance(src.get(k), str) or not src[k].strip():
                errors.append("source.%s must be a non-empty string" % k)
    elif "source" in obj:
        errors.append("source must be an object")
    if "common_theme" in obj and (
            not isinstance(obj["common_theme"], str)
            or not obj["common_theme"].strip()):
        errors.append("common_theme must be a non-empty string")
    try:
        with open(input_md_path, encoding="utf-8") as f:
            input_text = f.read()
    except (OSError, TypeError):
        return errors + ["cannot read input for heading check: %r" % (input_md_path,)]
    _mode, expected = expected_parts(input_text)
    parts = obj.get("parts")
    ids = []
    if isinstance(parts, list):
        if not parts:
            errors.append("parts must be non-empty")
        got = []
        for i, p in enumerate(parts):
            want = "p%d" % (i + 1)
            if not isinstance(p, dict):
                errors.append("parts[%d] must be an object" % i)
                continue
            pid = p.get("id")
            if pid != want:
                errors.append("parts[%d].id must be %r (got %r)" % (i, want, pid))
            if isinstance(pid, str):
                ids.append(pid)
            heading = p.get("heading")
            if not isinstance(heading, str) or not heading.strip():
                errors.append("parts[%s] needs a non-empty heading" % (pid,))
            else:
                got.append(_norm(heading))
            if not isinstance(p.get("covers"), str) or not p["covers"].strip():
                errors.append("parts[%s] needs non-empty covers" % (pid,))
            kws = p.get("keywords")
            if (not isinstance(kws, list) or not kws
                    or any(not isinstance(k, str) or not k.strip() for k in kws)):
                errors.append("parts[%s].keywords must be a non-empty string list" % (pid,))
        want_seq = [_norm(h) for h in expected]
        for h in want_seq:
            if h not in got:
                errors.append("section not mapped: %r" % (h,))
        for j, h in enumerate(got):
            if h not in want_seq:
                errors.append("parts[%d].heading not found in input: %r" % (j, h))
        if got != want_seq and not [e for e in errors
                                     if "not mapped" in e or "not found in input" in e]:
            errors.append("parts must follow source order")
        for num, title in deep_sections(input_text):
            parent = _parent_part(num, parts)
            if parent is None:
                continue
            blob = _norm(str(parent.get("covers", "")) + " "
                          + " ".join(parent.get("keywords") or []
                                      if isinstance(parent.get("keywords"), list) else []))
            words = [_norm(w) for w in _title_words(title)]
            hit = num in blob or (words and all(w in blob for w in words))
            if not hit:
                errors.append("deeper section %s (%r) missing from parent %s covers/keywords"
                              % (num, title, parent.get("id")))
    elif "parts" in obj:
        errors.append("parts must be a list")
    intent = obj.get("intent")
    if isinstance(intent, dict):
        if not isinstance(intent.get("overall"), str) or not intent["overall"].strip():
            errors.append("intent.overall must be a non-empty string")
        links = intent.get("links")
        if isinstance(links, list):
            seen = set()
            for j, lk in enumerate(links):
                if not isinstance(lk, dict):
                    errors.append("intent.links[%d] must be an object" % j)
                    continue
                a, b = lk.get("from"), lk.get("to")
                if a not in ids:
                    errors.append("intent.links[%d].from unknown part: %r" % (j, a))
                if b not in ids:
                    errors.append("intent.links[%d].to unknown part: %r" % (j, b))
                if not isinstance(lk.get("why"), str) or not lk["why"].strip():
                    errors.append("intent.links[%d] needs non-empty why" % j)
                if isinstance(a, str) and isinstance(b, str):
                    seen.add((a, b))
            for i in range(1, len(ids)):
                pair = (ids[i - 1], ids[i])
                if pair not in seen:
                    errors.append("missing neighbour link %s->%s" % pair)
        elif "links" in intent:
            errors.append("intent.links must be a list")
        else:
            errors.append("missing: intent.links")
    elif "intent" in obj:
        errors.append("intent must be an object")
    return errors


REQUIRED_REQUEST_TOP = ("order_id", "client_answers", "source_summary",
                          "production_notes", "open_questions")
REQUIRED_ANSWERS = ("audience", "length", "depth", "theme", "source")


def validate_request(obj):
    """Return a list of error strings (empty == valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["request must be an object"]
    for k in REQUIRED_REQUEST_TOP:
        if k not in obj:
            errors.append("missing: %s" % k)
    if "order_id" in obj and (
            not isinstance(obj["order_id"], str)
            or not obj["order_id"].strip()):
        errors.append("order_id must be a non-empty string")
    ans = obj.get("client_answers")
    if isinstance(ans, dict):
        for k in REQUIRED_ANSWERS:
            if not isinstance(ans.get(k), str) or not ans[k].strip():
                errors.append("client_answers.%s must be a non-empty string" % k)
    elif "client_answers" in obj:
        errors.append("client_answers must be an object")
    if "source_summary" in obj and (
            not isinstance(obj["source_summary"], str)
            or not obj["source_summary"].strip()):
        errors.append("source_summary must be a non-empty string")
    notes = obj.get("production_notes")
    if isinstance(notes, list):
        if not notes or any(not isinstance(n, str) or not n.strip()
                             for n in notes):
            errors.append("production_notes must be a non-empty string list")
    elif "production_notes" in obj:
        errors.append("production_notes must be a list")
    qs = obj.get("open_questions")
    if isinstance(qs, list):
        if any(not isinstance(q, str) or not q.strip() for q in qs):
            errors.append("open_questions must be a string list")
    elif "open_questions" in obj:
        errors.append("open_questions must be a list")
    return errors


def render_request_md(obj):
    """Human-readable production request (request.md) from a valid object."""
    ans = obj["client_answers"]
    lines = ["# Video production request — %s" % obj["order_id"], "",
             "Written by sales for PD/production from the order consultation.",
             "", "## Client answers (intake)",
             "",
             "- Audience: %s" % ans["audience"],
             "- Target length: %s" % ans["length"],
             "- Depth: %s" % ans["depth"],
             "- Theme direction: %s" % ans["theme"],
             "- Source material: %s" % ans["source"],
             "", "## Source summary", "",
             obj["source_summary"], "", "## Production notes", ""]
    lines += ["- %s" % n for n in obj["production_notes"]]
    lines += ["", "## Open questions", ""]
    if obj["open_questions"]:
        lines += ["- %s" % q for q in obj["open_questions"]]
    else:
        lines += ["- None."]
    lines.append("")
    return "\n".join(lines)


def _parent_part(number, parts):
    """Part owning a deeper section: prefix parent, else nearest preceding part."""
    prefix = number.rsplit(".", 1)[0]
    while "." in prefix:
        for p in parts:
            if isinstance(p, dict) and _num_prefix(str(p.get("heading", ""))) == prefix:
                return p
        prefix = prefix.rsplit(".", 1)[0]
    for p in parts:
        if isinstance(p, dict) and _num_prefix(str(p.get("heading", ""))) == prefix:
            return p
    return parts[0] if parts and isinstance(parts[0], dict) else None
