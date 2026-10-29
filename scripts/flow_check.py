"""Flow engine checks: registry, envelopes, validation, full stubbed runs.

Run: python scripts/flow_check.py (no model calls, offline).
"""
import copy
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents._frame import flow

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


# 1. Registry + schema subset.
reg = flow.registry()
ok(set(reg) == {"brief", "source", "request", "structure"}, "registry has 4")
ok(all(reg[c]["version"] == 1 for c in reg), "all v1")
S = reg["request"]["schema"]
good_req = {"order_id": "o1",
            "client_answers": {"audience": "a", "length": "b", "depth": "c",
                               "theme": "d", "source": "e"},
            "source_summary": "s", "production_notes": ["n"],
            "open_questions": []}
ok(flow.validate_schema(good_req, S) == [], "valid request passes")
bad = dict(good_req)
del bad["production_notes"]
ok(any("production_notes" in e
       for e in flow.validate_schema(bad, S)), "missing key caught")
bad2 = dict(good_req, production_notes="nope")
ok(any("must be an array" in e
       for e in flow.validate_schema(bad2, S)), "bad type caught")
bad3 = copy.deepcopy(good_req)
bad3["client_answers"] = {"audience": "a"}
ok(any("missing" in e for e in flow.validate_schema(bad3, S)),
   "nested required caught")
ok(flow.validate_schema("x", {"type": "integer"}) != [], "int rejects str")
ok(flow.validate_schema(True, {"type": "integer"}) != [], "int rejects bool")
ok(flow.validate_schema({"a": 1}, {"type": "object",
                                   "additionalProperties": False})
   != [], "closed object rejects unknown key")

# 2. Envelopes.
env = flow.make_envelope("request", "sales_sam", "o1", "r1", good_req)
ok(env["version"] == 1 and env["status"] == "unverified", "envelope wraps")
ok(flow.check_envelope(env) == [], "envelope validates")
env_bad = dict(env, version=99)
ok(any("version" in e for e in flow.check_envelope(env_bad)),
   "version mismatch refuses")
env_bad2 = dict(env, status="maybe")
ok(any("status" in e for e in flow.check_envelope(env_bad2)),
   "bad status refuses")
try:
    flow.make_envelope("nope", "x", "o", "r", {})
    ok(False, "unknown category wraps")
except RuntimeError:
    ok(True, "unknown category refuses")

# 3. Flow validation.
default = flow.load_flow("default")
ok(flow.validate_flow(default) == [], "default flow valid: %s"
   % flow.validate_flow(default))
ok(flow.topo_order(default) == ["order", "sales_sam", "pd_marty", "final"],
   "topo order")


def broken(mutate):
    f = copy.deepcopy(default)
    mutate(f)
    return [e["message"] for e in flow.validate_flow(f)]


ok(any("unknown category" in m for m in broken(
    lambda f: f["lines"][1].update(categories=["nope"]))),
    "unknown category caught")
ok(any("no input" in m for m in broken(
    lambda f: f["lines"].pop(1))), "agent without input caught")
ok(any("missing required input" in m for m in broken(
    lambda f: f["lines"].pop(1))), "missing required input caught")
ok(any("cycle" in m for m in broken(
    lambda f: f["lines"].append({"id": "l9", "from": "pd_marty",
                                     "to": "sales_sam",
                                     "categories": "*"}))),
    "cycle caught")
ok(any("duplicate line" in m for m in broken(
    lambda f: f["lines"].append({"id": "l9", "from": "order",
                                     "to": "sales_sam",
                                     "categories": "*"}))),
    "duplicate line caught")
ok(any("unknown agent" in m for m in broken(
    lambda f: f["nodes"].append({"id": "ghost"}))), "unknown agent caught")
ok(any("non-empty list" in m for m in broken(
    lambda f: f["lines"][1].update(categories=[]))),
    "empty selection caught")
ok(any("Order node takes no input" in m for m in broken(
    lambda f: f["lines"].append({"id": "l9", "from": "sales_sam",
                                     "to": "order",
                                     "categories": "*"}))),
    "order input caught")

# 4. Full stubbed run + failure path.
ODIR = os.path.join(ROOT, "orders", "_flowtest1")
os.makedirs(ODIR, exist_ok=True)
with open(os.path.join(ODIR, "meta.json"), "w", encoding="utf-8") as f:
    json.dump({"id": "_flowtest1",
               "answers": {"audience": "a", "length": "b", "depth": "c",
                           "theme": "d"},
               "files": {"source": "s.pdf", "parsed": "parsed.md"}}, f)
with open(os.path.join(ODIR, "parsed.md"), "w", encoding="utf-8") as f:
    f.write("# T\n\n## 1.1 A\n\ntext\n")


def stub(agent_dir, run_dir, brief, input_md):
    who = os.path.basename(run_dir)
    with open(input_md, encoding="utf-8") as f:
        text = f.read()
    assert brief["flow_run_id"], "brief carries run id"
    if who == "sales_sam":
        assert "From order / brief" in text and "From order / source" in text
        with open(os.path.join(run_dir, "request.json"), "w",
                  encoding="utf-8") as f:
            json.dump(good_req, f)
        with open(os.path.join(run_dir, "request.md"), "w",
                  encoding="utf-8") as f:
            f.write("# req\n")
    elif who == "pd_marty":
        assert "From sales_sam / request" in text
        with open(os.path.join(run_dir, "structure.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"source": {"book": "b", "chapter": "c"},
                       "common_theme": "t",
                       "parts": [{"id": "p1", "heading": "h",
                                  "covers": "c", "keywords": ["k"]}],
                       "intent": {"overall": "o", "links": []}}, f)
    else:
        raise AssertionError("unexpected agent " + who)
    return {"ok": True}


rid = flow.run_flow(default, "_flowtest1", stub, run_id="_flowtest_run1",
                    flow_id="default")
rdir = os.path.join(ROOT, "runs", rid)
ok(os.path.isfile(os.path.join(rdir, "order", "brief.json")),
   "order brief enveloped")
ok(os.path.isfile(os.path.join(rdir, "sales_sam", "request.json")),
   "sam request enveloped")
ok(os.path.isfile(os.path.join(rdir, "pd_marty", "structure.json")),
   "marty structure enveloped")
with open(os.path.join(rdir, "sales_sam", "request.json"),
          encoding="utf-8") as f:
    ok(json.load(f)["status"] == "checked", "handoff flips to checked")
with open(os.path.join(rdir, "sales_sam", "INPUTS.json"),
          encoding="utf-8") as f:
    man = json.load(f)
ok(len(man["inputs"]) == 2, "manifest lists 2 inputs")
with open(os.path.join(rdir, "events.jsonl"), encoding="utf-8") as f:
    evs = [json.loads(ln) for ln in f]
kinds = [e["ev"] for e in evs]
ok("flow_done" in kinds and kinds.count("line") == 3, "3 line events + done")
ok(os.path.isfile(os.path.join(rdir, "final", "summary.json")),
   "final collected")
with open(os.path.join(rdir, "STATUS.json"), encoding="utf-8") as f:
    ok(json.load(f)["state"] == "done", "STATUS done")


def stub_bad(agent_dir, run_dir, brief, input_md):
    with open(os.path.join(run_dir, "request.json"), "w",
              encoding="utf-8") as f:
        json.dump({"order_id": "x"}, f)
    return {"ok": True}


try:
    flow.run_flow(default, "_flowtest1", stub_bad,
                  run_id="_flowtest_run2", flow_id="default")
    ok(False, "bad payload runs")
except RuntimeError as e:
    ok("invalid" in str(e) and "request" in str(e),
       "bad payload aborts with reason")
rdir2 = os.path.join(ROOT, "runs", "_flowtest_run2")
with open(os.path.join(rdir2, "STATUS.json"), encoding="utf-8") as f:
    ok(json.load(f)["state"] == "error", "STATUS error recorded")
shutil.rmtree(ODIR, ignore_errors=True)
shutil.rmtree(os.path.join(ROOT, "runs", "_flowtest_run1"),
              ignore_errors=True)
shutil.rmtree(rdir2, ignore_errors=True)

# 5. Agents validate with flow sections.
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import validate_agent
ok(validate_agent.validate("agents/sales_sam") == [], "sam validates")
ok(validate_agent.validate("agents/pd_marty") == [], "marty validates")

print("FAILURES: %d" % fails if fails else "ALL PASS")
sys.exit(1 if fails else 0)
