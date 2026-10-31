"""Flow checks for agents/_frame/flow.py (v8). Stdlib only.

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
from agents._frame import pc as _pc
from agents._frame import video as _video
_video._TRANSCRIBE_FN = lambda p: []  # never live in tests

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
ok(len(cat["agents"]) >= 13, "catalog lists 13 agents")
drafts = sorted(a["id"] for a in cat["agents"] if a.get("draft"))
ok(drafts == ["voice_iris"], "1 draft flagged")
ok("sales_sam" in [a["id"] for a in cat["agents"] if a.get("flow")],
   "workers declare flow I/O")
ok(sorted(c["name"] for c in cat["categories"])
   == ["anim_picks", "brief", "cases", "concept", "concepts",
       "gen_picks", "narration", "photo_picks", "render_log",
       "request", "slide_draft", "source", "split_plan",
       "storyboard", "storyboard_draft", "storyboard_table",
       "structure", "style_guide", "video"],
   "catalog has 19 categories")
ok(all((a.get("color") or "").startswith("#") for a in cat["agents"]),
   "catalog colors")
ok(all(isinstance(a.get("tools"), list) and a["tools"]
       for a in cat["agents"]),
   "catalog agents carry tools")

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
ok("order" not in cat, "catalog has no order node")
ok([p["id"] for p in cat.get("pcs", [])]
   == ["pc_source", "pc_theory", "pc_article", "pc_image",
       "pc_generated", "pc_voice"],
   "catalog lists the six PCs")
ok([c["id"] for c in cat.get("code", [])]
   == ["video_production", "part_split"],
   "catalog lists the code nodes")
samdecl = next(a for a in cat["agents"] if a["id"] == "sales_sam")
ok(samdecl["flow"]["inputs"] == []
   and [o["category"] for o in samdecl["flow"]["outputs"]]
   == ["request"],
   "sam starts the flow, outputs request only")

dflt = flow.load_flow("default")
ok([n["id"] for n in dflt["nodes"]]
   == ["sales_sam", "pd_marty", "explain_cleo", "case_rex", "plan_ash",
       "voice_wren", "board_penn", "part_split", "photo_pia",
       "image_gene", "anim_max", "board_vera", "slide_remy",
       "final", "video_production", "pc_source", "pc_theory",
       "pc_article", "pc_image", "pc_generated", "pc_voice"]
   and dflt["name"] == "Order to video",
   "default flow is sam->..->wren->penn->helpers->vera->remy->video")
ok(not next(n for n in dflt["nodes"]
            if n["id"] == "final").get("temp")
   and len(dflt["lines"]) == 47
   and len(dflt.get("pc_lines", [])) == 44,
   "final takes video+storyboard_table, 47 solid + 44 dotted")
ok(next(n for n in dflt["nodes"]
        if n["id"] == "video_production").get("code") is True,
   "video node is marked code")
ok(all(isinstance(n.get("pc"), str)
       for n in dflt["nodes"] if n["id"].startswith("pc_")),
   "PC nodes carry their pc name")
ok(all(n.get("pc") for n in dflt["nodes"]
       if n["id"] in ("pc_source", "pc_theory", "pc_article", "pc_image",
                      "pc_generated", "pc_voice")),
   "all six PCs are on the canvas")
W, H, CW, CH = 206, 140, 3282, 900
boxes = {}
for n in dflt["nodes"]:
    p = dflt.get("positions", {}).get(n["id"])
    boxes[n["id"]] = (p[0], p[1], p[0] + W, p[1] + H) if p else None
ok(all(b for b in boxes.values())
   and all(b[2] <= CW and b[3] <= CH for b in boxes.values()),
   "every default node is placed inside the canvas")
clash = []
ids = sorted(boxes)
for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
        a, b = boxes[ids[i]], boxes[ids[j]]
        if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
            clash.append((ids[i], ids[j]))
ok(not clash, "default nodes do not overlap (%s)"
   % (", ".join("%s/%s" % c for c in clash) or "none"))
crew = {n["id"] for n in dflt["nodes"] if not n.get("pc")}
solids = dflt["lines"]
dots = dflt.get("pc_lines", [])
ok(len(solids) == 47 and len(dots) == 44
   and all(ln["from"] in crew and ln["to"] in crew for ln in solids)
   and all(pl["from"] in boxes and pl["to"] in boxes for pl in dots),
   "91 lines would draw (47 solid + 44 dotted)")
# No PC-row gap rule: the owner's drawn layout (source of truth)
# interleaves PCs with crew (Source PC sits above Sam).
try:
    flow.load_flow("../x")
    ok(False, "bad flow id raises")
except ValueError:
    ok(True, "bad flow id raises")

# ---- validate ----
ok(flow.validate_flow(dflt) == [], "default flow validates")
bad = json.loads(json.dumps(dflt))
bad["lines"].append({"id": "lx", "from": "sales_sam", "to": "pd_marty",
                      "categories": ["nope"]})
errs = flow.validate_flow(bad)
ok(any("unknown category" in e["message"] for e in errs)
   and errs[0].get("line") == "lx", "unknown category + line id")
bad = json.loads(json.dumps(dflt))
bad["lines"].append({"id": "ld", "from": "sales_sam", "to": "pd_marty",
                      "categories": ["request"]})
ok(any("duplicate categor" in e["message"]
       for e in flow.validate_flow(bad)),
   "dup category on a pair rejected")
bad = {"nodes": [{"id": "sales_sam"}, {"id": "pd_marty"},
                 {"id": "final"}],
       "lines": [{"id": "l1", "from": "sales_sam", "to": "final",
                  "categories": ["request"]}],
       "positions": {}}
errs = flow.validate_flow(bad)
ok(any("no incoming line" in e["message"] for e in errs)
   and any(e.get("node") == "pd_marty" for e in errs),
   "agent without input + node id")
starter = {"nodes": [{"id": "sales_sam"}, {"id": "final"}],
           "lines": [{"id": "l1", "from": "sales_sam", "to": "final",
                      "categories": ["video"]}],
           "positions": {}}
ok(flow.validate_flow(starter) == [], "sam starts without lines")
bad = json.loads(json.dumps(dflt))
bad["lines"] = [ln for ln in bad["lines"] if ln["id"] != "c3b"]
ok(any("misses required input 'structure'" in e["message"]
       for e in flow.validate_flow(bad)), "missing required input")
bad = json.loads(json.dumps(dflt))
bad["lines"] = [ln for ln in bad["lines"] if ln["id"] != "c61"]
ok(any("misses required input 'render_log'" in e["message"]
       for e in flow.validate_flow(bad)),
   "code node misses required input")
mflow = json.loads(json.dumps(dflt))
for ln in mflow["lines"]:
    if ln["id"] == "c2a":
        ln["categories"] = ["concept", "structure"]
mflow["lines"] = [ln for ln in mflow["lines"] if ln["id"] != "c2b"]
ok(flow.validate_flow(mflow) == [], "multi-category line stays valid")
w = flow.lint_flow(mflow)
ok(len(w) == 1 and w[0].get("line") == "c2a"
   and "split one line" in w[0]["message"],
   "multi-category line warns with line id")
ok(flow.lint_flow(dflt) == [], "default flow has no warnings")
cyc = {"nodes": [{"id": "sales_sam"},
                 {"id": "pd_marty"}, {"id": "final"}],
       "lines": [{"id": "l2", "from": "sales_sam", "to": "pd_marty",
                  "categories": ["request", "source"]},
                 {"id": "l3", "from": "pd_marty", "to": "sales_sam",
                  "categories": ["structure"]},
                 {"id": "l4", "from": "pd_marty", "to": "final",
                  "categories": ["video"]}],
       "positions": {}}
ok(any(e["message"].startswith("cycle:")
       for e in flow.validate_flow(cyc)), "cycle caught")
bad = json.loads(json.dumps(dflt))
bad["nodes"].append({"id": "voice_iris"})
bad["lines"].append({"id": "ld", "from": "sales_sam", "to": "voice_iris",
                      "categories": ["request"]})
errs = flow.validate_flow(bad)
ok(any("is a draft" in e["message"] for e in errs)
   and any(e.get("node") == "voice_iris" for e in errs),
   "connected draft rejected")
old = {"nodes": [{"id": "order"}, {"id": "sales_sam"},
                 {"id": "final"}],
       "lines": [{"id": "l1", "from": "order", "to": "sales_sam",
                  "categories": "*"}],
       "positions": {}}
ok(any("has no agent.json" in e["message"]
       for e in flow.validate_flow(old)),
   "retired order node fails clean")
multi = {"nodes": [{"id": "sales_sam"}, {"id": "pd_marty"},
                   {"id": "explain_cleo"}, {"id": "case_rex"},
                   {"id": "plan_ash"}, {"id": "board_penn"},
                   {"id": "voice_wren"}, {"id": "final"}],
         "lines": [{"id": "l1", "from": "sales_sam", "to": "pd_marty",
                    "categories": ["request", "source"]},
                   {"id": "l2", "from": "pd_marty", "to": "explain_cleo",
                    "categories": ["concept", "structure"]},
                   {"id": "l3", "from": "sales_sam", "to": "explain_cleo",
                    "categories": ["source"]},
                   {"id": "l9", "from": "pd_marty", "to": "case_rex",
                    "categories": ["concept", "structure"]},
                   {"id": "l4", "from": "pd_marty", "to": "plan_ash",
                    "categories": ["concept", "structure"]},
                   {"id": "l7", "from": "explain_cleo", "to": "plan_ash",
                    "categories": ["concepts"]},
                   {"id": "l8", "from": "case_rex", "to": "plan_ash",
                    "categories": ["cases"]},
                   {"id": "l6", "from": "plan_ash", "to": "board_penn",
                    "categories": ["storyboard_draft"]},
                   {"id": "l10", "from": "plan_ash", "to": "voice_wren",
                    "categories": ["storyboard_draft"]},
                   {"id": "l11", "from": "voice_wren", "to": "board_penn",
                    "categories": ["narration"]},
                   {"id": "l5", "from": "board_penn", "to": "final",
                    "categories": ["video"]}],
         "positions": {}}
# l5 carries video: final acceptance is validated, sender-output
# match is a run-time transfer check.
ok(flow.validate_flow(multi) == [], "multi-sender intake validates")
bad = json.loads(json.dumps(dflt))
bad["lines"].append({"id": "lx", "from": "explain_cleo", "to": "final",
                      "categories": ["concepts"]})
ok(any("final takes only" in e["message"]
       for e in flow.validate_flow(bad)),
   "final rejects non-video input")
bad = {"nodes": [{"id": "sales_sam"}, {"id": "pd_marty"},
                 {"id": "pc_source", "pc": "source"},
                 {"id": "final"}],
       "lines": [{"id": "l1", "from": "sales_sam", "to": "pc_source",
                  "categories": ["request"]}],
       "pc_lines": [], "positions": {}}
ok(any("touches a PC" in e["message"]
       for e in flow.validate_flow(bad)),
   "solid line to a PC rejected")
bad = json.loads(json.dumps(dflt))
bad["pc_lines"].append({"id": "dx", "from": "sales_sam",
                        "to": "pd_marty", "label": "crew to crew"})
ok(any("exactly one PC" in e["message"]
       for e in flow.validate_flow(bad)),
   "dotted line between crew rejected")
bad = json.loads(json.dumps(dflt))
bad["nodes"].append({"id": "pc_x", "pc": "warehouse"})
bad["pc_lines"].append({"id": "dx", "from": "sales_sam",
                        "to": "pc_x", "label": "bad pc"})
ok(any("unknown pc" in e["message"]
       for e in flow.validate_flow(bad)),
   "unknown pc name rejected")
bad = json.loads(json.dumps(dflt))
bad["pc_lines"].append({"id": "c1", "from": "sales_sam",
                        "to": "pc_source", "label": "dup id"})
ok(any("duplicate line id" in e["message"]
       for e in flow.validate_flow(bad)),
   "dotted id must not clash with solid ids")
pcnodes = {n["id"] for n in dflt["nodes"] if n.get("pc")}
ok(all((pl["from"] in pcnodes) != (pl["to"] in pcnodes)
       and pl.get("label", "").strip()
       and len(pl["label"]) <= 64
       for pl in dflt["pc_lines"]),
   "every default dotted line links one PC, labelled")
ok(all(pl["from"] not in pcnodes and pl["to"] not in pcnodes
       for pl in dflt["lines"]),
   "no solid line touches a PC")
seq = flow.topo_order(dflt)
ok(seq.index("sales_sam") < seq.index("pd_marty")
   < seq.index("explain_cleo") < seq.index("plan_ash")
   < seq.index("voice_wren") < seq.index("board_penn")
   < seq.index("part_split") < seq.index("photo_pia")
   < seq.index("board_vera") < seq.index("slide_remy")
   < seq.index("video_production")
   < seq.index("final") == len(seq) - 1
   and seq.index("pd_marty") < seq.index("case_rex")
   < seq.index("plan_ash")
   and seq.index("board_penn") < seq.index("image_gene")
   < seq.index("board_vera")
   and seq.index("board_penn") < seq.index("anim_max")
   < seq.index("board_vera")
   and not (pcnodes & set(seq)),
   "topo order respects lines, final last, PCs excluded")
ok(flow.new_run_id().startswith("flow-"), "run id shape")

# ---- transfer unit ----
tmp = tempfile.mkdtemp(prefix="flowcheck_")
rd = os.path.join(tmp, "r1")
os.makedirs(os.path.join(rd, "sales_sam"))
sreq = results.make_result(
    "sales_sam", "o1", "r1",
    {"request": {"order_id": "o1",
                 "client_answers": {"audience": "a", "length": "b",
                                    "depth": "c", "theme": "d",
                                    "source": "e"},
                 "source_summary": "s", "production_notes": ["n"],
                 "open_questions": []}})
results.save_result(os.path.join(rd, "sales_sam"), sreq)
got, nbytes, errs = flow._transfer(rd, "sales_sam", "x", ["request"],
                                   None)
ok(errs == [] and len(got) == 1 and got[0]["sender"] == "sales_sam"
   and got[0]["version"] == 1 and nbytes > 0, "transfer labels sender")
got, _, errs = flow._transfer(rd, "sales_sam", "x", ["request"],
                              [{"category": "request", "accept": [2]}])
ok(errs and "not in accepted" in errs[0], "accept list enforced")
got, _, errs = flow._transfer(rd, "sales_sam", "x", ["concept"], None)
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
SAM_SOURCE = {"ref": "pc://source/abc123abc123", "title": "s",
              "chars": 24, "sections": 2,
              "recipients": [{"agent": "pd_marty", "order_id": "o9",
                              "set_by": "sales_sam", "at": "t"}]}
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


def stub(agent_dir, run_dir, brief, input_md):
    who = os.path.basename(run_dir)
    if _re.fullmatch(r"p\d+", who):
        who = os.path.basename(os.path.dirname(run_dir))
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
    if brief.get("want_summary_ko"):
        with open(os.path.join(run_dir, "summary_ko.md"), "w",
                  encoding="utf-8") as f:
            f.write("Fixture summary for %s." % who)
    return {"ok": True}


od = os.path.join(tmp, "orders", "o9")
os.makedirs(od)
with open(os.path.join(od, "meta.json"), "w", encoding="utf-8") as f:
    json.dump({"answers": {"audience": "a", "length": "b", "depth": "c",
                           "theme": "d"},
               "files": {"source": "s.pdf"}}, f)
real_orders = flow.ORDERS_DIR
flow.ORDERS_DIR = os.path.join(tmp, "orders")
_pc.ROOT_OVERRIDE = tmp
try:
    out = flow.run_flow(dflt, "o9", stub, runs_root=os.path.join(tmp, "runs"),
                        run_id="rid1", flow_id="default")
finally:
    flow.ORDERS_DIR = real_orders
    _pc.ROOT_OVERRIDE = None
ok(out.get("ok"), "stubbed e2e run ok")
rdir = os.path.join(tmp, "runs", "rid1")
st = json.load(open(os.path.join(rdir, "STATUS.json"), encoding="utf-8"))
ok(st["state"] == "done" and st["flow_id"] == "default"
   and st["order_id"] == "o9"
   and st["received"] == ["video", "storyboard_table"],
   "STATUS done with ids")
sam = results.load_result(os.path.join(rdir, "sales_sam", "result.json"))
ok(sam["status"] == "checked"
   and sam["categories"]["request"]["version"] == 1
   and "source" not in sam["categories"], "sam checked")
mar = results.load_result(os.path.join(rdir, "pd_marty", "result.json"))
ok(mar["status"] == "checked"
   and mar["categories"]["concept"]["version"] == 1
   and mar["categories"]["structure"]["version"] == 3, "marty checked")
cleo = results.load_result(os.path.join(rdir, "explain_cleo",
                                        "result.json"))
ok(cleo["status"] == "checked"
   and cleo["categories"]["concepts"]["version"] == 1, "cleo checked")
rex = results.load_result(os.path.join(rdir, "case_rex", "result.json"))
ok(rex["status"] == "checked"
   and rex["categories"]["cases"]["version"] == 1, "rex checked")
ash = results.load_result(os.path.join(rdir, "plan_ash", "result.json"))
ok(ash["status"] == "checked"
   and ash["categories"]["storyboard_draft"]["version"] == 1,
   "ash checked")
penn = results.load_result(os.path.join(rdir, "board_penn",
                                        "result.json"))
ok(penn["status"] == "checked"
   and penn["categories"]["storyboard"]["version"] == 2
   and penn["categories"]["style_guide"]["version"] == 1,
   "penn checked")
wren = results.load_result(os.path.join(rdir, "voice_wren",
                                        "result.json"))
ok(wren["status"] == "checked"
   and wren["categories"]["narration"]["version"] == 2, "wren checked")
for _aid, _cat, _ver in (("photo_pia", "photo_picks", 1),
                         ("image_gene", "gen_picks", 1),
                         ("anim_max", "anim_picks", 2),
                         ("board_vera", "slide_draft", 2),
                         ("slide_remy", "render_log", 1)):
    _res = results.load_result(os.path.join(rdir, _aid, "result.json"))
    ok(_res["status"] == "checked"
       and _res["categories"][_cat]["version"] == _ver,
       "%s checked" % _aid)
vid = results.load_result(os.path.join(rdir, "video_production",
                                       "result.json"))
ok(vid["status"] == "checked"
   and vid["categories"]["video"]["version"] == 1
   and vid["categories"]["storyboard_table"]["version"] == 1,
   "video code node checked")
ok(os.path.isfile(os.path.join(rdir, "video_production",
                               "assembly.json"))
   and os.path.isfile(os.path.join(rdir, "video_production",
                                   "captions.srt"))
   and os.path.isfile(os.path.join(rdir, "video_production",
                                   "storyboard_table.json")),
   "video node writes assembly + srt + table")
asmj = json.load(open(os.path.join(rdir, "video_production",
                                  "assembly.json"),
                      encoding="utf-8"))
ok(asmj["segments"][0]["props"] == {"cutId": "s1c1",
                                    "probe": True}
   and asmj["segments"][0]["slide"].endswith("s1c1.png")
   and asmj["segments"][0]["slide_status"] == "rendered"
   and asmj["segments"][0]["voice_ref"].endswith("#s1c1"),
   "assembly segments record props + png + voice")
with open(os.path.join(rdir, "video_production", "captions.srt"),
          encoding="utf-8") as f:
    ok(f.read() == "1\n00:00:00,000 --> 00:00:20,000\nHello world\n",
       "subtitle timing exact")
sp = json.load(open(os.path.join(rdir, "video_production",
                                 "assembly.json"),
                    encoding="utf-8"))["speech"]
ok(sp == {"status": "proportional", "turns": 0, "mismatches": []}
   and "ffmpeg" in " ".join(json.load(
       open(os.path.join(rdir, "video_production", "assembly.json"),
            encoding="utf-8"))["ffmpeg_cmd"]),
   "empty transcript keeps proportional timing")
leg = os.path.join(tmp, "orders", "o9leg")
os.makedirs(leg)
results.save_result(leg, results.make_result(
    "sales_sam", "o9leg", "rleg",
    {"request": REQ, "source": SAM_SOURCE}))
_real2 = flow.ORDERS_DIR
flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    gotleg = flow._sam_stored_result("o9leg")
finally:
    flow.ORDERS_DIR = _real2
ok(gotleg is not None
   and set(gotleg["categories"]) == {"request", "source"},
   "legacy sam result with source still loads")
fin = results.load_result(os.path.join(rdir, "final", "result.json"))
ok(fin["producer"] == "postprocess" and fin["status"] == "checked"
   and fin["categories"] == {}, "final postprocess result")
ok(os.path.isfile(os.path.join(rdir, "pd_marty", "INPUTS.md"))
   and os.path.isfile(os.path.join(rdir, "explain_cleo", "INPUTS.md")),
   "agents get INPUTS.md on disk")
ok(os.path.isfile(os.path.join(rdir, "sales_sam", "report.md"))
   and os.path.isfile(os.path.join(rdir, "pd_marty", "INPUTS.json")),
   "reports + manifests written")
ok(os.path.isfile(os.path.join(rdir, "pd_marty", "usage.json")),
   "per-stage usage written")
muse = json.load(open(os.path.join(rdir, "pd_marty", "usage.json"),
                      encoding="utf-8"))
ok(muse["llm_calls"] == 0 and muse["tools"] == {},
   "stub usage counts zero")
ok(not open(os.path.join(rdir, "pd_marty", "report.md"),
            encoding="utf-8").read().startswith("# Stage summary"),
   "full runs carry no KO summary")
mani = json.load(open(os.path.join(rdir, "pd_marty", "INPUTS.json"),
                      encoding="utf-8"))
ok(mani["received"] == [{"sender": "sales_sam", "category": "request",
                         "version": 1,
                         "file": "received.sales_sam.request.json"}],
   "marty manifest has request only (source via PC)")
cmani = json.load(open(os.path.join(rdir, "explain_cleo", "INPUTS.json"),
                      encoding="utf-8"))
ok([(r["sender"], r["category"], r["version"]) for r in
    cmani["received"]] == [("pd_marty", "concept", 1),
                           ("pd_marty", "structure", 3)],
   "cleo manifest has concept + structure")
amani = json.load(open(os.path.join(rdir, "plan_ash", "INPUTS.json"),
                      encoding="utf-8"))
ok([(r["sender"], r["category"]) for r in amani["received"]]
   == [("pd_marty", "concept"), ("pd_marty", "structure"),
       ("explain_cleo", "concepts"), ("case_rex", "cases")],
   "ash manifest has concept + structure + reports")
wmani = json.load(open(os.path.join(rdir, "voice_wren", "INPUTS.json"),
                      encoding="utf-8"))
ok([(r["sender"], r["category"]) for r in wmani["received"]]
   == [("plan_ash", "storyboard_draft"), ("pd_marty", "concept")],
   "wren manifest has draft + concept")
vmani = json.load(open(os.path.join(rdir, "video_production",
                                   "INPUTS.json"),
                      encoding="utf-8"))
ok(sorted((r["sender"], r["category"]) for r in vmani["received"])
   == [("board_penn", "storyboard"), ("board_vera", "slide_draft"),
       ("pd_marty", "structure"), ("plan_ash", "storyboard_draft"),
       ("slide_remy", "render_log"), ("voice_wren", "narration")],
   "video manifest has all six inputs")
evs = [json.loads(ln) for ln in
       open(os.path.join(rdir, "events.jsonl"), encoding="utf-8")]
kinds = [e["ev"] for e in evs]
ok(kinds[0] == "flow_start" and kinds[-1] == "flow_done"
   and "order_ready" not in kinds and kinds.count("line") == 47
   and "final_ready" in kinds, "event trail complete")
line1 = next(e for e in evs if e.get("line") == "c1")
ok(line1["categories"] == ["request"]
   and line1["bytes"] > 0, "line log shows sent categories")

calls = []


def stub2(agent_dir, run_dir, brief, input_md):
    calls.append(os.path.basename(run_dir))
    return stub(agent_dir, run_dir, brief, input_md)


flow.ORDERS_DIR = os.path.join(tmp, "orders")
_pc.ROOT_OVERRIDE = tmp
try:
    out = flow.run_flow(dflt, "o9", stub2,
                        runs_root=os.path.join(tmp, "runs"),
                        run_id="rid1b")
finally:
    flow.ORDERS_DIR = real_orders
    _pc.ROOT_OVERRIDE = None
evs2 = [json.loads(ln) for ln in
        open(os.path.join(tmp, "runs", "rid1b", "events.jsonl"),
             encoding="utf-8")]
ok(out.get("ok") and "sales_sam" not in calls
   and any(e.get("ev") == "agent_done"
           and e.get("agent") == "sales_sam"
           and e.get("reused") for e in evs2),
   "sam reuses stored order result")
reuse_use = json.load(open(os.path.join(tmp, "runs", "rid1b",
                                        "sales_sam", "usage.json"),
                           encoding="utf-8"))
ok(reuse_use.get("reused") is True, "reused stage costs nothing")

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
    json.dump({"answers": {"audience": "a"},
               "files": {"source": "s.pdf"}}, f)
flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    out = flow.run_flow(dflt, "o8", stub,
                        runs_root=os.path.join(tmp, "runs"), run_id="rid0")
finally:
    flow.ORDERS_DIR = real_orders
ok(not out.get("ok") and "misses answers" in out.get("error", ""),
   "order without answers fails fast")

# ---- step mode ----
flow.ORDERS_DIR = os.path.join(tmp, "orders")
_pc.ROOT_OVERRIDE = tmp
try:
    s1 = flow.step_run(dflt, "o9", stub, "plan_ash",
                       run_id="step1",
                       runs_root=os.path.join(tmp, "runs"))
    ok(s1.get("ok") and s1.get("last") == "plan_ash"
       and s1.get("ran") == ["sales_sam", "pd_marty", "case_rex",
                             "explain_cleo", "plan_ash"],
       "step run stops at the target")
    sdir = os.path.join(tmp, "runs", "step1")
    sst = json.load(open(os.path.join(sdir, "STATUS.json"),
                         encoding="utf-8"))
    ok(sst["state"] == "step_paused" and sst["approved"] == []
       and not os.path.isdir(os.path.join(sdir, "voice_wren")),
       "paused run approves nothing, runs nothing further")
    for _n in s1["ran"]:
        _ap = flow.approve_node("step1", _n,
                                runs_root=os.path.join(tmp, "runs"))
        ok(_ap.get("ok"), "approve %s" % _n)
    s2 = flow.step_run(dflt, "o9", stub, "board_vera",
                       run_id="step1",
                       runs_root=os.path.join(tmp, "runs"))
    ok(s2.get("ok") and s2.get("ran") == ["voice_wren", "board_penn",
                                          "part_split", "anim_max",
                                          "image_gene", "photo_pia",
                                          "board_vera"],
       "approved stages are skipped, pair runs together")
    ok(open(os.path.join(sdir, "board_vera", "p1", "report.md"),
            encoding="utf-8").read().startswith("# Stage summary (KO)"),
       "step report starts with the KO summary")
    ok("want_summary_ko" not in json.load(
        open(os.path.join(sdir, "board_vera", "INPUTS.json"),
             encoding="utf-8")).get("received", [{}])[0],
       "manifest keeps only transfers")
    for _n in s2["ran"]:
        _ap = flow.approve_node("step1", _n,
                                runs_root=os.path.join(tmp, "runs"))
        ok(_ap.get("ok"), "approve %s" % _n)
    s2b = flow.step_run(dflt, "o9", stub, "slide_remy",
                        run_id="step1",
                        runs_root=os.path.join(tmp, "runs"))
    ok(s2b.get("ok") and s2b.get("ran") == ["slide_remy"],
       "step continues to the next stage")
    flow.approve_node("step1", "slide_remy",
                      runs_root=os.path.join(tmp, "runs"))
    inv = flow.invalidate_node("step1", "board_vera",
                               runs_root=os.path.join(tmp, "runs"))
    ok(inv.get("ok")
       and set(inv.get("removed", []))
       == {"board_vera", "slide_remy"}
       and not os.path.isdir(os.path.join(sdir, "board_vera")),
       "re-run invalidates later stages")
    s3 = flow.step_run(dflt, "o9", stub, "board_vera",
                       run_id="step1", note="OWNER-NOTE-7",
                       runs_root=os.path.join(tmp, "runs"))
    ok(s3.get("ok") and s3.get("ran") == ["board_vera"]
       and "OWNER-NOTE-7" in open(os.path.join(sdir, "board_vera",
                                               "INPUTS.md"),
                                  encoding="utf-8").read(),
       "re-run carries the owner note")
    sc = flow.step_status("step1", runs_root=os.path.join(tmp, "runs"))
    ok(sc.get("ok") and sc["status"]["nodes"]["pd_marty"]["approved"]
       and sc["status"]["nodes"]["pd_marty"]["usage"]["llm_calls"]
       == 0
       and not sc["status"]["nodes"]["board_vera"]["approved"],
       "step status shows approval + cost per stage")
    nok = flow.approve_node("step1", "slide_remy",
                            runs_root=os.path.join(tmp, "runs"))
    ok(not nok.get("ok"), "unrun stage cannot approve")
    nok2 = flow.step_status("nope",
                            runs_root=os.path.join(tmp, "runs"))
    ok(not nok2.get("ok"), "unknown run has no status")
    s5 = flow.step_run(dflt, "o9", stub, "final", run_id="step1",
                       runs_root=os.path.join(tmp, "runs"))
    ok(s5.get("ok")
       and s5.get("received") == ["video", "storyboard_table"],
       "stepping to final finishes the run")
finally:
    flow.ORDERS_DIR = real_orders
    _pc.ROOT_OVERRIDE = None

sp = os.path.join(tmp, "runs", "rid9", "explain_cleo")
os.makedirs(sp)
mp_ = os.path.join(tmp, "runs", "rid9", "pd_marty")
os.makedirs(mp_)
rx = os.path.join(tmp, "runs", "rid9", "case_rex")
os.makedirs(rx)
_pc.ROOT_OVERRIDE = tmp
_real_orders = flow.ORDERS_DIR
flow.ORDERS_DIR = os.path.join(tmp, "orders")
try:
    rr = _pc.ingest_source("o10", "s.pdf", "2026-10-30T07:00:00",
                           "sales_sam",
                           ["1.1 Getting started\nPreloaded text here."],
                           [], [], 0, root=tmp)
    _pc.set_recipients("source", rr["doc_id"], "o10",
                       ["explain_cleo"], "sales_sam", kind="map",
                       root=tmp)
    _pc.set_recipients("source", rr["doc_id"], "o10",
                       ["pd_marty"], "sales_sam", kind="full",
                       root=tmp)
    os.makedirs(os.path.join(tmp, "orders", "o10"))
    with open(os.path.join(tmp, "orders", "o10", "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"files": {"pc_ref": rr["ref"]}}, f)
    srcfile = {"sender": "sales_sam", "category": "source",
               "version": 3,
               "data": {"ref": rr["ref"], "title": "s", "chars": 1,
                        "sections": 1, "recipients": []}}
    with open(os.path.join(sp, "received.sales_sam.source.json"), "w",
              encoding="utf-8") as f:
        json.dump(srcfile, f)
    with open(os.path.join(mp_, "received.sales_sam.source.json"), "w",
              encoding="utf-8") as f:
        json.dump(srcfile, f)
    with open(os.path.join(rx, "received.sales_sam.source.json"), "w",
              encoding="utf-8") as f:
        json.dump(srcfile, f)
    rcv = [{"sender": "sales_sam", "category": "source", "version": 3,
            "file": "received.sales_sam.source.json"}]
    md = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}}, rcv,
        os.path.join(tmp, "runs", "rid9"), "explain_cleo")
    ok("## PC input" in md and "1.1 Getting started" in md
       and rr["ref"] in md and "Preloaded text here." not in md,
       "cleo input is map-based (no verbatim preload)")
    md2 = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}}, [],
        os.path.join(tmp, "runs", "rid9"), "explain_cleo")
    ok("1.1 Getting started" in md2,
       "order meta discovers the source entry")
    md2b = flow._render_inputs_md(
        {"order_id": "o10x", "answers": {"audience": "a"}}, [],
        os.path.join(tmp, "runs", "rid9"), "explain_cleo")
    ok("0 item(s)" in md2b, "no source means empty PC input")
    md3 = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}}, rcv,
        os.path.join(tmp, "runs", "rid9"), "sales_sam")
    ok("## PC input" not in md3, "sam gets no PC input")
    md4 = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}}, rcv,
        os.path.join(tmp, "runs", "rid9"), "pd_marty")
    ok("## PC input" in md4 and "1.1 Getting started" in md4
       and "Preloaded text here." in md4
       and "(ref: %s#s1.1)" % rr["ref"] in md4,
       "marty input is the full text (full row)")
    md5 = flow._render_inputs_md(
        {"order_id": "o10", "answers": {"audience": "a"}}, rcv,
        os.path.join(tmp, "runs", "rid9"), "case_rex")
    ok("## PC input" in md5 and "no access to 1 other item(s)" in md5
       and "### Source" not in md5
       and "1.1 Getting started" not in md5,
       "unlisted agent gets no chunk for the entry")
    tr = _pc.ingest_theory("https://ex.test/t9", "Picked Theory",
                           "ex.test", "2024-01-01",
                           "2026-10-30T00:00:00", "explain_cleo",
                           "Picked body text here.", root=tmp)
    with open(os.path.join(_pc.entry_dir("theory", tr["doc_id"],
                                         root=tmp), "map.json"),
              "w", encoding="utf-8") as f:
        json.dump({"entry_summary": "A theory about picks.",
                   "sections": [{"ref": "g1", "heading": "Picked Theory",
                                 "summary": [{"text": "Body about picks.",
                                              "see": "p1"}]}]}, f)
    rd9 = os.path.join(tmp, "runs", "ridp")
    os.makedirs(os.path.join(rd9, "explain_cleo"))
    with open(os.path.join(rd9, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump({"order_id": "o10"}, f)
    with open(os.path.join(rd9, "explain_cleo", "result.json"), "w",
              encoding="utf-8") as f:
        json.dump({"categories": {"concepts": {"data": {"parts": [{
            "picks": [{"ref": tr["ref"], "title": "Picked Theory",
                       "why_important": "Core idea.",
                       "how_to_use": "Cite it.",
                       "priority": "must"}]}]}}}}, f)
    pv, pmeta = _pc.picks_preview_for("Ash", "o10",
                                      os.path.join(tmp, "runs"))
    ok(pmeta["picks"] == 1 and "Core idea." in pv
       and "Body about picks." in pv
       and "%s#g1/p1" % tr["ref"] in pv,
       "ash picks preview shows maps + reasons")
    try:
        _pc.picks_preview_for("Ash", "o-none",
                              os.path.join(tmp, "runs"))
        ok(False, "picks preview without picks raises")
    except KeyError:
        ok(True, "picks preview without picks raises")
finally:
    _pc.ROOT_OVERRIDE = None
    flow.ORDERS_DIR = _real_orders


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
