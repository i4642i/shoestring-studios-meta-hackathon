"""Build Marty's run input from a Source PC entry (headings exact).

Usage: python scripts/marty_input.py <pc://source/<id>> --out <dir>
Writes input.md (cleaned content sections + map notes appendix) and
brief.json. Non-content sections are excluded; part headings always
come from the current entry, so write_structure validation matches.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import pc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    text = pc.marty_input_text(a.ref)
    entry = pc.load_entry_by_ref(a.ref)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "input.md"), "w",
              encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(a.out, "brief.json"), "w",
              encoding="utf-8") as f:
        json.dump({"order_id": entry.get("order_id", "adhoc"),
                   "entry_ref": entry["ref"]}, f)
    print("wrote %s (%d chars)" % (
        a.out, len(text)))


if __name__ == "__main__":
    main()
