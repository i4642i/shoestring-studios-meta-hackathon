"""Company PC core: ids, page cleaning, sections, addresses, open_ref.

Pure functions (stdlib only) behind the Source PC ingest pipeline and
the open_ref reader. Docs: RESULT_JSON_DRAFT_EN.md sections 8-10.
"""
import hashlib
import json
import os
import re
import time

MAP_VERSION = 1
PCS = ("source", "theory", "article")
MIN_FIG_PT = 50  # images smaller than this (both sides, PDF points) are decor

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
ROOT_OVERRIDE = None  # tests point storage+orders at a temp root


def _base(root):
    return root or ROOT_OVERRIDE or ROOT


def pc_dir(pc, root=None):
    assert pc in PCS, "unknown PC: %r" % pc
    return os.path.join(_base(root), "storage", "_pc", pc)


def entry_dir(pc, doc_id, root=None):
    return os.path.join(pc_dir(pc, root), "entries", doc_id)


def index_dir(pc, profile, root=None):
    return os.path.join(pc_dir(pc, root), "index", profile)


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
    """Tag formula lines: {line_index: [eq addr]}. Formulas hold '='
    plus a digit or math symbol. Tables come from pdfplumber, never
    from text guessing."""
    tags = {}
    eq_n = {}
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


# ---- figures and tables ----
_CAPTION_RE = re.compile(r"^(Figure|Fig\.|Exhibit|Table|Tab\.)\s+(\S+)"
                          r"\s*(.*)$")
_CAP_STOP = {"figure", "fig", "table", "tab", "exhibit"}


def parse_caption(line):
    """Split a printed caption into label/number/rest. None when the
    line is not a caption."""
    m = _CAPTION_RE.match((line or "").strip())
    if not m:
        return None
    return {"label": "%s %s" % (m.group(1), m.group(2)),
            "number": m.group(2), "rest": m.group(3).strip()}


def caption_terms(caption):
    """Key terms from a caption: alpha tokens len>=3 minus stopwords."""
    out = []
    for tok in re.findall(r"[A-Za-z]{3,}", caption or ""):
        if tok.lower() not in _CAP_STOP and tok not in out:
            out.append(tok)
    return out


def _section_for_page(sections, page):
    """Newest section (doc order) with a paragraph at or before page."""
    best = sections[0]["n"] if sections else "1"
    for s in sections or []:
        for p in s["paras"]:
            if min(p.get("pages", [0])) <= page:
                best = s["n"]
                break
    return best


def assign_objects(sections, figures, tables):
    """Give each figure/table a section-based address (fig1.1.1,
    tab1.2.1) and each figure a fig<n>.png file in (page, top) order.
    Tables without rows become kind "table-image" figures. Returns
    (figures, tables) with addr/file/sec set; inputs untouched."""
    figs = [dict(f) for f in figures or []]
    tabs = []
    for t in tables or []:
        if t.get("rows"):
            tabs.append(dict(t))
        else:
            f = dict(t)
            f["kind"] = "table-image"
            figs.append(f)
    order = sorted(range(len(figs)),
                   key=lambda i: (figs[i]["page"],
                                  figs[i].get("top", 0)))
    for n, i in enumerate(order, 1):
        figs[i] = dict(figs[i], file="fig%d.png" % n)
    fig_n, tab_n = {}, {}
    for f in figs:
        s = _section_for_page(sections, f["page"])
        fig_n[s] = fig_n.get(s, 0) + 1
        f["addr"] = "fig%s.%d" % (s, fig_n[s])
        f["sec"] = s
    for t in tabs:
        s = _section_for_page(sections, t["page"])
        tab_n[s] = tab_n.get(s, 0) + 1
        t["addr"] = "tab%s.%d" % (s, tab_n[s])
        t["sec"] = s
    return figs, tabs


def _round_bbox(bbox):
    try:
        return [round(float(v), 1) for v in bbox]
    except (TypeError, ValueError):
        return [0.0, 0.0, 0.0, 0.0]


def chunk_text(ref, kind_label, heading, caption, description, text,
               numbers, extra=""):
    """One LightRAG chunk per figure/table: the ref rides first AND
    last so any split piece still opens the object."""
    lines = ["[REF %s]" % ref,
             "%s in section: %s" % (kind_label, heading)]
    if caption:
        lines.append("Caption: " + caption)
    if description:
        lines.append("Description: " + description)
    if text:
        lines.append("Text: " + text)
    if numbers:
        lines.append("Numbers: " + ", ".join(numbers))
    if extra:
        lines.append(extra)
    lines.append("More: " + ref)
    return "\n".join(lines) + "\n"


# ---- entry assembly (§8.1) ----
def build_entry(doc_id, title, origin_file, order_id, parsed_at,
                added_by, sections, figures, tables, pc="source"):
    """Assemble the entry.json dict: addressed figures/tables,
    in-position placeholders, flat addressed paragraphs, and a section
    index into them. figures: [{page, top, caption, number, bbox, w,
    h, blob}]; tables: [{page, top, caption, number, bbox, rows,
    markdown, blob|None}]."""
    figs, tabs = assign_objects(sections, figures, tables)
    for s in sections or []:
        s["paras"] = list(s["paras"])
    by_sec = {}
    for f in figs:
        by_sec.setdefault(f["sec"], []).append(("fig", f))
    for t in tabs:
        by_sec.setdefault(t["sec"], []).append(("tab", t))
    for s in sections or []:
        items = sorted(by_sec.get(s["n"], []),
                       key=lambda x: (x[1]["page"],
                                      x[1].get("top", 0)))
        for _kind, o in items:
            cap = o.get("caption", "")
            tail = (" " + cap) if cap else ""
            ph = {"text": "[%s p.%d]%s" % (o["addr"], o["page"], tail),
                  "pages": [o["page"]], "has": [o["addr"]]}
            idx = len(s["paras"])
            for i, p in enumerate(s["paras"]):
                if min(p.get("pages", [0])) > o["page"]:
                    idx = i
                    break
            s["paras"].insert(idx, ph)
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
    figrec = [{"addr": f["addr"], "file": f["file"], "page": f["page"],
               "bbox": _round_bbox(f.get("bbox")),
               "w": f.get("w", 0), "h": f.get("h", 0),
               "caption": f.get("caption", ""),
               "printed_no": f.get("number", ""),
               "description": "", "text_in_image": "", "numbers": [],
               "kind": f.get("kind", ""), "described": False,
               "generated_by": "", "generated_at": ""}
              for f in figs]
    tabrec = [{"addr": t["addr"], "page": t["page"],
               "bbox": _round_bbox(t.get("bbox")),
               "caption": t.get("caption", ""),
               "printed_no": t.get("number", ""),
               "rows": t.get("rows") or [],
               "markdown": t.get("markdown", ""),
               "generated_by": "pdfplumber",
               "generated_at": parsed_at}
              for t in tabs]
    return {"pc": pc, "doc_id": doc_id, "ref": entry_ref(pc, doc_id),
            "title": title, "origin_file": origin_file,
            "order_id": order_id, "parsed_at": parsed_at,
            "added_by": added_by, "sections": out_secs,
            "paragraphs": flat, "figures": figrec, "tables": tabrec,
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
            if h.startswith("tab"):
                kind = "table"
            elif h.startswith("fig"):
                kind = "figure"
            else:
                kind = "formula"
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
                "figures": len(entry.get("figures", [])),
                "tables": len(entry.get("tables", [])),
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
    for fig in entry.get("figures", []):
        if fig["addr"] == frag:
            return {"kind": "figure", "ref": ref, "file": fig["file"],
                    "path": "figures/" + fig["file"],
                    "caption": fig.get("caption", ""),
                    "printed_no": fig.get("printed_no", ""),
                    "description": fig.get("description", ""),
                    "text_in_image": fig.get("text_in_image", ""),
                    "numbers": fig.get("numbers", []),
                    "fig_kind": fig.get("kind", ""),
                    "described": fig.get("described", False),
                    "page": fig.get("page", 0),
                    "provenance": _provenance(entry, [fig.get("page", 0)])}
    for tab in entry.get("tables", []):
        if tab["addr"] == frag:
            return {"kind": "table", "ref": ref,
                    "caption": tab.get("caption", ""),
                    "printed_no": tab.get("printed_no", ""),
                    "rows": tab.get("rows", []),
                    "markdown": tab.get("markdown", ""),
                    "page": tab.get("page", 0),
                    "provenance": _provenance(entry, [tab.get("page", 0)])}
    if frag.startswith("eq"):
        for p in entry.get("paragraphs", []):
            if frag in p.get("has", []):
                return {"kind": "formula", "ref": ref, "in": p["addr"],
                        "text": p["text"],
                        "provenance": _provenance(entry, p["pages"])}
        raise KeyError("no such object: %r" % ref)
    if frag.startswith("fig") or frag.startswith("tab"):
        raise KeyError("no such object: %r" % ref)
    raise ValueError("bad ref fragment: %r" % ref)


# ---- ingest (§10: hash -> id -> entry, map/index later) ----
def ingest_source(order_id, base, parsed_at, added_by, pages, images,
                  tables=None, skipped=0, root=None):
    """Full Source ingest: clean pages, split sections, hash the cleaned
    text to an id, dedup, and write entries/<id>/{entry.json, map.json,
    figures/} plus the first log line. images: [{page, top, caption,
    number, bbox, w, h, blob}]; tables: [{page, top, caption, number,
    bbox, rows, markdown, blob|None}]; skipped: tiny decor count.
    Map/index/descriptions are built by the worker. Returns {"ref",
    "doc_id", "duplicate", "title", "sections", "chars", "figures",
    "tables"}."""
    paras = clean_pages(pages)
    sections = split_sections(paras)
    fulltext = "\n\n".join(p["text"] for p in paras)
    doc_id = content_id(fulltext)
    edir = entry_dir("source", doc_id, root)
    ep = os.path.join(edir, "entry.json")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            old = json.load(f)
        return {"ref": old.get("ref", entry_ref("source", doc_id)),
                "doc_id": doc_id, "duplicate": True,
                "title": old.get("title", ""),
                "sections": len(old.get("sections", [])),
                "chars": old.get("chars", 0),
                "figures": len(old.get("figures", [])),
                "tables": len(old.get("tables", []))}
    title = os.path.splitext(base or "document")[0]
    entry = build_entry(doc_id, title, base or "", order_id, parsed_at,
                        added_by, sections, images, tables)
    os.makedirs(os.path.join(edir, "figures"), exist_ok=True)
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    with open(os.path.join(edir, "map.json"), "w",
              encoding="utf-8") as f:
        json.dump(blank_map(entry, ""), f, ensure_ascii=False, indent=2)
    aff, _tabs = assign_objects(sections, images, tables)
    for f in aff:
        with open(os.path.join(edir, "figures", f["file"]), "wb") as fh:
            fh.write(f["blob"])
    with open(os.path.join(edir, "log.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"ev": "ingested",
                            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "order_id": order_id, "pages": len(pages),
                            "paras": len(entry["paragraphs"]),
                            "figures": len(entry["figures"]),
                            "tables": len(entry["tables"]),
                            "skipped_decor": skipped}) + "\n")
    return {"ref": entry["ref"], "doc_id": doc_id, "duplicate": False,
            "title": entry["title"], "sections": len(entry["sections"]),
            "chars": entry["chars"], "figures": len(entry["figures"]),
            "tables": len(entry["tables"])}


# ---- order linkage + start prompts (§8.6) ----
def order_entry_ref(order_id, root=None):
    """The Source PC ref recorded on an order's upload, or None."""
    p = os.path.join(_base(root), "orders", order_id, "meta.json")
    try:
        with open(p, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    return meta.get("files", {}).get("pc_ref")


def load_entry_by_ref(ref, root=None):
    """Load the stored entry a ref points at (any PC)."""
    pcname, doc_id, _frag = parse_ref(ref)
    p = os.path.join(entry_dir(pcname, doc_id, root), "entry.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _match_section(heading, sections):
    m = re.match(r"^(\d+(?:\.\d+)*)\s+", (heading or "").strip())
    if m:
        for s in sections:
            if s["n"] == m.group(1):
                return s
    bare = re.sub(r"^\d+(?:\.\d+)*\s+", "",
                  (heading or "").strip()).lower()
    if bare:
        for s in sections:
            h = (s.get("heading") or "").lower()
            if h and (bare in h or h in bare):
                return s
    return None


def start_prompt_for(name, structure, entry, max_chars=6000):
    """Task input the runner preloads for Cleo/Rex: each structure
    part with its source section verbatim. Returns (text, {"parts",
    "missing"}). Long sections truncate with an honest note."""
    ref = entry.get("ref", "")
    lines = ["## Start prompt for %s (Source %s)" % (name, ref),
             "For each structure part, its source section verbatim. "
             "Quote with refs; never invent.", ""]
    missing = []
    parts = (structure or {}).get("parts", [])
    for part in parts:
        pid = part.get("id", "?")
        heading = part.get("heading", "")
        lines.append("### %s: %s" % (pid, heading))
        sec = _match_section(heading, entry.get("sections", []))
        if sec is None:
            lines += ["(no matching source section)", ""]
            missing.append(pid)
            continue
        ps = entry["paragraphs"][sec["start"]:sec["start"] + sec["count"]]
        text = "\n\n".join(p["text"] for p in ps)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[...truncated %d chars]" \
                % (len(text) - max_chars)
        objs = [o["addr"] for o in entry.get("figures", [])
                if o["addr"][3:].rsplit(".", 1)[0] == sec["n"]]
        objs += [o["addr"] for o in entry.get("tables", [])
                 if o["addr"][3:].rsplit(".", 1)[0] == sec["n"]]
        lines.append("Source s%s (%s#s%s):" % (sec["n"], ref, sec["n"]))
        lines.append(text)
        if objs:
            lines.append("Figures/tables here: " + ", ".join(objs))
        lines.append("")
    return "\n".join(lines), {"parts": len(parts), "missing": missing}


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
