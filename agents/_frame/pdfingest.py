"""PDF parsing for PC ingest (pdfplumber, vendored-free).

Moved here from scripts/server.py so Sam's pc_send_source tool
and the server share one parser. Stdlib + pdfplumber only.
"""
import re

from . import pc


XTOL = 1  # inter-word gaps in our PDFs sit under the default 3


def pdf_to_text(raw):
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber not installed (pip install -r requirements.txt)")
    import io
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n\n".join((page.extract_text(x_tolerance=XTOL) or "")
                            for page in pdf.pages)


def _rows_to_md(rows):
    cells = [[(c or "").strip().replace("|", "\\|") for c in r]
             for r in rows]
    width = max(len(r) for r in cells)
    cells = [r + [""] * (width - len(r)) for r in cells]
    out = ["| " + " | ".join(cells[0]) + " |",
           "| " + " | ".join("---" for _ in cells[0]) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in cells[1:]]
    return "\n".join(out)


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


def _is_table_row(text):
    s = (text or "").strip()
    return bool(s) and (s.startswith("(cid:") or s.startswith("\u2022"))


def _table_images(page, skip):
    """Borderless tables find_tables() misses: a Table/Tab caption plus
    the bullet-led rows below it, cropped as a PNG (table-image).
    skip holds bboxes of tables already found. Returns table dicts
    with rows None, blob set, and the row texts for search."""
    import io
    out = []
    rows = _text_rows(page)
    for ci, (cy, ctxt, _cx0, _cx1, _cb) in enumerate(rows):
        hit = pc.parse_caption(ctxt)
        if not hit or not hit["label"].lower().startswith(
                ("table", "tab")):
            continue
        body = []
        prev = cy
        for y, txt, x0, x1, bot in rows[ci + 1:]:
            if y > cy + 600 or y - prev > 30:
                break
            prev = y
            s = txt.strip()
            if not s:
                continue
            if not body:
                if pc.parse_caption(txt) or re.match(r"^\d", s):
                    break
                body.append((y, txt.strip(), x0, x1, bot))
            elif _is_table_row(txt):
                body.append((y, txt.strip(), x0, x1, bot))
            else:
                break
        if len(body) < 2:
            continue
        bbox = [min(b[2] for b in body) - 4, body[0][0] - 2,
                max(b[3] for b in body) + 4, body[-1][4] + 2]
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
            pages.append(page.extract_text(x_tolerance=XTOL) or "")
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
                tables.append({"page": i + 1, "top": bbox[1],
                               "caption": cap, "number": num, "bbox": bbox,
                               "rows": rows, "markdown": md, "blob": blob})
            for ti in _table_images(
                    page, [t["bbox"] for t in tables
                           if t.get("page") == i + 1]):
                ti["page"] = i + 1
                tables.append(ti)
    return pages, images, tables, skipped, marks
