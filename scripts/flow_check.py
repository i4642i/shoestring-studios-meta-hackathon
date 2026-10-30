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
   == ["brief", "concept", "request", "source", "structure", "video"],
   "catalog has 6 categories")
ok(all((a.get("color") or "").startswith("#") for a in cat["agents"]),
   "catalog colors")

# ---- page stamp tracks served code (ancestry, not equality) ----
import re as _re
import subprocess as _sp
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import server as _srv  # noqa: E402
_mm = _re.search(r'const PAGE_BUILD = "([0-9a-f]{40})";',
                 open(os.path.join(ROOT, "index.html"),
                      encoding="utf-8").read())
_stamp = _mm.group(1) if _mm else ""
_head = _sp.run(["git", "log", "-1", "--format=%H", "--"]
                + list(_srv.VERSION_PATHS),
                cwd=ROOT, capture_output=True,
                text=True).stdout.strip()
if _stamp and _head and _stamp != _head:
    _anc = _sp.run(["git", "merge-base", "--is-ancestor",
                    _stamp, _head],
                   cwd=ROOT).returncode == 0
else:
    _anc = _stamp == _head
ok(bool(_stamp) and bool(_head) and (_stamp == _head or _anc),
   "page stamp tracks served code")
ok([o["category"] for o in cat["order"]["outputs"]] == ["brief", "source"],
   "order outputs brief+source")

dflt = flow.load_flow("default")
ok([n["id"] for n in dflt["nodes"]]
   == ["order", "sales_sam", "pd_marty", "final"],
   "default flow is order->sam->marty->final")
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
bad["nodes"].append({"id": "explain_cleo"})
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
CONCEPT = {"common_theme": "t", "core_question": "q",
           "viewer_takeaway": "v", "intent_overall": "o"}
STRUCT = {"source_ref": "pc://source/abc123abc123",
          "parts": [{"id": "p1", "heading": "h",
                     "ref": "pc://source/abc123abc123#s1",
                     "covers": "x", "keywords": ["k"]}],
          "intent": {"overall": "o", "links": []}}
PAY = {"sales_sam": ("sales_sam", {"request": REQ}),
       "pd_marty": ("pd_marty", {"concept": CONCEPT,
                                        "structure": STRUCT})}


def stub(agent_dir, run_dir, brief, input_md):
    who = os.path.basename(run_dir)
    producer, cats = PAY[who]
    res = results.make_result(producer, brief["order_id"],
                              brief["flow_run_id"], cats)
    results.save_result(run_dir, res)
    return {"ok": True}


od = os.path.join(tmp, "orders", "o9")
os.makedirs(od)
with open(os.path.join(od, "meta.json"), "w", encoding="utf-8") as f:
    json.dump({"answers": {"audience": "a", "length": "b", "depth": "c",
                           "theme": "d"},
               "files": {"source": "s.pdf",
                         "pc_ref": "pc://source/abc123abc123",
                         "pc_title": "s", "pc_sections": 2,
                         "pc_chars": 24}}, f)
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
ok(mar["status"] == "checked"
   and mar["categories"]["concept"]["version"] == 1
   and mar["categories"]["structure"]["version"] == 2, "marty checked")
ores = results.load_result(os.path.join(rdir, "order", "result.json"))
osrc = ores["categories"]["source"]
ok(osrc["version"] == 2
   and osrc["data"]["ref"] == "pc://source/abc123abc123"
   and osrc["data"]["sections"] == 2
   and os.path.isfile(osrc["data"]["file"]), "order source is v2 pointer")
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
npc = os.path.join(tmp, "orders", "o8")
os.makedirs(npc)
with open(os.path.join(npc, "meta.json"), "w", encoding="utf-8") as f:
    json.dump({"answers": {"audience": "a", "length": "b", "depth": "c",
                           "theme": "d"},
               "files": {"source": "s.pdf"}}, f)
with open(os.path.join(npc, "parsed.md"), "w", encoding="utf-8") as f:
    f.write("# T\n\ntext\n")
flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    out = flow.run_flow(dflt, "o8", stub,
                        runs_root=os.path.join(tmp, "runs"), run_id="rid0")
finally:
    flow.ORDERS_DIR = real_orders
ok(not out.get("ok") and "no PC entry" in out.get("error", ""),
   "order without PC entry fails fast")
from agents._frame import pc as _pc  # noqa: E402
sp = os.path.join(tmp, "runs", "rid9", "explain_cleo")
os.makedirs(sp)
with open(os.path.join(sp, "struct.json"), "w", encoding="utf-8") as f:
    json.dump({"data": {"parts": [{"id": "p1",
                                   "heading": "1.1 Getting started",
                                   "covers": "c", "keywords": []}]},
              "version": 1}, f)
_pc.ROOT_OVERRIDE = tmp
try:
    rr = _pc.ingest_source("o10", "s.pdf", "2026-10-30T07:00:00",
                           "sales_sam",
                           ["1.1 Getting started\nPreloaded text here."],
                           [], [], 0, root=tmp)
    os.makedirs(os.path.join(tmp, "orders", "o10"))
    with open(os.path.join(tmp, "orders", "o10", "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"files": {"pc_ref": rr["ref"]}}, f)
    md = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}},
        [{"sender": "pd_marty", "category": "structure",
          "file": "struct.json"}], os.path.join(tmp, "runs", "rid9"),
        "explain_cleo")
    ok("Start prompt for Cleo" in md and "Preloaded text here." in md,
       "cleo input preloads source sections")
    md2 = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}}, [],
        os.path.join(tmp, "runs", "rid9"), "explain_cleo")
    ok("Start prompt" not in md2, "no structure means no preload")
    md3 = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}},
        [{"sender": "pd_marty", "category": "structure",
          "file": "struct.json"}], os.path.join(tmp, "runs", "rid9"),
        "sales_sam")
    ok("Start prompt" not in md3, "preload only for cleo/rex")
finally:
    _pc.ROOT_OVERRIDE = None


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
