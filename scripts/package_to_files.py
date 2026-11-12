"""Turns document packages (made by pdf_to_package.py) into files the user gives a run with
`nextop run --file-server source=<folder>`:

  <doc>.md            the text in reading order: headings, paragraphs with page marks [p.N], tables (markdown),
                      equations ($$ LaTeX $$) and a line for each figure naming its file
  <doc>.md.json       title, description and source of the document (sidecar the platform reads)
  <doc>_<fig>.png     each figure, with <doc>_<fig>.png.json (title, description = caption, source = book and page)

usage: python scripts/package_to_files.py <packages folder> <output folder>
"""

import json
import pathlib
import shutil
import sys


def _source(meta: dict, title: str) -> str:
    book = meta.get("book") or title
    who = meta.get("publisher") or ""
    year = meta.get("published") or ""
    tail = ", ".join(x for x in (who, str(year)) if x)
    return f"{book} / {tail}" if tail else book


def convert(pkg: pathlib.Path, out: pathlib.Path) -> list[str]:
    doc = json.loads((pkg / "document.json").read_text(encoding="utf-8"))
    title, meta = doc.get("title") or pkg.name, doc.get("meta") or {}
    source = _source(meta, title)
    lines = [f"# {title}", "", f"출처: {source}", ""]
    heading, page, written = None, None, []
    for p in doc.get("parts", []):
        if p.get("heading") and p["heading"] != heading:
            heading = p["heading"]
            lines += [f"## {heading}", ""]
        mark = f"[p.{p['page']}] " if p.get("page") and p.get("page") != page else ""
        page = p.get("page", page)
        kind = p.get("type", "text")
        if kind == "text":
            lines += [mark + p.get("text", "").strip(), ""]
        elif kind == "table":
            cap = p.get("caption") or p.get("label") or "표"
            lines += [f"{mark}{cap}", "", p.get("text", "").strip(), ""]
        elif kind == "equation":
            lab = f" {p['label']}" if p.get("label") else ""
            lines += [f"{mark}수식{lab}:", "", "$$", p.get("latex", "").strip(), "$$", ""]
        elif kind == "figure":
            src = pkg / p.get("file", "")
            cap = p.get("caption") or p.get("label") or "그림"
            if src.is_file():
                name = f"{pkg.name}_{p.get('id', 'fig')}{src.suffix.lower() or '.png'}"
                shutil.copyfile(src, out / name)
                (out / f"{name}.json").write_text(json.dumps(
                    {"title": p.get("label") or cap[:60], "description": cap,
                     "source": f"{source}, p.{p.get('page', '?')}"}, ensure_ascii=False, indent=2), encoding="utf-8")
                written.append(name)
                lines += [f"{mark}[그림: {cap} — 파일 {name}]", ""]
            else:
                lines += [f"{mark}[그림: {cap}]", ""]
    md = out / f"{pkg.name}.md"
    md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (out / f"{pkg.name}.md.json").write_text(json.dumps(
        {"title": title, "description": f"{title} 본문 ({meta.get('pages', '?')}쪽)", "source": source},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return [md.name] + written


def main():
    src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    pkgs = [d for d in sorted(src.iterdir()) if (d / "document.json").is_file()]
    if not pkgs:
        sys.exit(f"no document packages in {src}")
    for d in pkgs:
        print(d.name, "->", convert(d, out))


if __name__ == "__main__":
    main()
