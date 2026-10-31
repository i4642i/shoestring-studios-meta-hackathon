"""Print the third-party package table (pins + installed licenses).

Reads requirements.txt pins and the installed importlib.metadata /
LICENSE files, and prints a markdown table so README.md and
data/third_party.json stay in sync. Heuristics only: when this
script and the hand-verified README disagree, README wins.

Usage: python scripts/list_licenses.py
Stdlib only, read-only.
"""
import glob
import os
import re
import sys

try:
    from importlib.metadata import distribution, PackageNotFoundError
except ImportError:  # pragma: no cover - py3.10+ always has it
    print("need Python 3.10+")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PACKAGES = [
    ("pdfplumber", "direct import: PDF text+image extraction"),
    ("lightrag-hku", "direct import: knowledge-graph index"),
    ("sentence-transformers", "direct import: local embeddings"),
    ("numpy", "direct import: embedding math"),
    ("Pillow", "direct import: figure thumbnails"),
    ("torch", "via sentence-transformers: CPU tensors"),
    ("transformers", "via sentence-transformers: model loading"),
    ("pdfminer.six", "via pdfplumber: PDF parsing"),
    ("networkx", "via lightrag-hku: graph store"),
    ("nano-vectordb", "via lightrag-hku: vector store"),
    ("tiktoken", "via lightrag-hku: token counting"),
    ("scikit-learn", "via sentence-transformers"),
    ("huggingface_hub", "via sentence-transformers/transformers"),
    ("python-dotenv", "pinned but not imported (own .env loader)"),
]


def pins():
    out = {}
    with open(os.path.join(ROOT, "requirements.txt"),
              encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            m = re.match(r"([A-Za-z0-9_.\-]+)==([^ ;]+)", line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    return out


def from_files(dist):
    import sysconfig
    base = sysconfig.get_paths()["purelib"]
    norm = re.sub(r"[-_.]+", "_", dist)
    for path in sorted(glob.glob(os.path.join(
            base, norm + "-*.dist-info",
            "licenses", "*")) + glob.glob(os.path.join(
            base, norm + "-*.dist-info", "LICENSE*"))):
        if os.path.isdir(path) or "third_party" in path:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read(4000)
        except OSError:
            continue
        low = text.lower()
        if "mit-cmu" in low:
            return "MIT-CMU"
        if "apache license" in low:
            return "Apache-2.0"
        if "redistribution and use in source and binary" in low:
            if "neither the name" in low:
                return "BSD-3-Clause"
            return "BSD (see package)"
        if "mit license" in low or (
                "permission is hereby granted" in low
                and "warrant" in low):
            return "MIT"
        if "3-clause bsd" in low:
            return "BSD-3-Clause"
    return ""


def _short(name):
    return {"mit license": "MIT",
            "apache 2.0 license": "Apache-2.0",
            "apache software license": "Apache-2.0",
            "bsd-3-clause": "BSD-3-Clause"}.get(name.lower(), name)


def license_of(name):
    try:
        meta = distribution(name).metadata
    except PackageNotFoundError:
        return "not installed"
    lic = (meta.get("License") or "").strip().splitlines()
    lic = lic[0].strip() if lic and lic[0].strip() else ""
    if lic and lic.lower() not in ("unknown",):
        return _short(lic)
    for clf in meta.get_all("Classifier") or []:
        if clf.startswith("License :: OSI Approved :: "):
            return _short(clf.split("::")[-1].strip())
    found = from_files(name)
    return found or "see package"


def main():
    pin = pins()
    print("| Package | Pinned | Installed | License | Used for |")
    print("|---|---|---|---|---|")
    for name, use in PACKAGES:
        try:
            inst = distribution(name).version
        except PackageNotFoundError:
            inst = "—"
        print("| %s | %s | %s | %s | %s |"
              % (name, pin.get(name.lower(), "(unpinned)"), inst,
                 license_of(name), use))


if __name__ == "__main__":
    main()
