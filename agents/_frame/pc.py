"""Company PC core: ids, page cleaning, sections, addresses, open_ref.

Pure functions (stdlib only) behind the Source PC ingest pipeline and
the open_ref reader. Docs: RESULT_JSON_DRAFT_EN.md sections 8-10.
"""
import hashlib
import json
import os
import re
import struct
import threading
import time

MAP_VERSION = 2  # has items carry kind (+file for figures) and equations
PCS = ("source", "theory", "article", "image", "generated",
       "voice")
MIN_FIG_PT = 50  # images smaller than this (both sides, PDF points) are decor

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
ROOT_OVERRIDE = None  # tests point storage+orders at a temp root

_PATH_LOCKS = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _path_lock(path):
    """The mutex for one entry (or PC) dir: every read-modify-write
    below holds it, so parallel clones never interleave. Nesting
    order is always PC dir first, then entry dir."""
    key = os.path.normcase(os.path.abspath(path))
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


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


_REF_RE = re.compile(r"^pc://(source|theory|article|image|generated|voice)/([0-9a-f]{12})"
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
def _norm_key(line):
    """Repeat-comparison key: whitespace-normalized, lowercased, with a
    bare page number dropped from either end (running heads/footers
    vary only by it: "28 HEADS" and "BARS 25" both reduce to words).
    Dotted numbers ("1.1") survive: only NAMELESS digits strip."""
    key = " ".join(line.split()).lower()
    key = re.sub(r"^\d{1,4}\s+", "", key)
    return re.sub(r"\s+\d{1,4}$", "", key)


def _is_heading(line):
    m = _HEADING_RE.match(line)
    if not m:
        return None
    if int(m.group(1).split(".")[0]) == 0:
        return None  # "0 ..." is a math fragment, never a section
    return (m.group(1), m.group(2))


def _is_bullet(line):
    return bool(_BULLET_RE.match(line))


_SENT_CLOSE_RE = re.compile(r"[.!?]['\"’”)\]]*$")


def _ends_sentence(line):
    return bool(_SENT_CLOSE_RE.search((line or "").strip()))


_NONCONTENT_RE = re.compile(
    r"^(exercises|references|bibliography)\b[\s\d.,:;]*$",
    re.IGNORECASE)


def _is_noncontent(text):
    """Non-content part starter (EXERCISES/REFERENCES/BIBLIOGRAPHY,
    optional trailing page number): its lowercase word, else None."""
    m = _NONCONTENT_RE.match((text or "").strip())
    return m.group(1).lower() if m else None


def _is_caps(line):
    return bool(_CAPS_RE.match(line))


def _strip_zones(page_lines):
    """Drop running headers/footers: the first/last line of each page is
    a candidate; a candidate on many pages (>= a third, at least 2)
    is removed everywhere it sits in a zone. The bar is a third, not
    a half, because recto/verso heads alternate and each variant sits
    on only half the pages. Numbered edge lines ("28 HEADS", "BARS
    25") need only 2 repeats: body text never looks like that, and
    subsection heads live on few pages. Bare page numbers in zones go
    unconditionally."""
    counts = {}
    numbered = set()
    for lines in page_lines:
        lead = [ln for ln in lines if ln[0].strip()]
        if not lead:
            continue
        for raw in {lead[0][0], lead[-1][0]}:
            key = _norm_key(raw)
            if len(key) < 2:
                continue
            counts[key] = counts.get(key, 0) + 1
            if key != " ".join(raw.split()).lower():
                numbered.add(key)
    if len(page_lines) >= 2:
        need = max(2, len(page_lines) // 3)
    else:
        need = 10 ** 9
    repeats = {k for k, n in counts.items()
               if n >= need or (k in numbered and n >= 2)}
    out = []
    for lines in page_lines:
        keep = []
        edge = [i for i, (ln, _pg) in enumerate(lines) if ln.strip()]
        zone_idx = {edge[0], edge[-1]} if edge else set()
        for i, (ln, pg) in enumerate(lines):
            s = ln.strip()
            zone = i in zone_idx
            if zone and (_BARE_NUM_RE.match(s)
                         or _norm_key(s) in repeats):
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


def _is_formula_line(ln):
    """A line holding '=' plus a digit or math symbol."""
    return "=" in ln and bool(re.search(
        r"[0-9\u03b1-\u03c9\u0391-\u03a9"
        r"\u2211\u222b\u221a\u221e\xb1\u2192"
        r"\u2190\u2194\u2264\u2265\u2260"
        r"\u2248\xd7\xf7\u03c0]", ln))


_VISION_MATH_RE = re.compile(r"[\u0370-\u03ff\u2200-\u22ff"
                             r"\u2190-\u21ff\u23a7-\u23ad{}]"
                             r"|\(cid:\d+\)")
_ISOLATED_RE = re.compile(r"\b[a-zA-Z]\b")


def _needs_vision_formula(line):
    """True when a formula line is garbled enough to need a vision
    re-read: math unicode / braces / cid gaps, or a short line of
    isolated single letters with no real word (broken
    sub/superscripts). Clean prose ("v is the volume ... at bar
    t") and code extract verbatim already."""
    if _VISION_MATH_RE.search(line or ""):
        return True
    if re.search(r"[a-zA-Z]{5,}", line or ""):
        return False
    return len(line or "") < 70 and \
        len(_ISOLATED_RE.findall(line or "")) >= 3


def formula_candidate_pages(pages):
    """Sorted 1-based pages holding at least one formula line that
    needs vision. Pure; the worker feeds it re-extracted page texts."""
    out = []
    for n, p in enumerate(pages or [], 1):
        for ln in (p or "").splitlines():
            if _is_formula_line(ln) and _needs_vision_formula(ln):
                out.append(n)
                break
    return out


def _tag_objects(lines):
    """Tag formula lines: {line_index: [eq addr]}. Formulas hold '='
    plus a digit or math symbol. Tables come from pdfplumber, never
    from text guessing."""
    tags = {}
    eq_n = {}
    for k, (ln, pg) in enumerate(lines):
        if _is_formula_line(ln):
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
        hm = _is_heading(ln)
        standalone = bool(hm and "." in hm[0]) or _is_caps(ln)
        if cur is not None and hm and "." not in hm[0] \
                and _ends_sentence(cur["lines"][-1]):
            standalone = True  # bare "10 ..." heads a para only after
            # a sentence end; mid-sentence it is a wrapped body line
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
    seen = set()
    cur = {"n": "0", "heading": "", "paras": [], "subsections": [],
           "non_content": False}
    for p in paras or []:
        nc = _is_noncontent(p["text"])
        if nc and nc not in seen:
            if cur["paras"] or cur["n"] != "0":
                secs.append(cur)
            seen.add(nc)
            cur = {"n": nc, "heading": p["text"].strip(), "paras": [],
                   "subsections": [], "non_content": True}
            p = dict(p)
            cur["paras"].append(p)
            continue
        m = _is_heading(p["text"])
        if m and m[0].count(".") <= 1 and m[0] not in seen:
            if cur["paras"] or cur["n"] != "0":
                secs.append(cur)
            seen.add(m[0])
            cur = {"n": m[0], "heading": m[1], "paras": [],
                   "subsections": [], "non_content": False}
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
_CAPTION_RE = re.compile(r"^(Figure|Fig\.|Exhibit|Table|Tab\.)\s*(\S+)"
                          r"\s*(.*)$", re.IGNORECASE)
_CAP_STOP = {"figure", "fig", "table", "tab", "exhibit"}


def parse_caption(line):
    """Split a printed caption into label/number/rest. None when the
    line is not a caption. Glued numbers ("FIGURE2.1Average...") split
    at the end of the numeric prefix."""
    m = _CAPTION_RE.match((line or "").strip())
    if not m:
        return None
    num, rest = m.group(2), m.group(3).strip()
    lead = re.match(r"\d+(?:\.\d+)*", num)
    if lead and lead.group(0) != num:
        rest = (num[lead.end():] + " " + rest).strip()
        num = lead.group(0)
    return {"label": "%s %s" % (m.group(1), num),
            "number": num, "rest": rest}


def caption_terms(caption):
    """Key terms from a caption: alpha tokens len>=3 minus stopwords."""
    out = []
    for tok in re.findall(r"[A-Za-z]{3,}", caption or ""):
        if tok.lower() not in _CAP_STOP and tok not in out:
            out.append(tok)
    return out


def _section_for_page(sections, page):
    """Newest content section (doc order) with a paragraph at or
    before page. Non-content sections never own figures/tables."""
    best = sections[0]["n"] if sections else "1"
    for s in sections or []:
        if s.get("non_content"):
            continue
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


def strip_ws(s):
    """Remove ALL whitespace (space-insensitive match)."""
    return "".join(str(s or "").split())


_TRANS_BULLET_RE = re.compile(r"\u2022|\(cid:\d+\)")
_LATEXY_RE = re.compile(r"[\\{}_^$]")


def _norm_trans(s):
    """Transcription-match normalization: bullets dropped (vision
    reads the rendered bullet that pdfplumber reports as (cid:N)),
    then whitespace dropped. Case kept."""
    return "".join(_TRANS_BULLET_RE.sub("", str(s or "")).split())


def _clean_runs(context):
    runs, cur = [], []
    for w in str(context or "").split():
        if _LATEXY_RE.search(w):
            if cur:
                runs.append(cur)
                cur = []
        else:
            cur.append(w)
    if cur:
        runs.append(cur)
    return runs


def anchor_words(context, page_text):
    """Word list anchoring a transcription context: the full context
    words when found, else the longest clean-prose run (5+ words)
    with its words in page order. [] when unanchored."""
    flat = _norm_trans(page_text)
    c = _norm_trans(context)
    if c and c in flat:
        return str(context or "").split()
    for run in sorted(_clean_runs(context), key=len, reverse=True):
        if len(run) >= 5 and _ordered_tokens(" ".join(run), flat):
            return run
    return []


def context_anchor(context, page_text):
    """Verbatim anchor for a transcription context: the full context
    when found, else the longest clean-prose run (5+ words) with its
    words in page order. Models latex-ify math spans inside contexts
    ("sequence {b_t}_{t=1,...} where"), and extraction interleaves
    stray subscript fragments inside prose runs, so order (not
    contiguity) anchors the formula. None when unanchored."""
    words = anchor_words(context, page_text)
    return _norm_trans(" ".join(words)) if words else None


def context_found(context, page_text):
    """A transcription's context counts only when anchored in the
    page text (space-insensitive, case kept)."""
    return context_anchor(context, page_text) is not None


def _ordered_tokens(cell, flat):
    """A cell's whitespace-separated tokens in page order: each token
    must occur at or after the previous one's position. A cell
    spanning print lines shares those lines with other columns, so
    its tokens are ordered but not contiguous."""
    pos = 0
    for tok in str(cell or "").split():
        t = _norm_trans(tok)
        if not t:
            continue
        at = flat.find(t, pos)
        if at < 0:
            return False
        pos = at + len(t)
    return True


def cells_found(columns, rows, page_text):
    """Headers + cells missing from the page text (space-insensitive;
    a cell may span lines, sharing them with other columns: its
    tokens must then appear in order). Blank cells are trivially
    found. Returns the missing cell texts (empty = all checked)."""
    flat = _norm_trans(page_text)
    bad = []
    cells = list(columns or []) + [c for r in (rows or []) for c in r]
    for c in cells:
        if _norm_trans(c) and not _ordered_tokens(c, flat):
            bad.append(c)
    return bad


def rows_to_md(rows):
    """Header-first rows to a markdown table (shared with the PDF
    parser so vision tables render identically)."""
    cells = [[(c or "").strip().replace("|", "\\|") for c in r]
             for r in rows]
    width = max(len(r) for r in cells)
    cells = [r + [""] * (width - len(r)) for r in cells]
    out = ["| " + " | ".join(cells[0]) + " |",
           "| " + " | ".join("---" for _ in cells[0]) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in cells[1:]]
    return "\n".join(out)


def _round_bbox(bbox):
    try:
        return [round(float(v), 1) for v in bbox]
    except (TypeError, ValueError):
        return [0.0, 0.0, 0.0, 0.0]


def sec_of_addr(addr):
    return addr[3:].rsplit(".", 1)[0]


def fig_desc(fig):
    if fig.get("description"):
        first = fig["description"].split(".")[0].strip()
        return first + "." if first else fig.get("caption", "")
    return fig.get("caption", "")


def tab_desc(tab):
    rows = tab.get("rows") or []
    cols = max([len(r) for r in rows] or [0])
    head = "Table %dx%d" % (len(rows), cols)
    if tab.get("caption"):
        head += ": " + tab["caption"]
    return head


def eq_desc(eq):
    ctx = (eq.get("context") or "")[:120]
    return "Formula" + (" (" + ctx + ")" if ctx else "")


def section_has(entry, sec_n):
    """Map "has" items for one section: figures, tables, equations.
    Navigation only, as before."""
    has = []
    for fig in entry.get("figures", []):
        if sec_of_addr(fig["addr"]) != sec_n:
            continue
        has.append({"ref": entry["ref"] + "#" + fig["addr"],
                    "kind": "figure", "file": fig["file"],
                    "caption": fig.get("caption", ""),
                    "desc": fig_desc(fig)})
    for tab in entry.get("tables", []):
        if sec_of_addr(tab["addr"]) != sec_n:
            continue
        has.append({"ref": entry["ref"] + "#" + tab["addr"],
                    "kind": "table",
                    "caption": tab.get("caption", ""),
                    "desc": tab_desc(tab)})
    for eq in entry.get("equations", []):
        if eq.get("sec", sec_of_addr(eq["addr"])) != sec_n:
            continue
        has.append({"ref": entry["ref"] + "#" + eq["addr"],
                    "kind": "equation",
                    "caption": eq.get("latex", ""),
                    "desc": eq_desc(eq)})
    return has


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
                         "subsections": list(s.get("subsections", [])),
                         "non_content": bool(s.get("non_content"))})
    figrec = [{"addr": f["addr"], "file": f["file"], "page": f["page"],
               "bbox": _round_bbox(f.get("bbox")),
               "w": f.get("w", 0), "h": f.get("h", 0),
               "caption": f.get("caption", ""),
               "printed_no": f.get("number", ""),
               "description": "",
               "text_in_image": f.get("text", ""),
               "numbers": [],
               "kind": f.get("kind", ""), "described": False,
               "described_by": "", "generated_at": ""}
              for f in figs]
    tabrec = [{"addr": t["addr"], "page": t["page"],
               "bbox": _round_bbox(t.get("bbox")),
               "caption": t.get("caption", ""),
               "printed_no": t.get("number", ""),
               "rows": t.get("rows") or [],
               "markdown": t.get("markdown", ""),
               "described_by": "pdfplumber",
               "generated_at": parsed_at}
              for t in tabs]
    return {"pc": pc, "doc_id": doc_id, "ref": entry_ref(pc, doc_id),
            "title": title, "origin_file": origin_file,
            "order_id": order_id, "parsed_at": parsed_at,
            "added_by": added_by, "recipients": [],
            "sections": out_secs,
            "paragraphs": flat, "figures": figrec, "tables": tabrec,
            "equations": [],
            "chars": sum(len(p["text"]) for p in flat)}


def section_for_page(entry, page):
    """Newest content section (doc order) with a paragraph at or
    before page. Same rule as _section_for_page, on a stored entry."""
    secs = entry.get("sections", [])
    flat = entry.get("paragraphs", [])
    best = secs[0]["n"] if secs else "1"
    for s in secs:
        if s.get("non_content"):
            continue
        for p in flat[s["start"]:s["start"] + s["count"]]:
            if min(p.get("pages", [0])) <= page:
                best = s["n"]
                break
    return best


def apply_equations(entry, page, formulas, page_text, model, at):
    """Store vision-transcribed formulas as equation objects
    (eq<section>.<n>), linked from the paragraphs that print their
    context. Context must be found in the page text
    (space-insensitive) or the formula is REJECTED (not stored).
    Paragraph text is never touched. Returns (added, rejected,
    dupes) with addresses / raw items."""
    added, rejected, dupes = [], [], []
    for f in formulas or []:
        if not isinstance(f, dict):
            rejected.append(f)
            continue
        latex = str(f.get("latex", "")).strip()
        ctx = str(f.get("context", "")).strip()
        if not latex or not context_found(ctx, page_text):
            rejected.append(f)
            continue
        old = [e for e in entry.get("equations", [])
               if e.get("latex") == latex and e.get("page") == page]
        if old:
            dupes.append(old[0]["addr"])
            continue
        sec = section_for_page(entry, page)
        n = sum(1 for e in entry.get("equations", [])
                if e.get("sec") == sec) + 1
        addr = "eq%s.%d" % (sec, n)
        words = anchor_words(ctx, page_text)
        in_addrs = [p["addr"] for p in entry.get("paragraphs", [])
                    if words and _ordered_tokens(" ".join(words),
                                                 _norm_trans(p["text"]))]
        entry.setdefault("equations", []).append(
            {"addr": addr, "sec": sec, "page": page, "latex": latex,
             "context": ctx, "in": in_addrs, "transcribed_by": model,
             "checked": True, "generated_at": at})
        for p in entry.get("paragraphs", []):
            if p["addr"] in in_addrs and addr not in p.get("has", []):
                p["has"] = sorted(p.get("has", []) + [addr])
        added.append(addr)
    return added, rejected, dupes


def apply_table_vision(entry, fig_addr, columns, rows, page_text,
                       model, at):
    """Store a vision-transcribed table (tab<section>.<n>) beside its
    table-image figure. Every header + cell must be found in the page
    text (space-insensitive) or the table is stored UNCHECKED
    (navigation only, image fallback kept). Returns (addr, checked,
    missing). "already" when the figure links a table."""
    fig = next((f for f in entry.get("figures", [])
                if f.get("addr") == fig_addr), None)
    if fig is None or fig.get("kind") != "table-image":
        return None, False, ["no such table-image figure"]
    if fig.get("table"):
        return fig["table"], "already", []
    if not isinstance(columns, list) or not columns or \
            not isinstance(rows, list):
        return None, False, ["bad transcription shape"]
    width = len(columns)
    data = []
    for r in rows:
        if not isinstance(r, list):
            return None, False, ["bad transcription shape"]
        data.append([str(c or "") for c in r] +
                    [""] * max(0, width - len(r)))
    missing = cells_found([str(c or "") for c in columns], data,
                          page_text)
    checked = not missing
    sec = section_for_page(entry, fig.get("page", 0))
    n = sum(1 for t in entry.get("tables", [])
            if t.get("sec", sec_of_addr(t["addr"])) == sec) + 1
    addr = "tab%s.%d" % (sec, n)
    rec = {"addr": addr, "sec": sec, "page": fig.get("page", 0),
           "bbox": fig.get("bbox"),
           "caption": fig.get("caption", ""),
           "printed_no": fig.get("printed_no", ""),
           "rows": [[str(c or "") for c in columns]] + data,
           "markdown": rows_to_md([[str(c or "") for c in columns]]
                                  + data),
           "figure": fig_addr, "transcribed_by": model,
           "checked": checked, "generated_at": at}
    if missing:
        rec["unchecked_cells"] = missing
    entry.setdefault("tables", []).append(rec)
    fig["table"] = addr
    return addr, checked, missing


# ---- omitted candidates + key terms (§10.2) ----
_MENTION_RE = re.compile(r"\b(Figure|Fig\.|Table|Tab\.)\s+\d+[A-Za-z]?")
_EXAMPLE_RE = re.compile(r"\b(for example|e\.g\.|i\.e\.|consider|suppose"
                          r"|imagine)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*%?\b")


_NOCID_RE = re.compile(r"\(cid:\d+\)")
_DOTTED_RE = re.compile(r"^\d+(?:\.\d+)+$")


def omitted_candidates(section):
    """Code-detected per-section candidates: numbers, formulas,
    figure/table mentions, lists, example sentences — each with its
    exact "pN" see ref. Formula and figure/table candidates carry
    their text so coverage can be judged on words, not ranges.
    (cid:N) bullets and dotted section numbers are not values."""
    out = []
    caps = {}
    for o in (section.get("figures", []) or []) + \
            (section.get("tables", []) or []):
        caps[o.get("addr", "")] = o.get("caption", "")
    for k, p in enumerate(section.get("paras", []), 1):
        see = "p%d" % k
        text = p.get("text", "")
        clean = _NOCID_RE.sub(" ", text)
        for m in _NUMBER_RE.findall(clean):
            if _DOTTED_RE.match(m):
                continue
            out.append({"what": "number " + m, "see": see})
        if _EXAMPLE_RE.search(text):
            out.append({"what": "example: " + text[:80], "see": see})
        for m in _MENTION_RE.finditer(text):
            out.append({"what": "mention " + m.group(0), "see": see})
        if _is_bullet(text):
            out.append({"what": "list: " + text[:80], "see": see})
        for h in sorted(p.get("has", [])):
            if h.startswith("tab"):
                out.append({"what": "table: "
                                    + caps.get(h, h)[:60], "see": see})
            elif h.startswith("fig"):
                out.append({"what": "figure: "
                                    + caps.get(h, h)[:60], "see": see})
            else:
                out.append({"what": "formula: " + text[:80],
                            "see": see})
    return out


_PHRASE_RE = re.compile(
    r"\b([A-Z][A-Za-z\-']*(?:\s+[A-Z][A-Za-z\-']*)+)\b")
_QUOTE_RES = (re.compile(r'"([^"\n]{2,60})"'),
              re.compile("“([^”\n]{2,60})”"))
_MD_BOLD_RE = re.compile(r"\*\*([^*][^*?\n]{1,59})\*\*")
_SENT_END_RE = re.compile(r"[.!?\u2026]\s*$")
_TERM_STOP = frozenset("""
    a an the and or but for nor so yet with from by as at to of in on off
    over under into out up down is are was were be been being have has had
    do does did will would shall should can could may might must not no
    if then else when while where which who whom whose what this that
    these those i we you he she it they them him her us our your his its
    their my mine yours most more less many much such other same one two
    first second third
    """.split())


def _sentence_initial(text, pos):
    """True when pos opens the paragraph or a sentence in it."""
    pre = text[:pos]
    return pre.strip() == "" or bool(_SENT_END_RE.search(pre))


def _collect_terms(section):
    """All candidate terms with origin: 0 quoted/bold, 1 phrase,
    2 mid-sentence single. First-seen dict order."""
    seen = {}

    def add(t, origin):
        t = " ".join((t or "").split())
        if not t or len(t) > 60:
            return
        prev = seen.get(t)
        if prev is None or origin < prev:
            seen[t] = origin

    paras = section.get("paras", [])
    mid = set()
    for p in paras:
        text = p.get("text", "")
        for m in re.finditer(r"[A-Za-z][A-Za-z\-']*", text):
            tok = m.group(0)
            if len(tok) >= 2 and tok[0].isupper() \
                    and not _sentence_initial(text, m.start()):
                mid.add(tok)
    for p in paras:
        text = p.get("text", "")
        for rx in _QUOTE_RES:
            for m in rx.findall(text):
                add(m, 0)
        for m in _MD_BOLD_RE.findall(text):
            add(m, 0)
        for b in p.get("bold", []):
            add(b, 0)
        for m in _PHRASE_RE.finditer(text):
            if len(m.group(1).split()) <= 6:
                add(m.group(1), 1)
        for m in re.finditer(r"[A-Za-z][A-Za-z\-']*", text):
            if m.group(0) in mid:
                add(m.group(0), 2)
    return seen


def key_terms(section):
    """Real terms in first-seen order: quoted spans, bold spans,
    multi-word capitalized phrases, and single capitalized words that
    also occur mid-sentence. Sentence-initial-only words are not
    terms and are dropped, as are singles already covered by a kept
    phrase ("TYPES" inside "TYPES OF DATA")."""
    seen = _collect_terms(section)
    keepers = [t for t, o in seen.items() if o < 2]
    return [t for t, o in seen.items()
            if o < 2 or (t.lower() not in _TERM_STOP and not any(
                re.search(r"\b%s\b" % re.escape(t), k)
                for k in keepers if k != t))]


TERMS_PER_SECTION = 15


def rank_key_terms(section):
    """Full term list, best first: occurrence count, +2 when
    multi-word, +3 when quoted/bold. First-seen breaks ties."""
    seen = _collect_terms(section)
    text = "\n".join(p.get("text", "")
                     for p in section.get("paras", []))
    scored = []
    for t, o in seen.items():
        n = len(re.findall(r"\b%s\b" % re.escape(t), text,
                           re.IGNORECASE))
        score = n + (2 if " " in t else 0) + (3 if o == 0 else 0)
        scored.append((t, o, score))
    keepers = [t for t, o, _s in scored if o < 2]
    out = [x for x in scored
           if x[1] < 2 or (x[0].lower() not in _TERM_STOP and not any(
               re.search(r"\b%s\b" % re.escape(x[0]), k)
               for k in keepers if k != x[0]))]
    out.sort(key=lambda x: -x[2])
    return [t for t, _o, _s in out]


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


def _content_words(s):
    return [w.lower() for w in re.findall(r"[A-Za-z]{4,}", s or "")
            if w.lower() not in _TERM_STOP]


def _stated_in(sentences, kind, body):
    """True when some summary sentence actually states the candidate:
    numbers/mentions by exact value, the rest by 2+ shared content
    words. Case-like examples are judged as examples."""
    if kind == "number":
        num = re.sub(r"[,\s%]", "", body).lower()
        return bool(num) and any(
            num in re.sub(r"[,\s%]", "", st).lower()
            for st in sentences)
    if kind == "mention":
        m = re.search(r"(Figure|Fig\.|Table|Tab\.|Exhibit)\s+(\S+)", body)
        if not m:
            return False
        num = m.group(2).rstrip(".,;:")
        return any(
            ("fig" in st.lower() or "table" in st.lower()
             or "exhibit" in st.lower())
            and re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(num), st)
            for st in sentences)
    keys = set(_content_words(body))
    if len(keys) < 2:
        return False
    return any(len(keys & set(_content_words(st))) >= 2
               for st in sentences)


def resolve_omitted(candidates, summaries, base=None):
    """Candidates the summary text does not state stay omitted, each
    with its exact ref (base + "/pN") when base is given. Candidates
    without a known kind keep the old see-range rule. Identical whats
    merge into their first occurrence: same value, same verdict."""
    sentences = [s.get("text", "") for s in summaries or []]
    covered = set()
    for s in summaries or []:
        covered |= _expand(s.get("see", ""))
    out, seen_whats = [], set()
    for c in candidates or []:
        what = c.get("what", "")
        if what in seen_whats:
            continue
        seen_whats.add(what)
        kind = what.split(":", 1)[0] if ": " in what \
            else what.split(" ", 1)[0]
        if kind in ("number", "mention", "example", "list", "formula",
                    "figure", "table"):
            body = what.split(": ", 1)[1] if ": " in what \
                else what[len(kind):].strip()
            stated = _stated_in(sentences, kind, body)
        else:
            m = re.match(r"^p(\d+)$", c.get("see", ""))
            stated = bool(m) and int(m.group(1)) in covered
        if not stated:
            d = dict(c)
            if base:
                d["ref"] = "%s%s" % (base, c.get("see", "")) \
                    if base.endswith("#") \
                    else "%s/%s" % (base, c.get("see", ""))
            out.append(d)
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
    if entry.get("url"):
        prov["url"] = entry["url"]
    if entry.get("publisher"):
        prov["publisher"] = entry["publisher"]
    if entry.get("date"):
        prov["date"] = entry["date"]
    if entry.get("fetched_at"):
        prov["fetched_at"] = entry["fetched_at"]
    if entry.get("supersedes"):
        prov["supersedes"] = entry["supersedes"]
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
    if pc in ("voice", "image", "generated"):
        return _open_media_ref(entry, ref, pc, frag)
    base = entry.get("ref", entry_ref(pc, doc_id))
    if not frag:
        return {"kind": "entry", "ref": base, "title": entry.get("title"),
                "sections": [{"n": s["n"], "heading": s["heading"],
                              "count": s["count"],
                              "non_content": bool(s.get("non_content"))}
                             for s in entry.get("sections", [])],
                "figures": len(entry.get("figures", [])),
                "tables": len(entry.get("tables", [])),
                "equations": len(entry.get("equations", [])),
                "provenance": _provenance(entry)}
    m = re.match(r"^s(.+)/p(\d+)-p?(\d+)$", frag)
    if m:
        a, b = int(m.group(2)), int(m.group(3))
        if a > b:
            raise ValueError("bad ref range: %r" % ref)
        want = ["s%s/p%d" % (m.group(1), k)
                for k in range(a, b + 1)]
        got = [p for p in entry.get("paragraphs", [])
               if p["addr"] in want]
        if len(got) != len(want):
            raise KeyError("no such paragraph range: %r" % ref)
        pages = sorted({pg for p in got for pg in p["pages"]})
        return {"kind": "range", "ref": ref,
                "text": "\n\n".join(p["text"] for p in got),
                "provenance": _provenance(entry, pages)}
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
    m = re.match(r"^p(\d+)-p?(\d+)$", frag)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            raise ValueError("bad ref range: %r" % ref)
        want = ["p%d" % k for k in range(a, b + 1)]
        got = [p for p in entry.get("paragraphs", [])
               if p["addr"] in want]
        if len(got) != len(want):
            raise KeyError("no such paragraph range: %r" % ref)
        pages = sorted({pg for p in got for pg in p["pages"]})
        return {"kind": "range", "ref": ref,
                "text": "\n\n".join(p["text"] for p in got),
                "provenance": _provenance(entry, pages)}
    m = re.match(r"^p(\d+)$", frag)
    if m:
        for p in entry.get("paragraphs", []):
            if p["addr"] == frag:
                return {"kind": "paragraph", "ref": ref,
                        "text": p["text"],
                        "provenance": _provenance(entry, p["pages"])}
        raise KeyError("no such paragraph: %r" % ref)
    m = re.match(r"^g(.+?)(?:/p(\d+))?$", frag)
    if m:
        for s in entry.get("sections", []):
            if "g" + s["n"] == "g" + m.group(1):
                ps = entry["paragraphs"][s["start"]
                                          :s["start"] + s["count"]]
                if m.group(2):
                    k = int(m.group(2)) - 1
                    if 0 <= k < len(ps):
                        return {"kind": "paragraph", "ref": ref,
                                "text": ps[k]["text"],
                                "provenance": _provenance(
                                    entry, ps[k]["pages"])}
                    raise KeyError("no such paragraph: %r" % ref)
                pages = sorted({pg for p in ps for pg in p["pages"]})
                return {"kind": "group", "ref": ref,
                        "heading": s["heading"],
                        "text": "\n\n".join(p["text"] for p in ps),
                        "provenance": _provenance(entry, pages)}
        raise KeyError("no such group: %r" % ref)
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
            verbatim = tab.get("transcribed_by", "pdfplumber") == \
                "pdfplumber" or tab.get("checked")
            out = {"kind": "table", "ref": ref,
                   "caption": tab.get("caption", ""),
                   "printed_no": tab.get("printed_no", ""),
                   "page": tab.get("page", 0),
                   "transcribed_by": tab.get("transcribed_by",
                                             "pdfplumber"),
                   "checked": bool(verbatim),
                   "provenance": _provenance(entry,
                                             [tab.get("page", 0)])}
            if verbatim:
                out["rows"] = tab.get("rows", [])
                out["markdown"] = tab.get("markdown", "")
                if tab.get("transcribed_by") not in (
                        None, "", "pdfplumber"):
                    out["evidence_note"] = ("transcribed by model, "
                                            "checked against page text")
            else:
                out["rows"] = []
                out["markdown"] = ""
                out["note"] = ("model-transcribed, UNCHECKED against "
                               "page text: navigation only, read the "
                               "figure image instead")
            return out
    for eq in entry.get("equations", []):
        if eq["addr"] == frag:
            out = {"kind": "equation", "ref": ref,
                   "page": eq.get("page", 0),
                   "in": list(eq.get("in", [])),
                   "transcribed_by": eq.get("transcribed_by", ""),
                   "checked": bool(eq.get("checked")),
                   "provenance": _provenance(entry, [eq.get("page", 0)])}
            if eq.get("checked"):
                out["latex"] = eq.get("latex", "")
                out["context"] = eq.get("context", "")
                out["evidence_note"] = ("transcribed by model, "
                                        "checked against page text")
            else:
                out["latex"] = ""
                out["context"] = ""
                out["note"] = ("model-transcribed, UNCHECKED against "
                               "page text: navigation only")
            return out
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
def _attach_bold(paras, marks):
    """Copy per-page bold phrases onto the paragraphs that print them
    (page provenance + word-boundary match). Marks may be None."""
    if not marks:
        return
    by_page = {}
    for i, mk in enumerate(marks, 1):
        by_page[i] = (mk or {}).get("bold", [])
    for p in paras or []:
        found = []
        for pg in p.get("pages", []):
            for phrase in by_page.get(pg, []):
                if phrase in found:
                    continue
                if re.search(r"\b%s\b" % re.escape(phrase),
                             p.get("text", "")):
                    found.append(phrase)
        if found:
            p["bold"] = found


def ingest_source(order_id, base, parsed_at, added_by, pages, images,
                  tables=None, skipped=0, root=None, marks=None,
                  doc_id=None):
    """Full Source ingest: clean pages, split sections, hash the cleaned
    text to an id, dedup, and write entries/<id>/{entry.json, map.json,
    figures/} plus the first log line. images: [{page, top, caption,
    number, bbox, w, h, blob}]; tables: [{page, top, caption, number,
    bbox, rows, markdown, blob|None}]; skipped: tiny decor count;
    marks: per-page {"bold": [...]} typography (optional).
    doc_id forces the id (re-ingest after a parser fix): the entry
    is rebuilt in place, recipients are kept, figure descriptions
    carry over onto byte-identical blobs, the vision cache is left
    alone, and the log gains a "reingested" line.
    Map/index/descriptions are built by the worker. Returns {"ref",
    "doc_id", "duplicate", "title", "sections", "chars", "figures",
    "tables"}."""
    paras = clean_pages(pages)
    sections = split_sections(paras)
    fulltext = "\n\n".join(p["text"] for p in paras)
    forced = doc_id or content_id(fulltext)
    edir = entry_dir("source", forced, root)
    ep = os.path.join(edir, "entry.json")
    if os.path.isfile(ep) and not doc_id:
        with open(ep, encoding="utf-8") as f:
            old = json.load(f)
        return {"ref": old.get("ref", entry_ref("source", forced)),
                "doc_id": forced, "duplicate": True,
                "title": old.get("title", ""),
                "sections": len(old.get("sections", [])),
                "chars": old.get("chars", 0),
                "paras": len(old.get("paragraphs", [])),
                "figures": len(old.get("figures", [])),
                "tables": len(old.get("tables", []))}
    old = None
    oldblobs = {}
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            old = json.load(f)
        for f in old.get("figures", []):
            try:
                with open(os.path.join(edir, "figures", f["file"]),
                          "rb") as fh:
                    oldblobs[f["file"]] = fh.read()
            except (OSError, KeyError):
                pass
    title = os.path.splitext(base or "document")[0]
    entry = build_entry(forced, title, base or "", order_id, parsed_at,
                        added_by, sections, images, tables)
    _attach_bold(entry["paragraphs"], marks)
    for s in entry["sections"]:
        ps = entry["paragraphs"][s["start"]:s["start"] + s["count"]]
        s["terms_all"] = rank_key_terms({"paras": ps})
    aff, _tabs = assign_objects(sections, images, tables)
    carried = 0
    if old:
        entry["recipients"] = old.get("recipients", [])
        newblobs = dict((f["file"], f["blob"]) for f in aff)
        ofigs = dict((f.get("file"), f)
                     for f in old.get("figures", []))
        for f in entry["figures"]:
            of = ofigs.get(f["file"])
            if not of or not of.get("described"):
                continue
            if oldblobs.get(f["file"]) != newblobs.get(f["file"]):
                continue
            for k in ("description", "numbers", "described",
                      "described_by", "generated_at"):
                f[k] = of.get(k, f.get(k))
            if of.get("kind") and f.get("kind") != "table-image":
                f["kind"] = of["kind"]
            if not f.get("text_in_image"):
                f["text_in_image"] = of.get("text_in_image", "")
            carried += 1
    os.makedirs(os.path.join(edir, "figures"), exist_ok=True)
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    with open(os.path.join(edir, "map.json"), "w",
              encoding="utf-8") as f:
        json.dump(blank_map(entry, ""), f, ensure_ascii=False, indent=2)
    for f in aff:
        with open(os.path.join(edir, "figures", f["file"]), "wb") as fh:
            fh.write(f["blob"])
    with open(os.path.join(edir, "log.jsonl"), "w" if not old else "a",
              encoding="utf-8") as f:
        f.write(json.dumps({"ev": "reingested" if old else "ingested",
                            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "order_id": order_id, "pages": len(pages),
                            "paras": len(entry["paragraphs"]),
                            "figures": len(entry["figures"]),
                            "tables": len(entry["tables"]),
                            "carried_descriptions": carried,
                            "skipped_decor": skipped}) + "\n")
    return {"ref": entry["ref"], "doc_id": forced, "duplicate": False,
            "title": entry["title"], "sections": len(entry["sections"]),
            "chars": entry["chars"],
            "paras": len(entry["paragraphs"]),
            "figures": len(entry["figures"]),
            "tables": len(entry["tables"])}


# ---- theory/article pick ingest (§8.2, §13.1) ----
def _web_urls(pcname, root=None):
    p = os.path.join(pc_dir(pcname, root), "urls.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _web_save_urls(pcname, urls, root=None):
    os.makedirs(pc_dir(pcname, root), exist_ok=True)
    with open(os.path.join(pc_dir(pcname, root), "urls.json"), "w",
              encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)


def _ingest_web(pcname, url, title, publisher, date, fetched_at,
                added_by, text, root=None):
    """Pick ingest for Theory/Article PCs: clean the fetched text, hash
    it to an id, and write entries/<id>/{entry.json, map.json} plus
    the first log line. Same content = same id (no-op, even under a
    new url); same url + changed content = new entry with
    `supersedes` pointing at the previous id. Paragraphs are one
    group addressed p1..pN (§9); map/index/descriptions are built by
    the worker. Returns {"ref", "doc_id", "duplicate", "title",
    "paras", "chars", "supersedes"}."""
    paras = clean_pages([text or ""])
    fulltext = "\n\n".join(p["text"] for p in paras)
    doc_id = content_id(fulltext)
    edir = entry_dir(pcname, doc_id, root)
    ep = os.path.join(edir, "entry.json")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            old = json.load(f)
        return {"ref": old.get("ref", entry_ref(pcname, doc_id)),
                "doc_id": doc_id, "duplicate": True,
                "title": old.get("title", ""),
                "paras": len(old.get("paragraphs", [])),
                "chars": old.get("chars", 0), "supersedes": None}
    flat = [{"addr": "p%d" % (k + 1), "text": p["text"], "pages": [],
             "has": []} for k, p in enumerate(paras)]
    sec = {"n": "1", "heading": title or "Full text", "start": 0,
           "count": len(flat), "subsections": [], "non_content": False,
           "terms_all": rank_key_terms({"paras": flat})}
    entry = {"pc": pcname, "doc_id": doc_id,
             "ref": entry_ref(pcname, doc_id), "url": url,
             "title": title or "", "publisher": publisher or "",
             "date": date or "", "fetched_at": fetched_at,
             "added_by": added_by, "supersedes": None,
             "recipients": [],
             "sections": [sec], "paragraphs": flat,
             "figures": [], "tables": [], "chars": len(fulltext)}
    urls = _web_urls(pcname, root)
    ids = urls.get(url, [])
    if ids:
        entry["supersedes"] = ids[-1]
    urls[url] = ids + [doc_id]
    os.makedirs(edir, exist_ok=True)
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    with open(os.path.join(edir, "map.json"), "w",
              encoding="utf-8") as f:
        json.dump(blank_map(entry, ""), f, ensure_ascii=False, indent=2)
    with open(os.path.join(edir, "log.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"ev": "ingested",
                            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "url": url, "paras": len(flat),
                            "supersedes": entry["supersedes"]}) + "\n")
    _web_save_urls(pcname, urls, root)
    return {"ref": entry["ref"], "doc_id": doc_id, "duplicate": False,
            "title": entry["title"], "paras": len(flat),
            "chars": entry["chars"],
            "supersedes": entry["supersedes"]}


def ingest_theory(url, title, publisher, date, fetched_at, added_by,
                  text, root=None):
    """Pick ingest into the Theory PC (§13.1)."""
    return _ingest_web("theory", url, title, publisher, date,
                       fetched_at, added_by, text, root)


def ingest_article(url, title, publisher, date, fetched_at, added_by,
                   text, root=None):
    """Pick ingest into the Article PC (§13.1)."""
    return _ingest_web("article", url, title, publisher, date,
                       fetched_at, added_by, text, root)


def order_picks_with_reasons(order_id, runs_root):
    """This order's Theory/Article picks with Cleo/Rex reasons:
    [{ref, title, why_important, how_to_use, priority, from}].
    The reports ARE the pick set (13.2)."""
    out = []
    seen = set()
    if not order_id or not runs_root or not os.path.isdir(runs_root):
        return out
    for rid in sorted(os.listdir(runs_root)):
        rd = os.path.join(runs_root, rid)
        try:
            with open(os.path.join(rd, "STATUS.json"),
                      encoding="utf-8") as f:
                if json.load(f).get("order_id") != order_id:
                    continue
        except (OSError, ValueError):
            continue
        for ag, cat in (("explain_cleo", "concepts"),
                        ("case_rex", "cases")):
            try:
                with open(os.path.join(rd, ag, "result.json"),
                          encoding="utf-8") as f:
                    res = json.load(f)
            except (OSError, ValueError):
                continue
            data = ((res.get("categories") or {}).get(cat)
                    or {}).get("data", {})
            for part in data.get("parts", []) or []:
                for pk in (part or {}).get("picks", []) or []:
                    ref = (pk or {}).get("ref", "")
                    if not ref or ref in seen:
                        continue
                    seen.add(ref)
                    out.append({"ref": ref,
                                "title": (pk or {}).get("title", ""),
                                "why_important": (pk or {}).get(
                                    "why_important", ""),
                                "how_to_use": (pk or {}).get(
                                    "how_to_use", ""),
                                "priority": (pk or {}).get(
                                    "priority", ""),
                                "from": ag})
    return out


def pick_orders(ref, runs_root):
    """Orders that picked this entry, newest first: [{order_id,
    run_id, picked_by, part_id, why_important, how_to_use}]. Matches
    by entry, so a passage ref finds its entry's picks."""
    try:
        rpc, rid, _frag = parse_ref(ref)
        want = entry_ref(rpc, rid)
    except ValueError:
        return []
    found = []
    if runs_root and os.path.isdir(runs_root):
        for r in sorted(os.listdir(runs_root)):
            rd = os.path.join(runs_root, r)
            try:
                with open(os.path.join(rd, "STATUS.json"),
                          encoding="utf-8") as f:
                    oid = json.load(f).get("order_id", "")
                stamp = os.path.getmtime(os.path.join(rd, "STATUS.json"))
            except (OSError, ValueError):
                continue
            if not oid:
                continue
            for ag, cat in (("explain_cleo", "concepts"),
                            ("case_rex", "cases")):
                try:
                    with open(os.path.join(rd, ag, "result.json"),
                              encoding="utf-8") as f:
                        res = json.load(f)
                except (OSError, ValueError):
                    continue
                data = ((res.get("categories") or {}).get(cat)
                        or {}).get("data", {})
                for part in data.get("parts", []) or []:
                    for pk in (part or {}).get("picks", []) or []:
                        try:
                            prpc, prid, _f = parse_ref(
                                (pk or {}).get("ref", ""))
                        except ValueError:
                            continue
                        if entry_ref(prpc, prid) != want:
                            continue
                        found.append((stamp,
                                      {"order_id": oid, "run_id": r,
                                       "picked_by": ag,
                                       "part_id": (part or {}).get(
                                           "part_id", ""),
                                       "why_important": (pk or {}).get(
                                           "why_important", ""),
                                       "how_to_use": (pk or {}).get(
                                           "how_to_use", "")}))
    found.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in found]


def picks_preview_for(name, order_id, runs_root):
    """Start-prompt material for a later agent: ONLY this order's
    picks — each pick's map + refs + Cleo/Rex reasons. Returns
    (text, meta). Raises KeyError when the order has no picks yet."""
    picks = order_picks_with_reasons(order_id, runs_root)
    if not picks:
        raise KeyError("order %r has no Theory/Article picks yet"
                       % (order_id,))
    lines = ["# Start prompt for %s (order %s)" % (name, order_id), "",
             "You may read ONLY the %d picked items below, plus the "
             "Source PC. Open passages with open_ref." % len(picks), ""]
    for n, pk in enumerate(picks, 1):
        lines += ["## Pick %d: %s" % (n, pk["title"] or pk["ref"]),
                  "Ref: %s (picked by %s, %s)"
                  % (pk["ref"], pk["from"], pk["priority"]),
                  "Why: %s" % pk["why_important"],
                  "How to use: %s" % pk["how_to_use"], ""]
        try:
            entry = load_entry_by_ref(pk["ref"])
            mp = load_map_by_ref(pk["ref"])
        except (OSError, ValueError, KeyError) as exc:
            lines += ["(map unavailable: %s)" % exc, ""]
            continue
        if mp.get("entry_summary"):
            lines += ["Map: %s" % mp["entry_summary"], ""]
        for sec in mp.get("sections", []):
            sref = "%s#%s" % (entry["ref"], sec.get("ref", ""))
            lines.append("### %s (%s)" % (sec.get("heading", ""), sref))
            for b in sec.get("summary", []) or []:
                see = (b or {}).get("see", "")
                full = "%s/%s" % (sref, see) if see else sref
                lines.append("- %s [%s]" % ((b or {}).get("text", ""),
                                            full))
            lines.append("")
    meta = {"picks": len(picks), "refs": [p["ref"] for p in picks]}
    return "\n".join(lines), meta


def marty_input_text(ref):
    """Marty's run input text for a Source entry. Non-content
    sections excluded; headings exact and each numbered section
    followed by its (ref: ...) line for verbatim copy. Shared by
    scripts/marty_input.py and the flow's Marty preload."""
    entry = load_entry_by_ref(ref)
    try:
        mp = load_map_by_ref(ref)
    except (OSError, ValueError, KeyError):
        mp = {}
    by_ref = {s.get("ref", ""): s for s in mp.get("sections", [])}
    out = ["# %s" % entry.get("title", "source"), "",
           "(Source PC %s; headings below are exact.)" % entry["ref"],
           ""]
    if mp.get("entry_summary"):
        out += ["# MAP NOTES (navigation only; never map these as parts)",
                "", mp["entry_summary"], ""]
        for s in entry.get("sections", []):
            if s.get("non_content"):
                continue
            ms = by_ref.get("s" + s["n"], {})
            out += ["## MAP s%s: %s" % (s["n"], s.get("heading", "")), ""]
            for b in ms.get("summary", []):
                out.append("- %s [%s]" % (b.get("text", ""),
                                          b.get("see", "")))
            if ms.get("key_terms"):
                out.append("Terms: " + ", ".join(ms["key_terms"][:15]))
            for h in ms.get("has", []):
                out.append("Has %s: %s" % (h.get("ref", "").split("#")[-1],
                                           h.get("caption", "")))
            out.append("")
    for s in entry.get("sections", []):
        if s.get("non_content"):
            continue
        if s["n"] != "0":
            out += ["## %s %s" % (s["n"], s.get("heading", "")), "",
                    "(ref: %s#s%s)" % (entry["ref"], s["n"]), ""]
        for p in entry["paragraphs"][s["start"]:s["start"] + s["count"]]:
            out += [p["text"], ""]
    return "\n".join(out)


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


def load_map_by_ref(ref, root=None):
    """Load the entry's map.json, or None when not built yet."""
    try:
        pcname, doc_id, _frag = parse_ref(ref)
        p = os.path.join(entry_dir(pcname, doc_id, root), "map.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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


def start_prompt_for(name, structure, entry, map_data=None,
                     max_chars=6000):
    """Task input the runner preloads for Cleo/Rex (scope lock C):
    entry summary, section list, each structure part with its source
    section verbatim, map notes per section, and how to read more via
    open_ref. Returns (text, {"parts", "missing"}). Long sections
    truncate with an honest note."""
    ref = entry.get("ref", "")
    lines = ["## Start prompt for %s (Source %s)" % (name, ref),
             "For each structure part, its source section verbatim. "
             "Quote with refs; never invent.", ""]
    if map_data and map_data.get("entry_summary"):
        lines += ["### Entry summary", map_data["entry_summary"], ""]
    else:
        lines += ["### Entry summary", "(map pending)", ""]
    lines.append("### Section list")
    for s in entry.get("sections", []):
        if s.get("non_content"):
            continue
        lines.append("- s%s %s (%s#s%s)" % (s["n"], s.get("heading", ""),
                                            ref, s["n"]))
    lines.append("")
    by_ref = {}
    if isinstance(map_data, dict):
        for s in map_data.get("sections", []):
            by_ref[s.get("ref", "")] = s
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
        kept, used = [], 0
        for p in ps:
            if kept and used + len(p["text"]) + 2 > max_chars:
                break
            kept.append(p["text"])
            used += len(p["text"]) + 2
        text = "\n\n".join(kept)
        if len(kept) < len(ps):
            a = len(kept) + 1
            rng = "p%d-p%d" % (a, len(ps)) if len(ps) > a \
                else "p%d" % a
            text += "\n%s not included -> open_ref %s#s%s/%s" \
                % (rng, ref, sec["n"], rng)
        objs = [o["addr"] for o in entry.get("figures", [])
                if o["addr"][3:].rsplit(".", 1)[0] == sec["n"]]
        objs += [o["addr"] for o in entry.get("tables", [])
                 if o["addr"][3:].rsplit(".", 1)[0] == sec["n"]]
        lines.append("Source s%s (%s#s%s):" % (sec["n"], ref, sec["n"]))
        lines.append(text)
        if objs:
            lines.append("Figures/tables here: " + ", ".join(objs))
        ms = by_ref.get("s" + sec["n"], {})
        for b in ms.get("summary", []):
            lines.append("- %s [%s]" % (b.get("text", ""), b.get("see")))
        if ms.get("key_terms"):
            lines.append("Terms: " + ", ".join(ms["key_terms"]))
        if ms.get("omitted"):
            lines.append("Omitted (look these up, never guess): "
                         + "; ".join("%s [%s]" % (o.get("what"),
                                                  o.get("ref",
                                                        o.get("see")))
                                     for o in ms["omitted"]))
        lines.append("")
    lines += ["### How to read more",
              "You hold Source PC read tools. pc_list_source lists "
              "sections; pc_read_source({section: \"1.1\"}) or "
              "({ref: \"...\"}) reads verbatim; open_ref({ref: \"...\"}) "
              "opens any pc:// ref you hold the grant for. Cite every "
              "used passage as {ref, quote} with the quote verbatim; "
              "AI-made descriptions and map summaries are navigation "
              "only, never evidence.", ""]
    return "\n".join(lines), {"parts": len(parts), "missing": missing}


# ---- recipients: one shared gate for every PC (§8.9) ----
def recipients_of(entry):
    """Recipient rows [{agent, order_id, set_by, at}], or None when the
    entry predates recipients (legacy: open to every agent)."""
    rows = (entry or {}).get("recipients")
    return list(rows) if isinstance(rows, list) else None


def may_read(entry, agent_id, order_id):
    """True when agent_id holds any row for this entry + order. Legacy
    entries without a recipients key stay open."""
    return entry_access(entry, agent_id, order_id) is not None \
        or recipients_of(entry) is None


def row_kind(row):
    """A row's kind ("map"/"full"). Rows written before kinds default
    to full (behavior-preserving)."""
    return (row or {}).get("kind") or "full"


def row_parts(row):
    """A row's listed parts (refs). Empty = the whole entry."""
    parts = (row or {}).get("parts")
    return list(parts) if isinstance(parts, list) else []


def entry_access(entry, agent_id, order_id):
    """The recipient row for (agent, order), or None. One row per
    agent + order."""
    for r in recipients_of(entry) or []:
        if isinstance(r, dict) and r.get("agent") == agent_id \
                and r.get("order_id") == order_id:
            return r
    return None


_CLONE_RE = re.compile(r"^(.+)@p(\d+)$")


def _frag_short(ref):
    """'pc://source/d#s1.1' -> 's1.1' for matrix cells."""
    frag = (ref or "").split("#", 1)
    return frag[1] if len(frag) > 1 and frag[1] else "ref"


def cell_label(kind, parts, agent):
    """One matrix cell value: full / map / map·P1 / map·§frag.
    Clone agents name their part (pia@p1 reads part 1's items);
    listed part refs show the first fragment + a count."""
    if kind == "full":
        return "full"
    m = _CLONE_RE.match(agent or "")
    if m:
        return "map·P%s" % m.group(2)
    if parts:
        first = _frag_short(parts[0])
        if len(parts) > 1:
            return "map·%s+%d" % (first, len(parts) - 1)
        return "map·%s" % first
    return "map"


def rights_for_order(order_id, root=None):
    """Real per-employee rights for one order, from recipient
    rows (not tool grants): {"agents": [base and clone ids
    holding any row], "cells": {(agent, pc): {"kind", "parts",
    "entries": [{doc_id, ref, title}]}}}."""
    cells, agents = {}, set()
    base = _base(root)
    for pcname in PCS:
        edir = os.path.join(base, "storage", "_pc", pcname,
                            "entries")
        try:
            docs = sorted(os.listdir(edir))
        except OSError:
            continue
        for doc in docs:
            ddir = os.path.join(edir, doc)
            if not os.path.isdir(ddir):
                continue
            try:
                with open(os.path.join(ddir, "entry.json"),
                          encoding="utf-8") as f:
                    entry = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(entry, dict):
                continue
            for row in recipients_of(entry) or []:
                if not isinstance(row, dict) \
                        or row.get("order_id") != order_id:
                    continue
                agent = row.get("agent", "")
                if not agent:
                    continue
                key = (agent, pcname)
                cell = cells.get(key)
                if cell is None:
                    cell = {"kind": "map", "parts": [],
                            "entries": []}
                    cells[key] = cell
                    agents.add(agent)
                if row_kind(row) == "full":
                    cell["kind"] = "full"
                for p in row_parts(row):
                    if p not in cell["parts"]:
                        cell["parts"].append(p)
                info = {"doc_id": doc,
                        "ref": entry.get("ref", ""),
                        "title": entry.get("title", "")}
                if info not in cell["entries"]:
                    cell["entries"].append(info)
    return {"agents": sorted(agents), "cells": cells}


def set_recipients(pcname, doc_id, order_id, agents, set_by, kind="map",
                   parts=None, root=None):
    """Upsert recipients for one order (merge per agent; other orders'
    rows are kept). kind is "map" or "full"; parts (refs, []) limits
    the grant to those parts. Atomic under the entry lock. Returns
    the full row list."""
    if kind not in ("map", "full"):
        raise ValueError("kind must be map or full")
    parts = list(parts or [])
    edir = entry_dir(pcname, doc_id, root)
    with _path_lock(edir):
        return _set_recipients_in(edir, order_id, agents, set_by,
                                  kind, parts)


def _set_recipients_in(edir, order_id, agents, set_by, kind, parts):
    p = os.path.join(edir, "entry.json")
    with open(p, encoding="utf-8") as f:
        entry = json.load(f)
    rows = recipients_of(entry) or []
    have = {(r.get("agent"), r.get("order_id")): r for r in rows
            if isinstance(r, dict)}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for a in agents or []:
        key = (a, order_id)
        if key in have:
            have[key]["kind"] = kind
            have[key]["parts"] = parts
            have[key]["set_by"] = set_by
            have[key]["at"] = now
        else:
            have[key] = {"agent": a, "order_id": order_id,
                         "kind": kind, "parts": parts,
                         "set_by": set_by, "at": now}
    entry["recipients"] = [have[k] for k in sorted(have)]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return entry["recipients"]


def _frag_within(rfrag, pfrag):
    """True when requested fragment rfrag sits inside part pfrag:
    exact match, or a paragraph/range under a listed section/group."""
    if not pfrag:
        return True
    if rfrag == pfrag:
        return True
    return bool(rfrag) and rfrag.startswith(pfrag + "/")


def ref_within(requested_ref, part_ref):
    """True when requested_ref names the same entry as part_ref and
    sits inside that part. A bare entry ref (whole text) is inside
    nothing: parts-limited members read listed parts only."""
    try:
        rpc, rid, rfrag = parse_ref(requested_ref)
        ppc, pid, pfrag = parse_ref(part_ref)
    except ValueError:
        return False
    return rpc == ppc and rid == pid and _frag_within(rfrag, pfrag)


def apply_handoff(order_id, draft, set_by="plan_ash", root=None):
    """Apply storyboard_draft scenes[].handoff[] as recipient rows
    (kind map + parts). Same lister rule as the tool: set_by must
    hold a row on each entry, and every handoff ref must sit inside
    what set_by holds (no widening). Validates everything first,
    then applies. Returns {"applied": [(ref, agent)], "grants": n}
    or {"error": msg} (nothing applied)."""
    scenes = (draft or {}).get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return {"error": "draft has no scenes"}
    planned = {}
    for sc in scenes:
        if not isinstance(sc, dict):
            return {"error": "scene is not an object"}
        for h in (sc.get("handoff") or []):
            if not isinstance(h, dict):
                return {"error": "scene %s: handoff is not an object"
                                 % sc.get("n", "?")}
            ref = h.get("ref", "")
            tos = h.get("to", [])
            if not isinstance(ref, str) or not ref:
                return {"error": "scene %s: handoff needs ref"
                                 % sc.get("n", "?")}
            if not isinstance(tos, list) or not tos \
                    or any(not isinstance(a, str) or not a
                           for a in tos):
                return {"error": "scene %s: handoff %r needs "
                                 "to: [agent ids]" % (sc.get("n", "?"),
                                                      ref)}
            try:
                rpc, rid, _frag = parse_ref(ref)
            except ValueError:
                return {"error": "scene %s: bad handoff ref %r"
                                 % (sc.get("n", "?"), ref)}
            try:
                entry = load_entry_by_ref(entry_ref(rpc, rid),
                                          root=root)
            except (OSError, ValueError, KeyError):
                return {"error": "scene %s: unknown entry for %r"
                                 % (sc.get("n", "?"), ref)}
            mine = entry_access(entry, set_by, order_id)
            if mine is None:
                return {"error": "scene %s: %s holds no row for %s"
                                 " (order %s)"
                                 % (sc.get("n", "?"), set_by,
                                    entry.get("ref", ""), order_id)}
            if row_parts(mine) and not any(
                    ref_within(ref, part)
                    for part in row_parts(mine)):
                return {"error": "scene %s: %r sits outside %s's "
                                 "listed parts" % (sc.get("n", "?"),
                                                   ref, set_by)}
            for a in tos:
                if not os.path.isfile(os.path.join(
                        ROOT, "agents", a, "agent.json")):
                    return {"error": "scene %s: unknown agent %r"
                                     % (sc.get("n", "?"), a)}
                planned.setdefault((rpc, rid, a), []).append(ref)
    applied = []
    for (rpc, rid, a), refs in sorted(planned.items()):
        try:
            set_recipients(rpc, rid, order_id, [a], set_by,
                           kind="map", parts=refs, root=root)
        except (OSError, ValueError) as exc:
            return {"error": "cannot list %s on %s: %s"
                             % (a, entry_ref(rpc, rid), exc)}
        applied.append((entry_ref(rpc, rid), a))
    return {"applied": applied, "grants": len(applied)}


def entry_parts_allow(entry, agent_id, order_id, target_ref):
    """True when (agent, order) may open target_ref: a row exists and
    (no parts limit, or the ref sits inside a listed part). Legacy
    keyless entries stay open."""
    if recipients_of(entry) is None:
        return True
    row = entry_access(entry, agent_id, order_id)
    if row is None:
        return False
    parts = row_parts(row)
    if not parts:
        return True
    return any(ref_within(target_ref, part) for part in parts)


def entry_markdown(entry):
    """Full entry text as markdown (content sections only): the text
    writer checks validate against. Headings exact, each followed by
    its (ref: ...) line for verbatim copy."""
    ref = entry.get("ref", "")
    out = ["# %s" % entry.get("title", "source"), "",
           "(Source PC %s; headings below are exact.)" % ref, ""]
    for s in entry.get("sections", []):
        if s.get("non_content"):
            continue
        if s["n"] != "0":
            out += ["## %s %s" % (s["n"], s.get("heading", "")), "",
                    "(ref: %s#s%s)" % (ref, s["n"]), ""]
        for p in entry["paragraphs"][s["start"]:s["start"] + s["count"]]:
            out += [p["text"], ""]
    return "\n".join(out)


def _entry_chunk(entry, mp, reason=None):
    """Map-based input for one entry: ref/title, entry summary,
    section list, per-section map notes with see-refs, omitted list,
    key terms, figures/tables, and how to drill deeper. reason carries
    a pick's {why_important, how_to_use, from} for Theory/Article."""
    ref = entry.get("ref", "")
    pcname = entry.get("pc", "source")
    label = {"source": "Source", "theory": "Theory",
             "article": "Article"}.get(pcname, pcname)
    lines = ["### %s: %s (%s)" % (label, entry.get("title", ""), ref)]
    if isinstance(reason, dict) and reason.get("why_important"):
        lines += ["Picked by %s: %s"
                  % (reason.get("from", "?"),
                     reason["why_important"]),
                  "How to use: %s" % reason.get("how_to_use", "")]
    if isinstance(mp, dict) and mp.get("entry_summary"):
        lines += ["Summary: %s" % mp["entry_summary"]]
    else:
        lines += ["Summary: (map pending)"]
    lines.append("Sections:")
    for s in entry.get("sections", []):
        if s.get("non_content"):
            continue
        lines.append("- s%s %s (%s#s%s)"
                     % (s["n"], s.get("heading", ""), ref, s["n"]))
    by_ref = {}
    if isinstance(mp, dict):
        for s in mp.get("sections", []):
            by_ref[s.get("ref", "")] = s
    for s in entry.get("sections", []):
        if s.get("non_content"):
            continue
        ms = by_ref.get("s" + s["n"], {})
        if not ms:
            continue
        lines.append("Map s%s:" % s["n"])
        for b in ms.get("summary", []) or []:
            lines.append("- %s [%s#%s/%s]"
                         % ((b or {}).get("text", ""), ref, "s" + s["n"],
                            (b or {}).get("see", "")))
        if ms.get("key_terms"):
            lines.append("Terms: " + ", ".join(ms["key_terms"]))
        if ms.get("omitted"):
            lines.append("Omitted (look these up, never guess): "
                         + "; ".join("%s [%s]" % (o.get("what"),
                                                  o.get("ref",
                                                        o.get("see")))
                                     for o in ms["omitted"]))
        if ms.get("has"):
            lines.append("Has: " + "; ".join(
                "%s %s" % (h.get("ref", "").split("#")[-1],
                           h.get("caption", "")) for h in ms["has"]))
    if pcname == "source":
        lines.append("Drill deeper with pc_list_source / "
                     "pc_read_source({section|ref}); open_ref opens any "
                     "pc:// ref you hold the grant for.")
    else:
        lines.append("Drill deeper with pc_read_%s({ref}); open_ref "
                     "opens any pc:// ref you hold the grant for."
                     % pcname)
    lines += ["AI-made descriptions and map summaries are navigation "
              "only, never evidence: cite only verbatim passages.", ""]
    return "\n".join(lines)


FULL_CHUNK_CAP = 100000  # full-text chunk cap (chars)

# Agents whose Source prompt chunk ends with the figure/table/formula
# list (addr + title; files stay on the PC). Penn names screens from
# it; Ash plans scenes from it. Nobody else gets the list.
MEDIA_LIST_AGENTS = ("plan_ash", "board_penn")


def _media_title(item, latex_ok=False):
    bits = [str(item.get("printed_no") or ""),
            str(item.get("caption") or "")]
    title = " ".join(b for b in bits if b).strip()
    if latex_ok and not title:
        title = str(item.get("latex") or "")
    return title


def media_list_block(entry, parts=None):
    """Figures/tables/formulas of a Source entry as addr + title
    lines (no files, no pixels). parts (refs, []) narrows the list
    to listed items. "" when the entry holds none."""
    ref = entry.get("ref", "")
    allow = set(parts or [])
    lines = []
    for kind, items, latex in (
            ("FIGURE", entry.get("figures", []), False),
            ("TABLE", entry.get("tables", []), False),
            ("FORMULA", entry.get("equations", []), True)):
        for it in items or []:
            if not isinstance(it, dict) or not it.get("addr"):
                continue
            full = "%s#%s" % (ref, it["addr"])
            if allow and full not in allow:
                continue
            title = _media_title(it, latex)
            if latex and len(title) > 80:
                title = title[:77] + "..."
            lines.append("- %s %s — %s" % (kind, full, title or
                                           "(no title)"))
    if not lines:
        return ""
    return "Figures/tables/formulas in this entry (open a listed one " \
        "with pc_read_source({ref}) or open_ref; files stay on the " \
        "PC):\n" + "\n".join(lines)


def _agent_base(agent_id):
    return (agent_id or "").split("@")[0]


def _section_of(entry, frag):
    """Section dict enclosing a fragment (section/para/range/group)."""
    base = (frag or "").split("/")[0]
    for s in entry.get("sections", []):
        tag = ("g" if s["n"].startswith("g") else "s") + s["n"]
        if tag == base:
            return s
    return None


def _parts_chunk(entry, mp, parts, reason=None):
    """Map lines for listed parts only: each part's ref plus the map
    notes of the sections the parts sit in (nothing else)."""
    ref = entry.get("ref", "")
    label = {"source": "Source", "theory": "Theory",
             "article": "Article"}.get(entry.get("pc", ""), "Source")
    lines = ["### %s (listed parts): %s (%s)"
             % (label, entry.get("title", ""), ref)]
    if isinstance(reason, dict) and reason.get("why_important"):
        lines += ["Picked by %s: %s"
                  % (reason.get("from", "?"),
                     reason["why_important"]),
                  "How to use: %s" % reason.get("how_to_use", "")]
    lines.append("Your parts:")
    for part in parts:
        lines.append("- %s" % part)
    by_ref = {}
    if isinstance(mp, dict):
        for s in mp.get("sections", []):
            by_ref[s.get("ref", "")] = s
    seen = set()
    for part in parts:
        try:
            _rpc, _rid, frag = parse_ref(part)
        except ValueError:
            continue
        sec = _section_of(entry, frag)
        if sec is None or sec["n"] in seen:
            continue
        seen.add(sec["n"])
        ms = by_ref.get(("g" if sec["n"].startswith("g") else "s")
                        + sec["n"], {})
        lines.append("Map %s%s:" % ("" if sec["n"].startswith("g")
                                    else "s", sec["n"]))
        for b in (ms.get("summary", []) or []):
            lines.append("- %s [%s#%s/%s]"
                         % ((b or {}).get("text", ""), ref,
                            ("g" if sec["n"].startswith("g") else "s")
                            + sec["n"], (b or {}).get("see", "")))
        if ms.get("key_terms"):
            lines.append("Terms: " + ", ".join(ms["key_terms"]))
    lines += ["Open only your listed parts with the PC read tools; "
              "cite every used passage as {ref, quote} verbatim.", ""]
    return "\n".join(lines)


def _parts_text(entry, parts):
    """Full text of listed parts only (section/paragraph/figure)."""
    ref = entry.get("ref", "")
    out = ["# %s (listed parts)" % entry.get("title", ""), ""]
    paras = entry.get("paragraphs", [])
    for part in parts:
        try:
            _rpc, _rid, frag = parse_ref(part)
        except ValueError:
            continue
        if not frag:
            continue
        sec = _section_of(entry, frag)
        if sec is None:
            for fig in entry.get("figures", []) \
                    + entry.get("tables", []):
                if fig.get("ref", "").endswith("#" + frag):
                    out += ["(ref: %s#%s)" % (ref, frag),
                            fig.get("caption", ""), ""]
            continue
        if "/" not in frag:
            out += ["## %s %s" % (sec["n"],
                                  sec.get("heading", "")), "",
                    "(ref: %s#%s)" % (ref, frag), ""]
            for p in paras[sec["start"]:sec["start"] + sec["count"]]:
                out += [p["text"], ""]
            continue
        want = frag.split("/", 1)[1]
        lo, hi = (want.split("-", 1) + [None])[:2]
        for p in paras[sec["start"]:sec["start"] + sec["count"]]:
            paddr = p.get("addr") or p.get("ref", "").split("#", 1)[-1]
            ptag = paddr.split("/", 1)[1] if "/" in paddr else paddr
            if ptag == want or (hi and lo <= ptag <= hi):
                out += ["(ref: %s#%s)" % (ref, paddr), p["text"], ""]
    return "\n".join(out)


def _full_chunk(entry, parts, root=None):
    """Full-text chunk: the whole entry (Marty-08 shape, capped with
    an honest note) or only the listed parts."""
    if parts:
        return _parts_text(entry, parts)
    # Byte-identical to the proven full-text input (override-aware).
    text = marty_input_text(entry.get("ref"))
    if len(text) <= FULL_CHUNK_CAP:
        return text
    return text[:FULL_CHUNK_CAP] + \
        "\n\n[TRUNCATED: %d more chars; read the rest with " \
        "pc_read_source section by section.]" % (len(text)
                                                 - FULL_CHUNK_CAP)


def prompt_chunks_for(agent_id, order_id, source_refs, runs_root,
                      root=None):
    """The ONE recipients-gated PC input for a crew member's prompt:
    every listed source entry plus this order's listed Theory/Article
    picks. kind map -> map chunk; kind full -> full text (capped),
    except Ash (map only, tools stay) and Marty (map first, then
    full text); Ash and Penn also get the Source figure/table/formula
    list. Listed parts narrow either. Returns (text, {"included",
    "denied", "rows", "picks"})."""
    refs = []
    for r in source_refs or []:
        try:
            rpc, rid, _frag = parse_ref(r)
        except ValueError:
            continue
        eref = entry_ref(rpc, rid)
        if eref not in refs:
            refs.append(eref)
    reasons = {}
    for pk in order_picks_with_reasons(order_id, runs_root):
        try:
            rpc, rid, _frag = parse_ref(pk.get("ref", ""))
        except ValueError:
            continue
        eref = entry_ref(rpc, rid)
        reasons.setdefault(eref, pk)
        if eref not in refs:
            refs.append(eref)
    included, denied, blocks = [], [], []
    rows = {}
    for eref in refs:
        try:
            entry = load_entry_by_ref(eref, root=root)
        except (OSError, ValueError, KeyError):
            denied.append(eref)
            continue
        row = entry_access(entry, agent_id, order_id)
        if row is None and recipients_of(entry) is not None:
            denied.append(eref)
            continue
        parts = row_parts(row)
        try:
            mp = load_map_by_ref(eref, root=root)
        except (OSError, ValueError, KeyError):
            mp = {}
        base = _agent_base(agent_id)
        if row_kind(row) == "full" and base != "plan_ash":
            chunk = _full_chunk(entry, parts, root=root)
            if base == "pd_marty" and not parts:
                chunk = _entry_chunk(entry, mp or {},
                                     reasons.get(eref)) + "\n" + chunk
        elif parts:
            chunk = _parts_chunk(entry, mp or {}, parts,
                                 reasons.get(eref))
        else:
            chunk = _entry_chunk(entry, mp or {},
                                 reasons.get(eref))
        if base in MEDIA_LIST_AGENTS \
                and entry.get("pc", "source") == "source":
            media = media_list_block(entry, parts or None)
            if media:
                chunk = chunk.rstrip("\n") + "\n" + media + "\n"
        blocks.append(chunk)
        included.append(eref)
        rows[eref] = {"kind": row_kind(row),
                      "parts": row_parts(row)}
    lines = ["## PC input (order %s)" % (order_id or "?"),
             "You may read ONLY the %d item(s) below. Open passages "
             "with the PC read tools; cite every used passage as "
             "{ref, quote} with the quote verbatim." % len(blocks), ""]
    lines.extend(blocks)
    if denied:
        lines.append("(no access to %d other item(s) for this order)"
                     % len(denied))
    meta = {"included": included, "denied": denied,
            "rows": rows,
            "picks": sum(1 for r in included if "/"
                         in r and r.split("/")[1] in ("theory",
                                                      "article"))}
    return "\n".join(lines), meta


# ---- map skeleton (§10.3/10.5) ----
def blank_map(entry, llm_model):
    pre = "s" if entry.get("pc", "source") == "source" else "g"
    return {"ref": entry.get("ref", ""), "doc_id": entry.get("doc_id"),
            "built_at": "", "llm_model": llm_model,
            "map_version": MAP_VERSION, "status": "pending",
            "entry_summary": "",
            "sections": [{"ref": pre + s["n"], "heading": s["heading"],
                          "summary": [], "omitted": [],
                          "key_terms": [], "has": [], "chars": 0,
                          "subsections": list(s.get("subsections", []))}
                         for s in entry.get("sections", [])
                         if not s.get("non_content")]}

def media_dims_from_bytes(blob):
    """(width, height) from PNG/GIF/JPEG bytes, stdlib only. None
    when the format is unknown or the blob is too short."""
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 26:
        return None
    b = bytes(blob)
    if b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) >= 24:
        w, h = struct.unpack(">II", b[16:24])
        return (w, h) if w > 0 and h > 0 else None
    if b[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", b[6:10])
        return (w, h) if w > 0 and h > 0 else None
    if b[:2] == b"\xff\xd8":
        i = 2  # scan markers for a Start Of Frame with dims
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return (w, h) if w > 0 and h > 0 else None
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7 or m == 0x01:
                i += 2
                continue
            if i + 3 >= len(b):
                return None
            (seglen,) = struct.unpack(">H", b[i + 2:i + 4])
            if seglen < 2:
                return None
            i += 2 + seglen
    return None


def media_dims(path):
    """(width, height) of an image file, or None. Reads the head
    only (a JPEG Start Of Frame past 64 KB is missed)."""
    try:
        with open(path, "rb") as f:
            return media_dims_from_bytes(f.read(65536))
    except OSError:
        return None


def resolve_material_file(ref):
    """(full_path, entry, fig_or_None) for an image/generated entry
    ref or a source figure ref (#fig addr). Raises ValueError
    (not a material ref), KeyError (nothing stored there), or
    OSError (stored file missing)."""
    rpc, rid, frag = parse_ref(ref)
    entry = load_entry_by_ref(entry_ref(rpc, rid))
    edir = entry_dir(rpc, rid)
    if rpc in ("image", "generated"):
        fname = entry.get("file", "")
        if not fname:
            raise KeyError("entry has no file")
        full = os.path.join(edir, "files", fname)
        if not os.path.isfile(full):
            raise OSError("stored file is missing")
        return full, entry, None
    if rpc == "source" and frag:
        for fig in entry.get("figures", []):
            if fig.get("addr") == frag and fig.get("file"):
                full = os.path.join(edir, "figures", fig["file"])
                if not os.path.isfile(full):
                    raise OSError("stored file is missing")
                return full, entry, fig
        raise KeyError("no such figure: %r" % frag)
    raise ValueError("not a material ref: %r" % ref)


# ---- media PCs: voice, image, generated (v8) ----
MEDIA_CONSUMERS = {
    "voice": ["voice_wren"],
    "image": ["photo_pia", "board_vera", "slide_remy"],
    "generated": ["image_gene", "board_vera", "slide_remy"],
}

_CLONE_GRANT_RE = re.compile(r"^([A-Za-z0-9_]+)@p(\d+)$")


def media_grantees(pcname, set_by):
    """Recipient agents for a fresh image/generated pick. Whole
    runs keep the base consumers; a clone's pick goes only to
    its part's Vera/Remy clones plus video_production."""
    m = _CLONE_GRANT_RE.match(set_by or "")
    if not m:
        return list(MEDIA_CONSUMERS.get(pcname, []))
    base, no = m.group(1), m.group(2)
    out = ["%s@p%s" % (c, no)
           for c in MEDIA_CONSUMERS.get(pcname, [])
           if c != base]
    if "video_production" not in out:
        out.append("video_production")
    return out


def voice_save(order_id, cut_id, wav_bytes, text, seconds, attempt,
               engine, root=None):
    """Store one cut's narration audio in this order's Voice entry
    (one entry per order). Atomic under the entry lock. Returns
    {ref, doc_id, file}."""
    doc_id = content_id("voice:" + order_id)
    edir = entry_dir("voice", doc_id, root)
    os.makedirs(os.path.join(edir, "audio"), exist_ok=True)
    with _path_lock(edir):
        return _voice_save_in(edir, order_id, cut_id, wav_bytes,
                              text, seconds, attempt, engine)


def _voice_save_in(edir, order_id, cut_id, wav_bytes, text, seconds,
                   attempt, engine):
    doc_id = os.path.basename(edir)
    ep = os.path.join(edir, "entry.json")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            entry = json.load(f)
    else:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        entry = {"pc": "voice", "doc_id": doc_id,
                 "ref": entry_ref("voice", doc_id),
                 "order_id": order_id, "parsed_at": now,
                 "added_by": "voice_wren", "cuts": {},
                 "recipients": []}
        for a in MEDIA_CONSUMERS["voice"]:
            entry["recipients"].append(
                {"agent": a, "order_id": order_id, "kind": "full",
                 "parts": [], "set_by": "voice_wren", "at": now})
    fname = "%s-t%d.wav" % (cut_id, attempt)
    with open(os.path.join(edir, "audio", fname), "wb") as f:
        f.write(wav_bytes)
    entry["cuts"][cut_id] = {
        "file": fname, "text": text, "seconds": seconds,
        "attempt": attempt, "engine": engine,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return {"ref": entry["ref"] + "#" + cut_id, "doc_id": doc_id,
            "file": fname}


def _find_duplicate_blob(pcname, blob, license, root):
    """Entry dir already holding these exact bytes under the same
    license, or None. Same file, new URL: reuse, don't store twice."""
    digest = hashlib.sha256(blob or b"").hexdigest()
    edirs = os.path.join(pc_dir(pcname, root), "entries")
    try:
        names = sorted(os.listdir(edirs))
    except OSError:
        return None
    for n in names:
        ep = os.path.join(edirs, n, "entry.json")
        try:
            with open(ep, encoding="utf-8") as f:
                e = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(e, dict):
            continue
        if e.get("sha256") == digest \
                and e.get("license") == license \
                and e.get("file"):
            full = os.path.join(edirs, n, "files", e["file"])
            if os.path.isfile(full):
                return os.path.join(edirs, n)
    return None


def _merge_media_rows(entry, pcname, order_id, set_by):
    rows = recipients_of(entry) or []
    have = {(r.get("agent"), r.get("order_id")) for r in rows
            if isinstance(r, dict)}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for a in media_grantees(pcname, set_by):
        if (a, order_id) not in have:
            rows.append({"agent": a, "order_id": order_id,
                         "kind": "full", "parts": [],
                         "set_by": set_by, "at": now})
    entry["recipients"] = rows


def image_store_pick(order_id, source_url, blob, license, reason,
                     set_by="photo_pia", suffix=".jpg", root=None):
    """Store one licensed web pick (one entry per URL: same URL is
    the same entry, recipients gain rows per order; same bytes
    under the same license reuse the first entry). Atomic under
    the PC + entry locks."""
    doc_id = content_id("image:" + source_url)
    with _path_lock(pc_dir("image", root)):
        edir = entry_dir("image", doc_id, root)
        dup = None
        if not os.path.isfile(os.path.join(edir, "entry.json")):
            dup = _find_duplicate_blob("image", blob, license,
                                       root)
        if dup is not None:
            edir = dup
        with _path_lock(edir):
            return _image_store_pick_in(
                edir, order_id, source_url, blob, license,
                reason, set_by, suffix, bool(dup))


def _image_store_pick_in(edir, order_id, source_url, blob, license,
                         reason, set_by, suffix, deduped):
    os.makedirs(os.path.join(edir, "files"), exist_ok=True)
    ep = os.path.join(edir, "entry.json")
    new = not os.path.isfile(ep)
    if new:
        doc_id = os.path.basename(edir)
        entry = {"pc": "image", "doc_id": doc_id,
                 "ref": entry_ref("image", doc_id),
                 "source_url": source_url, "license": license,
                 "added_by": set_by, "recipients": []}
    else:
        with open(ep, encoding="utf-8") as f:
            entry = json.load(f)
    if deduped:
        _merge_media_rows(entry, "image", order_id, set_by)
        with open(ep, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        return {"ref": entry["ref"], "doc_id": entry["doc_id"],
                "file": entry["file"], "reused_entry": True,
                "deduped": True}
    fname = "pick%s" % suffix
    with open(os.path.join(edir, "files", fname), "wb") as f:
        f.write(blob)
    entry["file"] = fname
    entry["sha256"] = hashlib.sha256(blob or b"").hexdigest()
    dims = media_dims_from_bytes(blob)
    entry["width"], entry["height"] = dims if dims else (None, None)
    entry["reason"] = reason
    _merge_media_rows(entry, "image", order_id, set_by)
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return {"ref": entry["ref"], "doc_id": entry["doc_id"],
            "file": fname, "reused_entry": not new,
            "deduped": False}


def generated_store(order_id, prompt, blob, cost_usd, model,
                    set_by="image_gene", root=None):
    """Store one generated image (one entry per prompt: the same
    prompt reuses the stored image). Atomic under the PC + entry
    locks."""
    doc_id = content_id("generated:" + prompt)
    with _path_lock(pc_dir("generated", root)):
        edir = entry_dir("generated", doc_id, root)
        with _path_lock(edir):
            return _generated_store_in(edir, order_id, prompt,
                                       blob, cost_usd, model,
                                       set_by)


def _generated_store_in(edir, order_id, prompt, blob, cost_usd,
                        model, set_by):
    os.makedirs(os.path.join(edir, "files"), exist_ok=True)
    ep = os.path.join(edir, "entry.json")
    new = not os.path.isfile(ep)
    if new:
        doc_id = os.path.basename(edir)
        entry = {"pc": "generated", "doc_id": doc_id,
                 "ref": entry_ref("generated", doc_id),
                 "prompt": prompt, "model": model,
                 "cost_usd": cost_usd, "added_by": set_by,
                 "recipients": []}
        fname = "gen.png"
        with open(os.path.join(edir, "files", fname), "wb") as f:
            f.write(blob)
        entry["file"] = fname
        dims = media_dims_from_bytes(blob)
        entry["width"], entry["height"] = dims if dims else (None,
                                                             None)
    else:
        with open(ep, encoding="utf-8") as f:
            entry = json.load(f)
    _merge_media_rows(entry, "generated", order_id, set_by)
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return {"ref": entry["ref"], "doc_id": entry["doc_id"],
            "file": entry["file"], "reused_entry": not new}


def _open_media_ref(entry, ref, pcname, frag):
    """Passages for voice/image/generated entries."""
    if pcname == "voice":
        if not frag:
            return {"kind": "entry", "ref": entry["ref"],
                    "cuts": sorted(entry.get("cuts", {})),
                    "provenance": _provenance(entry)}
        cut = entry.get("cuts", {}).get(frag)
        if cut is None:
            raise KeyError("no such cut: %r" % ref)
        return {"kind": "voice_clip", "ref": ref,
                "file": cut["file"], "path": "audio/" + cut["file"],
                "text": cut["text"], "seconds": cut["seconds"],
                "attempt": cut["attempt"], "engine": cut["engine"],
                "provenance": _provenance(entry)}
    if pcname == "image":
        if frag:
            raise KeyError("no such fragment: %r" % ref)
        return {"kind": "image_pick", "ref": ref,
                "file": entry.get("file", ""),
                "path": "files/" + entry.get("file", ""),
                "source_url": entry.get("source_url", ""),
                "license": entry.get("license", ""),
                "reason": entry.get("reason", ""),
                "provenance": _provenance(entry)}
    if frag:
        raise KeyError("no such fragment: %r" % ref)
    return {"kind": "generated_image", "ref": ref,
            "file": entry.get("file", ""),
            "path": "files/" + entry.get("file", ""),
            "prompt": entry.get("prompt", ""),
            "model": entry.get("model", ""),
            "cost_usd": entry.get("cost_usd", 0),
            "provenance": _provenance(entry)}
