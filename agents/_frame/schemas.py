"""JSON contracts between crew (v1). Stdlib only."""

import re
from urllib.parse import quote as _urlquote

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


REQUIRED_CONCEPT_TOP = ("common_theme", "core_question",
                          "viewer_takeaway", "intent_overall")
REQUIRED_STRUCT_TOP = ("source_ref", "parts", "links")


def validate_concept(obj):
    """Return a list of error strings (empty == valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["concept must be an object"]
    for k in REQUIRED_CONCEPT_TOP:
        if k not in obj:
            errors.append("concept missing: %s" % k)
        elif (not isinstance(obj[k], str) or not obj[k].strip()):
            errors.append("concept.%s must be a non-empty string" % k)
    return errors


def validate_structure(obj, input_md_path):
    """Return a list of error strings (empty == valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["structure must be an object"]
    for k in REQUIRED_STRUCT_TOP:
        if k not in obj:
            errors.append("missing: %s" % k)
    sref = obj.get("source_ref", "")
    if not isinstance(sref, str) or not sref.startswith("pc://source/"):
        errors.append("source_ref must be a pc://source/<id> ref "
                      "(copy it from the input head)")
        sref = ""
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
            ref = p.get("ref", "")
            if sref and (not isinstance(ref, str)
                          or not ref.startswith(sref + "#s")):
                errors.append("parts[%s].ref must be the input section "
                              "address (%s#s<n>)" % (pid, sref))
            elif not sref and (not isinstance(ref, str)
                                or not ref.strip()):
                errors.append("parts[%s] needs a non-empty ref" % (pid,))
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
    links = obj.get("links")
    if isinstance(links, list):
        seen = set()
        for j, lk in enumerate(links):
            if not isinstance(lk, dict):
                errors.append("links[%d] must be an object" % j)
                continue
            a, b = lk.get("from"), lk.get("to")
            if a not in ids:
                errors.append("links[%d].from unknown part: %r" % (j, a))
            if b not in ids:
                errors.append("links[%d].to unknown part: %r" % (j, b))
            if not isinstance(lk.get("why"), str) or not lk["why"].strip():
                errors.append("links[%d] needs non-empty why" % j)
            if isinstance(a, str) and isinstance(b, str):
                seen.add((a, b))
        for i in range(1, len(ids)):
            pair = (ids[i - 1], ids[i])
            if pair not in seen:
                errors.append("missing neighbour link %s->%s" % pair)
    elif "links" in obj:
        errors.append("links must be a list")
    return errors


PRIORITIES = ("must", "should", "optional")
CASE_KINDS = ("event", "company", "person", "film", "other")


def _nonempty(errors, obj, key, where):
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        errors.append("%s needs non-empty %s" % (where, key))


def _check_citations(errors, claim, where):
    cits = claim.get("citations")
    if not isinstance(cits, list) or not cits:
        errors.append("%s needs >=1 citation" % where)
        return
    for n, cit in enumerate(cits):
        cw = "%s.citations[%d]" % (where, n)
        if not isinstance(cit, dict):
            errors.append("%s must be an object" % cw)
            continue
        _nonempty(errors, cit, "ref", cw)
        _nonempty(errors, cit, "quote", cw)


def _check_pick(errors, pick, where, want_pc):
    if not isinstance(pick, dict):
        errors.append("%s must be an object" % where)
        return
    for k in ("ref", "title", "why_important", "how_to_use"):
        _nonempty(errors, pick, k, where)
    ref = pick.get("ref", "")
    if (isinstance(ref, str) and ref
            and not ref.startswith("pc://%s/" % want_pc)):
        errors.append("%s.ref must point at the %s PC" % (where, want_pc))
    ev = pick.get("evidence")
    if not isinstance(ev, dict):
        errors.append("%s.evidence must be {ref, quote}" % where)
    else:
        _nonempty(errors, ev, "ref", where + ".evidence")
        _nonempty(errors, ev, "quote", where + ".evidence")
        eref = ev.get("ref", "")
        if (isinstance(ref, str) and isinstance(eref, str) and ref
                and eref and not eref.startswith(ref)):
            errors.append("%s.evidence.ref must sit inside the pick"
                          % where)
    if pick.get("priority") not in PRIORITIES:
        errors.append("%s.priority must be must|should|optional" % where)


def _check_part_ids(errors, parts, where):
    for i, p in enumerate(parts):
        want = "p%d" % (i + 1)
        if not isinstance(p, dict) or p.get("part_id") != want:
            errors.append("%s[%d].part_id must be %r" % (where, i, want))


def _check_gaps(errors, part, where):
    gaps = part.get("gaps")
    if (not isinstance(gaps, list)
            or any(not isinstance(g, str) for g in gaps)):
        errors.append("%s.gaps must be a string list" % where)


def validate_concepts(obj):
    """Return a list of error strings (empty == valid). Static shape
    only; verbatim and picks-match checks live in the writer tool."""
    errors = []
    if not isinstance(obj, dict):
        return ["concepts must be an object"]
    parts = obj.get("parts")
    if not isinstance(parts, list) or not parts:
        return ["concepts.parts must be a non-empty list"]
    _check_part_ids(errors, parts, "concepts.parts")
    for i, p in enumerate(parts):
        if not isinstance(p, dict):
            errors.append("concepts.parts[%d] must be an object" % i)
            continue
        where = "concepts.parts[%s]" % p.get("part_id", i)
        for k in ("concept_name", "easy_explanation", "why_it_came_about",
                  "analogy_or_example", "common_misunderstanding"):
            _nonempty(errors, p, k, where)
        words = p.get("easy_explanation", "")
        if (isinstance(words, str) and words.strip()
                and len(words.split()) < 30):
            errors.append("%s.easy_explanation too thin (%d words, "
                          "need >=30)" % (where, len(words.split())))
        claims = p.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append("%s needs >=1 claim" % where)
        else:
            for m, cl in enumerate(claims):
                cw = "%s.claims[%d]" % (where, m)
                if not isinstance(cl, dict):
                    errors.append("%s must be an object" % cw)
                    continue
                _nonempty(errors, cl, "text", cw)
                _check_citations(errors, cl, cw)
        picks = p.get("picks")
        if not isinstance(picks, list):
            errors.append("%s.picks must be a list" % where)
        else:
            for m, pk in enumerate(picks):
                _check_pick(errors, pk, "%s.picks[%d]" % (where, m),
                            "theory")
        _check_gaps(errors, p, where)
    return errors


def validate_cases(obj):
    """Return a list of error strings (empty == valid). Static shape
    only; verbatim and picks-match checks live in the writer tool."""
    errors = []
    if not isinstance(obj, dict):
        return ["cases must be an object"]
    parts = obj.get("parts")
    if not isinstance(parts, list) or not parts:
        return ["cases.parts must be a non-empty list"]
    _check_part_ids(errors, parts, "cases.parts")
    for i, p in enumerate(parts):
        if not isinstance(p, dict):
            errors.append("cases.parts[%d] must be an object" % i)
            continue
        where = "cases.parts[%s]" % p.get("part_id", i)
        cases = p.get("cases")
        if not isinstance(cases, list) or not cases:
            errors.append("%s needs >=1 case" % where)
        else:
            for m, cs in enumerate(cases):
                cw = "%s.cases[%d]" % (where, m)
                if not isinstance(cs, dict):
                    errors.append("%s must be an object" % cw)
                    continue
                for k in ("title", "summary", "fit_why",
                          "viewer_hook"):
                    _nonempty(errors, cs, k, cw)
                words = cs.get("summary", "")
                if (isinstance(words, str) and words.strip()
                        and len(words.split()) < 15):
                    errors.append("%s.summary too thin (%d words, "
                                  "need >=15)" % (cw, len(words.split())))
                if cs.get("kind") not in CASE_KINDS:
                    errors.append("%s.kind must be %s"
                                  % (cw, "|".join(CASE_KINDS)))
                date = cs.get("date", "")
                if (not isinstance(date, str) or not date.strip()
                        or not any(ch.isdigit() for ch in date)):
                    errors.append("%s.date must name when it happened"
                                  % cw)
                claims = cs.get("claims")
                if not isinstance(claims, list) or not claims:
                    errors.append("%s needs >=1 claim" % cw)
                else:
                    for n, cl in enumerate(claims):
                        lw = "%s.claims[%d]" % (cw, n)
                        if not isinstance(cl, dict):
                            errors.append("%s must be an object" % lw)
                            continue
                        _nonempty(errors, cl, "text", lw)
                        _check_citations(errors, cl, lw)
        picks = p.get("picks")
        if not isinstance(picks, list):
            errors.append("%s.picks must be a list" % where)
        else:
            for m, pk in enumerate(picks):
                _check_pick(errors, pk, "%s.picks[%d]" % (where, m),
                            "article")
        _check_gaps(errors, p, where)
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
    """Production request (request v1 report template) from a valid object."""
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


def render_cite_md(ref, quote):
    """One citation as a link that opens the passage via open_ref."""
    return "[%s](api/ref?ref=%s)" % (quote, _urlquote(ref, safe=""))


def render_brief_md(obj):
    """Order intake (brief v1) as markdown."""
    ans = obj["answers"]
    return "\n".join(
        ["# Order brief — %s" % obj["order_id"], "",
         "- Audience: %s" % ans["audience"],
         "- Target length: %s" % ans["length"],
         "- Depth: %s" % ans["depth"],
         "- Theme direction: %s" % ans["theme"],
         "- Source file: %s" % obj["source_file"], ""])


def render_source_md(obj):
    """Source pointer (source v1) as markdown."""
    lines = ["# Source — %s" % obj["file"], "",
             "- Characters: %d" % obj["chars"], ""]
    if obj.get("head"):
        lines += ["## Opening excerpt", "", obj["head"], ""]
    return "\n".join(lines)


def render_source_v2_md(obj):
    """Source PC pointer (source v2) as markdown."""
    lines = ["# Source — %s" % obj["title"], "",
             "- Ref: [%s](api/ref?ref=%s)" % (obj["ref"], obj["ref"]),
             "- Characters: %d" % obj["chars"],
             "- Sections: %d" % obj["sections"], ""]
    if obj.get("head"):
        lines += ["## Opening excerpt", "", obj["head"], ""]
    return "\n".join(lines)


def render_structure_md(obj):
    """Structure map (structure v1) as markdown."""
    src = obj["source"]
    lines = ["# Structure map — %s / %s" % (src["book"], src["chapter"]),
             "", "Theme: %s" % obj["common_theme"], "", "## Parts", ""]
    for p in obj["parts"]:
        lines.append("- %s `%s`: %s (keywords: %s)"
                     % (p["id"], p["heading"], p["covers"],
                        ", ".join(p["keywords"])))
    lines += ["", "## Author intent", "", obj["intent"]["overall"], ""]
    for link in obj["intent"]["links"]:
        lines.append("- %s -> %s: %s"
                     % (link["from"], link["to"], link["why"]))
    lines.append("")
    return "\n".join(lines)


def render_concept_md(obj):
    """Video concept (concept v1) as markdown."""
    return "\n".join(
        ["# Video concept", "", "Theme: %s" % obj["common_theme"], "",
         "## Core question", "", obj["core_question"], "",
         "## Viewer takeaway", "", obj["viewer_takeaway"], "",
         "## Author intent (overall)", "", obj["intent_overall"], ""])


def render_structure_v2_md(obj):
    """Structure map (structure v2) as markdown."""
    lines = ["# Structure map — %s" % obj["source_ref"], "",
             "## Parts", ""]
    for p in obj["parts"]:
        lines.append("- %s `%s`: %s (keywords: %s) [%s]"
                     % (p["id"], p["heading"], p["covers"],
                        ", ".join(p["keywords"]), p["ref"]))
    lines += ["", "## Links", ""]
    for link in obj["links"]:
        lines.append("- %s -> %s: %s"
                     % (link["from"], link["to"], link["why"]))
    lines.append("")
    return "\n".join(lines)


def _render_claims_md(lines, claims):
    for cl in claims:
        lines.append("- %s" % cl["text"])
        for cit in cl["citations"]:
            lines.append("  - %s"
                         % render_cite_md(cit["ref"], cit["quote"]))
    return lines


def _render_picks_md(lines, picks):
    for pk in picks:
        lines.append("- [%s] %s (%s)"
                     % (pk["priority"], pk["title"],
                        render_cite_md(pk["ref"], pk["ref"])))
        lines.append("  Why: %s Use: %s"
                     % (pk["why_important"], pk["how_to_use"]))
        ev = pk["evidence"]
        lines.append("  Evidence: %s"
                     % render_cite_md(ev["ref"], ev["quote"]))
    return lines


def render_concepts_md(obj):
    """Easy theory report (concepts v1) as markdown."""
    lines = ["# Concepts report", ""]
    for p in obj["parts"]:
        lines += ["## %s — %s" % (p["part_id"], p["concept_name"]), "",
                  p["easy_explanation"], "",
                  "Why it came about: %s" % p["why_it_came_about"], "",
                  "Analogy: %s" % p["analogy_or_example"], "",
                  "Common misunderstanding: %s"
                  % p["common_misunderstanding"], "", "### Claims", ""]
        _render_claims_md(lines, p["claims"])
        lines += ["", "### Picks", ""]
        if p["picks"]:
            _render_picks_md(lines, p["picks"])
        else:
            lines.append("- None.")
        lines += ["", "### Gaps", ""]
        if p["gaps"]:
            lines += ["- %s" % g for g in p["gaps"]]
        else:
            lines.append("- None.")
        lines.append("")
    return "\n".join(lines)


def render_cases_md(obj):
    """Case research report (cases v1) as markdown."""
    lines = ["# Cases report", ""]
    for p in obj["parts"]:
        lines += ["## %s" % p["part_id"], ""]
        for cs in p["cases"]:
            lines += ["### %s (%s, %s)" % (cs["title"], cs["kind"],
                                           cs["date"]),
                      "", cs["summary"], "",
                      "Fit: %s" % cs["fit_why"],
                      "Hook: %s" % cs["viewer_hook"], ""]
            _render_claims_md(lines, cs["claims"])
            lines.append("")
        lines += ["### Picks", ""]
        if p["picks"]:
            _render_picks_md(lines, p["picks"])
        else:
            lines.append("- None.")
        lines += ["", "### Gaps", ""]
        if p["gaps"]:
            lines += ["- %s" % g for g in p["gaps"]]
        else:
            lines.append("- None.")
        lines.append("")
    return "\n".join(lines)


def render_video_md(obj):
    """Video assembly record (video v1) as markdown."""
    f = obj["file"]
    lines = ["# Video — %s" % f["path"], "",
             "- Size: %d bytes, %s, %s" % (f["size_bytes"], f["format"],
                                           f["resolution"]),
             "- Duration: %s s" % obj["duration_s"],
             "- Built from run: %s" % obj["built_from"], ""]
    for sc in obj["scenes"]:
        lines.append("## Scene %d (%s–%s s)"
                     % (sc["n"], sc["start_s"], sc["end_s"]))
        lines.append("")
        for ln in sc["lines"]:
            cites = " ".join(render_cite_md(c["ref"], c["quote"])
                             for c in ln["citations"])
            lines.append('- "%s" (%s–%s s) %s'
                         % (ln["text"], ln["start_s"], ln["end_s"], cites))
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
