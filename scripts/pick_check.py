"""Pick/search/scope checks (stdlib only, Tavily stubbed).

Run: python scripts/pick_check.py. Covers pc_search_*, pc_pick_*,
pc_read_* and picks-scoped open_ref against a temp root. No sockets,
no model calls.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
os.makedirs(tempfile.tempdir, exist_ok=True)
from agents._frame import pc  # noqa: E402
from agents._frame import tools as tmod  # noqa: E402

FAILS = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


tmp = tempfile.mkdtemp()
pc.ROOT_OVERRIDE = tmp
old_search, old_extract = tmod._tavily_search, tmod._tavily_extract
tmod._tavily_search = lambda q, n: [  # noqa: E731 - stub
    {"title": "TWAP Guide", "url": "https://example.com/twap",
     "snippet": "TWAP slices orders."},
    {"title": "Noise", "url": "https://example.com/noise",
     "snippet": "Unrelated."}][:n]
tmod._tavily_extract = lambda u: {  # noqa: E731 - stub
    "title": "TWAP Guide",
    "text": "TWAP slices orders over time.\n\nIt suits patient "
            "traders using VWAP daily."}
try:
    def ctx(agent, producer="explain_cleo", order="ord-20261030-001"):
        rd = os.path.join(tmp, "rundir", producer)
        return {"agent_dir": os.path.join(ROOT, "agents", agent),
                "producer": producer, "order_id": order,
                "run_id": "r1", "run_dir": rd}

    c = ctx("explain_cleo")
    s = tmod.pc_search_theory(c, {"query": "twap", "max_results": 1})
    ok(s["query"] == "twap" and len(s["hits"]) == 1
       and s["hits"][0]["url"] == "https://example.com/twap",
       "search returns stubbed hits")
    evs = [json.loads(ln) for ln in open(
        os.path.join(c["run_dir"], "research.jsonl"), encoding="utf-8")]
    ok(evs[0]["ev"] == "search" and evs[0]["tool"] == "pc_search_theory"
       and evs[0]["hits"][0]["title"] == "TWAP Guide",
       "search hits logged, nothing stored")
    ok("error" in tmod.pc_search_theory(c, {"query": "  "}),
       "empty query rejected")
    ok(pc._web_urls("theory", root=tmp) == {},
       "search stores nothing in the PC")

    p = tmod.pc_pick_theory(c, {"url": "https://example.com/twap",
                                "part_id": "p1",
                                "why_important": "core method",
                                "how_to_use": "explain simply"})
    ok(not p.get("error") and p["duplicate"] is False
       and p["ref"].startswith("pc://theory/")
       and p["paras"] == 2,
       "pick ingests and returns ref")
    ent = pc.load_entry_by_ref(p["ref"], root=tmp)
    ok(ent["url"] == "https://example.com/twap"
       and ent["added_by"] == "explain_cleo"
       and [x["addr"] for x in ent["paragraphs"]] == ["p1", "p2"],
       "pick entry keeps provenance + pN addrs")
    evs = [json.loads(ln) for ln in open(
        os.path.join(c["run_dir"], "research.jsonl"), encoding="utf-8")]
    pk = evs[-1]
    ok(pk["ev"] == "pick" and pk["ref"] == p["ref"]
       and pk["part_id"] == "p1" and pk["picked_by"] == "explain_cleo"
       and pk["order_id"] == "ord-20261030-001"
       and pk["run_id"] == "r1" and pk["reason"] == "core method",
       "pick logs provenance")
    p2 = tmod.pc_pick_theory(c, {"url": "https://example.com/other",
                                 "part_id": "p2",
                                 "why_important": "again",
                                 "how_to_use": "reuse"})
    ok(p2["duplicate"] is True and p2["ref"] == p["ref"],
       "same content re-pick is a no-op")
    miss = tmod.pc_pick_theory(c, {"url": "https://example.com/x"})
    ok("part_id" in miss.get("error", "")
       and "why_important" in miss.get("error", ""),
       "pick names missing args")
    st = tmod.research_status(c, {})
    ok(st["searches"] == 1 and st["hits_seen"] == 1
       and st["picks"] == 2 and st["citations"] == 0
       and st["line"] == "STATUS searches=1 hits_seen=1 picks=2 "
                         "citations=0",
       "status counts searches, hits, picks")
    ok(st["parts"]["p1"]["picks"] == [p["ref"]]
       and st["parts"]["p2"]["citations"] == 0,
       "status breaks down per part")
    fresh = ctx("explain_cleo", producer="nobody", order="ord-x")
    st0 = tmod.research_status(fresh, {})
    ok(st0["searches"] == 0 and st0["line"].endswith("citations=0"),
       "status with no log is zeros")

    r = tmod.pc_read_theory(c, {"ref": p["ref"] + "#p2"})
    ok(r.get("text", "").startswith("It suits patient traders"),
       "picker reads whole entry")
    m = ctx("pd_marty", producer="pd_marty")
    ok(tmod.pc_read_theory(m, {"ref": p["ref"]}).get("error", "")
       == "no read grant for theory",
       "read without grant refused")
    a = ctx("plan_ash", producer="plan_ash")
    ok(tmod.pc_read_theory(a, {"ref": p["ref"]}).get("error", "")
       == "not picked for this order",
       "later agent refused outside pick set")
    rd = os.path.join(tmp, "runs", "rr1")
    os.makedirs(os.path.join(rd, "explain_cleo"))
    json.dump({"order_id": "ord-20261030-001"},
              open(os.path.join(rd, "STATUS.json"), "w"))
    json.dump({"categories": {"concepts": {"data": {"parts": [
        {"picks": [{"ref": p["ref"]}]}]}}}},
              open(os.path.join(rd, "explain_cleo", "result.json"),
                   "w"))
    r2 = tmod.pc_read_theory(a, {"ref": p["ref"] + "#p1"})
    ok(r2.get("text", "").startswith("TWAP slices"),
       "later agent reads picked entry")
    o = tmod.open_ref(a, {"ref": p["ref"] + "#p2"})
    ok(o.get("text", "").startswith("It suits patient traders"),
       "open_ref honors pick scope (allow)")
    other = pc.ingest_theory("https://example.com/elsewhere", "Else",
                             "", "", "2026-10-30T00:00:00",
                             "explain_cleo",
                             "Elsewhere content body.\n\nMore here.",
                             root=tmp)
    ok(tmod.open_ref(a, {"ref": other["ref"]}).get("error", "")
       == "not picked for this order",
       "open_ref honors pick scope (deny)")

    saved = os.environ.pop("TAVILY_API_KEY", None)
    try:
        tmod._tavily_search = old_search
        try:
            tmod._tavily_search("x", 1)
            ok(False, "missing key raises")
        except RuntimeError as exc:
            ok("TAVILY_API_KEY missing" in str(exc),
               "missing key raises clean error")
    finally:
        if saved is not None:
            os.environ["TAVILY_API_KEY"] = saved
finally:
    tmod._tavily_search, tmod._tavily_extract = old_search, old_extract
    pc.ROOT_OVERRIDE = None

print("FAILURES: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
