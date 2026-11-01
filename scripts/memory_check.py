"""Employee project memory checks, J8/J9 (no sockets, no model calls).

Stub indexer/retriever injected into agents/_frame/memory.py: approve
queues a background build (clones merged into one memory per base
agent); re-run approval rebuilds fresh and keeps the old log lines;
failure + retry; close deletes only the memory; run cost includes
memory usage; the server chat gate answers 409 until ready and injects
memory context when ready; the new-order open-project gate; Sam's
memory collected from the consultation. Fixture runs live under a
temporary runs root; the order-gate test uses the real (git-ignored)
orders/ folder and removes its fixtures in a finally.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from agents._frame import flow  # noqa: E402
from agents._frame import memory as mem  # noqa: E402
from agents._frame import office  # noqa: E402
from agents._frame import runner  # noqa: E402
import server as _srv  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


TMP = tempfile.mkdtemp(prefix="memcheck_")
REAL_RUNS = flow.RUNS_DIR
flow.RUNS_DIR = TMP

SEEN = {"docs": None, "fail": False, "calls": 0}


def stub_indexer(docs, store_dir, log_id, profile):
    SEEN["calls"] += 1
    if SEEN["fail"]:
        raise RuntimeError("stub boom")
    SEEN["docs"] = [(n, t) for n, t in docs]
    os.makedirs(store_dir, exist_ok=True)
    with open(os.path.join(store_dir, "index.json"), "w",
              encoding="utf-8") as f:
        json.dump({"stub": True}, f)
    return {"llm_calls": 3, "profile": profile or "stub"}


def stub_retriever(store_dir, question, log_id, profile):
    return "stub memory says: %s" % question[:40]


mem._INDEXER = stub_indexer
mem._RETRIEVER = stub_retriever


def wfile(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def wait_mem(run_id, agent, want=("ready", "failed"), timeout=15,
             since=None):
    """Poll until STATUS is fresh (mtime > since) and in want, so a
    rebuild never reads the previous build's STATUS."""
    sp = os.path.join(TMP, run_id, "memory", agent, "STATUS.json")
    end = time.time() + timeout
    while time.time() < end:
        try:
            fresh = since is None or os.path.getmtime(sp) > since
        except OSError:
            fresh = False
        st = mem.memory_state(run_id, agent, TMP)
        if fresh and st["state"] in want:
            return st
        time.sleep(0.05)
    return mem.memory_state(run_id, agent, TMP)


def status_mtime(run_id, agent):
    try:
        return os.path.getmtime(os.path.join(
            TMP, run_id, "memory", agent, "STATUS.json"))
    except OSError:
        return 0


def seed_stage(run_id, node, part=None, marker="v1"):
    d = os.path.join(TMP, run_id, node,
                     ("p%d" % part) if part else "")
    wfile(os.path.join(d, "INPUTS.md"), "# inputs %s\n" % marker)
    wfile(os.path.join(d, "result.json"),
          json.dumps({"categories": {}, "marker": marker}))
    wfile(os.path.join(d, "report.md"), "# report %s\n" % marker)


try:
    # 1. story agent: approve -> queued -> ready, all 3 files indexed.
    seed_stage("r1", "pd_marty")
    out = flow.approve_node("r1", "pd_marty", runs_root=TMP)
    ok(out.get("ok"), "m1 approve marty ok")
    st = wait_mem("r1", "pd_marty")
    ok(st["state"] == "ready", "m1 marty memory ready")
    names = sorted(n for n, _ in (SEEN["docs"] or []))
    ok(names == ["INPUTS.md", "report.md", "result.json"],
       "m1 received + written indexed (%s)" % names)
    ok(mem.memory_state("r1", "pd_marty", TMP)["state"]
       == "ready", "m1 badge state ready")
    mst, _ = office._memory_state(os.path.join(TMP, "r1"),
                                  "pd_marty")
    ok(mst == "ready", "m1 office reads the same state")

    # 2. clones: one part is not enough; all parts merge into one.
    wfile(os.path.join(TMP, "r2", "part_split", "split.json"),
          json.dumps({"parts": [{"no": 1}, {"no": 2}]}))
    seed_stage("r2", "photo_pia", part=1)
    seed_stage("r2", "photo_pia", part=2)
    flow.approve_node("r2", "photo_pia@p1", runs_root=TMP)
    time.sleep(0.5)
    ok(mem.memory_state("r2", "photo_pia", TMP)["state"]
       == "none", "m2 single part builds nothing")
    flow.approve_node("r2", "photo_pia@p2", runs_root=TMP)
    st = wait_mem("r2", "photo_pia")
    ok(st["state"] == "ready", "m2 all parts -> one memory")
    names = sorted(n for n, _ in (SEEN["docs"] or []))
    ok(names == ["p1/INPUTS.md", "p1/report.md",
                 "p1/result.json", "p2/INPUTS.md",
                 "p2/report.md", "p2/result.json"],
       "m2 clones merged (%d docs)" % len(names))
    ok(not os.path.exists(os.path.join(
        TMP, "r2", "memory", "photo_pia@p1")),
       "m2 no per-clone memory dir")

    # 3. hook inert without an indexer.
    mem._INDEXER = None
    seed_stage("r3", "pd_marty")
    flow.approve_node("r3", "pd_marty", runs_root=TMP)
    time.sleep(0.3)
    ok(not os.path.exists(os.path.join(TMP, "r3", "memory")),
       "m3 no indexer -> no build, no thread")
    mem._INDEXER = stub_indexer

    # 4. re-run approval rebuilds fresh, keeps the old log.
    seed_stage("r4", "pd_marty", marker="v1")
    flow.approve_node("r4", "pd_marty", runs_root=TMP)
    ok(wait_mem("r4", "pd_marty")["state"] == "ready",
       "m4 first build ready")
    seed_stage("r4", "pd_marty", marker="v2-CHANGED")
    m4since = status_mtime("r4", "pd_marty")
    flow.approve_node("r4", "pd_marty", runs_root=TMP)
    ok(wait_mem("r4", "pd_marty", since=m4since)["state"]
       == "ready", "m4 rebuild ready")
    texts = " ".join(t for _, t in (SEEN["docs"] or []))
    ok("v2-CHANGED" in texts and "v1" not in texts.replace(
        "v2-CHANGED", ""), "m4 fresh text only, old gone")
    with open(os.path.join(TMP, "r4", "memory", "pd_marty",
                           "log.jsonl"), encoding="utf-8") as f:
        log = f.read()
    ok("mem_rebuilt" in log and log.count("mem_build_done")
       == 2, "m4 previous log kept + rebuilt line")

    # 5. failure -> failed + reason; retry rebuilds.
    SEEN["fail"] = True
    seed_stage("r5", "pd_marty")
    flow.approve_node("r5", "pd_marty", runs_root=TMP)
    st = wait_mem("r5", "pd_marty")
    ok(st["state"] == "failed" and st["error"],
       "m5 failure recorded (%s)" % st["error"])
    SEEN["fail"] = False
    m5since = status_mtime("r5", "pd_marty")
    out = mem.queue_build(
        "r5", "pd_marty",
        mem.default_docs_fn("r5", "pd_marty", TMP),
        runs_root=TMP)
    ok(out.get("ok") and wait_mem("r5", "pd_marty",
                                  since=m5since)["state"]
       == "ready", "m5 retry from current files -> ready")

    # 6. close deletes only the memory; other runs untouched.
    ok(mem.close_run_memory("r1", TMP), "m6 close returns True")
    ok(not os.path.exists(os.path.join(TMP, "r1", "memory")),
       "m6 memory dir gone")
    ok(os.path.isfile(os.path.join(TMP, "r1",
                                   "MEMORY_CLOSED.json")),
       "m6 closed marker left")
    ok(os.path.isfile(os.path.join(TMP, "r1", "pd_marty",
                                   "result.json"))
       and os.path.isfile(os.path.join(TMP, "r1", "pd_marty",
                                       "report.md")),
       "m6 results and reports stay")
    ok(mem.memory_state("r2", "photo_pia", TMP)["state"]
       == "ready", "m6 other run untouched")
    ok(mem.is_closed("r1", TMP)
       and not mem.is_closed("r2", TMP), "m6 closed flag per run")

    # 7. states listing + run cost includes memory usage.
    states = mem.run_memory_states("r2", TMP)
    ok(states.get("photo_pia", {}).get("state") == "ready",
       "m7 states listing")
    cost = flow._run_cost(os.path.join(TMP, "r2"))
    ok(cost.get("llm_calls") == 3,
       "m7 memory cost in run usage (%s)" % cost)

    # 8. server chat gate (in-process handler, stubbed model).
    handler = _srv.Handler.__new__(_srv.Handler)
    captured = {}

    def _cap(code, obj):
        captured["code"] = code
        captured["obj"] = obj

    handler._json = _cap
    real_chat = runner._chat
    real_key = runner.key_present
    seen_system = {}
    runner.key_present = lambda model: True

    def fake_chat(model, messages, tools, timeout=120, **kw):
        seen_system["system"] = messages[0]["content"]
        return {"choices": [{"message": {
            "content": "I remember this project."}}]}

    runner._chat = fake_chat
    try:
        def chat(eid, run_id):
            captured.clear()
            handler._body = json.dumps(
                {"messages": [{"role": "user",
                               "content": "what did you do?"}],
                 "run_id": run_id}).encode()
            handler._api_chat(eid)
            return captured["code"], captured["obj"]

        wfile(os.path.join(TMP, "r6", "memory", "explain_cleo",
                           "STATUS.json"),
              json.dumps({"state": "building"}))
        code, obj = chat("explain_cleo", "r6")
        ok(code == 200 and obj.get("reply")
           == "I remember this project.",
           "m8 building -> 200 interview")
        ok("My memory of this project is still building."
           in seen_system.get("system", ""),
           "m8 building sentence in prompt")
        wfile(os.path.join(TMP, "r6", "memory", "explain_cleo",
                           "STATUS.json"),
              json.dumps({"state": "failed", "error": "no GPU"}))
        code, obj = chat("explain_cleo", "r6")
        ok(code == 200, "m8 failed -> 200 interview")
        ok("My memory of this project failed to build: no GPU."
           in seen_system.get("system", ""),
           "m8 failed sentence in prompt")
        code, obj = chat("explain_cleo", "r2")
        ok(code == 200, "m8 no memory -> 200 interview")
        ok("I have not worked on this project yet."
           in seen_system.get("system", ""),
           "m8 not-yet sentence in prompt")
        ok("# Cleo" in seen_system.get("system", "")
           and "PROFILE CARD" in seen_system.get("system", ""),
           "m8 interview prompt holds the profile")
        code, obj = chat("explain_cleo", "no-such-run")
        ok(code == 404, "m8 unknown run -> 404")
        code, obj = chat("photo_pia", "r1")
        ok(code == 200, "m8 closed project -> 200 interview")
        ok("My memory of this project was deleted when the "
           "project closed." in seen_system.get("system", ""),
           "m8 closed sentence in prompt")
        code, obj = chat("photo_pia", "r2")
        ok(code == 200 and obj.get("reply")
           == "I remember this project.",
           "m8 ready -> 200 reply")
        ok("PROJECT MEMORY" in seen_system.get("system", "")
           and "stub memory says" in seen_system.get(
               "system", "")
           and "UNAVAILABLE" not in seen_system.get(
               "system", ""),
           "m8 memory context in the prompt")
        captured.clear()
        handler._body = json.dumps(
            {"messages": [{"role": "user",
                           "content": "hi"}]}).encode()
        handler._api_chat("explain_cleo")
        ok(captured["code"] == 200
           and "PROFILE CARD" in seen_system.get("system", ""),
           "m8 legacy chat without run still works")
    finally:
        runner._chat = real_chat
        runner.key_present = real_key

    # 9. Sam's memory collected from the consultation.
    odir = os.path.join(ROOT, "orders", "ord-mem9-001")
    os.makedirs(odir, exist_ok=True)
    with open(os.path.join(odir, "chat.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"role": "user",
                            "content": "beginners"}) + "\n")
        f.write(json.dumps({"role": "assistant",
                            "content": "noted"}) + "\n")
    meta9 = {"answers": {"audience": "beginners"},
             "files": {"pc_ref": "pc://source/abc"}}
    wfile(os.path.join(odir, "result.json"), '{"ok": true}')
    wfile(os.path.join(odir, "report.md"), "# req\n")
    docs = mem.collect_sam_docs(odir, meta9)
    names = sorted(n for n, _ in docs)
    ok(names == ["client answers", "consultation chat",
                 "request report.md", "request result.json",
                 "source pdf facts"],
       "m9 sam docs in+out (%s)" % names)
    ok(any("pc://source/abc" in t for _, t in docs),
       "m9 sam source ref kept")
    shutil.rmtree(odir, ignore_errors=True)

    # 10. new-order gate + order close (real orders dir).
    oid10 = "ord-20260230-901"
    odir2 = os.path.join(ROOT, "orders", oid10)
    os.makedirs(odir2, exist_ok=True)
    with open(os.path.join(odir2, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"id": oid10,
                   "assignee": "sales_sam", "status": "consulting",
                   "answers": {}, "files": {}}, f)
    wfile(os.path.join(TMP, "r10", "STATUS.json"),
          json.dumps({"order_id": oid10}))
    seed_stage("r10", "pd_marty")
    mem.build_memory("r10", "pd_marty",
                     [("result.json", "x")], runs_root=TMP)
    with open(os.path.join(odir2, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"id": oid10,
                   "assignee": "sales_sam",
                   "status": "in_production", "answers": {},
                   "files": {}}, f)
    try:
        captured.clear()
        handler._body = json.dumps(
            {"assignee": "sales_sam"}).encode()
        handler._api_order_create()
        ok(captured["code"] == 200
           and captured["obj"].get("created") is False
           and oid10 in captured["obj"].get(
               "open_orders", []),
           "m10 open project blocks new order")
        captured.clear()
        handler._body = json.dumps(
            {"assignee": "sales_sam",
             "force": True}).encode()
        handler._api_order_create()
        ok(captured["code"] == 201
           and captured["obj"].get("created") is True
           and captured["obj"].get("id"),
           "m10 force creates anyway")
        forced = captured["obj"]["id"]
        shutil.rmtree(os.path.join(ROOT, "orders", forced),
                      ignore_errors=True)
        captured.clear()
        handler._body = b"{}"
        handler._api_order_close(oid10)
        ok(captured["code"] == 200
           and captured["obj"].get("runs") == ["r10"],
           "m10 order close lists its runs")
        with open(os.path.join(odir2, "meta.json"),
                  encoding="utf-8") as f:
            meta10 = json.load(f)
        ok(meta10.get("closed") is True
           and not os.path.exists(os.path.join(
               TMP, "r10", "memory"))
           and os.path.isfile(os.path.join(
               TMP, "r10", "pd_marty", "result.json")),
           "m10 close: order marked, memory gone, results stay")
        ok(oid10 not in handler._open_orders(),
           "m10 closed order no longer blocks")
    finally:
        shutil.rmtree(odir2, ignore_errors=True)

    # 11. memory folders are git-ignored.
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q",
             "runs/r2/memory/photo_pia/STATUS.json"],
            cwd=ROOT, timeout=30)
        ok(r.returncode == 0, "m11 runs/ git-ignored")
    except (OSError, subprocess.SubprocessError):
        ok(False, "m11 runs/ git-ignored")
finally:
    mem._INDEXER = None
    mem._RETRIEVER = None
    flow.RUNS_DIR = REAL_RUNS
    shutil.rmtree(TMP, ignore_errors=True)

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
