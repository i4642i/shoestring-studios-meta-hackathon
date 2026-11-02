import json
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")
for ln in open(".env", encoding="utf-8").read().splitlines():
    if "=" in ln and not ln.strip().startswith("#"):
        k, v = ln.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from agents._frame import tools as tmod

rd = tempfile.mkdtemp(prefix="verify_pick_")
ctx = {"producer": "explain_cleo", "order_id": "ord-verify-idx",
       "run_dir": rd, "agent_dir": "agents/explain_cleo"}
out = tmod.pc_pick_theory(
    ctx, {"url": "https://en.wikipedia.org/wiki/Water_wheel",
          "part_id": "p1", "why_important": "index path verification",
          "how_to_use": "background"})
print("pick:", json.dumps(out)[:300])
if out.get("error"):
    raise SystemExit(1)
ref = out["ref"]
doc = ref.split("/")[2]
ef = "storage/_pc/theory/entries/%s/log.jsonl" % doc
t0 = time.time()
while time.time() - t0 < 600:
    try:
        lines = open(ef, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    evs = [json.loads(l).get("ev") for l in lines if l.strip()]
    if "index_done" in evs:
        print("indexed in %.0fs" % (time.time() - t0))
        break
    if any(e in ("failed", "map_failed", "index_failed")
           for e in evs):
        print("worker failed:", lines[-1][:200])
        raise SystemExit(1)
    time.sleep(15)
else:
    print("TIMEOUT waiting for index_done")
    raise SystemExit(1)
mark = json.load(open("storage/_pc/theory/index/jetson/index.json",
                      encoding="utf-8"))
print("in jetson index:", doc in mark.get("entries", []))
print("worker note:", out.get("worker"))
