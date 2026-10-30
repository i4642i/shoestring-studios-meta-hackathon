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
       == "no access to this item",
       "unlisted agent refused before listing")
    rd = os.path.join(tmp, "runs", "rr1")
    os.makedirs(os.path.join(rd, "explain_cleo"))
    json.dump({"order_id": "ord-20261030-001"},
              open(os.path.join(rd, "STATUS.json"), "w"))
    json.dump({"categories": {"concepts": {"data": {"parts": [
        {"picks": [{"ref": p["ref"], "title": "TWAP Guide",
                    "why_important": "core method",
                    "how_to_use": "explain simply"}]}]}}}},
              open(os.path.join(rd, "explain_cleo", "result.json"),
                   "w"))
    auto = pc.load_entry_by_ref(p["ref"], root=tmp)
    ok(any(r.get("agent") == "explain_cleo"
           and r.get("order_id") == "ord-20261030-001"
           and r.get("kind") == "full"
           for r in auto.get("recipients", [])),
       "picker auto-listed on pick (full)")
    ok(tmod.pc_read_theory(a, {"ref": p["ref"] + "#p1"}).get("error")
       == "no access to this item",
       "picked but unlisted agent refused")
    cleo = ctx("explain_cleo")
    grant = tmod.pc_set_recipients(cleo, {"ref": p["ref"],
                                          "map": ["plan_ash"]})
    ok("error" not in grant
       and any(r.get("agent") == "plan_ash"
               and r.get("kind") == "map"
               for r in grant.get("recipients", [])),
       "picker lists ash (map) via the tool")
    ok("only Sam grants full" in tmod.pc_set_recipients(
        cleo, {"ref": p["ref"], "full": ["plan_ash"]}).get("error", ""),
       "non-sam cannot grant full")
    ok("unknown agents" in tmod.pc_set_recipients(
        cleo, {"ref": p["ref"], "map": ["nope"]}).get("error", ""),
       "unknown listee refused")
    _rpc, rid, _frag = pc.parse_ref(p["ref"])
    pc.set_recipients("theory", rid, "ord-20261030-001",
                      ["voice_wren"], "plan_ash", kind="map",
                      parts=[p["ref"] + "#p1"])
    ok("widen" in tmod.pc_set_recipients(
        ctx("voice_wren", "voice_wren"), {"ref": p["ref"],
                                          "map": ["board_penn"]}).get(
                                              "error", ""),
       "parts-limited lister cannot widen")
    r2 = tmod.pc_read_theory(a, {"ref": p["ref"] + "#p1"})
    ok(r2.get("text", "").startswith("TWAP slices"),
       "later agent reads picked entry")
    o = tmod.open_ref(a, {"ref": p["ref"] + "#p2"})
    ok(o.get("text", "").startswith("It suits patient traders"),
       "open_ref honors listing (allow)")
    other = pc.ingest_theory("https://example.com/elsewhere", "Else",
                             "", "", "2026-10-30T00:00:00",
                             "explain_cleo",
                             "Elsewhere content body.\n\nMore here.",
                             root=tmp)
    ok(tmod.open_ref(a, {"ref": other["ref"]}).get("error", "")
       == "no access to this item",
       "open_ref honors listing (deny)")
    atext, ameta = pc.prompt_chunks_for("plan_ash", "ord-20261030-001",
                                        [], os.path.join(tmp, "runs"))
    ok(ameta["included"] == [p["ref"]]
       and "core method" in atext
       and "TWAP slices" not in atext,
       "ash prompt has the theory map, not the text")
    _pt, pmeta = pc.prompt_chunks_for("board_penn", "ord-20261030-001",
                                      [], os.path.join(tmp, "runs"))
    ok(pmeta["included"] == [] and pmeta["denied"] == [p["ref"]],
       "penn has nothing until ash lists him")
    src = pc.ingest_source("ord-20261030-001", "s.pdf",
                           "2026-10-30T00:00:00", "sales_sam",
                           ["1.1 Alpha\nAlpha body here.",
                            "1.2 Beta\nBeta body here."], [], [], 0,
                           root=tmp)
    pc.set_recipients("source", src["doc_id"], "ord-20261030-001",
                      ["plan_ash"], "sales_sam", kind="map")
    draft = {"scenes": [{"n": 1, "handoff": [
        {"ref": p["ref"] + "#p1", "to": ["board_penn"],
         "why": "w", "how_to_use": "h"},
        {"ref": src["ref"] + "#s1.1", "to": ["board_penn"],
         "why": "w", "how_to_use": "h"}]}]}
    ap = pc.apply_handoff("ord-20261030-001", draft)
    ok(ap.get("grants") == 2, "handoff applies map+parts rows")
    ptext, pmeta2 = pc.prompt_chunks_for(
        "board_penn", "ord-20261030-001", [src["ref"]],
        os.path.join(tmp, "runs"))
    ok(sorted(pmeta2["included"]) == sorted([p["ref"], src["ref"]])
       and src["ref"] + "#s1.1" in ptext
       and p["ref"] + "#p1" in ptext
       and src["ref"] + "#s1.2" not in ptext
       and "Beta body here." not in ptext,
       "penn prompt holds exactly the handed parts")
    wtext, wmeta = pc.prompt_chunks_for(
        "voice_wren", "ord-20261030-001", [src["ref"]],
        os.path.join(tmp, "runs"))
    ok(src["ref"] not in str(wmeta["included"])
       and "Alpha body here." not in wtext,
       "wren gets no source part before her handoff")
    wpart = src["ref"] + "#s1.2/p2"
    ap2 = pc.apply_handoff("ord-20261030-001",
                           {"scenes": [{"n": 2, "handoff": [
                               {"ref": wpart, "to": ["voice_wren"],
                                "why": "w", "how_to_use": "h"}]}]})
    ok(ap2.get("grants") == 1, "map-only ash hands a part to wren")
    w = ctx("voice_wren", "voice_wren")
    ok(tmod.pc_read_source(w, {"ref": wpart}).get("text", "")
       == "Beta body here.",
       "wren quotes inside the part")
    ok(tmod.pc_read_source(
        w, {"ref": src["ref"] + "#s1.1/p1"}).get("error")
       == "no access to this item",
       "wren refused outside the part")
    bad = pc.apply_handoff("ord-20261030-001",
                           {"scenes": [{"n": 3, "handoff": [
                               {"ref": other["ref"] + "#p1",
                                "to": ["voice_wren"],
                                "why": "w", "how_to_use": "h"}]}]})
    ok("holds no row" in bad.get("error", ""),
       "handoff outside ash rows fails clean")

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
