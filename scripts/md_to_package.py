"""Turn a markdown file (what a PDF parser gives) into a document package for the original file server "source".

  python scripts/md_to_package.py docs/samples/battery_ko.md inputs/source

Writes inputs/source/<name>/document.json (+ figures/), the shape nextop's original file servers take:
  headings start a section; paragraphs become "text" parts, markdown tables "table" parts,
  display math ($$...$$) "equation" parts, images ![caption](file) "figure" parts.
Then run:  nextop run --file-server source=inputs/source --input input.json
The real PDF parser comes later; it only has to write the same markdown (or the package directly).
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

IMAGE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")


def blocks(text: str) -> list[list[str]]:
    out, cur = [], []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            if cur:
                out.append(cur)
            cur = []
            continue
        if line.startswith("#") and cur:
            out.append(cur)
            cur = []
        cur.append(line)
        if line.startswith("#"):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def convert(md_path: pathlib.Path, out_root: pathlib.Path) -> pathlib.Path:
    text = md_path.read_text(encoding="utf-8")
    title, heading, parts = md_path.stem, "", []
    counters = {"text": 0, "table": 0, "figure": 0, "equation": 0}
    prefix = {"text": "p", "table": "t", "figure": "f", "equation": "e"}
    dst = out_root / md_path.stem
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "figures").mkdir(parents=True)

    def add(kind: str, **fields):
        counters[kind] += 1
        part = {"id": f"{prefix[kind]}{counters[kind]}", "type": kind, "page": 1}
        if heading and kind == "text":
            part["heading"] = heading
        part.update(fields)
        parts.append(part)

    for b in blocks(text):
        first = b[0]
        if first.startswith("# ") and title == md_path.stem:
            title = first[2:].strip()
        elif first.startswith("#"):
            heading = first.lstrip("#").strip()
        elif all(x.strip().startswith("|") for x in b):
            add("table", text="\n".join(b))
        elif first.strip().startswith("$$"):
            add("equation", latex="\n".join(b).strip().strip("$").strip())
        elif IMAGE.match(first):
            cap, src = IMAGE.match(first).groups()
            img = (md_path.parent / src).resolve()
            name = f"figures/f{counters['figure'] + 1}{img.suffix or '.png'}"
            shutil.copy2(img, dst / name)
            add("figure", caption=cap, file=name)
        else:
            add("text", text="\n".join(b))
    doc = {"title": title, "source": md_path.name, "meta": {"pages": 1}, "parts": parts}
    (dst / "document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if not any((dst / "figures").iterdir()):
        (dst / "figures").rmdir()
    return dst


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    dst = convert(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
    from nextop.file_server.package import check_package
    problems = check_package(dst)
    for p in problems:
        print("[error]", p)
    print(f"{dst}: {'ok' if not problems else 'has problems'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
