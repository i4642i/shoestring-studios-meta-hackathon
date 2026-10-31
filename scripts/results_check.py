"""Focused checks for agents/_frame/results.py (Step 1). Stdlib only.

Run: python scripts/results_check.py. Writes only to a temp dir.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
from agents._frame import results
from agents._frame.schemas import render_cite_md
from agents._frame.tools import (write_cases, write_concepts,
                                    write_narration, write_request,
                                    write_storyboard,
                                    write_storyboard_draft,
                                    write_structure)

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def raises(fn, msg):
    try:
        fn()
    except RuntimeError:
        ok(True, msg)
        return
    ok(False, msg)


REQ = {"order_id": "o1",
       "client_answers": {"audience": "a", "length": "b", "depth": "c",
                         "theme": "d", "source": "e"},
       "source_summary": "s", "production_notes": ["n"],
       "open_questions": []}

reg = results.registry()
ok(set(reg) == {"brief", "cases", "concept", "concepts", "source",
                "request", "structure",
                "video", "storyboard_draft", "storyboard",
                "narration", "style_guide", "photo_picks", "gen_picks",
                "anim_picks", "slide_draft", "render_log",
                "storyboard_table"},
   "registry has 18 incl v8 cats")
ok(reg["source"]["version"] == 3 and reg["structure"]["version"] == 3
   and reg["storyboard"]["version"] == 2
   and reg["narration"]["version"] == 2
   and all(reg[c]["version"] == 1 for c in reg
           if c not in ("source", "structure", "storyboard",
                        "narration")),
   "source v3 + structure v3 + wren/penn v2, rest v1")

r = results.make_result("sales_sam", "o1", "r1", {"request": dict(REQ)})
ok(r["status"] == "unverified" and r["format_version"] == 1
   and r["categories"]["request"]["version"] == 1, "make_result wraps")
ok(results.check_result(r) == [], "fresh result validates")
raises(lambda: results.make_result("x", "o", "r", {"nope": {}}),
       "unknown category raises")
raises(lambda: results.make_result("x", "o", "r", {"request": []}),
       "non-dict data raises")

bad = dict(r)
del bad["run_id"]
ok(any("run_id" in e for e in results.check_result(bad)),
   "missing header key caught")
bad = dict(r, format_version=2)
ok(any("format_version" in e for e in results.check_result(bad)),
   "bad format_version caught")
bad = dict(r, status="maybe")
ok(any("status" in e for e in results.check_result(bad)),
   "bad status caught")
bad = {"producer": "x", "format_version": 1, "order_id": "o",
       "run_id": "r", "created_at": "t", "status": "unverified",
       "reviewed_by": None, "reviewed_at": None,
       "verified_by": None, "verified_at": None,
       "categories": {"request": {"version": 2, "data": dict(REQ)}}}
ok(any("not in accepted" in e for e in results.check_result(bad)),
   "version mismatch refuses")
ok(results.check_result(bad, {"request": [1, 2]}) == [],
   "accepted versions honored")
bad2 = dict(REQ)
del bad2["production_notes"]
r2 = results.make_result("sales_sam", "o1", "r1", {"request": bad2})
ok(any("production_notes" in e for e in results.check_result(r2)),
   "bad payload caught")

results.promote_checked(r)
ok(r["status"] == "checked", "promote to checked")
results.promote_checked(r)
ok(r["status"] == "checked", "promote idempotent")
results.set_reviewed(r, "board_vera")
ok(r["status"] == "reviewed" and r["reviewed_by"] == "board_vera"
   and r["reviewed_at"], "reviewed stamps reviewer")
raises(lambda: results.promote_checked(r), "promote reviewed refuses")
raises(lambda: results.set_reviewed(
    results.make_result("x", "o", "r", {"request": dict(REQ)}), "v"),
    "review unverified refuses")
raises(lambda: results.set_verified(r, "sales_sam"),
       "non-developer verify refuses")
raises(lambda: results.set_verified(
    results.make_result("x", "o", "r", {"request": dict(REQ)}), "developer"),
    "verify unverified refuses")
results.set_verified(r, "developer")
ok(r["status"] == "verified" and r["verified_by"] == "developer"
   and r["verified_at"], "developer verify stamps")
raises(lambda: results.set_verified(r, "developer"), "re-verify refuses")
ok(any("reviewed_by" in e for e in results.check_result(
    dict(r, reviewed_by=None))), "verified needs reviewed_by")

tmp = tempfile.mkdtemp(prefix="rescheck_")
p = results.save_result(tmp, r)
ok(os.path.basename(p) == "result.json"
   and results.load_result(p)["status"] == "verified", "save/load roundtrip")
raises(lambda: results.save_result(tmp, dict(r, status="checked")),
       "overwrite verified refuses")

wdir = tempfile.mkdtemp(prefix="writecheck_")
ctx = {"run_dir": wdir, "agent_dir": os.path.join(ROOT, "agents",
                                                  "sales_sam"),
       "producer": "sales_sam", "order_id": "o1", "run_id": "r9"}
from agents._frame import pc as _pc
samroot = tempfile.mkdtemp(prefix="samroot_")
_pc.ROOT_OVERRIDE = samroot
sent = _pc.ingest_source("o1", "s.pdf", "2026-10-30T00:00:00",
                         "sales_sam",
                         ["1.1 Alpha\nSource alpha text."], [], [], 0,
                         root=samroot)
_pc.set_recipients("source", sent["doc_id"], "o1",
                   ["sales_sam"], "sales_sam", kind="full", root=samroot)
_pc.set_recipients("source", sent["doc_id"], "o1",
                   ["pd_marty"], "sales_sam", kind="full", root=samroot)
sendp = os.path.join(wdir, "send.json")
with open(sendp, "w", encoding="utf-8") as f:
    json.dump({"ref": sent["ref"], "doc_id": sent["doc_id"],
               "at": "t"}, f)
out = write_request(ctx, {"request": dict(REQ)})
ok(out.get("ok") and out.get("output") == "result.json"
   and os.path.isfile(os.path.join(wdir, "result.json")),
   "write_request emits result.json")
saved = results.load_result(os.path.join(wdir, "result.json"))
ok(saved["producer"] == "sales_sam" and saved["run_id"] == "r9"
   and saved["status"] == "unverified"
   and saved["categories"]["request"]["data"]["order_id"] == "o1",
   "request envelope header + data")
ok(set(saved["categories"]) == {"request"},
   "write_request saves request only (no source category)")
os.remove(sendp)
no_send = write_request(ctx, {"request": dict(REQ)})
ok(no_send.get("ok") is False
   and "pc_send_source" in " ".join(no_send.get("errors", [])),
   "write_request without send refuses")
with open(sendp, "w", encoding="utf-8") as f:
    json.dump({"ref": sent["ref"], "doc_id": sent["doc_id"],
               "at": "t"}, f)
ep = os.path.join(samroot, "storage", "_pc", "source", "entries",
                  sent["doc_id"], "entry.json")
with open(ep, encoding="utf-8") as f:
    ent0 = json.load(f)
ent0["recipients"] = [r for r in ent0["recipients"]
                       if r["order_id"] != "o1"]
with open(ep, "w", encoding="utf-8") as f:
    json.dump(ent0, f)
no_rec = write_request(ctx, {"request": dict(REQ)})
ok(no_rec.get("ok") is False
   and "pc_set_recipients" in " ".join(no_rec.get("errors", [])),
   "write_request without recipients refuses")
_pc.set_recipients("source", sent["doc_id"], "o1",
                   ["sales_sam"], "sales_sam", kind="full", root=samroot)
_pc.set_recipients("source", sent["doc_id"], "o1",
                   ["pd_marty"], "sales_sam", kind="full", root=samroot)
bad = dict(REQ)
del bad["order_id"]
ok(write_request(ctx, {"request": bad}).get("ok") is False,
   "write_request invalid refuses")
_pc.ROOT_OVERRIDE = None

mdp = os.path.join(wdir, "input.md")
with open(mdp, "w", encoding="utf-8") as f:
    f.write("# T\n\n## 1.1 Alpha\n\ntext\n\n## 1.2 Beta\n\ntext\n")
CONCEPT = {"common_theme": "t", "core_question": "q",
           "viewer_takeaway": "v", "intent_overall": "o"}
SREF = "pc://source/abcd1234abcd1234"
struct = {"source_ref": SREF,
          "parts": [{"id": "p1", "heading": "1.1 Alpha",
                     "ref": SREF + "#s1.1", "covers": "x",
                     "keywords": ["k"]},
                    {"id": "p2", "heading": "1.2 Beta",
                     "ref": SREF + "#s1.2", "covers": "y",
                     "keywords": ["k"]}],
          "links": [{"from": "p1", "to": "p2", "why": "w"}],
          "duration": {"total_s": 60,
                       "parts": [{"part_id": "p1", "seconds": 30,
                                  "why": "w"},
                                 {"part_id": "p2", "seconds": 30,
                                  "why": "w"}]}}

ctx2 = dict(ctx, input_md=mdp, producer="pd_marty", run_id="r10")
out2 = write_structure(ctx2, {"result": {"concept": dict(CONCEPT),
                                      "structure": struct}})
ok(out2.get("ok") and out2.get("output") == "result.json",
   "write_structure emits result.json")
saved2 = results.load_result(os.path.join(wdir, "result.json"))
ok("structure" in saved2["categories"]
   and "concept" in saved2["categories"]
   and results.check_result(saved2) == [],
   "concept+structure envelope validates")
badc = dict(CONCEPT)
del badc["core_question"]
ok(write_structure(ctx2, {"result": {"concept": badc,
                                    "structure": struct}}).get("ok")
   is False, "write_structure bad concept refuses")
badp = json.loads(json.dumps(struct))
badp["parts"][0]["ref"] = "pc://source/other#s1.1"
ok(write_structure(ctx2, {"result": {"concept": dict(CONCEPT),
                                    "structure": badp}}).get("ok")
   is False, "write_structure foreign ref refuses")
ok(write_structure(ctx2, {"structure": struct}).get("ok") is False,
   "write_structure old shape refuses")
badd = json.loads(json.dumps(struct))
del badd["duration"]
ok(write_structure(ctx2, {"result": {"concept": dict(CONCEPT),
                                    "structure": badd}}).get("ok")
   is False, "write_structure duration missing refuses")
badd = json.loads(json.dumps(struct))
badd["duration"]["parts"][0]["seconds"] = 31
ok("sum to 61" in " ".join(write_structure(
    ctx2, {"result": {"concept": dict(CONCEPT),
                     "structure": badd}}).get("errors", [])),
   "write_structure duration sum enforced")
men = _pc.ingest_source("o1", "m.pdf", "2026-10-30T00:00:00",
                        "sales_sam",
                        ["1.1 Alpha\nAlpha body.",
                         "1.2 Beta\nBeta body."], [], [], 0,
                        root=samroot)
mstruct = {"source_ref": men["ref"],
           "parts": [{"id": "p1", "heading": "1.1 Alpha",
                      "ref": men["ref"] + "#s1.1", "covers": "x",
                      "keywords": ["k"]},
                     {"id": "p2", "heading": "1.2 Beta",
                      "ref": men["ref"] + "#s1.2", "covers": "y",
                      "keywords": ["k"]}],
           "links": [{"from": "p1", "to": "p2", "why": "w"}],
           "duration": {"total_s": 60,
                        "parts": [{"part_id": "p1", "seconds": 30,
                                   "why": "w"},
                                  {"part_id": "p2", "seconds": 30,
                                   "why": "w"}]}}
_pc.set_recipients("source", men["doc_id"], "o1", ["pd_marty"],
                   "sales_sam", kind="full", root=samroot)
uen = _pc.ingest_source("o1", "u.pdf", "2026-10-30T00:00:00",
                        "sales_sam", ["1.1 Gamma\nGamma body."],
                        [], [], 0, root=samroot)
ustruct = {"source_ref": uen["ref"],
           "parts": [{"id": "p1", "heading": "1.1 Gamma",
                      "ref": uen["ref"] + "#s1.1", "covers": "x",
                      "keywords": ["k"]}],
           "links": [],
           "duration": {"total_s": 10,
                        "parts": [{"part_id": "p1", "seconds": 10,
                                   "why": "w"}]}}
mdp2 = os.path.join(wdir, "other.md")
with open(mdp2, "w", encoding="utf-8") as f:
    f.write("# T\n\n## 9.9 Else\n\ntext\n")
_pc.ROOT_OVERRIDE = samroot
ctx3 = dict(ctx2, input_md=mdp2, run_id="r11")
ok(write_structure(ctx3, {"result": {"concept": dict(CONCEPT),
                                    "structure": mstruct}}).get("ok")
   is True, "entry text wins over input file")
mshort = json.loads(json.dumps(mstruct))
del mshort["parts"][1]
ok(write_structure(ctx3, {"result": {"concept": dict(CONCEPT),
                                    "structure": mshort}}).get("ok")
   is False, "entry coverage enforced (missing part)")
ok("not listed" in " ".join(write_structure(
    ctx3, {"result": {"concept": dict(CONCEPT),
                     "structure": ustruct}}).get("errors", [])),
   "unlisted source_ref refuses")
_pc.ROOT_OVERRIDE = None
ok(os.path.isfile(os.path.join(wdir, "report.md")),
   "writers also write report.md")

rep = results.render_report(saved)
ok("generated from r9, do not edit" in rep
   and "## request (v1)" in rep and "Client answers" in rep,
   "request report renders with stamp")
rep2 = results.render_report(saved2)
ok("## structure (v3)" in rep2 and "1.1 Alpha" in rep2
   and "p1 -> p2" in rep2 and "## concept (v1)" in rep2
   and "Time plan" in rep2,
   "structure+concept report renders")
ok(render_cite_md("pc://article/ab12#p3", "quoted")
   == "[quoted](api/ref?ref=pc%3A%2F%2Farticle%2Fab12%23p3)",
   "citation link format")
VID = {"file": {"path": "output/o1/r1/video.mp4", "size_bytes": 10,
                "format": "mp4", "resolution": "1920x1080"},
       "duration_s": 12.5, "built_from": "r0",
       "scenes": [{"n": 1, "start_s": 0.0, "end_s": 12.5,
                   "lines": [{"text": "hi", "start_s": 0.0, "end_s": 4.2,
                              "citations": [{"ref": "pc://a/b#p1",
                                             "quote": "q"}]}]}]}
rv = results.make_result("postprocess", "o1", "r1", {"video": VID})
ok(results.check_result(rv) == [], "video envelope validates")
ok("api/ref?ref=pc%3A%2F%2Fa%2Fb%23p1" in results.render_report(rv),
   "video report links citations")
rvx = results.make_result("postprocess", "o1", "r1", {"video": VID})
rvx["categories"]["video"]["version"] = 99
ok("```json" in results.render_report(rvx), "unknown version falls back")

# ---- Cleo/Rex writers (temp PC storage, verbatim vs fixtures) ----
from agents._frame import pc as _pc
pcdir = tempfile.mkdtemp(prefix="writerpc_")
rdir = tempfile.mkdtemp(prefix="writerrun_")
_pc.ROOT_OVERRIDE = pcdir
try:
    src = _pc.ingest_source("o20", "s.pdf", "2026-10-30T00:00:00",
                            "sales_sam",
                            ["1.1 Alpha\nSource alpha text states facts "
                             "clearly.",
                             "1.2 Beta\nSource beta text stays simple."],
                            [], [], 0, root=pcdir)
    the = _pc.ingest_theory("https://ex.test/t1", "Theory One", "ex.test",
                            "2024-01-02", "2026-10-30T00:00:00",
                            "explain_cleo",
                            "Theory one explains slowly. Markets adapt "
                            "slowly over time.", root=pcdir)
    the2 = _pc.ingest_theory("https://ex.test/t2", "Theory Two",
                             "ex.test", "2024-03-04",
                             "2026-10-30T00:00:00", "explain_cleo",
                             "Second theory drifts yearly. Nothing else "
                             "matters.", root=pcdir)
    art = _pc.ingest_article("https://ex.test/a1", "Case One", "ex.test",
                             "2023-05-06", "2026-10-30T00:00:00",
                             "case_rex",
                             "In 2023 the mill trial failed loudly. "
                             "Workers walked out twice.", root=pcdir)
    SREF = src["ref"]
    TREF = the["ref"]
    TREF2 = the2["ref"]
    AREF = art["ref"]
    with open(os.path.join(rdir, "research.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"ev": "pick", "ref": TREF}) + "\n")
        f.write(json.dumps({"ev": "search", "query": "q"}) + "\n")
    cctx = {"run_dir": rdir, "agent_dir": os.path.join(ROOT, "agents",
                                                       "explain_cleo"),
            "producer": "explain_cleo", "order_id": "o20",
            "run_id": "rw1"}
    CONCEPTS = {"parts": [{
        "part_id": "p1",
        "concept_name": "Alpha",
        "easy_explanation": "Alpha in plain words, told slowly for a "
                            "curious adult meeting the topic cold for the "
                            "very first time without any background at all, "
                            "with each idea in its own short sentence.",
        "why_it_came_about": "Because beta.",
        "analogy_or_example": "Like gamma.",
        "common_misunderstanding": "Not delta.",
        "claims": [{"text": "Alpha states facts.",
                    "citations": [{"ref": SREF + "#s1.1/p2",
                                   "quote": "states facts clearly"}]}],
        "picks": [{"ref": TREF, "title": "Theory One",
                   "why_important": "Explains alpha.",
                   "how_to_use": "Cite for p1.",
                   "evidence": {"ref": TREF + "#p1",
                                "quote": "Markets adapt slowly"},
                   "priority": "must"}],
        "gaps": []}]}
    outc = write_concepts(cctx, {"concepts": CONCEPTS})
    ok(outc.get("ok"), "write_concepts accepts verbatim report")
    wevs = [json.loads(ln) for ln in open(
        os.path.join(rdir, "research.jsonl"), encoding="utf-8")]
    ok(any(e.get("ev") == "citations" and e.get("part_id") == "p1"
           and len(e.get("refs", [])) == 2 for e in wevs),
       "write_concepts logs citations")
    savedc = results.load_result(os.path.join(rdir, "result.json"))
    ok(savedc["categories"]["concepts"]["version"] == 1
       and results.check_result(savedc) == [],
       "concepts envelope validates")
    repc = results.render_report(savedc)
    ok("## concepts (v1)" in repc and "Alpha in plain words" in repc
       and "api/ref?ref=" in repc
       and "](api/ref?ref=pc%3A%2F%2Ftheory" in repc,
       "concepts report renders")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["claims"][0]["citations"][0]["quote"] = \
        "states myths loudly"
    ok("verbatim" in " ".join(write_concepts(
        cctx, {"concepts": bad}).get("errors", [])),
       "write_concepts invented quote refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["claims"][0]["citations"][0]["ref"] = SREF
    ok("whole entry" in " ".join(write_concepts(
        cctx, {"concepts": bad}).get("errors", [])),
       "write_concepts whole-entry ref refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["claims"][0]["citations"] = []
    ok(write_concepts(cctx, {"concepts": bad}).get("ok") is False,
       "write_concepts citationless claim refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["picks"][0]["ref"] = AREF
    ok("theory PC" in " ".join(write_concepts(
        cctx, {"concepts": bad}).get("errors", [])),
       "write_concepts article pick refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["picks"][0]["ref"] = TREF2
    bad["parts"][0]["picks"][0]["evidence"] = {"ref": TREF2 + "#p1",
                                               "quote": "drifts yearly"}
    ok("never picked" in " ".join(write_concepts(
        cctx, {"concepts": bad}).get("errors", [])),
       "write_concepts unpicked ref refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["picks"] = []
    ok("missing from the report" in " ".join(write_concepts(
        cctx, {"concepts": bad}).get("errors", [])),
       "write_concepts dropped pick refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["part_id"] = "p2"
    ok(write_concepts(cctx, {"concepts": bad}).get("ok") is False,
       "write_concepts part_id gap refuses")
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["easy_explanation"] = "Too short."
    ok("too thin" in " ".join(write_concepts(
        cctx, {"concepts": bad}).get("errors", [])),
       "write_concepts thin explanation refuses")
    with open(os.path.join(rdir, "INPUTS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"received": [{"sender": "pd_marty",
                                 "category": "structure",
                                 "file": "received.pd_marty.structure.json"}]},
                  f)
    with open(os.path.join(rdir, "received.pd_marty.structure.json"), "w",
              encoding="utf-8") as f:
        json.dump({"data": {"source_ref": SREF}}, f)
    with open(os.path.join(_pc.entry_dir("source", src["doc_id"],
                                         root=pcdir), "map.json"),
              "w", encoding="utf-8") as f:
        json.dump({"sections": [{"ref": "s1.1", "omitted": [
            {"what": "number 7", "see": "p2",
             "ref": SREF + "#s1.1/p2"}]}]}, f)
    bad = json.loads(json.dumps(CONCEPTS))
    bad["parts"][0]["claims"][0]["citations"] = []
    errs = write_concepts(cctx, {"concepts": bad}).get("errors", [])
    ok(any(e.startswith("hint: try ") and SREF + "#s1.1/p2" in e
           for e in errs),
       "write_concepts suggests omitted refs")
    with open(os.path.join(rdir, "research.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"ev": "pick", "ref": AREF}) + "\n")
    rctx = dict(cctx, agent_dir=os.path.join(ROOT, "agents", "case_rex"),
                producer="case_rex", run_id="rw2")
    CASES = {"parts": [{
        "part_id": "p1",
        "cases": [{"title": "Mill trial", "kind": "event",
                   "date": "2023-05-06",
                   "summary": "The mill trial failed after three long "
                              "days of loud testimony before a tired jury "
                              "at last.",
                   "fit_why": "Shows failure plainly.",
                   "viewer_hook": "A loud failure.",
                   "claims": [{"text": "Workers walked out.",
                               "citations": [{"ref": AREF + "#p1",
                                              "quote": "walked out twice"}]}]}],
        "picks": [{"ref": AREF, "title": "Case One",
                   "why_important": "Real failure.",
                   "how_to_use": "Illustrate p1.",
                   "evidence": {"ref": AREF + "#p1",
                                "quote": "mill trial failed loudly"},
                   "priority": "should"}],
        "gaps": ["No second case found."]}]}
    outr = write_cases(rctx, {"cases": CASES})
    ok(outr.get("ok"), "write_cases accepts verbatim report")
    savedr = results.load_result(os.path.join(rdir, "result.json"))
    ok(savedr["categories"]["cases"]["version"] == 1
       and results.check_result(savedr) == [],
       "cases envelope validates")
    repr_ = results.render_report(savedr)
    ok("## cases (v1)" in repr_ and "Mill trial" in repr_
       and "api/ref?ref=" in repr_, "cases report renders")
    bad = json.loads(json.dumps(CASES))
    bad["parts"][0]["cases"][0]["kind"] = "rumor"
    ok(write_cases(rctx, {"cases": bad}).get("ok") is False,
       "write_cases bad kind refuses")
    bad = json.loads(json.dumps(CASES))
    bad["parts"][0]["cases"][0]["date"] = "someday"
    ok(write_cases(rctx, {"cases": bad}).get("ok") is False,
       "write_cases dateless case refuses")
    bad = json.loads(json.dumps(CASES))
    bad["parts"][0]["cases"] = []
    ok(write_cases(rctx, {"cases": bad}).get("ok") is False,
       "write_cases empty cases refuses")
    bad = json.loads(json.dumps(CASES))
    bad["parts"][0]["cases"][0]["summary"] = "Too short."
    ok("too thin" in " ".join(write_cases(
        rctx, {"cases": bad}).get("errors", [])),
       "write_cases thin summary refuses")
finally:
    _pc.ROOT_OVERRIDE = None

# ---- stage 3 writers: Ash/Penn/Wren (offline fixtures) ----
stud = tempfile.mkdtemp(prefix="studio_")
_pc.ROOT_OVERRIDE = stud
try:
    sent = _pc.ingest_source("o7", "s.pdf", "2026-10-30T00:00:00",
                             "sales_sam",
                             ["2.1 Motivation\nWhy it matters.",
                              "2.2 Data\nData body here."], [], [], 0,
                             root=stud)
    tpick = _pc.ingest_theory("https://example.com/t1", "T1", "", "",
                              "2026-10-30T00:00:00", "explain_cleo",
                              "Theory core idea.\n\nMore detail.",
                              root=stud)
    _pc.set_recipients("source", sent["doc_id"], "o7", ["plan_ash"],
                       "sales_sam", kind="map", root=stud)
    _pc.set_recipients("theory", tpick["doc_id"], "o7", ["plan_ash"],
                       "explain_cleo", kind="map", root=stud)
    sref, tref = sent["ref"], tpick["ref"]
    STRUCT3 = {"source_ref": sref,
               "parts": [{"id": "p1", "heading": "2.1 Motivation",
                          "ref": sref + "#s2.1", "covers": "x",
                          "keywords": ["k"]},
                         {"id": "p2", "heading": "2.2 Data",
                          "ref": sref + "#s2.2", "covers": "y",
                          "keywords": ["k"]}],
               "links": [{"from": "p1", "to": "p2", "why": "w"}],
               "duration": {"total_s": 100,
                            "parts": [{"part_id": "p1", "seconds": 40,
                                       "why": "w"},
                                      {"part_id": "p2", "seconds": 60,
                                       "why": "w"}]}}
    CONC7 = {"parts": [{"part_id": "p1", "picks": [
        {"ref": tref, "title": "T1", "why_important": "w",
         "how_to_use": "h"}]}]}
    CASES7 = {"parts": []}
    adir = os.path.join(stud, "rundir", "plan_ash")
    os.makedirs(adir)
    for sender, cat, data in (
            ("pd_marty", "structure", STRUCT3),
            ("explain_cleo", "concepts", CONC7),
            ("case_rex", "cases", CASES7)):
        with open(os.path.join(
                adir, "received.%s.%s.json" % (sender, cat)),
                "w", encoding="utf-8") as f:
            json.dump({"sender": sender, "category": cat,
                       "version": 1, "data": data}, f)
    actx = {"run_dir": adir,
            "agent_dir": os.path.join(ROOT, "agents", "plan_ash"),
            "producer": "plan_ash", "order_id": "o7", "run_id": "r7"}
    D = {"total_s": 100, "scenes": [
        {"n": 1, "start_s": 0, "end_s": 40, "part_id": "p1",
         "role": "hook", "viewer_learns": "v", "screen_idea": "s",
         "narration_points": [{"text": "t", "citations": [
             {"ref": sref + "#s2.1/p2",
              "quote": "Why it matters."}]}],
         "materials": [{"ref": sref + "#s2.1", "from": "source",
                        "how_used": "h"}],
         "handoff": [{"ref": sref + "#s2.1/p2", "to": ["board_penn"],
                      "why": "w", "how_to_use": "h"}],
         "next_link": "n"},
        {"n": 2, "start_s": 40, "end_s": 100, "part_id": "p2",
         "role": "explain", "viewer_learns": "v", "screen_idea": "s",
         "narration_points": [{"text": "t", "citations": [
             {"ref": tref + "#p1",
              "quote": "Theory core idea."}]}],
         "materials": [{"ref": tref + "#p1", "from": "theory",
                        "how_used": "h"}],
         "handoff": [{"ref": tref + "#p1", "to": ["voice_wren"],
                      "why": "w", "how_to_use": "h"}],
         "next_link": "end"}],
        "unused_picks": []}
    out7 = write_storyboard_draft(actx, {"storyboard_draft": D})
    ok(out7.get("ok") is True, "ash draft accepts")
    saved7 = results.load_result(os.path.join(adir, "result.json"))
    ok(results.check_result(saved7) == []
       and saved7["categories"]["storyboard_draft"]["version"] == 1,
       "draft envelope validates")
    ok("## storyboard_draft (v1)" in results.render_report(saved7)
       and "Scene 1" in results.render_report(saved7),
       "draft report renders")
    prow = _pc.entry_access(_pc.load_entry_by_ref(sref),
                            "board_penn", "o7")
    ok(prow is not None and prow.get("kind") == "map"
       and prow.get("parts") == [sref + "#s2.1/p2"],
       "draft handoff lists penn with parts")
    bad = json.loads(json.dumps(D))
    bad["scenes"][0]["end_s"] = 39
    ok("contiguity" in " ".join(write_storyboard_draft(
        actx, {"storyboard_draft": bad}).get("errors", [])),
       "draft scene gap refuses")
    bad = json.loads(json.dumps(D))
    bad["scenes"][0]["end_s"] = 20
    bad["scenes"][1]["start_s"] = 20
    ok("15%" in " ".join(write_storyboard_draft(
        actx, {"storyboard_draft": bad}).get("errors", [])),
       "draft part skew refuses")
    bad = json.loads(json.dumps(D))
    bad["scenes"][0]["narration_points"][0]["citations"][0][
        "quote"] = "invented words"
    ok(write_storyboard_draft(
        actx, {"storyboard_draft": bad}).get("ok") is False,
       "draft invented quote refuses")
    bad = json.loads(json.dumps(D))
    bad["scenes"][1]["materials"] = []
    bad["scenes"][1]["handoff"] = []
    ok("neither used nor explained" in " ".join(
        write_storyboard_draft(
            actx, {"storyboard_draft": bad}).get("errors", [])),
       "draft dropped pick refuses")
    bad = json.loads(json.dumps(D))
    bad["scenes"][0]["materials"][0]["from"] = "theory"
    ok("!= ref PC" in " ".join(write_storyboard_draft(
        actx, {"storyboard_draft": bad}).get("errors", [])),
       "draft material from-mismatch refuses")
    bare = dict(actx, run_dir=os.path.join(stud, "rundir", "empty"))
    os.makedirs(bare["run_dir"])
    ok("no structure received" in " ".join(write_storyboard_draft(
        bare, {"storyboard_draft": D}).get("errors", [])),
       "draft without structure refuses")
    wdir = os.path.join(stud, "rundir", "voice_wren")
    os.makedirs(wdir)
    with open(os.path.join(wdir,
                           "received.plan_ash.storyboard_draft.json"),
              "w", encoding="utf-8") as f:
        json.dump({"sender": "plan_ash", "category": "storyboard_draft",
                   "version": 1, "data": D}, f)
    wctx = {"run_dir": wdir,
            "agent_dir": os.path.join(ROOT, "agents", "voice_wren"),
            "producer": "voice_wren", "order_id": "o7", "run_id": "r7"}
    _CUTS = [("c1", 1, 0, 20,
               "Theory core idea explained here slowly", True),
              ("c2", 1, 20, 40, "Two plus two is 4", True),
              ("c3", 2, 40, 60, "Data flows onward today fast", False),
              ("c4", 2, 60, 80, "Second scene keeps moving forward",
               False),
              ("c5", 2, 80, 100, "Closing thoughts land softly here",
               False)]
    _vcuts = []
    for _cid, _sc, _st, _en, _tx, _cite in _CUTS:
        _saved = _pc.voice_save("o7", _cid, b"\x00" * 32, _tx, 20, 1,
                                "stub")
        _cites = [{"ref": tref + "#p1",
                   "quote": "Theory core idea."}] if _cite else []
        _vcuts.append({"cut_id": _cid, "scene_n": _sc, "start_s": _st,
                       "end_s": _en, "lines": [{"text": _tx,
                                                "citations": _cites}],
                       "words": len(_tx.split()),
                       "audio": {"voice_pc_ref": _saved["ref"],
                                 "seconds": 20},
                       "attempts": 1})
    WN = {"cuts": _vcuts}
    ok(write_narration(wctx, {"narration": WN}).get("ok") is True,
       "wren narration accepts")
    savedw = results.load_result(os.path.join(wdir, "result.json"))
    ok(results.check_result(savedw) == []
       and "## narration (v2)" in results.render_report(savedw),
       "narration envelope + report")
    bad = json.loads(json.dumps(WN))
    bad["cuts"][1]["lines"][0]["citations"] = []
    ok("needs >=1 citation" in " ".join(write_narration(
        wctx, {"narration": bad}).get("errors", [])),
       "wren digit line without citation refuses")
    bad = json.loads(json.dumps(WN))
    bad["cuts"][1]["words"] = 4
    ok("!= counted" in " ".join(write_narration(
        wctx, {"narration": bad}).get("errors", [])),
       "wren word miscount refuses")
    bad = json.loads(json.dumps(WN))
    bad["cuts"][0]["attempts"] = 3
    ok("attempts must be 1-2" in " ".join(write_narration(
        wctx, {"narration": bad}).get("errors", [])),
       "wren third attempt refuses")
    bad = json.loads(json.dumps(WN))
    bad["cuts"][0]["end_s"] = 5
    ok("want 10-30" in " ".join(write_narration(
        wctx, {"narration": bad}).get("errors", [])),
       "wren short cut refuses")
    bad = json.loads(json.dumps(WN))
    bad["cuts"][0]["lines"][0]["citations"][0][
        "quote"] = "invented words"
    ok(write_narration(wctx, {"narration": bad}).get("ok") is False,
       "wren invented quote refuses")
    pdir = os.path.join(stud, "rundir", "board_penn")
    os.makedirs(pdir)
    with open(os.path.join(pdir,
                           "received.voice_wren.narration.json"),
              "w", encoding="utf-8") as f:
        json.dump({"sender": "voice_wren", "category": "narration",
                   "version": 2, "data": WN}, f)
    pctx = {"run_dir": pdir,
            "agent_dir": os.path.join(ROOT, "agents", "board_penn"),
            "producer": "board_penn", "order_id": "o7", "run_id": "r7"}
    SB = {"cuts": [{"cut_id": c["cut_id"], "scene_n": c["scene_n"],
                    "start_s": c["start_s"], "end_s": c["end_s"],
                    "show_what": "Card", "show_why": "Intro",
                    "on_screen_text": ["Hello"]}
                   for c in WN["cuts"]]}
    GUIDE = {"palette": {"background": "#101418", "text": "#f5f2ea",
                         "accent": "#e0a458"},
             "fonts": {"heading": "sans", "body": "sans"},
             "image_tone": "plain", "rules": ["Keep it calm."]}
    ok(write_storyboard(pctx, {"storyboard": SB,
                               "style_guide": GUIDE}).get("ok") is True,
       "penn storyboard accepts")
    savedp = results.load_result(os.path.join(pdir, "result.json"))
    ok(results.check_result(savedp) == []
       and "## storyboard (v2)" in results.render_report(savedp)
       and "## style_guide (v1)" in results.render_report(savedp),
       "storyboard envelope + report")
    bad = {"cuts": SB["cuts"][:-1]}
    ok("cut set must equal" in " ".join(write_storyboard(
        pctx, {"storyboard": bad,
               "style_guide": GUIDE}).get("errors", [])),
       "storyboard dropped cut refuses")
    bad = json.loads(json.dumps(SB))
    bad["cuts"][0]["on_screen_text"] = ["a", "b", "c", "d"]
    ok("must hold 0-3" in " ".join(write_storyboard(
        pctx, {"storyboard": bad,
               "style_guide": GUIDE}).get("errors", [])),
       "storyboard fourth text line refuses")
    badg = dict(GUIDE)
    del badg["palette"]
    ok(write_storyboard(pctx, {"storyboard": SB,
                               "style_guide": badg}).get("ok") is False,
       "storyboard bad guide refuses")
    ok(write_narration(wctx, {"narration": bad}).get("ok") is False,
       "wren invented quote refuses")
finally:
    _pc.ROOT_OVERRIDE = None

if fails:
    print("%d FAILURES" % fails)
    sys.exit(1)
print("ALL PASS")
