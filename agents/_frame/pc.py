"""Company PC core: ids, page cleaning, sections, addresses, open_ref.

Pure functions (stdlib only) behind the Source PC ingest pipeline and
the open_ref reader. Docs: RESULT_JSON_DRAFT_EN.md sections 8-10.
"""
import hashlib
import os
import re

MAP_VERSION = 1
PCS = ("source", "theory", "article")

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))


def pc_dir(pc):
    assert pc in PCS, "unknown PC: %r" % pc
    return os.path.join(ROOT, "storage", "_pc", pc)


def entry_dir(pc, doc_id):
    return os.path.join(pc_dir(pc), "entries", doc_id)


def index_dir(pc, profile):
    return os.path.join(pc_dir(pc), "index", profile)


# ---- ids and refs (§9) ----
def normalize_text(s):
    return " ".join((s or "").split()).lower()


def content_id(text):
    return hashlib.sha256(normalize_text(text).encode()).hexdigest()[:12]


def entry_ref(pc, doc_id):
    return "pc://%s/%s" % (pc, doc_id)


_REF_RE = re.compile(r"^pc://(source|theory|article)/([0-9a-f]{12})"
                     r"(?:#(.*))?$")


def parse_ref(ref):
    m = _REF_RE.match(ref or "")
    if not m:
        raise ValueError("bad ref: %r" % ref)
    return m.group(1), m.group(2), m.group(3) or ""


# ---- page cleaning ----
_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$")
_BULLET_RE = re.compile(r"^(?:[-*\u2022\u2023]|\d+[.)]"
                         r"|\([a-z0-9]+\))\s+\S")
_CAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s\-:;,&'\u2019]{1,60}$")
_BARE_NUM_RE = re.compile(r"^(?:\d{1,4}|p(?:ag(?:e)?)?\.?\s*\d{1,4})$",
                           re.IGNORECASE)
def _is_heading(line):
    m = _HEADING_RE.match(line)
    return (m.group(1), m.group(2)) if m else None


def _is_bullet(line):
    return bool(_BULLET_RE.match(line))


def _is_caps(line):
    return bool(_CAPS_RE.match(line))


def _strip_zones(page_lines):
    """Drop running headers/footers: the first/last line of each page is
    a candidate; a candidate on most pages (>= half + 1, needs >= 2
    pages) is removed everywhere it sits in a zone. Bare page numbers
    in zones go unconditionally."""
    counts = {}
    for lines in page_lines:
        lead = [ln for ln in lines if ln[0].strip()]
        if not lead:
            continue
        keys = {" ".join(lead[0][0].split()).lower(),
                " ".join(lead[-1][0].split()).lower()}
        for key in keys:
            if len(key) >= 2:
                counts[key] = counts.get(key, 0) + 1
    need = len(page_lines) // 2 + 1 if len(page_lines) >= 2 else 10 ** 9
    repeats = {k for k, n in counts.items() if n >= need}
    out = []
    for lines in page_lines:
        keep = []
        edge = [i for i, (ln, _pg) in enumerate(lines) if ln.strip()]
        zone_idx = {edge[0], edge[-1]} if edge else set()
        for i, (ln, pg) in enumerate(lines):
            s = ln.strip()
            zone = i in zone_idx
            if zone and (_BARE_NUM_RE.match(s)
                         or " ".join(s.split()).lower() in repeats):
                continue
            keep.append((ln, pg))
        out.append(keep)
    return out


def _join_hyphens(lines):
    """Re-join words hyphenated across line ends: next line starting
    lowercase drops the hyphen, starting uppercase keeps it."""
    out = []
    i = 0
    while i < len(lines):
        ln, pg = lines[i]
        if (ln.endswith("-") and len(ln) > 1 and i + 1 < len(lines)
                and lines[i + 1][0][:1].strip()):
            nxt, npg = lines[i + 1]
            both = pg + tuple(p for p in npg if p not in pg)
            if nxt[:1].islower():
                out.append((ln[:-1] + nxt, both))
            else:
                out.append((ln + nxt, both))
            i += 2
            continue
        if ln.endswith("\xad") and i + 1 < len(lines):
            npg = lines[i + 1][1]
            both = pg + tuple(p for p in npg if p not in pg)
            out.append((ln[:-1] + lines[i + 1][0], both))
            i += 2
            continue
        out.append((ln, pg))
        i += 1
    return out


def _tag_objects(lines):
    """Tag table/formula lines: {line_index: [tab/eq addr]}. Tables are
    2+ consecutive same-page lines each holding 2+ wide gaps; formulas
    hold '=' plus a digit or math symbol."""
    tags = {}
    tab_n, eq_n = {}, {}
    i = 0
    while i < len(lines):
        ln, pg = lines[i]
        if ln.strip() and len(re.findall(r"\s{2,}", ln)) >= 2:
            j = i
            while (j < len(lines) and lines[j][0].strip()
                   and set(lines[j][1]) & set(pg)
                   and len(re.findall(r"\s{2,}", lines[j][0])) >= 2):
                j += 1
            if j - i >= 2:
                tab_n[pg[0]] = tab_n.get(pg[0], 0) + 1
                addr = "tab%d.%d" % (pg[0], tab_n[pg[0]])
                for k in range(i, j):
                    tags.setdefault(k, []).append(addr)
                i = j
                continue
        i += 1
    for k, (ln, pg) in enumerate(lines):
        if "=" in ln and re.search(r"[0-9\u03b1-\u03c9\u0391-\u03a9"
                                   r"\u2211\u222b\u221a\u221e\xb1\u2192"
                                   r"\u2190\u2194\u2264\u2265\u2260"
                                   r"\u2248\xd7\xf7\u03c0]", ln):
            eq_n[pg[0]] = eq_n.get(pg[0], 0) + 1
            tags.setdefault(k, []).append("eq%d.%d" % (pg[0],
                                                      eq_n[pg[0]]))
    return tags


def clean_pages(pages):
    """Clean per-page texts into paragraphs with page provenance.

    Removes repeating first/last lines and zone page numbers, joins
    hyphenated words, and joins wrapped lines (across page breaks
    too). Returns [{"text", "pages", "has"}]. Headings, bullets, and
    caps lines always stand alone; blank lines split.
    """
    zoned = _strip_zones([[ (ln.strip(), (n + 1,))
                            for ln in (p or "").splitlines()]
                          for n, p in enumerate(pages)])
    stream = [ln for lines in zoned for ln in lines]
    stream = _join_hyphens(stream)
    tags = _tag_objects(stream)
    paras, cur = [], None

    def flush():
        if cur and cur["lines"]:
            text = " ".join(cur["lines"])
            paras.append({"text": text, "pages": sorted(cur["pages"]),
                          "has": sorted(cur["has"])})

    for k, (ln, pg) in enumerate(stream):
        if not ln.strip():
            if cur:
                flush()
                cur = None
            continue
        standalone = bool(_is_heading(ln)) or _is_caps(ln)
        if cur is not None and (standalone or _is_bullet(ln)):
            flush()
            cur = None
        if cur is None:
            cur = {"lines": [], "pages": set(), "has": set()}
        cur["lines"].append(ln.strip())
        cur["pages"].update(pg)
        for t in tags.get(k, []):
            cur["has"].add(t)
        if standalone:
            flush()
            cur = None
    if cur:
        flush()
        cur = None
    return paras


# ---- section split (Source: numbered headings) ----
def split_sections(paras):
    """Split cleaned paragraphs at numbered headings (depth <= 1 starts
    a top section; deeper numbers become subsections of the current
    one). Returns [{"n", "heading", "paras", "subsections"}]."""
    secs = []
    cur = {"n": "0", "heading": "", "paras": [], "subsections": []}
    for p in paras or []:
        m = _is_heading(p["text"])
        if m and m[0].count(".") <= 1:
            if cur["paras"] or cur["n"] != "0":
                secs.append(cur)
            cur = {"n": m[0], "heading": m[1], "paras": [],
                   "subsections": []}
            p = dict(p)
            cur["paras"].append(p)
            continue
        if m:
            cur["subsections"].append(p["text"])
        cur["paras"].append(p)
    if cur["paras"] or not secs:
        secs.append(cur)
    if len(secs) == 1 and secs[0]["n"] == "0":
        secs[0]["n"] = "1"
    return secs


# ---- entry assembly (§8.1) ----
def build_entry(doc_id, title, origin_file, order_id, parsed_at,
                added_by, sections, images, pc="source"):
    """Assemble the entry.json dict: flat addressed paragraphs, a
    section index into them, and figure addresses from images
    ([(file, page, index)])."""
    flat, out_secs = [], []
    for s in sections or []:
        start = len(flat)
        for k, p in enumerate(s["paras"], 1):
            flat.append({"addr": "s%s/p%d" % (s["n"], k),
                         "text": p["text"],
                         "pages": sorted(p.get("pages", [])),
                         "has": sorted(p.get("has", []))})
        out_secs.append({"n": s["n"], "heading": s["heading"],
                         "start": start, "count": len(s["paras"]),
                         "subsections": list(s.get("subsections", []))})
    imgs = [{"file": f, "caption": "",
             "addr": "fig%d.%d" % (pg, n)} for f, pg, n in images or []]
    return {"pc": pc, "doc_id": doc_id, "ref": entry_ref(pc, doc_id),
            "title": title, "origin_file": origin_file,
            "order_id": order_id, "parsed_at": parsed_at,
            "added_by": added_by, "sections": out_secs,
            "paragraphs": flat, "images": imgs,
            "chars": sum(len(p["text"]) for p in flat)}


# ---- omitted candidates + key terms (§10.2) ----
_MENTION_RE = re.compile(r"\b(Figure|Fig\.|Table|Tab\.)\s+\d+[A-Za-z]?")
_EXAMPLE_RE = re.compile(r"\b(for example|e\.g\.|i\.e\.|consider|suppose"
                          r"|imagine)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*%?\b")


def omitted_candidates(section):
    """Code-detected per-section candidates: numbers, formulas,
    figure/table mentions, lists, example sentences — each with its
    exact "pN" see ref."""
    out = []
    for k, p in enumerate(section.get("paras", []), 1):
        see = "p%d" % k
        text = p.get("text", "")
        for m in _NUMBER_RE.findall(text):
            out.append({"what": "number " + m, "see": see})
        if _EXAMPLE_RE.search(text):
            out.append({"what": "example: " + text[:80], "see": see})
        for m in _MENTION_RE.finditer(text):
            out.append({"what": "mention " + m.group(0), "see": see})
        if _is_bullet(text):
            out.append({"what": "list: " + text[:80], "see": see})
        for h in sorted(p.get("has", [])):
            kind = "table" if h.startswith("tab") else "formula"
            out.append({"what": "%s %s" % (kind, h), "see": see})
    return out


def key_terms(section):
    """Quoted, bold, and capitalized (not sentence-initial) terms in
    first-seen order."""
    out, seen = [], set()

    def add(t):
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    for p in section.get("paras", []):
        text = p.get("text", "")
        for m in re.findall(r'"([^"\n]{2,60})"', text):
            add(m)
        for m in re.findall(r"\*\*([^*][^*?\n]{1,59})\*\*", text):
            add(m)
        first = re.search(r"[A-Za-z]", text)
        pos0 = first.start() if first else -1
        for m in re.finditer(r"[A-Za-z][A-Za-z\-']*", text):
            tok = m.group(0)
            if len(tok) < 2:
                continue
            if m.start() == pos0 and not (tok.isupper()
                                          and len(tok) >= 2):
                continue
            if tok[0].isupper():
                add(tok)
    return out


# ---- see ranges (§10.2-10.3) ----
_SEE_RE = re.compile(r"^p(\d+)(?:-p?(\d+))?$")


def _expand(see):
    m = _SEE_RE.match(see or "")
    if not m:
        return set()
    a = int(m.group(1))
    b = int(m.group(2) or a)
    if a < 1 or b < a:
        return set()
    return set(range(a, b + 1))


def check_see(see, n_paras):
    cov = _expand(see)
    return bool(cov) and max(cov) <= n_paras


def resolve_omitted(candidates, summaries):
    """Candidates not covered by any summary see-range stay omitted."""
    covered = set()
    for s in summaries or []:
        covered |= _expand(s.get("see", ""))
    out = []
    for c in candidates or []:
        m = re.match(r"^p(\d+)$", c.get("see", ""))
        if not m or int(m.group(1)) not in covered:
            out.append(c)
    return out


# ---- open_ref (§9) ----
def _provenance(entry, pages=None):
    prov = {"pc": entry.get("pc", "source"),
            "doc_id": entry.get("doc_id", ""),
            "title": entry.get("title", ""),
            "origin_file": entry.get("origin_file", ""),
            "order_id": entry.get("order_id", ""),
            "parsed_at": entry.get("parsed_at", ""),
            "added_by": entry.get("added_by", "")}
    if pages:
        prov["pages"] = list(pages)
    return prov


def open_ref(entry, ref, grant=None):
    """Return the passage at ref verbatim with provenance. Grant
    enforcement arrives with the agent tools; the HTTP route serves
    the UI/developer. Raises ValueError (bad ref) or KeyError
    (nothing stored there)."""
    pc, doc_id, frag = parse_ref(ref)
    if doc_id != entry.get("doc_id") or pc != entry.get("pc", "source"):
        raise KeyError("no such entry: %r" % ref)
    base = entry.get("ref", entry_ref(pc, doc_id))
    if not frag:
        return {"kind": "entry", "ref": base, "title": entry.get("title"),
                "sections": [{"n": s["n"], "heading": s["heading"],
                              "count": s["count"]}
                             for s in entry.get("sections", [])],
                "provenance": _provenance(entry)}
    m = re.match(r"^s(.+)/p(\d+)$", frag)
    if m:
        want = "s%s/p%s" % (m.group(1), m.group(2))
        for p in entry.get("paragraphs", []):
            if p["addr"] == want:
                return {"kind": "paragraph", "ref": ref,
                        "text": p["text"],
                        "provenance": _provenance(entry, p["pages"])}
        raise KeyError("no such paragraph: %r" % ref)
    m = re.match(r"^s(.+)$", frag)
    if m:
        for s in entry.get("sections", []):
            if s["n"] == m.group(1):
                ps = entry["paragraphs"][s["start"]
                                          :s["start"] + s["count"]]
                pages = sorted({pg for p in ps for pg in p["pages"]})
                return {"kind": "section", "ref": ref,
                        "heading": s["heading"],
                        "text": "\n\n".join(p["text"] for p in ps),
                        "provenance": _provenance(entry, pages)}
        raise KeyError("no such section: %r" % ref)
    for img in entry.get("images", []):
        if img["addr"] == frag:
            return {"kind": "figure", "ref": ref, "file": img["file"],
                    "caption": img.get("caption", ""),
                    "provenance": _provenance(entry)}
    if frag.startswith("tab") or frag.startswith("eq"):
        for p in entry.get("paragraphs", []):
            if frag in p.get("has", []):
                kind = "table" if frag.startswith("tab") else "formula"
                return {"kind": kind, "ref": ref, "in": p["addr"],
                        "text": p["text"],
                        "provenance": _provenance(entry, p["pages"])}
        raise KeyError("no such object: %r" % ref)
    raise ValueError("bad ref fragment: %r" % ref)


# ---- map skeleton (§10.3/10.5) ----
def blank_map(entry, llm_model):
    return {"ref": entry.get("ref", ""), "doc_id": entry.get("doc_id"),
            "built_at": "", "llm_model": llm_model,
            "map_version": MAP_VERSION, "status": "pending",
            "entry_summary": "",
            "sections": [{"ref": "s" + s["n"], "heading": s["heading"],
                          "summary": [], "omitted": [],
                          "key_terms": [], "has": [], "chars": 0,
                          "subsections": list(s.get("subsections", []))}
                         for s in entry.get("sections", [])]}
