"""Office live-state checks, J10 (no sockets, no model calls).

Builds fixture runs under tempfile and asserts the office endpoint
(reads real run files only): waiting roam, working action phrases
from real tool events, per-part clone bubbles, done/approved/error/
paused states, and memory states (item-9 contract). Also covers the
runner tool_detail helper.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import flow  # noqa: E402
from agents._frame import office  # noqa: E402
from agents._frame import runner  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ---- tool_detail: short honest hints, nothing secret ----
ok(runner.tool_detail("pc_read_source",
                      {"ref": "pc://source/abc123#s3.2"})
   == "\u00a73.2", "ref section becomes _3.2")
ok(runner.tool_detail("open_ref",
                      {"ref": "pc://article/abc#p4"}) == "#p4",
   "bare fragment kept")
ok(runner.tool_detail("pc_search_images", {"query": "solar"})
   == "solar", "query passes through")
ok(runner.tool_detail("render_slide", {"cut_id": "s1c2"})
   == "s1c2", "cut id passes through")
ok(runner.tool_detail("pc_read_source", {}) == "",
   "no args gives no detail")
ok(runner.tool_detail("x", {"file": "a/b/c.png"}) == "c.png",
   "file becomes its basename")
ok(len(runner.tool_detail("t", {"query": "z" * 100})) <= 60,
   "long detail truncated")

# ---- action phrases ----
ok(office.action_phrase("pc_read_source", "\u00a73.2")
   == "Reading source \u00a73.2", "phrase: reading section")
ok(office.action_phrase("pc_search_images", "solar panels")
   == "Searching photos: solar panels", "phrase: photo query")
ok(office.action_phrase("pc_generate_image", "", 2, 6)
   == "Generating image 2/6", "phrase: image count/quota")
ok(office.action_phrase("write_narration", "")
   == "Writing report\u2026", "phrase: writer")
ok(office.action_phrase("render_slide", "s1c2")
   == "Rendering cut 1-2", "phrase: cut id prettified")
ok(office.action_phrase("vera_view_image", "fig1.png")
   == "Viewing fig1.png", "phrase: viewing")
ok(office.action_phrase("pc_list_entries", "")
   == "List entries", "phrase: unknown tool humanized")


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def wevs(path, evs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ev in evs:
            f.write(json.dumps(ev) + "\n")


def card(out, base):
    for e in out.get("employees", []):
        if e["id"] == base:
            return e
    return {}


def mkflow(r):
    os.makedirs(r, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "data", "flows", "default.json"),
                os.path.join(r, "flow.json"))


tmp = tempfile.mkdtemp(prefix="officecheck_")
runs = os.path.join(tmp, "runs")

# ---- fixture 1: active run, marty working, sam done, rest waiting ----
r1 = os.path.join(runs, "run1")
mkflow(r1)
wjson(os.path.join(r1, "STATUS.json"),
      {"run_id": "run1", "flow_id": "default", "order_id": "o1",
       "state": "running", "current": "pd_marty",
       "completed": ["sales_sam"], "approved": [], "error": ""})
wjson(os.path.join(r1, "sales_sam", "result.json"),
      {"producer": "sales_sam", "categories": {}})
wevs(os.path.join(r1, "events.jsonl"),
     [{"ev": "agent_start", "agent": "sales_sam"},
      {"ev": "agent_done", "agent": "sales_sam"},
      {"ev": "agent_start", "agent": "pd_marty"}])
wevs(os.path.join(r1, "pd_marty", "events.jsonl"),
     [{"ev": "run_start", "agent": "pd_marty"},
      {"ev": "tool", "step": 1, "tool": "pc_read_source",
        "ok": True, "detail": "\u00a73.2"}])
out = office.build_office("run1", runs_root=runs)
ok(out.get("ok") and out.get("state") == "running",
   "run1 builds while running")
m = card(out, "pd_marty")
ok(m.get("stage") == "working"
   and m.get("bubble") == "Reading source \u00a73.2"
   and m.get("seated") is True and m.get("red") is False,
   "marty works seated with the real action (%s)" % m)
s = card(out, "sales_sam")
ok(s.get("stage") == "done_wait"
   and s.get("bubble") == "Report done \u2014 waiting for approval"
   and s.get("seated") is True, "sam done-waiting, seated")
c = card(out, "explain_cleo")
ok(c.get("stage") == "waiting" and c.get("bubble") == ""
   and c.get("seated") is False, "cleo roams while waiting")
p = card(out, "photo_pia")
ok(p.get("stage") == "waiting",
   "video node waits before the split")

# ---- fixture 2: clones mid-run, mixed parts; gene counting ----
r2 = os.path.join(runs, "run2")
mkflow(r2)
wjson(os.path.join(r2, "STATUS.json"),
      {"run_id": "run2", "flow_id": "default", "order_id": "o1",
       "state": "running", "current": "photo_pia@p1",
       "completed": ["sales_sam", "pd_marty"], "approved": [],
       "error": ""})
wjson(os.path.join(r2, "part_split", "split.json"),
      {"parts": [{"no": 1, "quota": 4}, {"no": 2, "quota": 2}]})
wevs(os.path.join(r2, "events.jsonl"),
     [{"ev": "agent_start", "agent": "photo_pia@p1"}])
wevs(os.path.join(r2, "photo_pia", "p1", "events.jsonl"),
     [{"ev": "tool", "step": 1, "tool": "pc_search_images",
       "ok": True, "detail": "solar panels"}])
wjson(os.path.join(r2, "photo_pia", "p2", "result.json"),
      {"producer": "photo_pia@p2", "categories": {}})
out = office.build_office("run2", runs_root=runs)
pia = card(out, "photo_pia")
ok(pia.get("stage") == "working" and pia.get("seated") is True,
   "pia works while a part works")
ok(pia.get("bubble") == "P1 Searching photos: solar panels"
   " \u00b7 P2 Report done", "pia bubble lists parts (%s)"
   % pia.get("bubble"))
ok([p["stage"] for p in pia.get("parts", [])]
   == ["working", "done_wait"], "pia part stages")

# ---- fixture 3: paused run, next-up + last-done get pause ----
r3 = os.path.join(runs, "run3")
mkflow(r3)
wjson(os.path.join(r3, "STATUS.json"),
      {"run_id": "run3", "flow_id": "default", "order_id": "o1",
       "state": "paused", "current": "",
       "completed": ["sales_sam", "pd_marty"], "approved": [],
       "error": ""})
wjson(os.path.join(r3, "sales_sam", "result.json"),
      {"producer": "sales_sam", "categories": {}})
wjson(os.path.join(r3, "pd_marty", "result.json"),
      {"producer": "pd_marty", "categories": {}})
out = office.build_office("run3", runs_root=runs)
ok(card(out, "pd_marty").get("bubble") == "\u23f8 Paused",
   "paused: last finished shows pause")
ok(card(out, "case_rex").get("bubble") == "\u23f8 Paused",
   "paused: next up shows pause")
ok(card(out, "sales_sam").get("stage") == "done_wait",
   "paused: older work stays done-waiting")

# ---- fixture 4: error run, gene approved, wren memory ----
r4 = os.path.join(runs, "run4")
mkflow(r4)
wjson(os.path.join(r4, "STATUS.json"),
      {"run_id": "run4", "flow_id": "default", "order_id": "o1",
       "state": "failed",
       "error": "case_rex failed: model API error: empty reply",
       "current": "", "completed": ["sales_sam", "pd_marty"],
       "approved": ["image_gene"]})
wjson(os.path.join(r4, "sales_sam", "result.json"),
      {"producer": "sales_sam", "categories": {}})
wjson(os.path.join(r4, "image_gene", "result.json"),
      {"producer": "image_gene", "categories": {}})
wevs(os.path.join(r4, "events.jsonl"),
     [{"ev": "agent_start", "agent": "sales_sam"},
      {"ev": "agent_done", "agent": "sales_sam"},
      {"ev": "agent_start", "agent": "pd_marty"},
      {"ev": "agent_done", "agent": "pd_marty"},
      {"ev": "agent_start", "agent": "case_rex"}])
wjson(os.path.join(r4, "memory", "voice_wren", "STATUS.json"),
      {"state": "ready"})
wjson(os.path.join(r4, "memory", "plan_ash", "STATUS.json"),
      {"state": "failed", "error": "no embedding key"})
out = office.build_office("run4", runs_root=runs)
ok(out.get("state") == "error", "failed run reports error")
rex = card(out, "case_rex")
ok(rex.get("stage") == "error" and rex.get("red") is True
   and rex.get("bubble") == "Error: model API error: empty reply"
   and rex.get("seated") is True,
   "rex shows the short red error (%s)" % rex.get("bubble"))
ok(card(out, "image_gene").get("bubble") == "Done \u2713",
   "approved gene is done")
ok(card(out, "voice_wren").get("bubble")
   == "Done \u2713 \u00b7 Memory ready",
   "memory ready overrides the stage bubble")
ash = card(out, "plan_ash")
ok(ash.get("bubble") == "Memory failed" and ash.get("red") is True,
   "memory failure is red")
ok(card(out, "sales_sam").get("stage") == "done",
   "older work on an error run is done")

# ---- fixture 5: memory building + done run ----
r5 = os.path.join(runs, "run5")
mkflow(r5)
wjson(os.path.join(r5, "STATUS.json"),
      {"run_id": "run5", "flow_id": "default", "order_id": "o1",
       "state": "done", "current": "",
       "completed": ["sales_sam", "pd_marty"], "approved": [],
       "error": ""})
wjson(os.path.join(r5, "sales_sam", "result.json"),
      {"producer": "sales_sam", "categories": {}})
wjson(os.path.join(r5, "pd_marty", "result.json"),
      {"producer": "pd_marty", "categories": {}})
wjson(os.path.join(r5, "memory", "pd_marty", "STATUS.json"),
      {"state": "building"})
out = office.build_office("run5", runs_root=runs)
ok(card(out, "pd_marty").get("bubble")
   == "Learning this project (LightRAG)\u2026",
   "memory building bubble")
ok(card(out, "pd_marty").get("still") is not True,
   "building is seated but not frozen")
ok(card(out, "sales_sam").get("bubble") == "Done \u2713"
   and card(out, "sales_sam").get("still") is True,
   "done run parks everyone done")
ok(office.build_office("nosuch", runs_root=runs).get("ok")
   is False, "unknown run refused")

shutil.rmtree(tmp, ignore_errors=True)
print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
