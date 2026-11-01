"""Project-log checks, J16 (no sockets, no model calls).

Fixture order + run + PC entries under a temp dir (projlog root
overrides + pc.ROOT_OVERRIDE): per-source timeline lines, the
run-event mirror table, LOG_INDEX.json completeness both ways,
secret scrubbing, TIMELINE.md, real hook paths (run_flow with a
stub runner, build_memory with a stub indexer, approve /
invalidate / stop / close), and the projectlog safe path.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents._frame import flow  # noqa: E402
from agents._frame import memory as memstore  # noqa: E402
from agents._frame import pc as _pc  # noqa: E402
from agents._frame import projlog  # noqa: E402
from agents._frame import results  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


OID = "ord-20260101-001"
RID = "plrun1"

tmp = tempfile.mkdtemp(prefix="projlog_")
T_ORDERS = os.path.join(tmp, "orders")
T_RUNS = os.path.join(tmp, "runs")
T_OUTPUT = os.path.join(tmp, "output", "runs")

projlog.ORDERS_OVERRIDE = T_ORDERS
projlog.RUNS_OVERRIDE = T_RUNS
projlog.OUTPUT_OVERRIDE = T_OUTPUT
_pc.ROOT_OVERRIDE = tmp
real_orders = flow.ORDERS_DIR
flow.ORDERS_DIR = T_ORDERS

NODE_FILES = ["result.json", "report.md", "INPUTS.md",
              "inputs_log.json", "reads_log.jsonl",
              "inputs_check.json", "events.jsonl", "usage.json"]


def wjson(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def wtext(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def wbin(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)


def wnode(run, node, part=None):
    base = os.path.join(T_RUNS, run, node)
    ndir = os.path.join(base, "p%d" % part) \
        if part is not None else base
    for fn in NODE_FILES:
        wtext(os.path.join(ndir, fn), "%s %s" % (node, fn))


ODIR = os.path.join(T_ORDERS, OID)
wjson(os.path.join(ODIR, "meta.json"),
      {"id": OID, "answers": {"audience": "a"}})
wtext(os.path.join(ODIR, "chat.jsonl"), '{"user": "hi"}\n')
wbin(os.path.join(ODIR, "source.pdf"), b"%PDF-1.4 fake")
wjson(os.path.join(ODIR, "intake.json"), {"order_id": OID})
wtext(os.path.join(ODIR, "report.md"), "# sam report")
wjson(os.path.join(ODIR, "result.json"), {"producer": "x"})

SODIR = os.path.join(T_OUTPUT, OID)
for fn in ("INPUTS.md", "events.jsonl", "result.json",
           "report.md", "usage.json"):
    wtext(os.path.join(SODIR, fn), "sam %s" % fn)

RDIR = os.path.join(T_RUNS, RID)
wjson(os.path.join(RDIR, "STATUS.json"),
      {"run_id": RID, "order_id": OID, "state": "done",
       "approved": []})
wjson(os.path.join(RDIR, "flow.json"), {"id": "default"})
wtext(os.path.join(RDIR, "events.jsonl"), "{}\n")
wnode(RID, "pd_marty")
wnode(RID, "photo_pia", 1)
wnode(RID, "photo_pia", 2)
VDIR = os.path.join(RDIR, "video_production")
for fn in ("assembly.json", "video.mp4", "clip.srt",
           "storyboard_table.json"):
    wtext(os.path.join(VDIR, fn), "video %s" % fn)
MDIR = os.path.join(RDIR, "memory", "photo_pia")
for fn in ("STATUS.json", "log.jsonl", "usage.json"):
    wtext(os.path.join(MDIR, fn), "mem %s" % fn)
wbin(os.path.join(MDIR, "index", "vectors.bin"), b"\x00" * 8)
wbin(os.path.join(MDIR, "index", "graph.bin"), b"\x00" * 8)

FRUN = os.path.join(T_RUNS, "plforeign1")
wjson(os.path.join(FRUN, "STATUS.json"),
      {"run_id": "plforeign1", "order_id": "ord-19990101-999",
       "state": "done"})


def wentry(pcname, doc_id, order_id):
    edir = os.path.join(tmp, "storage", "_pc", pcname,
                        "entries", doc_id)
    wjson(os.path.join(edir, "entry.json"),
          {"pc": pcname, "doc_id": doc_id,
           "ref": "pc://%s/%s" % (pcname, doc_id),
           "order_id": order_id})
    wjson(os.path.join(edir, "map.json"), {"status": "done"})
    wtext(os.path.join(edir, "log.jsonl"), "{}\n")
    wtext(os.path.join(edir, "worker.log"), "worked\n")
    wbin(os.path.join(edir, "files", "f.png"), b"\x89PNG")


wentry("source", "d1", OID)
wentry("image", "d2", OID)
wentry("generated", "d3", "ord-19990101-999")


def timeline_rows():
    rows = []
    with open(os.path.join(ODIR, "timeline.jsonl"),
              encoding="utf-8") as f:
        for ln in f.read().splitlines():
            rows.append(json.loads(ln))
    return rows


try:
    # ---- timeline lines from every source ----
    ok(projlog.log_event(OID, "order", "created", "opened",
                         file="orders/%s/meta.json" % OID),
       "order line logged")
    ok(projlog.log_event(OID, "sam", "done", "wrote it",
                         node="sales_sam"),
       "sam line logged")
    ok(projlog.log_event(OID, "flow", "run_done", "finished",
                         run_id=RID),
       "flow line logged")
    ok(projlog.log_event(OID, "agent", "done", "done",
                         run_id=RID, node="pd_marty",
                         file="runs/%s/pd_marty/result.json"
                         % RID),
       "agent line logged")
    ok(projlog.log_event(OID, "pc_worker", "done", "mapped",
                         file="pc://source/d1"),
       "pc_worker line logged")
    ok(projlog.log_event(OID, "memory", "done", "ready",
                         run_id=RID, node="photo_pia"),
       "memory line logged")
    ok(projlog.log_event(OID, "video", "done", "assembled",
                         run_id=RID,
                         node="video_production"),
       "video line logged")
    ok(projlog.log_event(OID, "owner", "approve", "",
                         run_id=RID, node="pd_marty"),
       "owner line logged")
    rows = timeline_rows()
    ok([r["source"] for r in rows] ==
       ["order", "sam", "flow", "agent", "pc_worker",
        "memory", "video", "owner"],
       "timeline keeps every source in order")
    ok(all(set(r) == {"at", "source", "run_id", "node",
                      "part", "ev", "summary", "file"}
           for r in rows),
       "timeline rows carry exactly the schema keys")
    ok(projlog.log_event("ord-19990101-999", "order",
                         "created", "x") is False
       and projlog.log_event("../evil", "order", "created",
                             "x") is False
       and projlog.log_event(OID, "nope", "created", "x")
       is False,
       "missing order, bad id and bad source stay silent")

    # ---- secrets never land in the logs ----
    sek = "sk" + "-abc123XYZ"
    ber = "Bearer" + " " + "tok987"
    nasty = ("key=" + sek + " " + ber + " "
             "api_key=SECRET hunter2 password: s3cret "
             "token:abc " + "x" * 300)
    ok(projlog.log_event(OID, "owner", "note", nasty),
       "nasty summary accepted (scrubbed)")
    raw = open(os.path.join(ODIR, "timeline.jsonl"),
               encoding="utf-8").read()
    ok(sek not in raw and ber.split(" ")[-1] not in raw
       and "SECRET" not in raw and "s3cret" not in raw
       and "token:abc" not in raw
       and "sk-[redacted]" in raw
       and "Bearer [redacted]" in raw,
       "secrets redacted in timeline.jsonl")
    last = timeline_rows()[-1]
    ok(len(last["summary"]) <= 200,
       "summaries capped at 200 chars")

    # ---- run-event mirror table ----
    mir = [
        ({"ev": "agent_start", "agent": "pd_marty"},
         ("agent", "start", "pd_marty", None, ""), False),
        ({"ev": "agent_done", "agent": "photo_pia@p2"},
         ("agent", "done", "photo_pia", 2,
          "runs/%s/photo_pia/p2/result.json" % RID), True),
        ({"ev": "agent_start", "agent": "video_production",
          "code": True},
         ("video", "start", "video_production", None, ""),
         False),
        ({"ev": "agent_done", "agent": "part_split",
          "code": True},
         ("flow", "done", "part_split", None,
          "runs/%s/part_split/result.json" % RID), True),
        ({"ev": "agent_skip", "agent": "plan_ash"},
         ("agent", "skipped", "plan_ash", None, ""), False),
        ({"ev": "flow_start", "flow": "default",
          "order": OID},
         ("flow", "run_start", "", None, ""), False),
        ({"ev": "flow_done", "run": RID},
         ("flow", "run_done", "", None, ""), True),
        ({"ev": "step_start", "target": "plan_ash",
          "run": RID},
         ("flow", "step_start", "plan_ash", None,
          "runs/%s/events.jsonl" % RID), False),
        ({"ev": "flow_error", "error": "boom"},
         ("flow", "error", "", None,
          "runs/%s/events.jsonl" % RID), True),
        ({"ev": "step_stopped", "at": "plan_ash"},
         ("flow", "stopped", "", None,
          "runs/%s/events.jsonl" % RID), True),
        ({"ev": "flow_paused"}, ("flow", "paused", "", None,
                                 ""), False),
        ({"ev": "flow_resumed"}, ("flow", "resumed", "", None,
                                  ""), False),
        ({"ev": "flow_step"}, ("flow", "step", "", None, ""),
         False),
        ({"ev": "step_paused", "target": "plan_ash"},
         ("flow", "step_paused", "", None, ""), False),
        ({"ev": "final_ready", "inputs": 3},
         ("flow", "final_ready", "", None, ""), False),
        ({"ev": "something_new"},
         ("flow", "something_new", "", None, ""), False),
    ]
    n0 = len(timeline_rows())
    allok = True
    for ev, want, want_refresh in mir:
        got_refresh = projlog.mirror_run_event(OID, RID, ev)
        row = timeline_rows()[-1]
        got = (row["source"], row["ev"], row["node"],
               row["part"], row["file"])
        if got != want or got_refresh != want_refresh \
                or row["run_id"] != RID:
            allok = False
    ok(allok, "run-event mirror table (16 events)")
    ok(projlog.mirror_run_event(OID, RID, {"ev": "line"})
       is False
       and len(timeline_rows()) == n0 + len(mir),
       "line events skipped, nothing else dropped")
    ok(projlog.mirror_owner_event(
        RID, {"ev": "run_pause", "by": "owner"}) is True
        and timeline_rows()[-1]["source"] == "owner"
        and timeline_rows()[-1]["ev"] == "pause",
       "owner control events mirrored")
    ok(projlog.mirror_owner_event("plforeign1",
                                  {"ev": "run_stop"})
       is False,
       "foreign run's owner event not logged here")
    ok(projlog.memory_event(RID, "photo_pia", "done",
                            "3s, 1 calls", T_RUNS) is True
       and timeline_rows()[-1]["source"] == "memory"
       and timeline_rows()[-1]["node"] == "photo_pia",
       "memory events logged with the node")
    ok(projlog.pc_event(OID, "done", "mapped 3 sections",
                        ref="pc://source/d1") is True
       and timeline_rows()[-1]["source"] == "pc_worker",
       "pc_worker events logged")
    ok(projlog.log_owner(OID, RID, "approve",
                         "photo_pia@p2") is True
       and timeline_rows()[-1]["node"] == "photo_pia"
       and timeline_rows()[-1]["part"] == 2,
       "clone ids split into node + part")

    # ---- LOG_INDEX.json completeness, both ways ----
    projlog.do_refresh(OID)
    idx = json.load(open(os.path.join(ODIR, "LOG_INDEX.json"),
                         encoding="utf-8"))
    ok(isinstance(idx, dict) and idx["order_id"] == OID,
       "index builds")

    def walk(top):
        found = []
        for dirpath, _dirs, names in os.walk(top):
            for fn in names:
                full = os.path.join(dirpath, fn)
                if "/index/" in full.replace("\\", "/"):
                    continue
                found.append(full)
        return found

    expect = set()
    for f in walk(ODIR):
        expect.add("orders/%s/%s"
                   % (OID, os.path.relpath(
                       f, ODIR).replace("\\", "/")))
    for f in walk(SODIR):
        expect.add("output/runs/%s/%s"
                   % (OID, os.path.relpath(
                       f, SODIR).replace("\\", "/")))
    for f in walk(RDIR):
        expect.add("runs/%s/%s"
                   % (RID, os.path.relpath(
                       f, RDIR).replace("\\", "/")))
    for pcname, doc in (("source", "d1"), ("image", "d2")):
        top = os.path.join(tmp, "storage", "_pc", pcname,
                           "entries", doc)
        for f in walk(top):
            expect.add("storage/_pc/%s/entries/%s/%s"
                       % (pcname, doc, os.path.relpath(
                           f, top).replace("\\", "/")))
    got = set(idx["order"]) | set(idx["sam_run"])
    for r in idx["runs"]:
        got.update(r["files"])
    for m in idx["memory"]:
        got.update(m["files"])
    for v in idx["video"]:
        got.update(v["files"])
    for e in idx["pc"]:
        got.update(e["files"])
    ok(got == expect, "every file indexed, nothing extra")
    groups = [idx["order"], idx["sam_run"]]
    groups += [r["files"] for r in idx["runs"]]
    groups += [m["files"] for m in idx["memory"]]
    groups += [v["files"] for v in idx["video"]]
    groups += [e["files"] for e in idx["pc"]]
    flat = [p for g in groups for p in g]
    ok(len(flat) == len(set(flat)),
       "no file listed in two groups")
    ok([r["run_id"] for r in idx["runs"]] == [RID]
       and len(idx["memory"]) == 1
       and idx["memory"][0]["agent"] == "photo_pia"
       and sorted(p.split("/")[-1]
                  for p in idx["memory"][0]["files"])
       == ["STATUS.json", "log.jsonl", "usage.json"]
       and len(idx["video"]) == 1
       and len(idx["video"][0]["files"]) == 4
       and sorted(e["doc_id"] for e in idx["pc"])
       == ["d1", "d2"],
       "groups hold the right members")
    ok(any("memory/*/index/" in s and "(2 files"
           in s for s in idx["skipped"]),
       "generated index counted in skipped")
    ok(not any("plforeign1" in p or "/d3/" in p
               for p in flat),
       "foreign run and entry excluded")
    ok("orders/%s/LOG_INDEX.json" % OID in idx["order"]
       and "orders/%s/timeline.jsonl" % OID in idx["order"],
       "the log files index themselves")
    idx2 = projlog.rebuild_index(OID)
    same = dict(idx2)
    same["built_at"] = idx["built_at"]
    ok(same == idx, "rebuild is deterministic")

    # ---- TIMELINE.md ----
    n = projlog.render_timeline_md(OID)
    md = open(os.path.join(ODIR, "TIMELINE.md"),
              encoding="utf-8").read()
    ok(n == len(timeline_rows())
       and md.count("\n- ") == n,
       "TIMELINE.md carries one line per event")
    ok("# Project timeline" in md
       and "[memory] done photo_pia" in md
       and "photo_pia@p2" in md
       and sek not in md
       and "sk-[redacted]" in md,
       "TIMELINE.md content honest and scrubbed")

    # ---- resolvers + safe path ----
    ok(projlog.order_of_run(RID, T_RUNS) == OID
       and projlog.order_of_run("nosuchrun", T_RUNS) == ""
       and projlog.order_of_run("../x", T_RUNS) == "",
       "order_of_run")
    ok(projlog.runs_for_order(OID, T_RUNS) == [RID],
       "runs_for_order skips foreign runs")
    ok(sorted(e["doc_id"]
              for e in projlog.entries_for_order(OID))
       == ["d1", "d2"],
       "entries_for_order skips foreign entries")
    ok(projlog.projectlog_path(
        OID, "TIMELINE.md").endswith("TIMELINE.md")
        and projlog.projectlog_path(
            OID, "timeline.jsonl") is not None
        and projlog.projectlog_path(
            OID, "LOG_INDEX.json") is not None,
       "projectlog serves the three logs")
    ok(projlog.projectlog_path(OID, "meta.json") is None
       and projlog.projectlog_path(OID, "../x") is None
       and projlog.projectlog_path(OID, "") is None
       and projlog.projectlog_path("../evil", "TIMELINE.md")
       is None
       and projlog.projectlog_path("ord-19990101-999",
                                   "TIMELINE.md") is None,
       "projectlog refuses the rest")

    # ---- real hook paths: approve / stop / invalidate ----
    ARUN = os.path.join(T_RUNS, "plappr1")
    wjson(os.path.join(ARUN, "STATUS.json"),
          {"run_id": "plappr1", "order_id": OID,
           "state": "step_paused", "approved": []})
    wjson(os.path.join(ARUN, "pd_marty", "result.json"),
          {"producer": "pd_marty"})
    out = flow.approve_node("plappr1", "pd_marty",
                            runs_root=T_RUNS)
    row = timeline_rows()[-1]
    ok(out.get("ok") is True and row["source"] == "owner"
       and row["ev"] == "approve"
       and row["node"] == "pd_marty"
       and row["file"].endswith(
           "runs/plappr1/pd_marty/result.json"),
       "approve logs the owner line with the file")
    out = flow.stop_run("plappr1", runs_root=T_RUNS)
    row = timeline_rows()[-1]
    ok(out.get("ok") is True and row["ev"] == "stop",
       "stop logs the owner line")
    flowjson = flow.load_flow("default")
    IRUN = os.path.join(T_RUNS, "plinval1")
    wjson(os.path.join(IRUN, "flow.json"), flowjson)
    wjson(os.path.join(IRUN, "STATUS.json"),
          {"run_id": "plinval1", "order_id": OID,
           "state": "step_paused",
           "approved": ["pd_marty", "plan_ash"]})
    wjson(os.path.join(IRUN, "pd_marty", "result.json"),
          {"producer": "pd_marty"})
    wjson(os.path.join(IRUN, "plan_ash", "result.json"),
          {"producer": "plan_ash"})
    out = flow.invalidate_node("plinval1", "plan_ash",
                               runs_root=T_RUNS)
    row = timeline_rows()[-1]
    idx3 = json.load(open(os.path.join(ODIR, "LOG_INDEX.json"),
                         encoding="utf-8"))
    inv_files = [p for r in idx3["runs"]
                 if r["run_id"] == "plinval1"
                 for p in r["files"]]
    ok(out.get("ok") is True and row["ev"] == "rerun"
       and row["node"] == "plan_ash"
       and not any("plan_ash" in p for p in inv_files),
       "invalidate logs rerun and drops the files")

    # ---- real hook path: memory build ----
    real_indexer = memstore._INDEXER
    memstore._INDEXER = lambda docs, store, lid, prof: {
        "llm_calls": 1, "profile": "stub"}
    try:
        MRUN = os.path.join(T_RUNS, "plmem1")
        wjson(os.path.join(MRUN, "STATUS.json"),
              {"run_id": "plmem1", "order_id": OID,
               "state": "done"})
        wnode("plmem1", "pd_marty")
        mout = memstore.build_memory(
            "plmem1", "pd_marty",
            [("INPUTS.md", "hello")], runs_root=T_RUNS)
    finally:
        memstore._INDEXER = real_indexer
    mrows = [r for r in timeline_rows()
             if r["source"] == "memory"
             and r["run_id"] == "plmem1"]
    ok(mout.get("ok") is True
       and [r["ev"] for r in mrows] == ["start", "done"],
       "memory build logs start + done")
    idx4 = json.load(open(os.path.join(ODIR, "LOG_INDEX.json"),
                         encoding="utf-8"))
    ok(any(m["run_id"] == "plmem1"
           for m in idx4["memory"]),
       "memory files join the index")

    # ---- Close project keeps every log ----
    ok(memstore.close_run_memory(RID, T_RUNS) is True
       and not os.path.isdir(os.path.join(RDIR, "memory"))
       and os.path.isfile(os.path.join(
           RDIR, "MEMORY_CLOSED.json")),
       "close deletes only the memory")
    ok(os.path.isfile(os.path.join(ODIR, "LOG_INDEX.json"))
       and os.path.isfile(os.path.join(
           ODIR, "timeline.jsonl"))
       and os.path.isfile(os.path.join(
           ODIR, "TIMELINE.md")),
       "close keeps the project logs")
    idx5 = projlog.rebuild_index(OID)
    ok("runs/%s/MEMORY_CLOSED.json" % RID
       in [p for r in idx5["runs"]
           for p in r["files"]]
       and not any(m["run_id"] == RID
                   for m in idx5["memory"]),
       "index after close: marker in, memory out")

    # ---- end to end: a real stub flow run logs itself ----
    real_tree = {}
    for label, top in (("orders", os.path.join(ROOT, "orders")),
                       ("runs", os.path.join(ROOT, "runs")),
                       ("output",
                        os.path.join(ROOT, "output", "runs"))):
        try:
            real_tree[label] = sorted(os.listdir(top))
        except OSError:
            real_tree[label] = []
    wjson(os.path.join(ODIR, "meta.json"),
          {"id": OID, "answers": {"audience": "a",
                                 "length": "b", "depth": "c",
                                 "theme": "d"},
           "files": {"source": "s.pdf"}})
    REQ = {"order_id": OID,
           "client_answers": {"audience": "a", "length": "b",
                             "depth": "c", "theme": "d",
                             "source": "e"},
           "source_summary": "s", "production_notes": ["n"],
           "open_questions": []}
    CONCEPT = {"common_theme": "t", "core_question": "q",
               "viewer_takeaway": "v", "intent_overall": "o"}
    STRUCT = {"source_ref": "pc://source/abc123abc123",
              "parts": [{"id": "p1", "heading": "h",
                         "ref": "pc://source/abc123abc123#s1",
                         "covers": "x", "keywords": ["k"]}],
              "links": [],
              "duration": {"total_s": 60,
                           "parts": [{"part_id": "p1",
                                      "seconds": 60,
                                      "why": "w"}]}}
    CONCEPTS = {"parts": [{"part_id": "p1",
                           "concept_name": "c",
                           "easy_explanation": "e",
                           "why_it_came_about": "w",
                           "analogy_or_example": "a",
                           "common_misunderstanding": "m",
                           "claims": [], "picks": [],
                           "gaps": []}]}
    CASES = {"parts": [{"part_id": "p1", "cases": [],
                        "picks": [], "gaps": []}]}
    DRAFT = {"total_s": 60, "scenes": [],
             "unused_picks": []}
    BOARD = {"cuts": [{"cut_id": "s1c1", "scene_n": 1,
                       "start_s": 0, "end_s": 20,
                       "show_what": "Card",
                       "show_why": "Intro",
                       "on_screen_text": ["Hello"]}]}
    GUIDE = {"palette": {"background": "#101418",
                         "text": "#f5f2ea",
                         "accent": "#e0a458"},
             "fonts": {"heading": "sans", "body": "sans"},
             "image_tone": "plain", "rules": []}
    PHOTO = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                       "kind": "none", "reason": "stub"}]}
    GEN = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                     "reason": "stub"}],
           "images": []}
    ANIM = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                      "reason": "stub"}]}
    SLIDE = {"cuts": [{"cut_id": "s1c1", "start_s": 0,
                       "end_s": 20, "preset": "full",
                       "blocks": [{"kind": "text",
                                   "box": {"x": 64, "y": 300,
                                           "w": 1152,
                                           "h": 120},
                                   "order": 0, "appear_s": 0,
                                   "reason": "Headline",
                                   "font_size": 44,
                                   "data": {"lines": [
                                       "Hello"]}}],
                       "on_screen_text": ["Hello"],
                       "transitions": [], "why": "stub"}]}
    RLOG = {"cuts": [{"cut_id": "s1c1",
                      "slide_file": "slides/s1c1.png",
                      "renders_n": 1, "adjustments": [],
                      "issues": []}]}
    PAY = {"sales_sam": {"request": REQ},
           "pd_marty": {"concept": CONCEPT,
                        "structure": STRUCT},
           "explain_cleo": {"concepts": CONCEPTS},
           "case_rex": {"cases": CASES},
           "plan_ash": {"storyboard_draft": DRAFT},
           "board_penn": {"storyboard": BOARD,
                          "style_guide": GUIDE},
           "photo_pia": {"photo_picks": PHOTO},
           "image_gene": {"gen_picks": GEN},
           "anim_max": {"anim_picks": ANIM},
           "board_vera": {"slide_draft": SLIDE},
           "slide_remy": {"render_log": RLOG}}

    def stub(agent_dir, run_dir, brief, input_md):
        who = os.path.basename(run_dir)
        if who.startswith("p") and who[1:].isdigit():
            who = os.path.basename(os.path.dirname(run_dir))
        if who == "voice_wren":
            saved = _pc.voice_save(
                brief["order_id"], "s1c1", b"\x00" * 32,
                "Hello world", 20, 1, "stub")
            cats = {"narration": {"cuts": [{
                "cut_id": "s1c1", "scene_n": 1, "start_s": 0,
                "end_s": 20,
                "lines": [{"text": "Hello world",
                           "citations": []}],
                "words": 2,
                "audio": {"voice_pc_ref": saved["ref"],
                          "seconds": 20},
                "attempts": 1}]}}
            producer = "voice_wren"
        else:
            cats = PAY[who]
            producer = brief.get("clone_id", who)
        if who == "slide_remy":
            sdir = os.path.join(run_dir, "slides")
            os.makedirs(sdir, exist_ok=True)
            with open(os.path.join(sdir, "s1c1.png"), "w",
                      encoding="utf-8") as f:
                f.write("PNG")
            with open(os.path.join(sdir, "s1c1.props.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"cutId": "s1c1", "probe": True},
                          f)
        res = results.make_result(producer,
                                  brief["order_id"],
                                  brief["flow_run_id"],
                                  cats)
        results.save_result(run_dir, res)
        return {"ok": True,
                "usage": {"prompt_tokens": 10,
                          "completion_tokens": 5},
                "events": [{"ev": "llm"}]}

    dflt = flow.load_flow("default")
    dflt["settings"] = dict(dflt.get("settings") or {},
                            parallel_parts=False)
    n_before = len(timeline_rows())
    fout = flow.run_flow(dflt, OID, stub, runs_root=T_RUNS,
                         run_id="plflow1", flow_id="default")
    erows = [r for r in timeline_rows()[n_before:]
             if r["run_id"] == "plflow1"]
    ok(fout.get("ok") is True,
       "stub flow runs to done (%s)"
       % fout.get("error", ""))
    ok([r["ev"] for r in erows
        if r["source"] == "flow"][:1] == ["run_start"]
       and [r["ev"] for r in erows
            if r["source"] == "flow"][-1:] == ["run_done"],
       "flow start/end mirrored")
    mdone = [r for r in erows if r["source"] == "agent"
             and r["node"] == "pd_marty"
             and r["ev"] == "done"]
    ok(len(mdone) == 1
       and mdone[0]["file"].endswith(
           "runs/plflow1/pd_marty/result.json"),
       "agent done mirrored with the result file")
    ok(any(r["source"] == "agent"
           and r["node"] == "photo_pia"
           and r["part"] == 1 and r["ev"] == "done"
           for r in erows),
       "clone done mirrored with node + part")
    ok(any(r["source"] == "video" and r["ev"] == "done"
           for r in erows),
       "video code node mirrored as video")
    evs = [(r["node"], r["ev"]) for r in erows
           if r["source"] == "agent"]
    ok(evs.index(("pd_marty", "done")) <
       evs.index(("plan_ash", "done")),
       "agent lines follow run order")
    idx6 = json.load(open(os.path.join(ODIR, "LOG_INDEX.json"),
                         encoding="utf-8"))
    ok(any("runs/plflow1/pd_marty/result.json" in r["files"]
           for r in idx6["runs"]),
       "run files join the index by themselves")
    ok(any(e["ref"].startswith("pc://voice/")
           for e in idx6["pc"]),
       "stub voice entry joins the pc group")
    escaped = False
    for label, top in (("orders", os.path.join(ROOT, "orders")),
                       ("runs", os.path.join(ROOT, "runs")),
                       ("output",
                        os.path.join(ROOT, "output", "runs"))):
        try:
            now = sorted(os.listdir(top))
        except OSError:
            now = []
        if now != real_tree[label]:
            escaped = True
    ok(not escaped, "nothing escapes to the real tree")
finally:
    projlog.ORDERS_OVERRIDE = None
    projlog.RUNS_OVERRIDE = None
    projlog.OUTPUT_OVERRIDE = None
    _pc.ROOT_OVERRIDE = None
    flow.ORDERS_DIR = real_orders

print("fails: %d" % len(FAILS))
raise SystemExit(1 if FAILS else 0)
