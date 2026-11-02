"""JSON contracts between crew (v1). Stdlib only."""

import os
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
REQUIRED_STRUCT_TOP = ("source_ref", "parts", "links", "duration")


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
    """Return a list of error strings (empty == valid). input_md_path
    is a markdown file path, or the markdown text itself (the Source
    entry text when Marty read it through PC tools)."""
    errors = []
    if not isinstance(obj, dict):
        return ["structure must be an object"]
    for k in REQUIRED_STRUCT_TOP:
        if k not in obj:
            errors.append("missing: %s" % k)
    sref = obj.get("source_ref", "")
    if not isinstance(sref, str) or not sref.startswith("pc://source/"):
        errors.append("source_ref must be a pc://source/<id> ref "
                      "(copy it from the source pointer)")
        sref = ""
    if isinstance(input_md_path, str) and not os.path.isfile(input_md_path):
        input_text = input_md_path
    else:
        try:
            with open(input_md_path, encoding="utf-8") as f:
                input_text = f.read()
        except (OSError, TypeError):
            return errors + ["cannot read input for heading check: %r" % (input_md_path,)]
    if not input_text.strip():
        return errors + ["no source text to check headings against"]
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
        skipped = obj.get("skipped", [])
        skipped_heads = []
        if skipped:
            if not isinstance(skipped, list):
                errors.append("skipped must be a list")
            else:
                for j, sk in enumerate(skipped):
                    if not isinstance(sk, dict):
                        errors.append("skipped[%d] must be an object" % j)
                        continue
                    sh = sk.get("heading")
                    if not isinstance(sh, str) or not sh.strip():
                        errors.append("skipped[%d] needs a non-empty heading" % j)
                    else:
                        skipped_heads.append(_norm(sh))
                    if not isinstance(sk.get("why"), str) \
                            or not sk["why"].strip():
                        errors.append("skipped[%d] needs a non-empty why" % j)
        want_seq = [_norm(h) for h in expected]
        accounted = set(got) | set(skipped_heads)
        for h in want_seq:
            if h not in accounted:
                errors.append("section not mapped: %r" % (h,))
        for j, h in enumerate(got):
            if h not in want_seq:
                errors.append("parts[%d].heading not found in input: %r" % (j, h))
        for h in skipped_heads:
            if h not in want_seq:
                errors.append("skipped heading not found in input: %r" % (h,))
            if h in set(got):
                errors.append("section both part and skipped: %r" % (h,))
        if [h for h in want_seq if h in set(got)] != got \
                and not [e for e in errors
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
    dur = obj.get("duration")
    if isinstance(dur, dict):
        total = dur.get("total_s")
        dparts = dur.get("parts")
        if not isinstance(total, int) or isinstance(total, bool) \
                or total <= 0:
            errors.append("duration.total_s must be a positive integer")
        if not isinstance(dparts, list) or not dparts:
            errors.append("duration.parts must be a non-empty list")
        else:
            dsum, dids = 0, []
            for j, dp in enumerate(dparts):
                if not isinstance(dp, dict):
                    errors.append("duration.parts[%d] must be an object"
                                  % j)
                    continue
                pid = dp.get("part_id")
                sec = dp.get("seconds")
                if pid not in ids:
                    errors.append("duration.parts[%d].part_id unknown "
                                  "part: %r" % (j, pid))
                elif pid in dids:
                    errors.append("duration.parts repeats %r" % (pid,))
                else:
                    dids.append(pid)
                if not isinstance(sec, int) or isinstance(sec, bool) \
                        or sec <= 0:
                    errors.append("duration.parts[%d].seconds must be "
                                  "a positive integer" % j)
                else:
                    dsum += sec
                if not isinstance(dp.get("why"), str) \
                        or not dp["why"].strip():
                    errors.append("duration.parts[%d] needs non-empty "
                                  "why" % j)
            if sorted(dids) != sorted(ids):
                errors.append("duration.parts must cover every part "
                              "exactly once")
            if isinstance(total, int) and dsum != total:
                errors.append("duration seconds sum to %d, not total_s "
                              "%d" % (dsum, total))
    elif "duration" in obj:
        errors.append("duration must be an object")
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


REQUIRED_REQUEST_TOP = ("order_id", "client_answers",
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
             "", "## Production notes", ""]
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


def validate_storyboard_draft(obj, struct):
    """Ash's scene plan: shape + times vs Marty's structure (with
    duration). PC-side rules (verbatim, readability, pick coverage)
    live in write_storyboard_draft. Returns [errors]."""
    errors = []
    if not isinstance(obj, dict):
        return ["storyboard_draft must be an object"]
    for k in ("total_s", "scenes", "unused_picks"):
        if k not in obj:
            errors.append("missing: %s" % k)
    total = obj.get("total_s")
    if not isinstance(total, int) or isinstance(total, bool) \
            or total <= 0:
        errors.append("total_s must be a positive integer")
    dur = (struct or {}).get("duration", {}) or {}
    if dur.get("total_s") != total:
        errors.append("total_s %r != structure plan %r"
                      % (total, dur.get("total_s")))
    plan = {p.get("part_id"): p.get("seconds")
            for p in dur.get("parts", []) or []
            if isinstance(p, dict)}
    scenes = obj.get("scenes")
    used = {}
    if isinstance(scenes, list):
        if not scenes:
            errors.append("scenes must be non-empty")
        prev_end = 0
        for i, sc in enumerate(scenes):
            where = "scenes[%d]" % i
            if not isinstance(sc, dict):
                errors.append("%s must be an object" % where)
                continue
            for k in ("n", "start_s", "end_s", "part_id", "role",
                      "viewer_learns", "screen_idea", "narration_points",
                      "materials", "handoff", "next_link"):
                if k not in sc:
                    errors.append("%s missing: %s" % (where, k))
            if sc.get("n") != i + 1:
                errors.append("%s.n must be %d" % (where, i + 1))
            st, en = sc.get("start_s"), sc.get("end_s")
            if st != prev_end:
                errors.append("%s.start_s %r breaks contiguity "
                              "(want %d)" % (where, st, prev_end))
            if not isinstance(en, int) or en <= (st or 0):
                errors.append("%s needs end_s > start_s" % where)
                continue
            if isinstance(st, int) and en - st < 10:
                errors.append("%s runs %ds, need at least 10 s"
                              % (where, en - st))
            prev_end = en
            pid = sc.get("part_id")
            if pid not in plan:
                errors.append("%s.part_id unknown part: %r"
                              % (where, pid))
            else:
                used[pid] = used.get(pid, 0) + (en - st)
            if sc.get("role") not in ("hook", "explain", "case",
                                      "recap", "other"):
                errors.append("%s.role must be hook|explain|case|"
                              "recap|other" % where)
            for key in ("viewer_learns", "screen_idea", "next_link"):
                _nonempty(errors, sc, key, where)
            nps = sc.get("narration_points")
            if not isinstance(nps, list) or not nps:
                errors.append("%s.narration_points must be non-empty"
                              % where)
            else:
                for j, np in enumerate(nps):
                    if not isinstance(np, dict):
                        errors.append("%s.narration_points[%d] must be "
                                      "an object" % (where, j))
                        continue
                    _nonempty(errors, np, "text",
                              "%s.narration_points[%d]" % (where, j))
                    cits = np.get("citations")
                    if not isinstance(cits, list):
                        errors.append("%s.narration_points[%d]."
                                      "citations must be a list"
                                      % (where, j))
                    else:
                        for c in cits:
                            if not isinstance(c, dict) \
                                    or not c.get("ref") \
                                    or "quote" not in c:
                                errors.append("%s.narration_points[%d] "
                                              "citations need "
                                              "{ref, quote}"
                                              % (where, j))
                                break
            for key, need in (("materials", ("ref", "from",
                                             "how_used")),
                              ("handoff", ("ref", "to", "why",
                                           "how_to_use"))):
                items = sc.get(key)
                if not isinstance(items, list):
                    errors.append("%s.%s must be a list"
                                  % (where, key))
                    continue
                for j, it in enumerate(items):
                    if not isinstance(it, dict) \
                            or any(k not in it for k in need):
                        errors.append("%s.%s[%d] needs %s"
                                      % (where, key, j,
                                         "/".join(need)))
                    elif key == "materials" and it.get("from") \
                            not in ("source", "theory", "article"):
                        errors.append("%s.materials[%d].from must be "
                                      "source|theory|article"
                                      % (where, j))
                    elif key == "handoff":
                        tos = it.get("to")
                        if not isinstance(tos, list) or not tos \
                                or any(t not in ("board_penn",
                                                 "voice_wren",
                                                 "slide_remy")
                                       for t in tos):
                            errors.append("%s.handoff[%d].to names "
                                          "Penn, Wren and/or Remy only"
                                          " (rows land on their clones"
                                          " through part_split)"
                                          % (where, j))
        if isinstance(total, int) and prev_end != total:
            errors.append("scenes end at %d, not total_s %d"
                          % (prev_end, total))
        for pid, psecs in plan.items():
            got = used.get(pid, 0)
            if not used or pid not in used:
                errors.append("part %r has no scene" % (pid,))
            elif abs(got - psecs) > psecs * 0.15:
                errors.append("part %r scenes sum to %ds, plan says "
                              "%ds (±15%%)" % (pid, got, psecs))
    elif "scenes" in obj:
        errors.append("scenes must be a list")
    ups = obj.get("unused_picks")
    if isinstance(ups, list):
        for j, u in enumerate(ups):
            if not isinstance(u, dict) or "ref" not in u \
                    or not u.get("why_not_used"):
                errors.append("unused_picks[%d] needs {ref, "
                              "why_not_used}" % j)
    elif "unused_picks" in obj:
        errors.append("unused_picks must be a list")
    return errors


def _draft_scene_map(draft):
    """{scene_n: (start_s, end_s)} from a storyboard_draft data."""
    out = {}
    for sc in ((draft or {}).get("scenes") or []):
        if isinstance(sc, dict) and isinstance(sc.get("n"), int):
            out[sc["n"]] = (sc.get("start_s"), sc.get("end_s"))
    return out


def _cut_set_diff(got, want, source):
    """Cut-set mismatch that says how to fix: which cuts are
    missing and which are extra."""
    try:
        return ("cut set must equal the %s (missing %s; extra %s)"
                % (source, sorted(set(want) - set(got)),
                   sorted(set(got) - set(want))))
    except TypeError:
        return "cut set must equal the %s (cut lists differ)" % source


def validate_storyboard(obj, narration):
    """Penn's cut descriptions v2: exact cut match vs Wren's
    narration, text ≤3 lines. Penn writes no timing: scene_n,
    start_s and end_s in his cuts are refused and the writer
    copies them from the narration instead. Returns [errors]."""
    errors = []
    if not isinstance(obj, dict):
        return ["storyboard must be an object"]
    want = set(_cut_id_map((narration or {}).get("cuts")))
    cuts = obj.get("cuts")
    if not isinstance(cuts, list):
        return errors + ["cuts must be a list"]
    got = []
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        for k in ("cut_id", "show_what", "show_why",
                  "on_screen_text"):
            if k not in cut:
                errors.append("%s missing: %s" % (where, k))
        for k in ("scene_n", "start_s", "end_s"):
            if k in cut:
                errors.append("%s: %s is copied by the writer; "
                              "write only cut_id/show_what/show_why/"
                              "on_screen_text" % (where, k))
        got.append(cut.get("cut_id"))
        if cut.get("cut_id") not in want:
            errors.append("%s.cut_id %r is not received"
                          % (where, cut.get("cut_id")))
        _nonempty(errors, cut, "show_what", where)
        _nonempty(errors, cut, "show_why", where)
        ost = cut.get("on_screen_text")
        if not isinstance(ost, list) or len(ost) > 3 \
                or any(not isinstance(t, str) or not t.strip()
                       for t in ost):
            errors.append("%s.on_screen_text must hold 0-3 "
                          "non-empty lines" % where)
    if sorted(got) != sorted(want):
        errors.append(_cut_set_diff(got, want, "narration"))
    return errors


def validate_narration(obj, draft):
    """Wren's lines v2: cuts tile their scenes (10-30 s), words
    counted, audio within ±15% of the cut, attempts 1-2. Citation
    rules live in write_narration. Returns [errors]."""
    errors = []
    if not isinstance(obj, dict):
        return ["narration must be an object"]
    want = _draft_scene_map(draft)
    cuts = obj.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        return errors + ["cuts must be a non-empty list"]
    seen = set()
    by_scene = {}
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        for k in ("cut_id", "scene_n", "start_s", "end_s",
                  "lines", "words", "audio", "attempts"):
            if k not in cut:
                errors.append("%s missing: %s" % (where, k))
        cid = cut.get("cut_id")
        if cid in seen:
            errors.append("%s.cut_id %r repeats" % (where, cid))
        seen.add(cid)
        n = cut.get("scene_n")
        st, en = cut.get("start_s"), cut.get("end_s")
        if n not in want:
            errors.append("%s.scene_n %r is not in the draft"
                          % (where, n))
        dur = None
        if isinstance(st, (int, float)) and isinstance(en,
                                                       (int, float)):
            dur = en - st
            if dur < CUT_MIN_S or dur > CUT_MAX_S:
                errors.append("%s lasts %ss, want %d-%d s"
                              % (where, dur, CUT_MIN_S,
                                 CUT_MAX_S))
        by_scene.setdefault(n, []).append(cut)
        lines = cut.get("lines")
        words = 0
        if not isinstance(lines, list) or not lines:
            errors.append("%s.lines must be non-empty" % where)
        else:
            for j, ln in enumerate(lines):
                if not isinstance(ln, dict):
                    errors.append("%s.lines[%d] must be an object"
                                  % (where, j))
                    continue
                _nonempty(errors, ln, "text",
                          "%s.lines[%d]" % (where, j))
                words += len(str(ln.get("text", "")).split())
                if not isinstance(ln.get("citations"), list):
                    errors.append("%s.lines[%d].citations must be "
                                  "a list" % (where, j))
        if cut.get("words") != words:
            errors.append("%s.words %r != counted %d"
                          % (where, cut.get("words"), words))
        att = cut.get("attempts")
        if not isinstance(att, int) or isinstance(att, bool) \
                or not (1 <= att <= VOICE_MAX_ATTEMPTS):
            errors.append("%s.attempts must be 1-%d"
                          % (where, VOICE_MAX_ATTEMPTS))
        audio = cut.get("audio")
        if not isinstance(audio, dict) \
                or not audio.get("voice_pc_ref") \
                or not isinstance(audio.get("seconds"),
                                   (int, float)):
            errors.append("%s.audio needs {voice_pc_ref, seconds}"
                          % where)
        elif isinstance(dur, (int, float)) and dur > 0:
            sec = audio["seconds"]
            if abs(sec - dur) > dur * TTS_FIT:
                errors.append("%s.audio %ss strays from cut %ss "
                              "(±15%%)" % (where, sec, dur))
    for n, group in by_scene.items():
        if n not in want:
            continue
        ordered = sorted(
            (c for c in group
             if isinstance(c.get("start_s"), (int, float))),
            key=lambda c: c["start_s"])
        d0, d1 = want[n]
        if not ordered or ordered[0]["start_s"] != d0 \
                or ordered[-1]["end_s"] != d1:
            errors.append("scene %r cuts must tile %r" % (n,
                                                          want[n]))
            continue
        for a, b in zip(ordered, ordered[1:]):
            if b["start_s"] != a["end_s"]:
                errors.append("scene %r cuts gap/overlap at %s"
                              % (n, b["start_s"]))
    got_scenes = sorted(s for s in by_scene if isinstance(s, int))
    if got_scenes != sorted(want):
        errors.append("scene set must equal the draft's: %r"
                      % (sorted(want),))
    return errors


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


def render_storyboard_draft_md(obj):
    """Ash's scene plan (storyboard_draft v1) as markdown."""
    lines = ["# Scene plan — %d scenes, %ds total"
             % (len(obj.get("scenes", [])), obj.get("total_s", 0)),
             ""]
    for sc in obj.get("scenes", []):
        lines += ["## Scene %s (%ds-%ds, %s)" % (sc.get("n"),
                                                 sc.get("start_s"),
                                                 sc.get("end_s"),
                                                 sc.get("part_id")),
                  "", "- Role: %s" % sc.get("role"),
                  "- Viewer learns: %s" % sc.get("viewer_learns"),
                  "- Screen: %s" % sc.get("screen_idea"),
                  "- Materials: %s"
                  % (", ".join("[%s](api/ref?ref=%s)"
                               % (m.get("ref"), m.get("ref"))
                               for m in sc.get("materials", []))
                     or "—"),
                  "- Handoff: %s"
                  % (", ".join("%s -> %s"
                               % (h.get("ref"),
                                  ",".join(h.get("to", [])))
                               for h in sc.get("handoff", []))
                     or "—"),
                  "- Next: %s" % sc.get("next_link"), ""]
    if obj.get("unused_picks"):
        lines += ["## Unused picks", ""]
        for u in obj["unused_picks"]:
            lines.append("- [%s](api/ref?ref=%s): %s"
                         % (u.get("ref"), u.get("ref"),
                            u.get("why_not_used")))
        lines.append("")
    return "\n".join(lines)


def render_storyboard_md(obj):
    """Penn's composition (storyboard v1) as markdown."""
    lines = ["# Storyboard — %d scenes" % len(obj.get("scenes", [])),
             ""]
    for sc in obj.get("scenes", []):
        lines += ["## Scene %s (%ds-%ds)" % (sc.get("scene_n"),
                                             sc.get("start_s"),
                                             sc.get("end_s")),
                  "", "- Layout: %s" % sc.get("layout"),
                  "- On screen: %s"
                  % (sc.get("on_screen_text") or "—"),
                  "- Visuals: %s" % "; ".join(sc.get("visuals", [])),
                  "- Materials: %s"
                  % (", ".join("[%s](api/ref?ref=%s)"
                               % (m.get("ref"), m.get("ref"))
                               for m in sc.get("materials", []))
                     or "—"),
                  "- Notes for Wren: %s" % sc.get("notes_for_wren"),
                  ""]
    return "\n".join(lines)


def render_narration_md(obj):
    """Wren's lines (narration v1) as markdown."""
    lines = ["# Narration — %d scenes" % len(obj.get("scenes", [])),
             ""]
    for sc in obj.get("scenes", []):
        lines += ["## Scene %s (%ds-%ds, %dw ~%ds)"
                  % (sc.get("scene_n"), sc.get("start_s"),
                     sc.get("end_s"), sc.get("words"),
                     sc.get("est_seconds")), ""]
        for ln in sc.get("lines", []):
            lines.append("- %s" % ln.get("text"))
            for c in ln.get("citations", []):
                lines.append("  [%s](api/ref?ref=%s): %s"
                             % (c.get("ref"), c.get("ref"),
                                (c.get("quote", "") or "")[:120]))
        lines.append("")
    return "\n".join(lines)


def render_source_v3_md(obj):
    """Source PC pointer (source v3) as markdown."""
    lines = ["# Source — %s" % obj["title"], "",
             "- Ref: [%s](api/ref?ref=%s)" % (obj["ref"], obj["ref"]),
             "- Characters: %d" % obj["chars"],
             "- Sections: %d" % obj["sections"],
             "- Recipients: %s"
             % (", ".join(r.get("agent", "?")
                          for r in obj.get("recipients", [])
                          if isinstance(r, dict)) or "—"), ""]
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
    """Structure map (structure v2/v3) as markdown."""
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
    if isinstance(obj.get("duration"), dict):
        dur = obj["duration"]
        lines += ["", "## Time plan (%ds total)" % dur.get("total_s"),
                  ""]
        for dp in dur.get("parts", []) or []:
            lines.append("- %s: %ds (%s)"
                         % (dp.get("part_id"), dp.get("seconds"),
                            dp.get("why")))
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


CUT_MIN_S = 10
CUT_MAX_S = 30
TTS_FIT = 0.15  # cut audio must sit within ±15% of the cut plan
VOICE_MAX_ATTEMPTS = 2
GEN_IMAGES_MAX = 6
REMY_MAX_RENDERS = 3
def _license_core(lic):
    """'by-sa-2.0'/'by-sa 2.0' -> 'by-sa' for the reuse check."""
    parts = str(lic or "").lower().replace(" ", "-").split("-")
    return "-".join(p for p in parts if p and not p[0].isdigit())


PICK_LICENSES = ("cc0", "pdm", "by", "by-sa")
LAYOUT_FIELDS = ("position", "size", "font_size", "alignment",
                 "crop", "zoom", "padding", "accent", "x", "y",
                 "width", "height", "font")


def _cut_id_map(cuts):
    """{cut_id: cut} for a cuts list."""
    out = {}
    for c in cuts or []:
        if isinstance(c, dict) and c.get("cut_id") is not None:
            out[c["cut_id"]] = c
    return out


def _check_cut_times(errors, where, cut, want):
    cid = cut.get("cut_id")
    if cid not in want:
        errors.append("%s.cut_id %r is not received" % (where, cid))
    elif (cut.get("start_s"), cut.get("end_s")) != want[cid]:
        errors.append("%s times %r != received %r"
                      % (where, (cut.get("start_s"),
                                 cut.get("end_s")), want[cid]))


def validate_style_guide(obj):
    """Penn's visual style: palette, fonts, tone, rules."""
    errors = []
    if not isinstance(obj, dict):
        return ["style_guide must be an object"]
    pal = obj.get("palette")
    if not isinstance(pal, dict):
        errors.append("palette must be an object")
    else:
        for k in ("background", "text", "accent"):
            if not pal.get(k) or not isinstance(pal[k], str):
                errors.append("palette.%s must be a non-empty "
                              "string" % k)
    fonts = obj.get("fonts")
    if not isinstance(fonts, dict):
        errors.append("fonts must be an object")
    else:
        for k in ("heading", "body"):
            if not fonts.get(k) or not isinstance(fonts[k], str):
                errors.append("fonts.%s must be a non-empty "
                              "string" % k)
    _nonempty(errors, obj, "image_tone", "style_guide")
    rules = obj.get("rules")
    if not isinstance(rules, list) or not rules \
            or any(not isinstance(r, str) or not r.strip()
                   for r in rules):
        errors.append("rules must be a non-empty string list")
    return errors


def validate_photo_picks(obj, storyboard):
    """Pia's picks: cut match vs Penn, licensed use-picks."""
    errors = []
    if not isinstance(obj, dict):
        return ["photo_picks must be an object"]
    want = _cut_id_map((storyboard or {}).get("cuts"))
    cuts = obj.get("cuts")
    if not isinstance(cuts, list):
        return errors + ["cuts must be a list"]
    got = []
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        if "cut_id" not in cut or "decision" not in cut:
            errors.append("%s needs {cut_id, decision}" % where)
            continue
        got.append(cut["cut_id"])
        if cut["cut_id"] not in want:
            errors.append("%s.cut_id %r is not in the storyboard"
                          % (where, cut["cut_id"]))
        if cut.get("decision") == "use":
            for k in ("kind", "ref", "file", "source_url",
                      "license", "reason"):
                if not cut.get(k) or not isinstance(cut[k], str):
                    errors.append("%s.%s must be a non-empty string "
                                  "for a use pick" % (where, k))
            if cut.get("kind") not in ("source_figure", "web"):
                errors.append("%s.kind must be source_figure or web"
                              % where)
            lic = str(cut.get("license", ""))
            if cut.get("kind") == "source_figure":
                if lic.lower() != "internal":
                    errors.append("%s.license must be 'internal' for a "
                                  "source_figure pick (got %r)"
                                  % (where, cut.get("license")))
            elif _license_core(lic) not in PICK_LICENSES:
                errors.append("%s.license %r is not reuse-permitted "
                              "(%s)" % (where, cut.get("license"),
                                        "/".join(PICK_LICENSES)))
        elif cut.get("decision") != "none":
            errors.append("%s.decision must be use or none" % where)
    if sorted(got) != sorted(want):
        errors.append(_cut_set_diff(got, want, "storyboard"))
    return errors


def validate_gen_picks(obj, storyboard):
    """Gene's choices: cut match, prompt per generate cut, ≤6 images."""
    errors = []
    if not isinstance(obj, dict):
        return ["gen_picks must be an object"]
    want = _cut_id_map((storyboard or {}).get("cuts"))
    cuts = obj.get("cuts")
    if not isinstance(cuts, list):
        return errors + ["cuts must be a list"]
    gen = set()
    got = []
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        if "cut_id" not in cut or "decision" not in cut:
            errors.append("%s needs {cut_id, decision}" % where)
            continue
        got.append(cut["cut_id"])
        if cut["cut_id"] not in want:
            errors.append("%s.cut_id %r is not in the storyboard"
                          % (where, cut["cut_id"]))
        if cut.get("decision") == "generate":
            gen.add(cut["cut_id"])
            for k in ("prompt", "reason"):
                if not cut.get(k) or not isinstance(cut[k], str):
                    errors.append("%s.%s must be a non-empty string "
                                  "for a generate cut" % (where, k))
        elif cut.get("decision") != "none":
            errors.append("%s.decision must be generate or none"
                          % where)
    if sorted(got) != sorted(want):
        errors.append(_cut_set_diff(got, want, "storyboard"))
    images = obj.get("images")
    if not isinstance(images, list):
        errors.append("images must be a list")
    else:
        if len(images) > GEN_IMAGES_MAX:
            errors.append("at most %d images per run, got %d"
                          % (GEN_IMAGES_MAX, len(images)))
        covered = set()
        for i, im in enumerate(images):
            where = "images[%d]" % i
            if not isinstance(im, dict):
                errors.append("%s must be an object" % where)
                continue
            for k in ("cut_id", "file", "prompt", "reused"):
                if k not in im:
                    errors.append("%s missing: %s" % (where, k))
            if im.get("cut_id") not in gen:
                errors.append("%s.cut_id %r has no generate "
                              "decision" % (where, im.get("cut_id")))
            covered.add(im.get("cut_id"))
        if gen - covered:
            errors.append("generate cuts without images: %r"
                          % (sorted(gen - covered),))
    return errors


ANIM_TEMPLATES = ("bar", "line", "table", "formula", "steps")


_ANIM_EXAMPLE = ('valid shape e.g. {"template": "steps", "values": '
                 '{"items": ["First the desk logs the claim", "Then '
                 'the reviewer checks the table"]}, "refs": [{"ref": '
                 '"pc://source/<id>#s1.2/p7", "quote": "<verbatim '
                 'paragraph holding both sentences>"}], "reason": '
                 '"<why this cut needs motion>"}')


def _anim_values_ok(template, values, where, errors):
    """Template-shaped values object for a Max use pick."""
    _n0 = len(errors)
    if not isinstance(values, dict):
        errors.append("%s.values must be an object for a use pick"
                      % where)
        errors.append("%s.%s" % (where, _ANIM_EXAMPLE))
        return
    if template == "table":
        heads = values.get("headers")
        rows = values.get("rows")
        if not isinstance(heads, list) or not heads or \
                not all(isinstance(t, str) and t for t in heads):
            errors.append("%s.values.headers nonempty str list"
                          % where)
            heads = []
        if not isinstance(rows, list) or not rows or len(rows) > 10:
            errors.append("%s.values.rows 1-10" % where)
        else:
            for r in rows:
                if not isinstance(r, list) or len(r) != len(heads) \
                        or not all(isinstance(t, str) for t in r):
                    errors.append("%s.values.rows match headers"
                                  % where)
                    break
    elif template in ("bar", "line"):
        labs = values.get("labels")
        vals = values.get("values")
        if not isinstance(labs, list) or len(labs) < 2 or \
                not all(isinstance(t, str) and t for t in labs):
            errors.append("%s.values.labels >= 2 nonempty" % where)
            labs = []
        if not isinstance(vals, list) or len(vals) != len(labs) \
                or not all(_is_num(v) for v in vals):
            errors.append("%s.values.values match labels" % where)
    elif template == "formula":
        lines = values.get("lines")
        if not isinstance(lines, list) or not lines or \
                len(lines) > 8 or \
                not all(isinstance(t, str) and t for t in lines):
            errors.append("%s.values.lines 1-8 nonempty" % where)
    elif template == "steps":
        items = values.get("items")
        if not isinstance(items, list) or \
                not (2 <= len(items) <= 8) or \
                not all(isinstance(t, str) and t for t in items):
            errors.append("%s.values.items 2-8 nonempty" % where)
    if len(errors) > _n0:
        errors.append("%s.%s" % (where, _ANIM_EXAMPLE))


def validate_anim_picks(obj, storyboard):
    """Max's picks v2: cut match, template + structured values +
    verbatim refs per use."""
    errors = []
    if not isinstance(obj, dict):
        return ["anim_picks must be an object"]
    want = _cut_id_map((storyboard or {}).get("cuts"))
    cuts = obj.get("cuts")
    if not isinstance(cuts, list):
        return errors + ["cuts must be a list"]
    got = []
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        if "cut_id" not in cut or "decision" not in cut:
            errors.append("%s needs {cut_id, decision}" % where)
            continue
        got.append(cut["cut_id"])
        if cut["cut_id"] not in want:
            errors.append("%s.cut_id %r is not in the storyboard"
                          % (where, cut["cut_id"]))
        if cut.get("decision") == "use":
            if cut.get("template") not in ANIM_TEMPLATES:
                errors.append("%s.template one of %s for a use pick"
                              % (where, ANIM_TEMPLATES))
                errors.append("%s.%s" % (where, _ANIM_EXAMPLE))
            else:
                _anim_values_ok(cut["template"], cut.get("values"),
                                where, errors)
            refs = cut.get("refs")
            if not isinstance(refs, list) or not refs:
                errors.append("%s.refs must be a non-empty list "
                              "for a use pick" % where)
            else:
                for j, r in enumerate(refs):
                    if not isinstance(r, dict) or \
                            not isinstance(r.get("ref"), str) or \
                            not r.get("ref") or \
                            not isinstance(r.get("quote"), str) or \
                            not r.get("quote"):
                        errors.append("%s.refs[%d] needs "
                                      "{ref, quote}" % (where, j))
            if not cut.get("reason") or \
                    not isinstance(cut["reason"], str):
                errors.append("%s.reason must be a non-empty string "
                              "for a use pick" % where)
        elif cut.get("decision") == "none":
            if "template" in cut or "values" in cut:
                errors.append("%s: a none pick holds no "
                              "template/values" % where)
        else:
            errors.append("%s.decision must be use or none" % where)
    if sorted(got) != sorted(want):
        errors.append(_cut_set_diff(got, want, "storyboard"))
    return errors


# --- Cut-slide layout (Remotion CutSlide, 1280x720) ----------------------
SLIDE_W = 1280
SLIDE_H = 720
SAFE_MARGIN = 64          # 5% of width on every side
MIN_FONT = 20             # smallest size for data blocks at 720p
MIN_FONT_TEXT = 32        # text blocks stay readable at 720p
MIN_FONT_ONSCREEN = 36    # bottom on-screen line (renderer-fixed)
VERA_MAX_BLOCKS = 4
REVEAL_STEP_S = {"table": 0.5, "formula": 1.0, "steps": 0.8}
BLOCK_MAX_ITEMS = {"table": 10, "formula": 8, "steps": 8, "text": 6}
BLOCK_KINDS = ("photo", "generated", "source_figure", "table",
               "formula", "chart", "steps", "text")
LAYOUT_PRESETS = ("full", "split_h", "split_v", "main_side",
                  "grid2x2")
BLOCK_FONT_DEFAULT = {"table": 24, "formula": 30, "steps": 26,
                      "text": 44}


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_cut_layout(cut, dur_s):
    """One slide cut: boxes inside the safe area, no overlap, fonts
    readable, reveal steps finish inside the cut."""
    cid = cut.get("cut_id") if isinstance(cut, dict) else "?"
    errors = []
    if not isinstance(cut, dict):
        return ["cut %s must be an object" % cid]
    where = "cut %s" % cid
    if cut.get("preset") not in LAYOUT_PRESETS:
        errors.append("%s.preset one of %s" % (where, LAYOUT_PRESETS))
    blocks = cut.get("blocks")
    if not isinstance(blocks, list) or \
            not (1 <= len(blocks) <= VERA_MAX_BLOCKS):
        errors.append("%s.blocks must hold 1-%d items"
                      % (where, VERA_MAX_BLOCKS))
        return errors
    boxes = []
    for j, b in enumerate(blocks):
        bw = "%s.blocks[%d]" % (where, j)
        if not isinstance(b, dict):
            errors.append("%s must be an object" % bw)
            continue
        kind = b.get("kind")
        if kind not in BLOCK_KINDS:
            errors.append("%s.kind one of %s" % (bw, BLOCK_KINDS))
        box = b.get("box")
        w = None
        if isinstance(box, dict):
            vals = [box.get(k) for k in ("x", "y", "w", "h")]
            if all(isinstance(v, int) and not isinstance(v, bool)
                   and v >= 0 for v in vals):
                x, y, w, h = vals
                min_w, min_h = (200, 40) if kind == "text" \
                    else (120, 90)
                if w < min_w or h < min_h:
                    errors.append("%s.box min %dx%d"
                                  % (bw, min_w, min_h))
                if x < SAFE_MARGIN or y < SAFE_MARGIN or \
                        x + w > SLIDE_W - SAFE_MARGIN or \
                        y + h > SLIDE_H - SAFE_MARGIN:
                    errors.append("%s.box outside the safe area" % bw)
                boxes.append((j, x, y, w, h))
            else:
                errors.append("%s.box x/y/w/h ints >= 0" % bw)
        else:
            errors.append("%s.box must be an object" % bw)
        font = b.get("font_size",
                     BLOCK_FONT_DEFAULT.get(kind, MIN_FONT + 4))
        need = MIN_FONT_TEXT if kind == "text" else MIN_FONT
        font_ok = isinstance(font, int) and \
            not isinstance(font, bool) and font >= need
        if not font_ok:
            errors.append(
                "%s.font_size int >= %d (text blocks: widen the "
                "box or shorten the line, never go smaller)"
                % (bw, need))
        ap = b.get("appear_s", 0)
        ap_ok = _is_num(ap) and 0 <= ap < dur_s
        if not ap_ok:
            errors.append("%s.appear_s in [0, %s)"
                          % (bw, dur_s))
        if not isinstance(b.get("order"), int) or \
                isinstance(b.get("order"), bool) or \
                b.get("order") < 0:
            errors.append("%s.order int >= 0" % bw)
        if not isinstance(b.get("reason"), str) or not b.get("reason"):
            errors.append("%s.reason needs non-empty text" % bw)
        data = b.get("data") if isinstance(b.get("data"), dict) \
            else {}
        reveal_n = 0
        if kind == "table":
            heads = data.get("headers")
            rows = data.get("rows")
            if not isinstance(heads, list) or not heads or \
                    not all(isinstance(t, str) and t for t in heads):
                errors.append("%s.data.headers nonempty str list"
                              % bw)
                heads = []
            if not isinstance(rows, list) or not rows or \
                    len(rows) > BLOCK_MAX_ITEMS["table"]:
                errors.append("%s.data.rows 1-%d"
                              % (bw, BLOCK_MAX_ITEMS["table"]))
                rows = []
            else:
                for r in rows:
                    if not isinstance(r, list) or \
                            len(r) != len(heads) or \
                            not all(isinstance(t, str) for t in r):
                        errors.append("%s.data.rows match headers"
                                      % bw)
                        break
            if data.get("reveal", "all") not in ("all", "rows"):
                errors.append("%s.data.reveal must be 'all' or 'rows' "
                              "(got %r)" % (bw, data.get("reveal")))
            elif data.get("reveal") == "rows":
                reveal_n = len(rows)
            if font_ok and w is not None and heads:
                longest = max(
                    [len(t) for t in heads if isinstance(t, str)]
                    + [len(t) for r in rows if isinstance(r, list)
                       for t in r if isinstance(t, str)] + [0])
                if longest * font * 0.55 * len(heads) > w:
                    errors.append("%s.data too wide for the box" % bw)
        elif kind == "formula":
            lines = data.get("lines")
            if not isinstance(lines, list) or not lines or \
                    len(lines) > BLOCK_MAX_ITEMS["formula"] or \
                    not all(isinstance(t, str) and t for t in lines):
                errors.append("%s.data.lines 1-%d nonempty"
                              % (bw, BLOCK_MAX_ITEMS["formula"]))
                lines = []
            reveal_n = len(lines)
            if font_ok and w is not None and lines:
                longest = max(len(t) for t in lines)
                if longest * font * 0.55 * 0.8 > w:
                    errors.append("%s.data too wide for the box" % bw)
        elif kind == "chart":
            if data.get("subtype") not in ("bar", "line"):
                errors.append("%s.data.subtype bar|line" % bw)
            labs = data.get("labels")
            vals = data.get("values")
            if not isinstance(labs, list) or len(labs) < 2 or \
                    not all(isinstance(t, str) and t for t in labs):
                errors.append("%s.data.labels >= 2 nonempty" % bw)
                labs = []
            if not isinstance(vals, list) or len(vals) != len(labs) \
                    or not all(_is_num(v) for v in vals):
                errors.append("%s.data.values match labels" % bw)
        elif kind == "steps":
            items = data.get("items")
            if not isinstance(items, list) or \
                    not (2 <= len(items) <= BLOCK_MAX_ITEMS["steps"]) \
                    or not all(isinstance(t, str) and t
                               for t in items):
                errors.append("%s.data.items 2-%d nonempty"
                              % (bw, BLOCK_MAX_ITEMS["steps"]))
                items = []
            reveal_n = len(items)
            if font_ok and w is not None and items:
                need = sum(len(t) for t in items) * font * 0.55 \
                    + (len(items) - 1) * font
                if need > w:
                    errors.append("%s.data too wide for the box" % bw)
        elif kind == "text":
            lines = data.get("lines")
            if not isinstance(lines, list) or \
                    not (1 <= len(lines) <= BLOCK_MAX_ITEMS["text"]) \
                    or not all(isinstance(t, str) and t
                               for t in lines):
                errors.append("%s.data.lines 1-%d nonempty"
                              % (bw, BLOCK_MAX_ITEMS["text"]))
                lines = []
            if font_ok and w is not None and lines:
                longest = max(len(t) for t in lines)
                if longest * font * 0.55 > w:
                    errors.append("%s.data too wide for the box" % bw)
        elif kind in ("photo", "generated", "source_figure"):
            if not isinstance(b.get("ref"), str) or not b.get("ref"):
                errors.append("%s.ref needs non-empty text" % bw)
        step = REVEAL_STEP_S.get(kind)
        if step and reveal_n > 1 and ap_ok and \
                ap + (reveal_n - 1) * step > dur_s:
            errors.append("%s reveal ends after the cut" % bw)
    for a in range(len(boxes)):
        for b2 in range(a + 1, len(boxes)):
            _, x1, y1, w1, h1 = boxes[a]
            _, x2, y2, w2, h2 = boxes[b2]
            if x1 < x2 + w2 and x2 < x1 + w1 and \
                    y1 < y2 + h2 and y2 < y1 + h1:
                errors.append("%s.blocks[%d] overlaps blocks[%d]"
                              % (where, boxes[a][0], boxes[b2][0]))
    said = {}
    for ln in (cut.get("on_screen_text") or []):
        if isinstance(ln, str) and ln.strip():
            said[_norm(ln)] = "on_screen_text"
    for j, b in enumerate(blocks):
        if not isinstance(b, dict) or b.get("kind") != "text":
            continue
        data = b.get("data") if isinstance(b.get("data"), dict) \
            else {}
        for ln in (data.get("lines") or []):
            if not isinstance(ln, str) or not ln.strip():
                continue
            key = _norm(ln)
            if key in said:
                errors.append(
                    "%s.blocks[%d] repeats the %s line %r "
                    "(say it once: keep it in on_screen_text, cut "
                    "it from the block)" % (where, j, said[key],
                                             ln.strip()[:60]))
            else:
                said[key] = "%s.blocks[%d]" % (where, j)
    return errors


def validate_slide_draft(obj, narration):
    """Vera's slide plan v2: cut+time match vs Wren, Remotion-ready
    layout (preset + boxed blocks)."""
    errors = []
    if not isinstance(obj, dict):
        return ["slide_draft must be an object"]
    want = {}
    for cid, c in _cut_id_map((narration or {}).get("cuts")).items():
        want[cid] = (c.get("start_s"), c.get("end_s"))
    cuts = obj.get("cuts")
    if not isinstance(cuts, list):
        return errors + ["cuts must be a list"]
    got = []
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        for k in ("cut_id", "start_s", "end_s", "preset", "blocks",
                  "on_screen_text", "transitions", "why"):
            if k not in cut:
                errors.append("%s missing: %s" % (where, k))
        got.append(cut.get("cut_id"))
        _check_cut_times(errors, where, cut, want)
        st, en = cut.get("start_s"), cut.get("end_s")
        if _is_num(st) and _is_num(en) and en > st:
            for e in validate_cut_layout(cut, en - st):
                errors.append("%s.%s" % (where, e))
        _nonempty(errors, cut, "preset", where)
        _nonempty(errors, cut, "why", where)
        for k in ("on_screen_text", "transitions"):
            if not isinstance(cut.get(k), list):
                errors.append("%s.%s must be a list" % (where, k))
    if sorted(got) != sorted(want):
        errors.append(_cut_set_diff(got, want, "narration"))
    return errors


def validate_render_log(obj, slide_draft):
    """Remy's render record: cut match, ≤3 renders, layout-only
    adjustments. Content equality lives in the render tool."""
    errors = []
    if not isinstance(obj, dict):
        return ["render_log must be an object"]
    want = set(_cut_id_map((slide_draft or {}).get("cuts")))
    cuts = obj.get("cuts")
    if not isinstance(cuts, list):
        return errors + ["cuts must be a list"]
    got = []
    for i, cut in enumerate(cuts):
        where = "cuts[%d]" % i
        if not isinstance(cut, dict):
            errors.append("%s must be an object" % where)
            continue
        for k in ("cut_id", "slide_file", "renders_n",
                  "adjustments", "issues"):
            if k not in cut:
                errors.append("%s missing: %s" % (where, k))
        got.append(cut.get("cut_id"))
        if cut.get("cut_id") not in want:
            errors.append("%s.cut_id %r is not in the slide draft"
                          % (where, cut.get("cut_id")))
        status = cut.get("status", "rendered")
        if status not in ("rendered", "remotion_unavailable"):
            errors.append("%s.status must be rendered or "
                          "remotion_unavailable" % where)
        if status == "remotion_unavailable":
            if not isinstance(cut.get("slide_file"), str):
                errors.append("%s.slide_file must be a string"
                              % where)
            if cut.get("renders_n") != 0:
                errors.append("%s.renders_n must be 0 when Remotion "
                              "is unavailable" % where)
        else:
            _nonempty(errors, cut, "slide_file", where)
            n = cut.get("renders_n")
            if not isinstance(n, int) or isinstance(n, bool) \
                    or not (1 <= n <= REMY_MAX_RENDERS):
                errors.append("%s.renders_n must be 1-%d"
                              % (where, REMY_MAX_RENDERS))
        adjs = cut.get("adjustments")
        if not isinstance(adjs, list):
            errors.append("%s.adjustments must be a list" % where)
        else:
            for j, a in enumerate(adjs):
                if not isinstance(a, dict):
                    errors.append("%s.adjustments[%d] must be an "
                                  "object" % (where, j))
                    continue
                for k in ("field", "was", "now"):
                    if k not in a:
                        errors.append("%s.adjustments[%d] missing: "
                                      "%s" % (where, j, k))
                if a.get("field") not in LAYOUT_FIELDS:
                    errors.append("%s.adjustments[%d].field %r is "
                                  "not a layout value"
                                  % (where, j, a.get("field")))
        if not isinstance(cut.get("issues"), list):
            errors.append("%s.issues must be a list" % where)
    if sorted(got) != sorted(want):
        errors.append(_cut_set_diff(got, want, "slide draft"))
    return errors


def validate_storyboard_table(obj):
    """Final table: one row per cut with narration/screen/materials."""
    errors = []
    if not isinstance(obj, dict):
        return ["storyboard_table must be an object"]
    rows = obj.get("rows")
    if not isinstance(rows, list) or not rows:
        return errors + ["rows must be a non-empty list"]
    for i, r in enumerate(rows):
        where = "rows[%d]" % i
        if not isinstance(r, dict):
            errors.append("%s must be an object" % where)
            continue
        for k in ("part", "scene_n", "cut_id", "start_s",
                  "end_s", "narration", "screen", "materials"):
            if k not in r:
                errors.append("%s missing: %s" % (where, k))
        if not isinstance(r.get("materials"), list):
            errors.append("%s.materials must be a list" % where)
    return errors


def render_narration_v2_md(obj):
    """Wren's cuts (narration v2) as markdown."""
    lines = ["# Narration — %d cuts" % len(obj.get("cuts", [])),
             ""]
    for c in obj.get("cuts", []):
        a = c.get("audio", {})
        lines.append("## Cut %s (scene %s, %s–%s s, %d words, "
                     "audio %ss, %d attempt(s))"
                     % (c.get("cut_id"), c.get("scene_n"),
                        c.get("start_s"), c.get("end_s"),
                        c.get("words"), a.get("seconds"),
                        c.get("attempts")))
        lines.append("")
        for ln in c.get("lines", []):
            lines.append("- %s" % ln.get("text"))
            for cit in ln.get("citations", []):
                lines.append("  [%s](api/ref?ref=%s): %s"
                             % (cit.get("ref"), cit.get("ref"),
                                (cit.get("quote", "") or "")[:120]))
        lines.append("")
    return "\n".join(lines)


def render_storyboard_v2_md(obj):
    """Penn's cut descriptions (storyboard v2) as markdown."""
    lines = ["# Cut screens — %d cuts" % len(obj.get("cuts", [])),
             ""]
    for c in obj.get("cuts", []):
        lines += ["## Cut %s (scene %s, %s–%s s)"
                  % (c.get("cut_id"), c.get("scene_n"),
                     c.get("start_s"), c.get("end_s")),
                  "", "- Show: %s" % c.get("show_what"),
                  "- Why: %s" % c.get("show_why"),
                  "- On screen: %s"
                  % (" / ".join(c.get("on_screen_text", []))
                     or "—"), ""]
    return "\n".join(lines)


def render_style_guide_md(obj):
    """Penn's style guide as markdown."""
    pal = obj.get("palette", {})
    fonts = obj.get("fonts", {})
    lines = ["# Style guide", "",
             "- Palette: %s / %s / %s"
             % (pal.get("background"), pal.get("text"),
                pal.get("accent")),
             "- Fonts: %s / %s"
             % (fonts.get("heading"), fonts.get("body")),
             "- Image tone: %s" % obj.get("image_tone"), "",
             "## Rules", ""]
    for r in obj.get("rules", []):
        lines.append("- %s" % r)
    lines.append("")
    return "\n".join(lines)


def _render_pick_cuts_md(title, cuts, fmt):
    lines = ["# %s — %d cuts" % (title, len(cuts)), ""]
    for c in cuts:
        lines.append("## Cut %s: %s"
                     % (c.get("cut_id"), c.get("decision")))
        lines.append("")
        lines.append(fmt(c))
        lines.append("")
    return "\n".join(lines)


def _pick_size(c):
    """'WxH (aspect A)' for a stamped pick, else 'unknown'."""
    w, h = c.get("width"), c.get("height")
    good = all(isinstance(v, (int, float))
               and not isinstance(v, bool) and v > 0
               for v in (w, h))
    if not good:
        return "unknown"
    return "%sx%s (aspect %s)" % (w, h, round(w / h, 2))


def render_photo_picks_md(obj):
    """Pia's picks as markdown."""
    def fmt(c):
        if c.get("decision") == "none":
            return "No photo for this cut."
        return "- Kind: %s\n- File: %s\n- Source: %s\n- License: " \
               "%s\n- Size: %s\n- Why: %s" % (c.get("kind"), c.get("file"),
                                  c.get("source_url"),
                                  c.get("license"), _pick_size(c),
                                  c.get("reason"))
    return _render_pick_cuts_md("Photo picks",
                                obj.get("cuts", []), fmt)


def render_gen_picks_md(obj):
    """Gene's choices as markdown."""
    def fmt(c):
        if c.get("decision") == "none":
            return "No generated image for this cut."
        return "- Prompt: %s\n- Why: %s" % (c.get("prompt"),
                                            c.get("reason"))
    lines = [_render_pick_cuts_md("Generation choices",
                                  obj.get("cuts", []), fmt)]
    lines.append("## Images (%d)" % len(obj.get("images", [])))
    lines.append("")
    for im in obj.get("images", []):
        lines.append("- Cut %s: %s%s"
                     % (im.get("cut_id"), im.get("file"),
                        " (reused)" if im.get("reused") else ""))
    lines.append("")
    return "\n".join(lines)


def render_anim_picks_md(obj):
    """Max's picks as markdown."""
    def fmt(c):
        if c.get("decision") == "none":
            return "No animation for this cut."
        return "- Template: %s\n- Values: %s\n- Refs: %s\n- Why: " \
               "%s" % (c.get("template"), c.get("values"),
                       ", ".join(c.get("refs", [])),
                       c.get("reason"))
    return _render_pick_cuts_md("Animation picks",
                                obj.get("cuts", []), fmt)


def render_slide_draft_md(obj):
    """Vera's slide plan (v2 layout) as markdown."""
    lines = ["# Slide plan — %d cuts" % len(obj.get("cuts", [])),
             ""]
    for c in obj.get("cuts", []):
        lines += ["## Cut %s (%s–%s s)"
                  % (c.get("cut_id"), c.get("start_s"),
                     c.get("end_s")),
                  "", "- Layout: %s" % (c.get("preset") or
                                         c.get("layout")),
                  "- On screen: %s"
                  % (" / ".join(c.get("on_screen_text", []))
                     or "—"),
                  "- Transitions: %s"
                  % (", ".join(c.get("transitions", [])) or "—"),
                  "- Why: %s" % c.get("why")]
        for b in c.get("blocks", []):
            if not isinstance(b, dict):
                continue
            box = b.get("box") or {}
            lines.append("- Block [%s] %s @(%s,%s %sx%s): %s"
                         % (b.get("kind"),
                            b.get("ref") or "inline data",
                            box.get("x"), box.get("y"),
                            box.get("w"), box.get("h"),
                            b.get("reason")))
        lines.append("")
    return "\n".join(lines)


def render_render_log_md(obj):
    """Remy's render record as markdown."""
    lines = ["# Render log — %d cuts" % len(obj.get("cuts", [])),
             ""]
    for c in obj.get("cuts", []):
        lines += ["## Cut %s: %s (%d render(s))"
                  % (c.get("cut_id"), c.get("slide_file"),
                     c.get("renders_n")),
                  ""]
        for a in c.get("adjustments", []):
            lines.append("- %s: %s -> %s"
                         % (a.get("field"), a.get("was"),
                            a.get("now")))
        for issue in c.get("issues", []):
            lines.append("- Issue: %s" % issue)
        lines.append("")
    return "\n".join(lines)


def render_storyboard_table_md(obj):
    """Final storyboard table as markdown."""
    lines = ["# Storyboard table — %d cuts"
             % len(obj.get("rows", [])), "",
             "| Part | Scene | Cut | Time | Narration | Screen | "
             "Materials |",
             "|---|---|---|---|---|---|---|"]
    for r in obj.get("rows", []):
        lines.append("| %s | %s | %s | %s–%s | %s | %s | %s |"
                     % (r.get("part"), r.get("scene_n"),
                        r.get("cut_id"), r.get("start_s"),
                        r.get("end_s"), r.get("narration"),
                        r.get("screen"),
                        "; ".join(r.get("materials", []))))
    lines.append("")
    return "\n".join(lines)
