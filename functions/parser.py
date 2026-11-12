"""Function block: reads the customer's PDF that Sam passed on and puts the book on the file server "source".

The same code the site used before the run: scripts/pdf_to_package.py (PyMuPDF figures + the vision LLM reads each
page as Markdown) and scripts/package_to_files.py (the book as one .md with page marks, figures as .png, each with a
<file>.json for title, description and source). The files are uploaded to "source" and shared along the parser's
share line. The full text of the text files also goes out as the report "source", so the PD reads the whole book,
not only its map.

A parsed PDF is kept next to it in .<pdf name>-parsed/ (with the PDF's hash and the book title), so running the
order again or resuming it does not read the PDF again.
"""

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

NAME = "parser"
DESC = "Reads the customer's PDF into the book text (.md) and figures and uploads them to the file server source"
FILES_OUT = True                   # bottom point: uploads the book files and shares them
TIMEOUT = 1800                     # a long PDF takes minutes (one vision LLM call per page)
INPUTS = [{"name": "pdf", "description": "Sam's PDF hand-off: {path, title}", "required": True}]
OUTPUTS = [{"name": "source", "schema": {
    "type": "object", "description": "the full text of the customer's text files (.md, .txt), for the PD to read whole",
    "properties": {"documents": {"type": "array", "items": {"type": "object", "properties": {
        "title": {"type": "string"}, "source": {"type": "string"},
        "text": {"type": "string"}}, "required": ["title", "source", "text"]}}},
    "required": ["documents"]}}]
TEXT = (".md", ".txt")
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pdf_input(inputs: dict) -> dict:
    for k, v in inputs.items():
        if (k == "pdf" or k.endswith("/pdf")) and isinstance(v, dict):
            return v
    return {}


def book_title(pdf: pathlib.Path, given: str) -> str:
    """The title the person gave; else the PDF's own title; else the file name (as the site did)."""
    title = str(given or "").strip()
    if not title:
        try:
            import pymupdf
            title = str((pymupdf.open(pdf).metadata or {}).get("title") or "").strip()
        except Exception:  # noqa: BLE001 - the title is optional
            title = ""
    if not title or len(title) < 4 or title.lower().startswith(("microsoft", "untitled")):
        title = re.sub(r"[_-]+", " ", pdf.stem).strip() or "Document"
    return title[:120]


def _run(cmd: list[str], log: pathlib.Path) -> None:
    with open(log, "a", encoding="utf-8") as f:
        f.write("$ " + " ".join(cmd) + "\n")
        f.flush()
        code = subprocess.call(cmd, cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT)
    if code != 0:
        tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:] or ["?"]
        raise RuntimeError(f"{pathlib.Path(cmd[1]).name} failed (exit {code}): {tail[0][:300]}")


def parse(pdf: pathlib.Path, title: str, log: pathlib.Path) -> pathlib.Path:
    """The folder of source files for this PDF (made now, or kept from an earlier parse of the same PDF and title)."""
    cache = pdf.parent / f".{pdf.stem}-parsed"
    stamp = {"sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "book": title}
    files = cache / "files"
    try:
        if json.loads((cache / "stamp.json").read_text(encoding="utf-8")) == stamp and any(files.glob("*.md")):
            return files
    except (OSError, ValueError):
        pass
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    _run([sys.executable, str(ROOT / "scripts" / "pdf_to_package.py"), str(pdf), str(cache / "package"),
          "--book", title], log)
    _run([sys.executable, str(ROOT / "scripts" / "package_to_files.py"), str(cache / "package"), str(files)], log)
    (cache / "stamp.json").write_text(json.dumps(stamp), encoding="utf-8")
    return files


def run(ctx, inputs):
    given = _pdf_input(inputs)
    raw = str(given.get("path") or "").strip()
    if not raw:
        return {"error": "no PDF: the input pdf has no path"}
    pdf = pathlib.Path(raw)
    pdf = (pdf if pdf.is_absolute() else ROOT / pdf).resolve()
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        return {"error": "not a PDF file: " + str(pdf)}
    folder = parse(pdf, book_title(pdf, given.get("title", "")), pathlib.Path(ctx["files_dir"]) / "parse.log")
    uploads = []
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.suffix == ".json":
            continue
        side = p.with_name(p.name + ".json")
        meta = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
        uploads.append({"file_server": "source", "file": str(p.resolve()), "title": meta.get("title") or p.stem,
                        "description": meta.get("description") or f"{p.name} (source file from the client)",
                        "source": meta.get("source") or "client material"})
    if not uploads:
        return {"error": "the parsed PDF gave no files: " + str(folder)}
    documents = [{"title": u["title"], "source": u["source"],
                  "text": pathlib.Path(u["file"]).read_text(encoding="utf-8", errors="replace")}
                 for u in uploads if pathlib.Path(u["file"]).suffix.lower() in TEXT]
    return {"_uploads": uploads, "source": {"documents": documents}}
