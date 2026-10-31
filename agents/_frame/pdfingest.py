"""PDF parsing for PC ingest (pdfplumber, vendored-free).

Moved here from scripts/server.py so Sam's pc_send_source tool
and the server share one parser. Stdlib + pdfplumber only.
"""
import re

from . import pc


XTOL = 1  # Word gaps measure ~2.2pt on our PDFs (page 2 table:
# "Macro variables" etc.): the default 3 MERGES words
# ("Macrovariables", "...willbeextractedeachtime..."), 0.5
# over-splits inside words. Do not retune without re-checking.


def extract_page_text(page):
    """One page's text with the locked word-gap tolerance."""
    return page.extract_text(x_tolerance=XTOL) or ""


def page_png(page, resolution=200):
    """Render one pdfplumber page to PNG bytes (vision input)."""
    import io
    buf = io.BytesIO()
    page.to_image(resolution=resolution).original.save(buf, format="PNG")
    return buf.getvalue()


def pdf_to_text(raw):
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber not installed (pip install -r requirements.txt)")
    import io
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n\n".join(extract_page_text(page)
                            for page in pdf.pages)


def _rows_to_md(rows):
    return pc.rows_to_md(rows)


def _text_rows(page):
    """Char-grouped text lines: [(top, text, x0, x1, bottom)] sorted
    top-down. Gap-joined, so no crop edge ever clips glyphs away."""
    rows = {}
    for ch in page.chars:
        rows.setdefault(round(ch["top"]), []).append(ch)
    out = []
    for y in sorted(rows):
        cs = sorted(rows[y], key=lambda c: c["x0"])
        out.append((y, _join_chars(cs),
                    min(c["x0"] for c in cs),
                    max(c["x1"] for c in cs),
                    max(c["bottom"] for c in cs)))
    return out


def _near_caption(page, box):
    """Nearest printed caption line below a figure/table box, else
    nearest above (within half/quarter page). Lines come from char
    tops, not crops, so band edges never clip glyphs away. Returns
    (caption_line, number) or ("", "")."""
    bottom, top = box[3], box[1]
    cands = []
    for y, txt, _x0, _x1, _bot in _text_rows(page):
        if pc.parse_caption(txt):
            cands.append((y, txt.strip()))
    below = [(y, t) for y, t in cands
             if bottom - 4 <= y <= bottom + page.height / 2]
    if below:
        _y, t = min(below)
        return t, pc.parse_caption(t)["number"]
    above = [(y, t) for y, t in cands
             if top - page.height / 4 <= y <= top + 4]
    if above:
        _y, t = max(above)
        return t, pc.parse_caption(t)["number"]
    return "", ""


def _row_gap_counts(page):
    """Per row-top: how many inter-char gaps exceed 12pt (column
    separators). Table body rows show 2+; prose word gaps are ~2-5pt."""
    rows = {}
    for ch in page.chars:
        rows.setdefault(round(ch["top"]), []).append(ch)
    out = {}
    for y, cs in rows.items():
        cs = sorted(cs, key=lambda c: c["x0"])
        out[y] = sum(1 for a, b in zip(cs, cs[1:])
                     if b["x0"] - a["x1"] > 12)
    return out


def _is_raw_heading(text):
    return bool(re.match(r"^\d+(?:\.\d+)+\s+\S", (text or "").strip()))


def _scan_table_body(rows, gapcounts, ci, cy):
    """Body rows below a caption row: caption down to the next
    caption/heading/paragraph gap. rows: _text_rows output; ci: the
    caption's row index; cy: its top. Alternating text rows belong
    to the table (column gaps or bullets prove it); a short trailing
    row (". . .") is kept. Returns the body row tuples."""
    body = []
    prev = cy
    for y, txt, x0, x1, bot in rows[ci + 1:]:
        if y > cy + 600 or y - prev > 30:
            break
        s = txt.strip()
        if not s:
            continue
        if pc.parse_caption(txt) or _is_raw_heading(s):
            break
        if not body:
            if re.match(r"^\d", s):
                break
            body.append((y, txt.strip(), x0, x1, bot))
            prev = y
            continue
        if s.startswith("(cid:") or s.startswith("\u2022") \
                or gapcounts.get(y, 0) >= 2:
            body.append((y, txt.strip(), x0, x1, bot))
            prev = y
            continue
        if len(s) < 45 and y - prev <= 14:
            body.append((y, txt.strip(), x0, x1, bot))
            prev = y
            continue
        break
    return body


def _extend_table_bbox(page, bbox, caption):
    """Grow a vector-table bbox that clips rows (caption down to the
    next caption/heading/paragraph gap). Returns (bbox, body_text).
    Falls back to the input bbox when no body scan applies."""
    rows = _text_rows(page)
    gaps = _row_gap_counts(page)
    ci = None
    if caption:
        for i, (_y, txt, _x0, _x1, _bot) in enumerate(rows):
            if txt.strip() == caption.strip():
                ci = i
                break
    if ci is None:
        for i, (y, _t, _x0, _x1, _b) in enumerate(rows):
            if y >= bbox[1] - 2:
                ci = max(0, i - 1)
                break
    if ci is None:
        return list(bbox), ""
    _cy, _ct, _cx0, _cx1, _cb = rows[ci]
    body = _scan_table_body(rows, gaps, ci, rows[ci][0])
    if len(body) < 2:
        return list(bbox), ""
    top = min(bbox[1], rows[ci][0] - 2)
    left = min([bbox[0]] + [b[2] for b in body]) - 4
    right = max([bbox[2]] + [b[3] for b in body]) + 4
    bottom = max(bbox[3], body[-1][4] + 2)
    return ([left, top, right, bottom],
            "\n".join(b[1] for b in body))


def _table_images(page, skip):
    """Borderless tables find_tables() misses: a Table/Tab caption plus
    the body rows below it (caption down to the next
    caption/heading/paragraph gap), cropped as a PNG (table-image).
    skip holds bboxes of tables already found. Returns table dicts
    with rows None, blob set, and the row texts for search."""
    import io
    out = []
    rows = _text_rows(page)
    gaps = _row_gap_counts(page)
    for ci, (cy, ctxt, cx0, cx1, _cb) in enumerate(rows):
        hit = pc.parse_caption(ctxt)
        if not hit or not hit["label"].lower().startswith(
                ("table", "tab")):
            continue
        body = _scan_table_body(rows, gaps, ci, cy)
        if len(body) < 2:
            continue
        bbox = [min([cx0] + [b[2] for b in body]) - 4, cy - 2,
                max([cx1] + [b[3] for b in body]) + 4,
                body[-1][4] + 2]
        if any(not (bbox[2] < s[0] or s[2] < bbox[0]
                    or bbox[3] < s[1] or s[3] < bbox[1]) for s in skip):
            continue
        try:
            buf = io.BytesIO()
            page.crop(bbox).to_image(
                resolution=150).original.save(buf, format="PNG")
        except Exception:  # noqa: BLE001 - crop failed, drop it
            continue
        out.append({"top": bbox[1], "caption": ctxt.strip(),
                    "number": hit["number"], "bbox": bbox, "rows": None,
                    "markdown": "", "blob": buf.getvalue(),
                    "text": "\n".join(b[1] for b in body)})
    return out


def _page_marks(page):
    """Per-page typography marks: bold phrases (font name carries it),
    grouped within a row, for key terms."""
    rows = {}
    for ch in page.chars:
        rows.setdefault(round(ch["top"]), []).append(ch)
    out = []
    for y in sorted(rows):
        cs = sorted(rows[y], key=lambda c: c["x0"])
        cur = []
        for c in cs:
            if "bold" in (c.get("fontname") or "").lower():
                if cur and c["x0"] - cur[-1]["x1"] > 6:
                    out.append(_join_chars(cur))
                    cur = []
                cur.append(c)
            elif cur:
                out.append(_join_chars(cur))
                cur = []
        if cur:
            out.append(_join_chars(cur))
    seen, ded = set(), []
    for p in out:
        if len(p) >= 2 and not re.fullmatch(r"[\d.]+", p) \
                and p not in seen:
            seen.add(p)
            ded.append(p)
    return {"bold": ded}


def _join_chars(cs):
    parts = [cs[0]["text"]]
    for a, b in zip(cs, cs[1:]):
        if b["x0"] - a["x1"] > 1.5:
            parts.append(" ")
        parts.append(b["text"])
    return " ".join("".join(parts).split())


def pdf_parse(raw):
    """Split a PDF into per-page texts + figure/table records.

    Returns (pages, images, tables, skipped, marks): images and tables
    carry page/bbox/caption for the PC; skipped counts tiny decor
    images; marks holds per-page typography (bold phrases).
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber not installed (pip install -r requirements.txt)")
    import io
    pages, images, tables, marks = [], [], [], []
    skipped = 0
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for i, page in enumerate(pdf.pages):
            pages.append(extract_page_text(page))
            marks.append(_page_marks(page))
            for img in page.images:
                w, h = img["x1"] - img["x0"], img["bottom"] - img["top"]
                if w < pc.MIN_FIG_PT and h < pc.MIN_FIG_PT:
                    skipped += 1
                    continue
                try:
                    crop = page.crop((img["x0"], img["top"],
                                      img["x1"], img["bottom"]))
                    buf = io.BytesIO()
                    crop.to_image(resolution=150).original.save(
                        buf, format="PNG")
                    blob = buf.getvalue()
                except Exception:  # noqa: BLE001 - one bad image skips
                    continue
                cap, num = _near_caption(
                    page, (img["x0"], img["top"], img["x1"], img["bottom"]))
                images.append({"page": i + 1, "top": img["top"],
                               "caption": cap, "number": num,
                               "bbox": [img["x0"], img["top"], img["x1"],
                                        img["bottom"]],
                               "w": w, "h": h, "blob": blob})
            try:
                found = page.find_tables()
            except Exception:  # noqa: BLE001 - detection failed, no tables
                found = []
            for tab in found:
                bbox = list(tab.bbox)
                try:
                    rows = tab.extract(x_tolerance=XTOL)
                except Exception:  # noqa: BLE001 - extraction failed
                    rows = None
                if not rows or not any(
                        (c or "").strip() for r in rows for c in (r or [])):
                    rows = None
                cap, num = _near_caption(page, bbox)
                tab_text = ""
                if rows is None:
                    bbox, tab_text = _extend_table_bbox(page, bbox, cap)
                blob, md = None, ""
                if rows:
                    md = _rows_to_md(rows)
                else:
                    try:
                        buf = io.BytesIO()
                        page.crop(bbox).to_image(
                            resolution=150).original.save(buf, format="PNG")
                        blob = buf.getvalue()
                    except Exception:  # noqa: BLE001 - crop failed, drop it
                        continue
                rec = {"page": i + 1, "top": bbox[1],
                         "caption": cap, "number": num, "bbox": bbox,
                         "rows": rows, "markdown": md, "blob": blob}
                if tab_text:
                    rec["text"] = tab_text
                tables.append(rec)
            for ti in _table_images(
                    page, [t["bbox"] for t in tables
                           if t.get("page") == i + 1]):
                ti["page"] = i + 1
                tables.append(ti)
    return pages, images, tables, skipped, marks
