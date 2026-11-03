"""Run-control checks, J6 (no sockets, no model calls).

Drives agents/_frame/flow.py run_flow with a blocking stub runner on
the real default flow (parallel_parts OFF): pause mid-run finishes
the current stage and keeps its result; resume runs to done; step
runs exactly one stage; stop is final; pause_each_stage pauses after
every stage. Also covers the control transition guards and the
auto-start after Sam's request (server._do_complete with a stubbed
runner; fixture order/output/run dirs are deleted afterwards).

Temporary roots under tempfile; the auto-start test uses the real
orders/, output/ and runs/ folders (all git-ignored) and removes its
fixtures in a finally.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from agents._frame import flow  # noqa: E402
flow.AUTO_ASSEMBLE = False  # stubbed runs: no real ffmpeg at the end
from agents._frame import parts  # noqa: E402
from agents._frame import pc as _pc  # noqa: E402
from agents._frame import results  # noqa: E402
from agents._frame import runner  # noqa: E402
import server as _srv  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


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
          "links": [],
          "duration": {"total_s": 60,
                       "parts": [{"part_id": "p1", "seconds": 60,
                                  "why": "w"}]}}
CONCEPTS = {"parts": [{"part_id": "p1", "concept_name": "c",
                       "easy_explanation": "e",
                       "why_it_came_about": "w",
                       "analogy_or_example": "a",
                       "common_misunderstanding": "m",
                       "claims": [], "picks": [], "gaps": []}]}
CASES = {"parts": [{"part_id": "p1", "cases": [], "picks": [],
                    "gaps": []}]}
DRAFT = {"total_s": 60, "scenes": [], "unused_picks": []}
BOARD = {"cuts": [{"cut_id": "s1c1", "scene_n": 1, "start_s": 0,
                   "end_s": 20, "show_what": "Card",
                   "show_why": "Intro",
                   "on_screen_text": ["Hello"]}]}
GUIDE = {"palette": {"background": "#101418", "text": "#f5f2ea",
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
SLIDE = {"cuts": [{"cut_id": "s1c1", "start_s": 0, "end_s": 20,
                   "preset": "full",
                   "blocks": [{"kind": "text",
                               "box": {"x": 64, "y": 300, "w": 1152,
                                       "h": 120},
                               "order": 0, "appear_s": 0,
                               "reason": "Headline",
                               "font_size": 44,
                               "data": {"lines": ["Hello"]}}],
                   "on_screen_text": ["Hello"],
                   "transitions": [], "why": "stub"}]}
RLOG = {"cuts": [{"cut_id": "s1c1",
                  "slide_file": "slides/s1c1.png", "renders_n": 1,
                  "adjustments": [], "issues": []}]}
PAY = {"sales_sam": ("sales_sam", {"request": REQ}),
       "pd_marty": ("pd_marty", {"concept": CONCEPT,
                                 "structure": STRUCT}),
       "explain_cleo": ("explain_cleo", {"concepts": CONCEPTS}),
       "case_rex": ("case_rex", {"cases": CASES}),
       "plan_ash": ("plan_ash", {"storyboard_draft": DRAFT}),
       "board_penn": ("board_penn", {"storyboard": BOARD,
                                     "style_guide": GUIDE}),
       "photo_pia": ("photo_pia", {"photo_picks": PHOTO}),
       "image_gene": ("image_gene", {"gen_picks": GEN}),
       "anim_max": ("anim_max", {"anim_picks": ANIM}),
       "board_vera": ("board_vera", {"slide_draft": SLIDE}),
       "slide_remy": ("slide_remy", {"render_log": RLOG})}

BLOCK = {}
SAW = []
SAW_LOCK = threading.Lock()


def stub(agent_dir, run_dir, brief, input_md):
    who = os.path.basename(run_dir)
    if who.startswith("p") and who[1:].isdigit():
        who = os.path.basename(os.path.dirname(run_dir))
    with SAW_LOCK:
        SAW.append(who)
    gate = BLOCK.get(who)
    if gate is not None:
        gate.wait(120)
    if who == "voice_wren":
        saved = _pc.voice_save(brief["order_id"], "s1c1",
                               b"\x00" * 32, "Hello world", 20, 1,
                               "stub")
        cats = {"narration": {"cuts": [{
            "cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 20,
            "lines": [{"text": "Hello world", "citations": []}],
            "words": 2,
            "audio": {"voice_pc_ref": saved["ref"], "seconds": 20},
            "attempts": 1}]}}
        producer = "voice_wren"
    else:
        _base, cats = PAY[who]
        producer = brief.get("clone_id", _base)
    if who == "slide_remy":
        sdir = os.path.join(run_dir, "slides")
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "s1c1.png"), "w",
                  encoding="utf-8") as f:
            f.write("PNG")
        with open(os.path.join(sdir, "s1c1.props.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"cutId": "s1c1", "probe": True}, f)
    res = results.make_result(producer, brief["order_id"],
                              brief["flow_run_id"], cats)
    results.save_result(run_dir, res)
    return {"ok": True, "usage": {"prompt_tokens": 10,
                                  "completion_tokens": 5},
            "events": [{"ev": "llm"}]}


def read_status(run_dir):
    try:
        with open(os.path.join(run_dir, "STATUS.json"),
                  encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def wait_state(run_dir, want, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if read_status(run_dir).get("state") in want:
            return read_status(run_dir)
        time.sleep(0.2)
    return read_status(run_dir)


def wait_current(run_dir, want, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if read_status(run_dir).get("current") == want:
            return True
        time.sleep(0.2)
    return False


def wait_completed(run_dir, want, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if read_status(run_dir).get("completed") == want:
            return True
        time.sleep(0.2)
    return False


tmp = tempfile.mkdtemp(prefix="flowrun_")
runs_root = os.path.join(tmp, "runs")
os.makedirs(os.path.join(tmp, "orders", "octl"))
with open(os.path.join(tmp, "orders", "octl", "meta.json"), "w",
          encoding="utf-8") as f:
    json.dump({"answers": {"audience": "a", "length": "b",
                           "depth": "c", "theme": "d"},
               "files": {"source": "s.pdf"}}, f)
dflt = flow.load_flow("default")
dflt["settings"] = dict(dflt.get("settings") or {},
                         parallel_parts=False)
real_orders = flow.ORDERS_DIR
flow.ORDERS_DIR = os.path.join(tmp, "orders")
_pc.ROOT_OVERRIDE = tmp

try:
    # ---- t1: pause mid-run finishes the stage, keeps results ----
    BLOCK["pd_marty"] = threading.Event()
    r1 = os.path.join(runs_root, "run1")
    out1 = {}

    def _t1():
        out1.update(flow.run_flow(
            dflt, "octl", stub, runs_root=runs_root,
            run_id="run1", flow_id="default"))

    th = threading.Thread(target=_t1, daemon=True)
    th.start()
    ok(wait_current(r1, "pd_marty"), "t1 marty starts (current)")
    p = flow.ctl_pause("run1", True, runs_root=runs_root)
    ok(p.get("ok") and p.get("state") == "pausing",
       "t1 pause requested while marty works")
    BLOCK.pop("pd_marty").set()
    st = wait_state(r1, ("paused",), timeout=60)
    ok(st.get("state") == "paused", "t1 run pauses at the boundary")
    ok(os.path.isfile(os.path.join(
        r1, "pd_marty", "result.json")),
        "t1 marty result kept")
    ok(not os.path.isdir(os.path.join(r1, "explain_cleo")),
       "t1 cleo never starts")
    rs = flow.run_state("run1", runs_root=runs_root, live=True)
    ok(rs.get("completed") == ["sales_sam", "pd_marty"],
       "t1 completed lists sam + marty (%s)"
       % (rs.get("completed"),))
    ok(rs.get("cost", {}).get("llm_calls") == 2,
       "t1 cost counts both stages (%s)" % (rs.get("cost"),))
    ok(rs.get("current") == "", "t1 nothing current while paused")

    # ---- t2: resume runs to done ----
    r = flow.ctl_resume("run1", True, runs_root=runs_root)
    ok(r.get("ok"), "t2 resume accepted")
    th.join(timeout=240)
    ok(not th.is_alive(), "t2 run thread finishes")
    ok(out1.get("ok"), "t2 run reaches done")
    ok(read_status(r1).get("state") == "done", "t2 STATUS done")

    # ---- t3: step runs exactly one stage ----
    flow.write_control(os.path.join(runs_root, "run3"),
                       {"pause": True})
    r3 = os.path.join(runs_root, "run3")
    out3 = {}

    def _t3():
        out3.update(flow.run_flow(
            dflt, "octl", stub, runs_root=runs_root,
            run_id="run3", flow_id="default"))

    th3 = threading.Thread(target=_t3, daemon=True)
    th3.start()
    ok(wait_state(r3, ("paused",))["state"] == "paused",
       "t3 pre-set pause holds before stage 1")
    ok(not os.path.isdir(os.path.join(r3, "sales_sam")),
       "t3 nothing runs while held")
    s = flow.ctl_step("run3", True, runs_root=runs_root)
    ok(s.get("ok"), "t3 step accepted")
    ok(wait_completed(r3, ["sales_sam"])
       and wait_state(r3, ("paused",))["state"] == "paused",
       "t3 exactly sam runs, then paused again")
    ok(not os.path.isdir(os.path.join(r3, "pd_marty")),
       "t3 marty still untouched")
    s = flow.ctl_step("run3", True, runs_root=runs_root)
    ok(s.get("ok"), "t3 second step accepted")
    ok(wait_completed(r3, ["sales_sam", "pd_marty"])
       and wait_state(r3, ("paused",))["state"] == "paused",
       "t3 second step runs marty only")
    q = flow.ctl_stop("run3", True, runs_root=runs_root)
    ok(q.get("ok"), "t3 stop accepted")
    th3.join(timeout=60)
    ok(read_status(r3).get("state") == "stopped",
       "t3 run stops")
    ok("stopped:" in str(out3.get("error", "")),
       "t3 stop keeps the stopped: shape")

    # ---- t4: stop mid-run is final ----
    BLOCK["pd_marty"] = threading.Event()
    r4 = os.path.join(runs_root, "run4")
    out4 = {}

    def _t4():
        out4.update(flow.run_flow(
            dflt, "octl", stub, runs_root=runs_root,
            run_id="run4", flow_id="default"))

    th4 = threading.Thread(target=_t4, daemon=True)
    th4.start()
    ok(wait_current(r4, "pd_marty"), "t4 marty starts")
    q = flow.ctl_stop("run4", True, runs_root=runs_root)
    ok(q.get("ok"), "t4 stop accepted while marty works")
    BLOCK.pop("pd_marty").set()
    th4.join(timeout=60)
    ok(read_status(r4).get("state") == "stopped",
       "t4 stopped at the boundary")
    ok("halted after pd_marty" in str(out4.get("error", "")),
       "t4 current stage finishes first (%s)"
       % out4.get("error"))
    ok(os.path.isfile(os.path.join(
        r4, "pd_marty", "result.json")),
        "t4 marty result kept after stop")
    rr = flow.ctl_resume("run4", True, runs_root=runs_root)
    ok(not rr.get("ok") and "stopped" in rr.get("error", ""),
       "t4 resume refused after stop")
    ss = flow.ctl_step("run4", True, runs_root=runs_root)
    ok(not ss.get("ok"), "t4 step refused after stop")

    # ---- t5: pause_each_stage pauses after every stage ----
    r5 = os.path.join(runs_root, "run5")
    flow.write_control(r5, {"pause_each_stage": True})
    out5 = {}

    def _t5():
        out5.update(flow.run_flow(
            dflt, "octl", stub, runs_root=runs_root,
            run_id="run5", flow_id="default"))

    th5 = threading.Thread(target=_t5, daemon=True)
    th5.start()
    ok(wait_completed(r5, ["sales_sam"])
       and wait_state(r5, ("paused",))["state"] == "paused",
       "t5 pauses after sam")
    flow.ctl_resume("run5", True, runs_root=runs_root)
    ok(wait_completed(r5, ["sales_sam", "pd_marty"])
       and wait_state(r5, ("paused",))["state"] == "paused",
       "t5 pauses after marty")
    rs5 = flow.run_state("run5", runs_root=runs_root, live=True)
    ok(rs5.get("pause_each_stage") is True,
       "t5 state reports the toggle")
    flow.write_control(r5, {"pause_each_stage": False})
    flow.ctl_resume("run5", True, runs_root=runs_root)
    th5.join(timeout=240)
    ok(out5.get("ok"), "t5 runs to done after toggle off")

    # ---- t6: transition guards without a live thread ----
    r6 = os.path.join(runs_root, "run6")
    os.makedirs(r6)
    with open(os.path.join(r6, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"run_id": "run6", "flow_id": "default",
                   "order_id": "octl", "state": "paused",
                   "current": "", "completed": ["sales_sam"]}, f)
    ok(flow.ctl_pause("run6", False, runs_root=runs_root)
       .get("state") == "paused", "t6 pause is idempotent")
    rr = flow.ctl_resume("run6", False, runs_root=runs_root)
    ok(not rr.get("ok") and "step mode" in rr.get("error", ""),
       "t6 resume needs a live thread")
    ss = flow.ctl_step("run6", False, runs_root=runs_root)
    ok(not ss.get("ok"), "t6 step needs a live thread")
    q = flow.ctl_stop("run6", False, runs_root=runs_root)
    ok(q.get("ok") and read_status(r6).get("state") == "stopped",
       "t6 stop works file-only")
    ok(not flow.ctl_pause("run1", True, runs_root=runs_root)
       .get("ok"), "t6 pause refused on a done run")
    ok(not flow.ctl_resume("run1", True, runs_root=runs_root)
       .get("ok"), "t6 resume refused on a done run")
    st = flow.run_state("run1", runs_root=runs_root, live=False)
    ok(st.get("state") == "done", "t6 done stays done")
    r7 = os.path.join(runs_root, "run7")
    os.makedirs(r7)
    with open(os.path.join(r7, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"run_id": "run7", "state": "running",
                   "flow_id": "default", "order_id": "octl"}, f)
    st = flow.run_state("run7", runs_root=runs_root, live=False)
    ok(st.get("state") == "error"
       and "restarted" in st.get("error", ""),
       "t6 orphaned running run reports error")
    ok(not flow.ctl_pause("nosuch", True, runs_root=runs_root)
       .get("ok"), "t6 unknown run refused")

    # ---- t8: inputs_log.json + inputs_check.json per node/part ----
    def _load(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    mlog = _load(os.path.join(r1, "pd_marty", "inputs_log.json"))
    ok(mlog.get("node") == "pd_marty"
       and mlog.get("run_id") == "run1"
       and mlog.get("order_id") == "octl"
       and isinstance(mlog.get("items"), list) and mlog["items"]
       and isinstance(mlog.get("pc_rows"), list)
       and isinstance(mlog.get("denied"), list),
       "t8 marty inputs_log envelope")
    names = [i.get("item") for i in mlog["items"]]
    ok("brief" in names
       and "received.sales_sam.request" in names,
       "t8 marty log lists brief + sam request (%s)" % (names,))
    ok(all(set(i) == {"item", "category", "from", "part",
                      "chars", "est_tokens", "sha1", "note"}
           for i in mlog["items"]),
       "t8 every log item has the 8 keys")
    first = mlog["items"][0]
    ok(first["est_tokens"] == int(round(first["chars"] / 4)),
       "t8 est_tokens is chars/4")
    exp_brief = json.dumps(
        {"order_id": "octl",
         "answers": {"audience": "a", "length": "b",
                     "depth": "c", "theme": "d"},
         "source_file": "s.pdf"}, ensure_ascii=False, indent=1)
    brief = next(i for i in mlog["items"]
                 if i["item"] == "brief")
    ok(brief["sha1"] == hashlib.sha1(
        exp_brief.encode("utf-8")).hexdigest()
       and brief["chars"] == len(exp_brief),
       "t8 brief sha1/chars match the rendered block")
    ok(mlog.get("pc_rows") == [] and mlog.get("denied") == [],
       "t8 no granted rows on the fixture run")
    clog = _load(os.path.join(r1, "photo_pia", "p1",
                              "inputs_log.json"))
    ok("shared" in [i.get("item") for i in clog["items"]],
       "t8 clone log carries the shared block")
    sh = next(i for i in clog["items"] if i["item"] == "shared")
    ok(sh.get("part") == 1 and sh.get("from") == "part_split",
       "t8 shared block names part 1")
    slog = _load(os.path.join(r1, "photo_pia",
                              "inputs_log.json"))
    ok([i.get("item") for i in slog["items"]] == ["split"],
       "t8 split stub logs its stub inputs")
    chk = _load(os.path.join(r1, "pd_marty",
                             "inputs_check.json"))
    ok(chk.get("ok") is True and chk.get("spec") == "no spec",
       "t8 inputs_check passes vacuously without a spec")
    spec = {"nodes": {
        "pd_marty": {
            "items": [
                {"item": "brief", "category": "brief",
                 "from": "order"},
                {"item": "received.sales_sam.request",
                 "category": "request",
                 "from": "sales_sam"},
                {"item": "received.x.y", "optional": True}],
            "pc_rows": [{"pc": "source", "kind": "full",
                         "parts": []}]},
        "photo_pia@p*": {
            "items": [{"item": "shared", "part": 1}],
            "pc_rows": []}}}
    sp = os.path.join(tmp, "spec.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    base_items = [
        {"item": "brief", "category": "brief", "from": "order",
         "part": None},
        {"item": "received.sales_sam.request",
         "category": "request", "from": "sales_sam",
         "part": None},
        {"item": "owner_note", "category": "note",
         "from": "owner", "part": None}]
    base_rows = [{"pc": "source", "kind": "full", "parts": []}]
    c0 = flow._check_inputs_spec("pd_marty", base_items,
                                 base_rows, sp)
    ok(c0["ok"] and c0["missing"] == [] and c0["extra"] == []
       and c0["wrong_part"] == [] and c0["wrong_kind"] == [],
       "t8 spec match passes (owner_note allowed)")
    c1 = flow._check_inputs_spec("pd_marty", base_items[1:],
                                 base_rows, sp)
    ok(not c1["ok"] and c1["missing"] == ["brief"],
       "t8 missing item flagged")
    c2 = flow._check_inputs_spec(
        "pd_marty",
        base_items + [{"item": "zzz", "category": "z",
                       "from": "z", "part": None}],
        base_rows, sp)
    ok(not c2["ok"] and c2["extra"] == ["zzz"],
       "t8 extra item flagged")
    c3 = flow._check_inputs_spec(
        "photo_pia@p2", [{"item": "shared", "category": "shared",
                          "from": "part_split", "part": 2}],
        [], sp)
    ok(not c3["ok"]
       and len(c3["wrong_part"]) == 1
       and "shared" in c3["wrong_part"][0],
       "t8 wildcard entry checks the part")
    c4 = flow._check_inputs_spec("pd_marty", base_items,
                                 [{"pc": "source", "kind": "map",
                                   "parts": []}], sp)
    ok(not c4["ok"] and len(c4["wrong_kind"]) == 1,
       "t8 wrong kind flagged")
    c5 = flow._check_inputs_spec("pd_marty", base_items,
                                 [{"pc": "source", "kind": "full",
                                   "parts": ["pc://source/x#s1"]}],
                                 sp)
    ok(not c5["ok"] and len(c5["wrong_part"]) == 1
       and "pc_row:source" in c5["wrong_part"][0],
       "t8 wrong parts flagged")
    c6 = flow._check_inputs_spec("nobody", base_items,
                                 base_rows, sp)
    ok(c6["ok"] and c6["spec"] == "no entry",
       "t8 node without a spec entry passes vacuously")
    with open(sp, "w", encoding="utf-8") as f:
        f.write("{broken")
    c7 = flow._check_inputs_spec("pd_marty", base_items,
                                 base_rows, sp)
    ok(c7["ok"] is False and "error" in c7,
       "t8 broken spec fails the check, not the run")
finally:
    flow.ORDERS_DIR = real_orders
    _pc.ROOT_OVERRIDE = None

def _tiny_pdf():
    """A valid one-page PDF (correct xref) with one line of text, so
    the parser that finalize now runs accepts it."""
    stream = b"BT /F1 12 Tf 20 50 Td (Stub chapter text) Tj ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream
            + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offs = []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return out


# ---- t7: auto-start after Sam's request (real dirs, cleaned) ----
oid = "ord-ctl-autostart"
odir = os.path.join(ROOT, "orders", oid)
real_run = runner.run
real_key = runner.key_present


def sam_stub(agent_dir, run_dir, brief, input_md):
    if "flow_run_id" in brief:
        return stub(agent_dir, run_dir, brief, input_md)
    res = results.make_result(
        "sales_sam", brief["order_id"], "samrun",
        {"request": dict(REQ, order_id=brief["order_id"])})
    results.save_result(run_dir, res)
    with open(os.path.join(run_dir, "report.md"), "w",
              encoding="utf-8") as f:
        f.write("# Production request (stub)\n")
    return {"ok": True, "usage": {"prompt_tokens": 3,
                                  "completion_tokens": 1},
            "events": [{"ev": "llm"}]}


tmp2 = tempfile.mkdtemp(prefix="flowrun_auto_")
flow.ORDERS_DIR = os.path.join(ROOT, "orders")
_pc.ROOT_OVERRIDE = tmp2
runner.run = sam_stub
runner.key_present = lambda model: True
auto_run = None
try:
    os.makedirs(odir)
    with open(os.path.join(odir, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"status": "consulting", "assignee": "sales_sam",
                   "answers": {"audience": "a", "length": "b",
                               "depth": "c", "theme": "d"},
                   "files": {"source": "source.pdf"}}, f)
    with open(os.path.join(odir, "source.pdf"), "wb") as f:
        f.write(_tiny_pdf())  # finalize parses the PDF; a bare stub fails
    handler = _srv.Handler.__new__(_srv.Handler)
    code, obj = handler._do_complete(
        oid, odir, handler._order_meta(odir), {}, "in_production")
    ok(code == 200 and obj.get("ok"), "t7 sam request written")
    auto_run = obj.get("run_id")
    ok(bool(auto_run), "t7 response carries the run_id")
    if auto_run:
        live = _srv._FLOW_JOBS.get(auto_run, {}).get("state")
        ok(live == "running", "t7 flow auto-started (job %s)"
           % live)
        adir = os.path.join(ROOT, "runs", auto_run)
        st = wait_state(adir, ("done",), timeout=240)
        ok(st.get("state") == "done", "t7 auto run reaches done")
    ok(os.path.isfile(os.path.join(odir, "result.json")),
       "t7 order keeps sam result.json")
finally:
    runner.run = real_run
    runner.key_present = real_key
    flow.ORDERS_DIR = real_orders
    _pc.ROOT_OVERRIDE = None
    shutil.rmtree(odir, ignore_errors=True)
    shutil.rmtree(os.path.join(ROOT, "output", "runs", oid),
                  ignore_errors=True)
    if auto_run:
        shutil.rmtree(os.path.join(ROOT, "runs", auto_run),
                      ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(tmp2, ignore_errors=True)

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
