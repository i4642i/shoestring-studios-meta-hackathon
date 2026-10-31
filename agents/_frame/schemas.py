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
                                                 "voice_wren")
                                       for t in tos):
                            errors.append("%s.handoff[%d].to names "
                                          "Penn and/or Wren only"
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


def validate_storyboard(obj, narration):
    """Penn's cut descriptions v2: exact cut match vs Wren's
    narration, text ≤3 lines. Returns [errors]."""
    errors = []
    if not isinstance(obj, dict):
        return ["storyboard must be an object"]
    want = {}
    for cid, c in _cut_id_map(
            (narration or {}).get("cuts")).items():
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
        for k in ("cut_id", "scene_n", "start_s", "end_s",
                  "show_what", "show_why", "on_screen_text"):
            if k not in cut:
                errors.append("%s missing: %s" % (where, k))
        got.append(cut.get("cut_id"))
        _check_cut_times(errors, where, cut, want)
        _nonempty(errors, cut, "show_what", where)
        _nonempty(errors, cut, "show_why", where)
        ost = cut.get("on_screen_text")
        if not isinstance(ost, list) or len(ost) > 3 \
                or any(not isinstance(t, str) or not t.strip()
                       for t in ost):
            errors.append("%s.on_screen_text must hold 0-3 "
                          "non-empty lines" % where)
    if sorted(got) != sorted(want):
        errors.append("cut set must equal the narration's")
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
VERA_MAX_MATERIALS = 2
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
            if str(cut.get("license", "")).lower() \
                    not in PICK_LICENSES:
                errors.append("%s.license %r is not reuse-permitted "
                              "(%s)" % (where, cut.get("license"),
                                        "/".join(PICK_LICENSES)))
        elif cut.get("decision") != "none":
            errors.append("%s.decision must be use or none" % where)
    if sorted(got) != sorted(want):
        errors.append("cut set must equal the storyboard's")
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
        errors.append("cut set must equal the storyboard's")
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


def validate_anim_picks(obj, storyboard):
    """Max's picks: cut match, template + values + refs per use."""
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
            if cut.get("template") in (None, "", "none"):
                errors.append("%s.template must name a template "
                              "for a use pick" % where)
            for k in ("values", "reason"):
                if not cut.get(k) or not isinstance(cut[k], str):
                    errors.append("%s.%s must be a non-empty string "
                                  "for a use pick" % (where, k))
            if not isinstance(cut.get("refs"), list) \
                    or not cut["refs"]:
                errors.append("%s.refs must be a non-empty list "
                              "for a use pick" % where)
        elif cut.get("decision") != "none":
            errors.append("%s.decision must be use or none" % where)
    if sorted(got) != sorted(want):
        errors.append("cut set must equal the storyboard's")
    return errors


def validate_slide_draft(obj, narration):
    """Vera's slide plan: cut+time match vs Wren, 1-2 materials."""
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
        for k in ("cut_id", "start_s", "end_s", "materials",
                  "layout", "on_screen_text", "transitions",
                  "why"):
            if k not in cut:
                errors.append("%s missing: %s" % (where, k))
        got.append(cut.get("cut_id"))
        _check_cut_times(errors, where, cut, want)
        mats = cut.get("materials")
        if not isinstance(mats, list) or not (1 <= len(mats)
                                             <= VERA_MAX_MATERIALS):
            errors.append("%s.materials must hold 1-%d items"
                          % (where, VERA_MAX_MATERIALS))
        else:
            for j, m in enumerate(mats):
                if not isinstance(m, dict) or not m.get("kind") \
                        or not m.get("use"):
                    errors.append("%s.materials[%d] needs "
                                  "{kind, use}" % (where, j))
        _nonempty(errors, cut, "layout", where)
        _nonempty(errors, cut, "why", where)
        for k in ("on_screen_text", "transitions"):
            if not isinstance(cut.get(k), list):
                errors.append("%s.%s must be a list" % (where, k))
    if sorted(got) != sorted(want):
        errors.append("cut set must equal the narration's")
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
        errors.append("cut set must equal the slide draft's")
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


def render_photo_picks_md(obj):
    """Pia's picks as markdown."""
    def fmt(c):
        if c.get("decision") == "none":
            return "No photo for this cut."
        return "- Kind: %s\n- File: %s\n- Source: %s\n- License: " \
               "%s\n- Why: %s" % (c.get("kind"), c.get("file"),
                                  c.get("source_url"),
                                  c.get("license"), c.get("reason"))
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
    """Vera's slide plan as markdown."""
    lines = ["# Slide plan — %d cuts" % len(obj.get("cuts", [])),
             ""]
    for c in obj.get("cuts", []):
        lines += ["## Cut %s (%s–%s s)"
                  % (c.get("cut_id"), c.get("start_s"),
                     c.get("end_s")),
                  "", "- Layout: %s" % c.get("layout"),
                  "- On screen: %s"
                  % (" / ".join(c.get("on_screen_text", []))
                     or "—"),
                  "- Transitions: %s"
                  % (", ".join(c.get("transitions", [])) or "—"),
                  "- Why: %s" % c.get("why")]
        for m in c.get("materials", []):
            lines.append("- Material [%s]: %s (%s)"
                         % (m.get("kind"), m.get("file") or
                            m.get("ref") or "—", m.get("use")))
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
