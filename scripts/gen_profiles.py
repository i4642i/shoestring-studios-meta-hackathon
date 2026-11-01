"""Generate agents/<id>/profile.md from agent.json + persona + flow.

Usage: python scripts/gen_profiles.py
Stdlib only. Overwrites profile.md for every employee folder
(except agents/_frame). Re-running must produce no diff.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents._frame import profiles  # noqa: E402

FLOW = os.path.join(ROOT, "data", "flows", "default.json")


def main():
    adir = os.path.join(ROOT, "agents")
    names = {}
    for eid in sorted(os.listdir(adir)):
        if eid.startswith("_"):
            continue
        jp = os.path.join(adir, eid, "agent.json")
        if not os.path.isfile(jp):
            continue
        try:
            with open(jp, encoding="utf-8") as f:
                agent = json.load(f)
        except ValueError:
            continue
        names[eid] = agent.get("name", eid)
    n = 0
    for eid in sorted(names):
        path = os.path.join(adir, eid)
        text = profiles.build_profile(path, FLOW, names)
        with open(os.path.join(path, "profile.md"), "w",
                  encoding="utf-8") as f:
            f.write(text)
        n += 1
    print("wrote %d profile.md files" % n)


if __name__ == "__main__":
    main()
