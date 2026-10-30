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
    entry = pc.load_entry_by_ref(a.ref)
    try:
        mp = pc.load_map_by_ref(a.ref)
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
            out += ["## %s %s" % (s["n"], s.get("heading", "")), ""]
        for p in entry["paragraphs"][s["start"]:s["start"] + s["count"]]:
            out += [p["text"], ""]
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "input.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(out))
    with open(os.path.join(a.out, "brief.json"), "w",
              encoding="utf-8") as f:
        json.dump({"order_id": entry.get("order_id", "adhoc"),
                   "entry_ref": entry["ref"]}, f)
    print("wrote %s (%d chars)" % (
        a.out, sum(len(x) for x in out)))


if __name__ == "__main__":
    main()
