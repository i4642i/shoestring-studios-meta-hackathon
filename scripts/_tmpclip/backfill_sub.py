import json
import os
import subprocess
import sys
import time

t_all = time.time()
lockf = "D:/00_Agent/shoestring-studios-meta-hackathon/storage/_pc/backfill.lock"
if os.path.isfile(lockf):
    print("another backfill runs, exit")
    raise SystemExit(0)
open(lockf, "w").write(str(os.getpid()))
py = "D:/00_Agent/shoestring-studios-meta-hackathon/.venv/Scripts/python.exe"
root = "D:/00_Agent/shoestring-studios-meta-hackathon"
for ln in open(root + "/.env", encoding="utf-8").read().splitlines():
    if "=" in ln and not ln.strip().startswith("#"):
        k, v = ln.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))
sys.path.insert(0, root)
from agents._frame import pc

for pcname in ("theory", "article"):
    idx = pc.index_dir(pcname, "jetson")
    try:
        have = set(json.load(
            open(idx + "/index.json", encoding="utf-8")).get("entries", []))
    except (OSError, ValueError):
        have = set()
    ed = pc.pc_dir(pcname) + "/entries"
    missing = sorted(d for d in os.listdir(ed)
                     if len(d) == 12 and d not in have)
    print("%s: %d missing" % (pcname, len(missing)), flush=True)
    for n, doc in enumerate(missing, 1):
        try:
            have_now = set(json.load(
                open(idx + "/index.json",
                     encoding="utf-8")).get("entries", []))
        except (OSError, ValueError):
            have_now = set()
        if doc in have_now:
            print("%s %d/%d %s SKIP already indexed"
                  % (pcname, n, len(missing), doc), flush=True)
            continue
        t0 = time.time()
        try:
            pr = subprocess.run(
                [py, "scripts/pc_worker.py", doc, "index", pcname],
                cwd=root, capture_output=True, text=True, timeout=1800)
            tail = (pr.stdout or "").strip().splitlines()[-1:]
            print("%s %d/%d %s exit=%d %.0fs %s"
                  % (pcname, n, len(missing), doc, pr.returncode,
                     time.time() - t0, tail[0][:80] if tail else ""),
                  flush=True)
        except Exception as exc:
            print("%s %d/%d %s FAIL %s: %s"
                  % (pcname, n, len(missing), doc,
                     type(exc).__name__, exc), flush=True)
print("backfill done in %.0fs" % (time.time() - t_all), flush=True)
