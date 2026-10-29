"""Flow checks for agents/_frame/flow.py (Step 2). Stdlib only.

Run: python scripts/flow_check.py. Writes only to gitignored scratch
(directories are patched to temp locations; nothing lands in runs/).
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
from agents._frame import flow, results

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def msgs(errs):
    return " | ".join(e["message"] for e in errs)


# ---- catalog / load ----
cat = flow.load_catalog()
ok(len(cat["agents"]) >= 9, "catalog lists 9 agents")
drafts = sorted(a["id"] for a in cat["agents"] if a.get("draft"))
ok(drafts == ["board_penn", "board_vera", "case_rex", "explain_cleo",
              "plan_ash", "voice_iris", "voice_wren"], "7 drafts flagged")
ok("sales_sam" in [a["id"] for a in cat["agents"] if a.get("flow")],
   "workers declare flow I/O")
ok(sorted(c["name"] for c in cat["categories"])
   == ["brief", "request", "source", "structure", "video"],
   "catalog has 5 categories")
ok([o["category"] for o in cat["order"]["outputs"]] == ["brief", "source"],
   "order outputs brief+source")

dflt = flow.load_flow("default")
ok([n["id"] for n in dflt["nodes"]][:4]
   == ["order", "sales_sam", "pd_marty", "final"]
   and len(dflt["nodes"]) == 11, "default flow +7 draft nodes")
try:
    flow.load_flow("../x")
    ok(False, "bad flow id raises")
except ValueError:
    ok(True, "bad flow id raises")

# ---- validate ----
ok(flow.validate_flow(dflt) == [], "default flow validates")
bad = json.loads(json.dumps(dflt))
bad["lines"].append({"id": "lx", "from": "order", "to": "sales_sam",
                      "categories": ["nope"]})
errs = flow.validate_flow(bad)
ok(any("unknown category" in e["message"] for e in errs)
   and errs[0].get("line") == "lx", "unknown category + line id")
bad = json.loads(json.dumps(dflt))
bad["lines"].append({"id": "ld", "from": "order", "to": "sales_sam",
                      "categories": ["brief"]})
ok(any("duplicate line" in e["message"]
       for e in flow.validate_flow(bad)), "dup pair kept forbidden")
bad = {"nodes": [{"id": "order"}, {"id": "sales_sam"}, {"id": "final"}],
       "lines": [{"id": "l1", "from": "order", "to": "final",
                  "categories": ["brief"]}],
       "positions": {}}
errs = flow.validate_flow(bad)
ok(any("no incoming line" in e["message"] for e in errs)
   and any(e.get("node") == "sales_sam" for e in errs),
   "agent without input + node id")
bad = json.loads(json.dumps(dflt))
for ln in bad["lines"]:
    if ln["id"] == "l1":
        ln["categories"] = ["source"]
ok(any("misses required input 'brief'" in e["message"]
       for e in flow.validate_flow(bad)), "missing required input")
cyc = {"nodes": [{"id": "order"}, {"id": "sales_sam"},
                 {"id": "pd_marty"}, {"id": "final"}],
       "lines": [{"id": "l1", "from": "order", "to": "sales_sam",
                  "categories": "*"},
                 {"id": "l2", "from": "sales_sam", "to": "pd_marty",
                  "categories": ["request"]},
                 {"id": "l3", "from": "pd_marty", "to": "sales_sam",
                  "categories": ["structure"]},
                 {"id": "l4", "from": "pd_marty", "to": "final",
                  "categories": ["structure"]}],
       "positions": {}}
ok(any(e["message"].startswith("cycle:")
       for e in flow.validate_flow(cyc)), "cycle caught")
bad = json.loads(json.dumps(dflt))
bad["lines"].append({"id": "ld", "from": "order", "to": "explain_cleo",
                      "categories": ["brief"]})
errs = flow.validate_flow(bad)
ok(any("is a draft" in e["message"] for e in errs)
   and any(e.get("node") == "explain_cleo" for e in errs),
   "connected draft rejected")
multi = {"nodes": [{"id": "order"}, {"id": "sales_sam"},
                   {"id": "pd_marty"}, {"id": "final"}],
         "lines": [{"id": "l1", "from": "order", "to": "sales_sam",
                    "categories": "*"},
                   {"id": "l2", "from": "sales_sam", "to": "pd_marty",
                    "categories": ["request"]},
                   {"id": "l3", "from": "order", "to": "pd_marty",
                    "categories": ["source"]},
                   {"id": "l4", "from": "pd_marty", "to": "final",
                    "categories": ["structure"]}],
         "positions": {}}
ok(flow.validate_flow(multi) == [], "multi-sender intake validates")
seq = flow.topo_order(dflt)
ok(seq.index("order") < seq.index("sales_sam")
   < seq.index("pd_marty") < seq.index("final") == len(seq) - 1,
   "topo order respects lines, final last")
ok(flow.new_run_id().startswith("flow-"), "run id shape")

# ---- transfer unit ----
tmp = tempfile.mkdtemp(prefix="flowcheck_")
rd = os.path.join(tmp, "r1")
os.makedirs(os.path.join(rd, "order"))
oreq = results.make_result("order", "o1", "r1",
                           {"brief": {"order_id": "o1", "answers": {
                               "audience": "a", "length": "b", "depth": "c",
                               "theme": "d"}, "source_file": "s.pdf"}})
results.save_result(os.path.join(rd, "order"), oreq)
got, nbytes, errs = flow._transfer(rd, "order", "x", ["brief"], None)
ok(errs == [] and len(got) == 1 and got[0]["sender"] == "order"
   and got[0]["version"] == 1 and nbytes > 0, "transfer labels sender")
got, _, errs = flow._transfer(rd, "order", "x", ["brief"],
                              [{"category": "brief", "accept": [2]}])
ok(errs and "not in accepted" in errs[0], "accept list enforced")
got, _, errs = flow._transfer(rd, "order", "x", ["request"], None)
ok(errs and "has no category" in errs[0], "missing category aborts")

# ---- stubbed end-to-end ----
REQ = {"order_id": "o9",
       "client_answers": {"audience": "a", "length": "b", "depth": "c",
                         "theme": "d", "source": "e"},
       "source_summary": "s", "production_notes": ["n"],
       "open_questions": []}
STRUCT = {"source": {"book": "b", "chapter": "c"}, "common_theme": "t",
          "parts": [{"id": "p1", "heading": "h", "covers": "x",
                     "keywords": ["k"]}],
          "intent": {"overall": "o", "links": []}}
PAY = {"sales_sam": ("sales_sam", "request", REQ),
       "pd_marty": ("pd_marty", "structure", STRUCT)}


def stub(agent_dir, run_dir, brief, input_md):
    who = os.path.basename(run_dir)
    producer, cat, data = PAY[who]
    res = results.make_result(producer, brief["order_id"],
                              brief["flow_run_id"], {cat: data})
    results.save_result(run_dir, res)
    return {"ok": True}


od = os.path.join(tmp, "orders", "o9")
os.makedirs(od)
with open(os.path.join(od, "meta.json"), "w", encoding="utf-8") as f:
    json.dump({"answers": {"audience": "a", "length": "b", "depth": "c",
                           "theme": "d"},
               "files": {"source": "s.pdf"}}, f)
with open(os.path.join(od, "parsed.md"), "w", encoding="utf-8") as f:
    f.write("# T\n\n## 1.1 A\n\ntext\n")
real_orders = flow.ORDERS_DIR
flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    out = flow.run_flow(dflt, "o9", stub, runs_root=os.path.join(tmp, "runs"),
                        run_id="rid1", flow_id="default")
finally:
    flow.ORDERS_DIR = real_orders
ok(out.get("ok"), "stubbed e2e run ok")
rdir = os.path.join(tmp, "runs", "rid1")
st = json.load(open(os.path.join(rdir, "STATUS.json"), encoding="utf-8"))
ok(st["state"] == "done" and st["flow_id"] == "default"
   and st["order_id"] == "o9", "STATUS done with ids")
sam = results.load_result(os.path.join(rdir, "sales_sam", "result.json"))
ok(sam["status"] == "checked"
   and sam["categories"]["request"]["version"] == 1, "sam checked")
mar = results.load_result(os.path.join(rdir, "pd_marty", "result.json"))
ok(mar["status"] == "checked", "marty checked")
fin = results.load_result(os.path.join(rdir, "final", "result.json"))
ok(fin["producer"] == "postprocess" and fin["status"] == "checked"
   and fin["categories"] == {}, "final postprocess result")
ok(os.path.isfile(os.path.join(rdir, "sales_sam", "report.md"))
   and os.path.isfile(os.path.join(rdir, "pd_marty", "INPUTS.json")),
   "reports + manifests written")
mani = json.load(open(os.path.join(rdir, "pd_marty", "INPUTS.json"),
                      encoding="utf-8"))
ok(mani["received"] == [{"sender": "sales_sam", "category": "request",
                         "version": 1,
                         "file": "received.sales_sam.request.json"}],
   "manifest sender labels")
evs = [json.loads(ln) for ln in
       open(os.path.join(rdir, "events.jsonl"), encoding="utf-8")]
kinds = [e["ev"] for e in evs]
ok(kinds[0] == "flow_start" and kinds[-1] == "flow_done"
   and "order_ready" in kinds and kinds.count("line") == 3
   and "final_ready" in kinds, "event trail complete")
line1 = next(e for e in evs if e.get("line") == "l1")
ok(sorted(line1["categories"]) == ["brief", "source"]
   and line1["bytes"] > 0, "line log shows sent categories")

flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    out = flow.run_flow(dflt, "missing", stub,
                        runs_root=os.path.join(tmp, "runs"), run_id="rid2")
finally:
    flow.ORDERS_DIR = real_orders
ok(not out.get("ok") and "no such order" in out.get("error", ""),
   "missing order fails clean")


def boom(agent_dir, run_dir, brief, input_md):
    return {"ok": False, "error": "kaput"}


flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    out = flow.run_flow(dflt, "o9", boom,
                        runs_root=os.path.join(tmp, "runs"), run_id="rid3")
finally:
    flow.ORDERS_DIR = real_orders
ok(not out.get("ok") and "kaput" in out.get("error", ""),
   "agent failure aborts")
st3 = json.load(open(os.path.join(tmp, "runs", "rid3", "STATUS.json"),
                     encoding="utf-8"))
ok(st3["state"] == "failed", "STATUS failed recorded")
shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("%d FAILURES" % fails)
    sys.exit(1)
print("ALL PASS")
