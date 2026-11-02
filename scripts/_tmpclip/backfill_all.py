import json
import os
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

# Same .env loading as scripts/server.py (setdefault, never printed).
for ln in open(".env", encoding="utf-8").read().splitlines():
    if "=" in ln and not ln.strip().startswith("#"):
        k, v = ln.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from agents._frame import pc
import pc_worker

t_all = time.time()
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
        t0 = time.time()
        try:
            pc_worker.main(doc, "index", pcname)
            print("%s %d/%d %s OK %.1fs"
                  % (pcname, n, len(missing), doc, time.time() - t0),
                  flush=True)
        except Exception as exc:
            print("%s %d/%d %s FAIL %s: %s"
                  % (pcname, n, len(missing), doc,
                     type(exc).__name__, exc), flush=True)
print("backfill done in %.0fs" % (time.time() - t_all), flush=True)
