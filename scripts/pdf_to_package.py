"""Turn a PDF (Korean or English) into a document package for an original file server.

  python scripts/pdf_to_package.py PAPER.pdf inputs/source --book "Book title" [--author "Name"] [--year 2018]
                                   [--pages 1-5] [--dpi 170] [--workers 4]

--book is required: the person who gives the PDF names the book (or paper). The model never guesses it.
The package title becomes "<book> - <chapter heading found on page 1>"; author and year go to publisher/published.

How it works, page by page:
  1. PyMuPDF draws the page as an image and finds the figure/photo regions (embedded images and
     clusters of vector drawings, minus tables). Each region is cut out as figures/f<n>.png.
  2. The page image goes to the vision LLM of this project (project.json: llm "default", first model).
     It writes the page as Markdown: text as is (no translation), equations in LaTeX, tables as
     Markdown tables, and a marker line where each figure is.
  3. The Markdown becomes parts: text, table, equation, figure (with page, heading, caption, label).
Writes <out>/<pdf name>/document.json + figures/ + source.pdf, then checks the package.
Work files (page images, raw LLM replies) stay in <out>/.<pdf name>-work/ (ignored by nextop).
Then run:  nextop run . --file-server source=inputs/source --input input.json

There is no "photo" part type, so the kind of a figure (photo, chart, diagram, ...) goes at the start
of its caption, e.g. "[photo] Figure 2: ...".
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROMPT = """Transcribe this document page into Markdown.

Rules:
- Keep the original language exactly (Korean, English or mixed). Do not translate or summarize.
- Headings: "# " for the document title (first page only), "## " for sections, "### " for subsections.
- Paragraphs: one paragraph per block, separated by a blank line. Join lines broken by the layout.
- Math: inline math as $...$; display equations as $$...$$ on their own lines, with \\tag{n} for the
  equation number shown on the page.
- Tables: Markdown tables. Put the table caption on the line right before the table as
  [[TABLE | <caption as written>]]
- Figures, photos, charts and diagrams: do not describe them. Put one marker line where each appears:
  [[FIGURE <id> | <kind> | <caption as written, or empty>]]
  kind is one of: photo, chart, diagram, drawing, other.
  {figure_hint}
  Do not repeat the caption as a separate paragraph.
- Leave out running headers, footers and page numbers.
Output only the Markdown."""

FIGURE = re.compile(r"^\[\[FIGURE\s+([^|\]]*?)\s*\|\s*([^|\]]*?)\s*\|\s*(.*?)\]\]\s*$")
TABLE_CAP = re.compile(r"^\[\[TABLE\s*\|\s*(.*?)\]\]\s*$")
TAG = re.compile(r"\\tag\*?\{([^}]*)\}")
CAP_LABEL = re.compile(r"^((?:Figure|Fig\.|Table|그림|표|사진)\s*[0-9A-Za-z.\-]+)[:.]?\s*", re.I)


# ---------------------------------------------------------------- LLM

def llm_config(args) -> dict:
    proj = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
    opts = proj["adapters"]["llm"]["default"]["options"]
    env = {}
    env_file = ROOT / opts.get("env_file", ".env")
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return {"url": opts["base_url"].rstrip("/") + "/chat/completions",
            "key": env.get(opts.get("key_env", ""), ""),
            "model": args.model or proj["models"][0]["name"],
            "timeout": max(int(opts.get("timeout", 300)), 300)}


def ask_llm(cfg: dict, png: bytes, prompt: str, tries: int = 3) -> tuple[str, dict]:
    body = {"model": cfg["model"], "temperature": 0, "max_tokens": 8000,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
    headers = {"Content-Type": "application/json"}
    if cfg["key"]:
        headers["Authorization"] = "Bearer " + cfg["key"]
    last = ""
    for k in range(tries):
        try:
            req = urllib.request.Request(cfg["url"], json.dumps(body).encode(), headers)
            r = json.load(urllib.request.urlopen(req, timeout=cfg["timeout"]))
            text = r["choices"][0]["message"]["content"] or ""
            if text.strip():
                return text, r.get("usage") or {}
            last = "empty reply"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:          # network, timeout, bad JSON
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 * (k + 1))
    raise RuntimeError(last)


# ---------------------------------------------------------------- figures

def _merge(rects: list[pymupdf.Rect], gap: float = 6) -> list[pymupdf.Rect]:
    rects = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if (a + (-gap, -gap, gap, gap)).intersects(b):
                    rects[i] = a | b
                    del rects[j]
                    changed = True
                    break
            if changed:
                break
    return rects


def _visible(page: pymupdf.Page, xref: int, r: pymupdf.Rect) -> pymupdf.Rect:
    """The part of an image's frame that holds its visible content (images often carry white or transparent margins)."""
    try:
        from PIL import Image, ImageChops
        pix = pymupdf.Pixmap(page.parent, xref)
        if pix.colorspace and pix.colorspace.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        im = Image.open(io.BytesIO(pix.tobytes("png")))
        if "A" in im.getbands():
            box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        else:
            rgb = im.convert("RGB")
            diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255))).convert("L")
            box = diff.point(lambda v: 255 if v > 12 else 0).getbbox()
        if not box:
            return r
        w, h = im.size
        return pymupdf.Rect(r.x0 + r.width * box[0] / w, r.y0 + r.height * box[1] / h,
                            r.x0 + r.width * box[2] / w, r.y0 + r.height * box[3] / h)
    except Exception:                    # unusual image formats: keep the frame
        return r


def _cut_captions(page: pymupdf.Page, regions: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """End a region above a caption line ("Figure 2: ...", "그림 3 ...") that starts inside its lower half."""
    caps = [pymupdf.Rect(b[:4]) for b in page.get_text("blocks") if CAP_LABEL.match(b[4].strip())]
    out = []
    for r in regions:
        for c in caps:
            if r.y0 + r.height / 2 < c.y0 < r.y1 and c.x0 < r.x1 and c.x1 > r.x0:
                r = pymupdf.Rect(r.x0, r.y0, r.x1, c.y0 - 1)
        if r.height > 20:
            out.append(r)
    return out


def figure_regions(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Figure/photo regions on a page, in reading order (top to bottom, left column first)."""
    area = page.rect.get_area()
    found = []
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            r = _visible(page, img[0], r) & page.rect
            if r.get_area() >= 0.01 * area and r.width > 40 and r.height > 40:
                found.append(r)
    try:
        tables = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables]
    except Exception:
        tables = []
    try:
        clusters = page.cluster_drawings()
    except Exception:
        clusters = []
    for r in clusters:
        r = pymupdf.Rect(r) & page.rect
        if r.width < 60 or r.height < 40 or r.get_area() < 0.02 * area or r.get_area() > 0.9 * area:
            continue                     # rules, underlines, page frames
        if any((r & t).get_area() > 0.5 * r.get_area() for t in tables):
            continue                     # table borders
        found.append(r)
    regions = _cut_captions(page, _merge(found))
    mid = page.rect.width / 2
    two_columns = any(r.x1 <= mid + 10 for r in regions) and any(r.x0 >= mid - 10 for r in regions)
    if not two_columns:
        return sorted(regions, key=lambda r: r.y0)
    return sorted(regions, key=lambda r: (1 if r.x0 >= mid - 10 else 0, r.y0))


def figure_hint(page: pymupdf.Page, regions: list[pymupdf.Rect], first_id: int) -> str:
    if not regions:
        return ("No figure regions were detected on this page. If you still see a figure, use the id ? "
                "in its marker.")
    h, w = page.rect.height, page.rect.width
    rows = []
    for k, r in enumerate(regions):
        side = "left" if r.x1 <= w * 0.55 else "right" if r.x0 >= w * 0.45 else "full width"
        rows.append(f"f{first_id + k}: {side}, from {r.y0 / h:.0%} to {r.y1 / h:.0%} of the page height")
    return ("These figure regions were detected on this page; use these ids in the markers, one marker per "
            "region: " + "; ".join(rows) + ". If you see another figure, use the id ?.")


# ---------------------------------------------------------------- markdown -> parts

def md_parts(md: str, page_no: int, heading: str, figs: dict[str, str]) -> tuple[list[dict], str, str | None, list[str]]:
    """Parts of one page (ids filled later), the heading at the end of the page, the title, warnings."""
    md = md.strip()
    if md.startswith("```"):                               # some models wrap the reply in a code fence
        md = re.sub(r"^```[a-zA-Z]*\n?", "", md)
        md = re.sub(r"\n?```\s*$", "", md)
    lines = md.replace("\r\n", "\n").split("\n")
    parts, title, warn, para, table_cap = [], None, [], [], None
    used = set()

    def flush():
        nonlocal para
        if para:
            text = " ".join(x.strip() for x in para).strip()
            if text:
                p = {"type": "text", "page": page_no, "text": text}
                if heading:
                    p["heading"] = heading
                parts.append(p)
        para = []

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("$$"):
            flush()
            buf = [s]
            while not ("".join(buf).count("$$") >= 2) and i + 1 < len(lines):
                i += 1
                buf.append(lines[i].strip())
            latex = "\n".join(buf).strip()[2:]
            latex = latex[:-2] if latex.endswith("$$") else latex
            p = {"type": "equation", "page": page_no}
            m = TAG.search(latex)
            if m:
                p["label"] = f"({m.group(1).strip()})"
                latex = TAG.sub("", latex)
            p["latex"] = latex.strip()
            if heading:
                p["heading"] = heading
            if p["latex"]:
                parts.append(p)
        elif s.startswith("|"):
            flush()
            buf = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                buf.append(lines[i].strip())
                i += 1
            i -= 1
            p = {"type": "table", "page": page_no, "text": "\n".join(buf)}
            if table_cap:
                p["caption"] = table_cap
                m = CAP_LABEL.match(table_cap)
                if m:
                    p["label"] = m.group(1)
                table_cap = None
            if heading:
                p["heading"] = heading
            parts.append(p)
        elif TABLE_CAP.match(s):
            flush()
            table_cap = TABLE_CAP.match(s).group(1).strip() or None
        elif FIGURE.match(s):
            flush()
            fid, kind, cap = (x.strip() for x in FIGURE.match(s).groups())
            fid = fid.lower()
            caption = f"[{kind or 'other'}] {cap}".strip()
            if fid in figs and fid not in used:
                used.add(fid)
                p = {"type": "figure", "page": page_no, "file": figs[fid], "caption": caption, "_fid": fid}
                m = CAP_LABEL.match(cap)
                if m:
                    p["label"] = m.group(1)
                if heading:
                    p["heading"] = heading
                parts.append(p)
            else:
                warn.append(f"page {page_no}: the model saw a figure not found in the PDF ({cap or 'no caption'}); kept as text")
                para.append(f"[figure: {caption}]")
                flush()
        elif s.startswith("#"):
            flush()
            level = len(s) - len(s.lstrip("#"))
            text = s.lstrip("#").strip()
            if level == 1 and page_no == 1 and title is None:
                title = text
            elif text:
                heading = text
        else:
            para.append(s)
        i += 1
    flush()
    for fid, file in figs.items():                      # regions the model did not place: keep them anyway
        if fid not in used:
            warn.append(f"page {page_no}: figure {fid} was not placed by the model; added at the end of the page")
            p = {"type": "figure", "page": page_no, "file": file, "caption": "[other]", "_fid": fid}
            if heading:
                p["heading"] = heading
            parts.append(p)
    return parts, heading, title, warn


# ---------------------------------------------------------------- main

def page_list(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(1, n + 1))
    out = []
    for piece in spec.split(","):
        a, _, b = piece.partition("-")
        out += range(int(a), int(b or a) + 1)
    return [p for p in dict.fromkeys(out) if 1 <= p <= n]


def convert(pdf: pathlib.Path, out_root: pathlib.Path, args) -> tuple[pathlib.Path, list[str]]:
    cfg = llm_config(args)
    doc = pymupdf.open(pdf)
    pages = page_list(args.pages, doc.page_count)
    if not pages:
        raise SystemExit("no pages to read")
    name = re.sub(r"[^a-z0-9_-]+", "_", pdf.stem.lower()).strip("_") or "document"
    dst, work = out_root / name, out_root / f".{name}-work"
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "figures").mkdir(parents=True)
    work.mkdir(parents=True, exist_ok=True)

    # step 1 (main thread; PyMuPDF documents are not thread safe): page images and figure crops
    jobs, next_fig = [], 1
    for no in pages:
        page = doc[no - 1]
        png = page.get_pixmap(dpi=args.dpi).tobytes("png")
        (work / f"page{no:03d}.png").write_bytes(png)
        regions = figure_regions(page)
        figs = {}
        for k, r in enumerate(regions):
            fid = f"f{next_fig + k}"
            file = f"figures/{fid}.png"
            page.get_pixmap(dpi=max(args.dpi, 200), clip=r).save(str(dst / file))
            figs[fid] = file
        jobs.append((no, png, figs, PROMPT.replace("{figure_hint}", figure_hint(page, regions, next_fig))))
        next_fig += len(regions)

    # step 2: the LLM reads the pages in parallel
    def read(job):
        no, png, figs, prompt = job
        t = time.time()
        try:
            md, usage = ask_llm(cfg, png, prompt)
        except RuntimeError as e:
            return no, None, figs, f"page {no}: the model failed ({e})"
        (work / f"page{no:03d}.md").write_text(md, encoding="utf-8")
        print(f"  page {no}: {time.time() - t:.0f}s, {usage.get('total_tokens', '?')} tokens", flush=True)
        return no, md, figs, None

    print(f"{pdf.name}: {len(pages)} page(s), model {cfg['model']}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = sorted(ex.map(read, jobs), key=lambda x: x[0])

    # step 3: parts in reading order
    parts, warnings, heading, title = [], [], "", None
    for no, md, figs, err in results:
        if err:
            warnings.append(err + "; its figures are kept, its text is missing")
            md = ""
        got, heading, t, warn = md_parts(md, no, heading, figs)
        title = title or t
        parts += got
        warnings += warn
    counters, prefix = {}, {"text": "p", "table": "t", "figure": "f", "equation": "e"}
    for p in parts:
        if p["type"] == "figure":
            p["id"] = p.pop("_fid")
        else:
            counters[p["type"]] = counters.get(p["type"], 0) + 1
            p["id"] = f"{prefix[p['type']]}{counters[p['type']]}"
    parts = [{"id": p["id"], **{k: v for k, v in p.items() if k != "id"}} for p in parts]
    chapter = (title or "").strip()
    title = f"{args.book} - {chapter}" if chapter and chapter.lower() not in args.book.lower() else args.book
    meta = {"pages": doc.page_count, "pages_read": pages, "parser": "pymupdf + vision LLM", "model": cfg["model"],
            "book": args.book}
    if args.author:
        meta["publisher"] = args.author
    if args.year:
        meta["published"] = str(args.year)
    package = {"title": title, "source": pdf.name, "meta": meta, "parts": parts}
    (dst / "document.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(pdf, dst / ("source" + pdf.suffix.lower()))
    if not any((dst / "figures").iterdir()):
        (dst / "figures").rmdir()
    (work / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")
    return dst, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("out", help="folder given to nextop with --file-server file server=FOLDER")
    ap.add_argument("--book", required=True, help="title of the book or paper (given by the person who supplies the PDF)")
    ap.add_argument("--author", help="author(s), shown as the source")
    ap.add_argument("--year", help="year of publication")
    ap.add_argument("--pages", help="e.g. 1-3,5 (default: all)")
    ap.add_argument("--dpi", type=int, default=170, help="page image resolution sent to the model")
    ap.add_argument("--workers", type=int, default=4, help="pages read at the same time")
    ap.add_argument("--model", help="model name (default: the first model in project.json)")
    args = ap.parse_args()
    dst, warnings = convert(pathlib.Path(args.pdf), pathlib.Path(args.out), args)
    for w in warnings:
        print("[warn]", w)
    try:
        from nextop.file_server.package import check_package
    except ImportError:
        print(f"{dst}: written (nextop not found, package not checked)")
        return 0
    problems = check_package(dst)
    for p in problems:
        print("[error]", p)
    kinds = {}
    for p in json.loads((dst / "document.json").read_text(encoding="utf-8"))["parts"]:
        kinds[p["type"]] = kinds.get(p["type"], 0) + 1
    print(f"{dst}: {'ok' if not problems else 'has problems'} {kinds}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
