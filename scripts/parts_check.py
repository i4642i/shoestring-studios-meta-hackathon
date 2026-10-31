"""Part-clone checks (STEP 1). Stdlib only.

Run: python scripts/parts_check.py. No model calls: a stub agent
function writes canned per-part results; PC entries are fixtures
under a temp dir.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
from agents._frame import flow, parts, results
from agents._frame import media as _media
from agents._frame import pc as _pc
from agents._frame import tools as _tools

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


tmp = tempfile.mkdtemp(prefix="partscheck_")
RUNS = os.path.join(tmp, "runs")
os.makedirs(RUNS)
ORDER = "oparts1"

SID = _pc.content_id("source:parts-chapter")
SRC = "pc://source/%s" % SID

STRUCT = {
    "source_ref": SRC,
    "parts": [
        {"id": "p1", "heading": "1.1 Beginnings",
         "ref": SRC + "#s1.1", "covers": "start",
         "keywords": ["alpha"]},
        {"id": "p2", "heading": "1.2 Middles",
         "ref": SRC + "#s2.1", "covers": "middle",
         "keywords": ["beta"]},
        {"id": "p3", "heading": "1.3 Endings",
         "ref": SRC + "#s3.1", "covers": "end",
         "keywords": ["gamma"]}],
    "links": [{"from": "p1", "to": "p2", "why": "on"},
              {"from": "p2", "to": "p3", "why": "on"}],
    "duration": {"total_s": 90, "parts": [
        {"part_id": "p1", "seconds": 30, "why": "a"},
        {"part_id": "p2", "seconds": 30, "why": "b"},
        {"part_id": "p3", "seconds": 30, "why": "c"}]}}

CONCEPT = {"common_theme": "Thrift", "core_question": "How cheap?",
           "viewer_takeaway": "Save more",
           "intent_overall": "Build up"}

DRAFT = {"total_s": 90, "scenes": [
    {"n": 1, "start_s": 0, "end_s": 30, "part_id": "p1",
     "role": "explain", "viewer_learns": "m1",
     "screen_idea": "card", "narration_points": [],
     "materials": [{"ref": SRC + "#s1.1/p1", "from": "source",
                    "how_used": "fact"},
                   {"ref": SRC + "#fig1.1", "from": "source",
                    "how_used": "fig"}],
     "handoff": [], "next_link": ""},
    {"n": 2, "start_s": 30, "end_s": 60, "part_id": "p2",
     "role": "explain", "viewer_learns": "m2",
     "screen_idea": "card", "narration_points": [],
     "materials": [{"ref": SRC + "#s2.1/p1", "from": "source",
                    "how_used": "fact"}],
     "handoff": [], "next_link": ""},
    {"n": 3, "start_s": 60, "end_s": 90, "part_id": "p3",
     "role": "recap", "viewer_learns": "m3",
     "screen_idea": "card", "narration_points": [],
     "materials": [], "handoff": [], "next_link": ""}],
    "unused_picks": []}


def _cut(cid, scene, start, text):
    return {"cut_id": cid, "scene_n": scene, "start_s": start,
            "end_s": start + 15,
            "lines": [{"text": text, "citations": []}],
            "words": len(text.split()),
            "audio": {"voice_pc_ref": "VOICE#%s" % cid,
                      "seconds": 15.0},
            "attempts": 1}


NARR = {"cuts": [
    _cut("s1c1", 1, 0, "Part one opens."),
    _cut("s1c2", 1, 15, "Part one continues."),
    _cut("s2c1", 2, 30, "Part two opens."),
    _cut("s2c2", 2, 45, "Part two continues."),
    _cut("s3c1", 3, 60, "Part three opens."),
    _cut("s3c2", 3, 75, "Part three closes.")]}

BOARD = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 15,
     "show_what": "Card one", "show_why": "Intro",
     "on_screen_text": ["One"]},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 15, "end_s": 30,
     "show_what": "Card two", "show_why": "More",
     "on_screen_text": ["Two"]},
    {"cut_id": "s2c1", "scene_n": 2, "start_s": 30, "end_s": 45,
     "show_what": "Card three", "show_why": "Deep",
     "on_screen_text": ["Three"]},
    {"cut_id": "s2c2", "scene_n": 2, "start_s": 45, "end_s": 60,
     "show_what": "Card four", "show_why": "Proof",
     "on_screen_text": ["Four"]},
    {"cut_id": "s3c1", "scene_n": 3, "start_s": 60, "end_s": 75,
     "show_what": "Card five", "show_why": "Close",
     "on_screen_text": ["Five"]},
    {"cut_id": "s3c2", "scene_n": 3, "start_s": 75, "end_s": 90,
     "show_what": "Card six", "show_why": "Bye",
     "on_screen_text": ["Six"]}]}

GUIDE = {"palette": {"background": "#101418", "text": "#f5f2ea",
                     "accent": "#e0a458"},
         "fonts": {"heading": "sans", "body": "sans"},
         "image_tone": "calm", "rules": ["Keep it calm."]}

PHOTO = {"cuts": [
    {"cut_id": "s1c1", "decision": "use", "kind": "web",
     "ref": "IMG1", "file": "pick.jpg",
     "source_url": "https://example.com/1", "license": "CC0",
     "reason": "shows one"},
    {"cut_id": "s1c2", "decision": "none"},
    {"cut_id": "s2c1", "decision": "use", "kind": "web",
     "ref": "IMG2", "file": "pick.jpg",
     "source_url": "https://example.com/2", "license": "CC0",
     "reason": "shows two"},
    {"cut_id": "s2c2", "decision": "none"},
    {"cut_id": "s3c1", "decision": "none"},
    {"cut_id": "s3c2", "decision": "none"}]}

GEN = {"cuts": [
    {"cut_id": "s1c1", "decision": "generate",
     "prompt": "Lake at dawn", "reason": "art"},
    {"cut_id": "s1c2", "decision": "none"},
    {"cut_id": "s2c1", "decision": "generate",
     "prompt": "City at dusk", "reason": "art"},
    {"cut_id": "s2c2", "decision": "none"},
    {"cut_id": "s3c1", "decision": "generate",
     "prompt": "Lake at dawn", "reason": "same art"},
    {"cut_id": "s3c2", "decision": "none"}],
    "images": [
        {"cut_id": "s1c1", "file": "gen.png",
         "prompt": "Lake at dawn", "reused": False},
        {"cut_id": "s2c1", "file": "gen.png",
         "prompt": "City at dusk", "reused": False},
        {"cut_id": "s3c1", "file": "gen.png",
         "prompt": "Lake at dawn", "reused": True}]}

ANIM = {"cuts": [
    {"cut_id": "s1c1", "decision": "use", "template": "bar",
     "values": {"labels": ["a"], "series": [1]},
     "refs": [{"ref": SRC + "#s1.1/p1", "quote": "one"}],
     "reason": "numbers"},
    {"cut_id": "s1c2", "decision": "none"},
    {"cut_id": "s2c1", "decision": "none"},
    {"cut_id": "s2c2", "decision": "none"},
    {"cut_id": "s3c1", "decision": "none"},
    {"cut_id": "s3c2", "decision": "none"}]}


def _slide(cid, start, kind, ref):
    block = {"kind": kind, "order": 1, "appear_s": 0,
             "box": {"x": 64, "y": 64, "w": 1152, "h": 500},
             "reason": "fits"}
    if ref:
        block["ref"] = ref
    return {"cut_id": cid, "start_s": start, "end_s": start + 15,
            "preset": "full", "blocks": [block],
            "on_screen_text": ["T"], "transitions": [],
            "why": "simple"}


SLIDE = {"cuts": [
    _slide("s1c1", 0, "photo", "IMG1"),
    _slide("s1c2", 15, "text", None),
    _slide("s2c1", 30, "photo", "IMG2"),
    _slide("s2c2", 45, "text", None),
    _slide("s3c1", 60, "text", None),
    _slide("s3c2", 75, "text", None)]}

RLOG = {"cuts": [
    {"cut_id": "s1c1", "slide_file": "slides/s1c1.png",
     "renders_n": 1, "adjustments": [], "issues": []},
    {"cut_id": "s1c2", "slide_file": "slides/s1c2.png",
     "renders_n": 1, "adjustments": [], "issues": []},
    {"cut_id": "s2c1", "slide_file": "slides/s2c1.png",
     "renders_n": 1, "adjustments": [], "issues": []},
    {"cut_id": "s2c2", "slide_file": "slides/s2c2.png",
     "renders_n": 1, "adjustments": [], "issues": []},
    {"cut_id": "s3c1", "slide_file": "slides/s3c1.png",
     "renders_n": 1, "adjustments": [], "issues": []},
    {"cut_id": "s3c2", "slide_file": "slides/s3c2.png",
     "renders_n": 1, "adjustments": [], "issues": []}]}

PAY = {"photo_pia": ("photo_picks", PHOTO),
       "image_gene": ("gen_picks", GEN),
       "anim_max": ("anim_picks", ANIM),
       "board_vera": ("slide_draft", SLIDE),
       "slide_remy": ("render_log", RLOG)}

BRIEF = {"order_id": ORDER,
         "answers": {"audience": "a", "length": "b", "depth": "c",
                     "theme": "d"}}


def stub(agent_dir, run_dir, brief, input_md):
    base = os.path.basename(agent_dir)
    cat, full = PAY[base]
    cuts = set(brief.get("part_cuts", []))
    data = {"cuts": [c for c in full["cuts"]
                     if c.get("cut_id") in cuts]}
    if "images" in full:
        data["images"] = [im for im in full["images"]
                          if im.get("cut_id") in cuts]
    if base == "slide_remy":
        sdir = os.path.join(run_dir, "slides")
        os.makedirs(sdir, exist_ok=True)
        for c in data["cuts"]:
            with open(os.path.join(sdir, "%s.png" % c["cut_id"]),
                      "w", encoding="utf-8") as f:
                f.write("PNG")
            with open(os.path.join(
                    sdir, "%s.props.json" % c["cut_id"]), "w",
                    encoding="utf-8") as f:
                json.dump({"cutId": c["cut_id"]}, f)
    res = results.make_result(brief.get("clone_id", base),
                              brief["order_id"],
                              brief["flow_run_id"], {cat: data})
    results.save_result(run_dir, res)
    return {"ok": True, "events": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def wres(run_dir, node, producer, categories):
    ndir = os.path.join(run_dir, node)
    os.makedirs(ndir, exist_ok=True)
    res = results.make_result(producer, ORDER, "rparts",
                              categories)
    results.promote_checked(res)
    results.save_result(ndir, res)


# ---- unit: quotas ----
ok(parts.quotas_for([2, 2, 2]) == [2, 2, 2],
   "even cuts split the budget evenly")
ok(parts.quotas_for([4, 2, 2]) == [3, 2, 1],
   "quotas follow cut counts")
ok(parts.quotas_for([1]) == [6], "one part keeps the budget")
ok(parts.quotas_for([10, 1, 1]) == [4, 1, 1],
   "small parts keep at least one image")
many = parts.quotas_for([1] * 8)
ok(sum(many) == 6 and many.count(1) == 6,
   "more parts than budget still caps at six")

# ---- unit: plan ----
plan = parts.build_plan(STRUCT, DRAFT, NARR, CONCEPT, GUIDE)
ok([p["cuts"] for p in plan["parts"]]
   == [["s1c1", "s1c2"], ["s2c1", "s2c2"], ["s3c1", "s3c2"]],
   "cuts map to parts through scenes")
ok(plan["parts"][0]["materials"]
   == [SRC + "#s1.1/p1", SRC + "#fig1.1"]
   and plan["parts"][2]["materials"] == [],
   "materials collected per part")
ok([p["quota"] for p in plan["parts"]] == [2, 2, 2]
   and plan["shared"]["concept"]["common_theme"] == "Thrift"
   and plan["shared"]["style_guide"]["palette"]["accent"]
   == "#e0a458",
   "quotas plus shared context in the plan")
try:
    parts.build_plan(STRUCT, {"scenes": [], "unused_picks": []},
                     NARR, CONCEPT, GUIDE)
    ok(False, "unmapped scene raises")
except ValueError:
    ok(True, "unmapped scene raises")
one = parts.build_plan(
    {"parts": [STRUCT["parts"][0]],
     "duration": {"total_s": 30, "parts": [
         {"part_id": "p1", "seconds": 30}]}},
    {"scenes": [], "unused_picks": []}, NARR, CONCEPT, GUIDE)
ok(len(one["parts"]) == 1 and len(one["parts"][0]["cuts"]) == 6,
   "one part takes every cut")

# ---- live-ish: split + clones + merge ----
_pc.ROOT_OVERRIDE = tmp
real_runs = flow.RUNS_DIR
flow.RUNS_DIR = RUNS
try:
    sdir = _pc.entry_dir("source", SID)
    os.makedirs(os.path.join(sdir, "figures"), exist_ok=True)
    with open(os.path.join(sdir, "entry.json"), "w",
              encoding="utf-8") as f:
        json.dump({"pc": "source", "doc_id": SID, "ref": SRC,
                   "title": "Chapter",
                   "sections": [{"n": "1.1", "heading": "Beginnings",
                                 "start": 0, "count": 1},
                                {"n": "2.1", "heading": "Middles",
                                 "start": 1, "count": 1}],
                   "paragraphs": [
                       {"addr": "s1.1/p1", "pages": [3],
                        "text": "one"},
                       {"addr": "s2.1/p1", "pages": [5],
                        "text": "two"}],
                   "figures": [{"addr": "fig1.1",
                                "file": "fig1.png", "page": 3,
                                "caption": "fig"}],
                   "recipients": []}, f)
    vrefs = {}
    for c in NARR["cuts"]:
        saved = _pc.voice_save(ORDER, c["cut_id"], b"\x00" * 32,
                               "line", 15.0, 1, "stub")
        vrefs[c["cut_id"]] = saved["ref"]
    VOICE = vrefs["s1c1"].split("#")[0]
    for c in NARR["cuts"]:
        c["audio"]["voice_pc_ref"] = "%s#%s" % (VOICE,
                                                c["cut_id"])
    pick1 = _pc.image_store_pick(
        ORDER, "https://example.com/1", b"\xff\xd8" + b"\x00" * 40,
        "CC0", "shows one", set_by="photo_pia@p1", suffix=".jpg")
    pick2 = _pc.image_store_pick(
        ORDER, "https://example.com/2", b"\xff\xd8" + b"\x00" * 40,
        "CC0", "shows two", set_by="photo_pia@p2", suffix=".jpg")
    for c in PHOTO["cuts"]:
        if c.get("ref") == "IMG1":
            c["ref"] = pick1["ref"]
        elif c.get("ref") == "IMG2":
            c["ref"] = pick2["ref"]
    for c in SLIDE["cuts"]:
        if c["blocks"][0].get("ref") == "IMG1":
            c["blocks"][0]["ref"] = pick1["ref"]
        elif c["blocks"][0].get("ref") == "IMG2":
            c["blocks"][0]["ref"] = pick2["ref"]
    gen1 = _pc.generated_store(ORDER, "Lake at dawn",
                               b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
                               0.01, "muse-image-1.0",
                               set_by="image_gene@p1")
    gen2 = _pc.generated_store(ORDER, "City at dusk",
                               b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
                               0.01, "muse-image-1.0",
                               set_by="image_gene@p2")

    run_dir = os.path.join(RUNS, "rparts")
    os.makedirs(run_dir, exist_ok=True)
    wres(run_dir, "pd_marty", "pd_marty",
         {"concept": CONCEPT, "structure": STRUCT})
    wres(run_dir, "plan_ash", "plan_ash",
         {"storyboard_draft": DRAFT})
    wres(run_dir, "voice_wren", "voice_wren",
         {"narration": NARR})
    wres(run_dir, "board_penn", "board_penn",
         {"storyboard": BOARD, "style_guide": GUIDE})
    events = []
    emit = lambda ev: events.append(ev)  # noqa: E731
    incoming = [
        {"id": "c81", "from": "pd_marty",
         "categories": ["structure"]},
        {"id": "c82", "from": "pd_marty",
         "categories": ["concept"]},
        {"id": "c83", "from": "plan_ash",
         "categories": ["storyboard_draft"]},
        {"id": "c84", "from": "voice_wren",
         "categories": ["narration"]},
        {"id": "c85", "from": "board_penn",
         "categories": ["storyboard"]},
        {"id": "c86", "from": "board_penn",
         "categories": ["style_guide"]}]
    step = flow._run_code_node(run_dir, "part_split", ORDER,
                               BRIEF, incoming, emit)
    ok(step.get("ok"), "part_split code node runs: %s"
       % step.get("error", "ok"))
    split = parts.load_split(run_dir)
    ok(split is not None and len(split["parts"]) == 3,
       "split plan stored")
    sres = results.load_result(
        os.path.join(run_dir, "part_split", "result.json"))
    ok(set(sres["categories"])
       == {"split_plan", "narration", "storyboard"}
       and sres["status"] == "checked",
       "part_split result carries plan + shared inputs")
    ok(any("source" in g for g in
           split["row_writes"]["granted"])
       and any("voice" in g for g in
               split["row_writes"]["granted"]),
       "clone rows written on source + voice")

    sentry = _pc.load_entry_by_ref(SRC)
    ok(_pc.entry_parts_allow(sentry, "photo_pia@p1", ORDER,
                             SRC + "#fig1.1")
       and not _pc.entry_parts_allow(sentry, "photo_pia@p2",
                                     ORDER, SRC + "#fig1.1")
       and not _pc.entry_parts_allow(sentry, "image_gene@p2",
                                     ORDER, SRC + "#fig1.1"),
       "part-1-only figure opens for p1, not p2")
    ok(_pc.entry_parts_allow(sentry, "anim_max@p2", ORDER,
                             SRC + "#s2.1/p1")
       and not _pc.entry_parts_allow(sentry, "anim_max@p2",
                                     ORDER, SRC + "#s1.1/p1"),
       "anim rows hold only their part's items")
    ventry = _pc.load_entry_by_ref(VOICE)
    ok(_pc.entry_parts_allow(ventry, "slide_remy@p1", ORDER,
                             VOICE + "#s1c1")
       and not _pc.entry_parts_allow(ventry, "slide_remy@p1",
                                     ORDER, VOICE + "#s3c1"),
       "voice rows hold only the part's clips")

    e1 = _pc.load_entry_by_ref(pick1["ref"])
    got1 = sorted(r["agent"] for r in e1["recipients"]
                  if r.get("order_id") == ORDER)
    ok(got1 == ["board_vera@p1", "slide_remy@p1",
                "video_production"],
       "pia@p1 pick grants only p1 clones + video")
    e2 = _pc.load_entry_by_ref(pick2["ref"])
    ok(not _pc.may_read(e2, "board_vera@p1", ORDER)
       and _pc.may_read(e2, "board_vera@p2", ORDER),
       "vera@p1 cannot open pia@p2's picture")
    full, err = _media._resolve_view(
        {"producer": "board_vera@p1", "order_id": ORDER,
         "run_dir": tmp},
        {"ref": pick2["ref"]})
    ok(full is None and err == "no access to this item",
       "view tool refuses the foreign picture")
    full, err = _media._resolve_view(
        {"producer": "board_vera@p2", "order_id": ORDER,
         "run_dir": tmp},
        {"ref": pick2["ref"]})
    ok(bool(full) and not err, "view tool opens the own picture")
    g1 = _pc.load_entry_by_ref(gen1["ref"])
    gotg = sorted(r["agent"] for r in g1["recipients"]
                  if r.get("order_id") == ORDER)
    ok(gotg == ["board_vera@p1", "slide_remy@p1",
                "video_production"],
       "gene@p1 image grants only p1 clones + video")

    def incoming_for(node):
        lines = [{"id": "x", "from": "part_split",
                  "categories": [c]}
                 for c in ("split_plan", "narration",
                           "storyboard")]
        if node == "board_vera":
            lines += [{"id": "y%d" % i, "from": s,
                       "categories": [c]}
                      for i, (s, c) in enumerate([
                          ("photo_pia", "photo_picks"),
                          ("image_gene", "gen_picks"),
                          ("anim_max", "anim_picks")])]
        if node == "slide_remy":
            lines.append({"id": "z", "from": "board_vera",
                          "categories": ["slide_draft"]})
        return lines

    for node in parts.CLONE_NODES:
        step = flow._run_agent_node(run_dir, node, ORDER, BRIEF,
                                    incoming_for(node), stub,
                                    emit)
        ok(step.get("ok"), "%s clones run: %s"
           % (node, step.get("error", "ok")))
    for node in parts.CLONE_NODES:
        ndir = os.path.join(run_dir, node)
        missing = []
        for no in (1, 2, 3):
            pdir = os.path.join(ndir, "p%d" % no)
            for fn in ("INPUTS.md", "INPUTS.json",
                       "result.json", "report.md",
                       "usage.json"):
                if not os.path.isfile(os.path.join(pdir, fn)):
                    missing.append("p%d/%s" % (no, fn))
        ok(not missing, "%s wrote all per-clone files%s" % (
            node, "" if not missing else " (missing %s)"
            % ",".join(missing)))
    pia_in = open(os.path.join(run_dir, "photo_pia", "p1",
                               "INPUTS.md"),
                  encoding="utf-8").read()
    ok("s1c1" in pia_in and "s1c2" in pia_in
       and "s2c1" not in pia_in and "s3c2" not in pia_in
       and "You are Part 1" in pia_in
       and "Thrift" in pia_in and "#e0a458" in pia_in
       and "1.2 Middles" in pia_in,
       "clone inputs hold own cuts + shared context")
    vera_in = open(os.path.join(run_dir, "board_vera", "p2",
                                "INPUTS.md"),
                   encoding="utf-8").read()
    ok("s2c1" in vera_in and "s1c1" not in vera_in
       and "You are Part 2" in vera_in,
       "vera@p2 inputs hold only part 2")
    merged = results.load_result(
        os.path.join(run_dir, "photo_pia", "result.json"))
    ok([c["cut_id"] for c in
        merged["categories"]["photo_picks"]["data"]["cuts"]]
       == ["s1c1", "s1c2", "s2c1", "s2c2", "s3c1", "s3c2"]
       and merged["status"] == "checked"
       and merged["producer"] == "photo_pia",
       "merged photo picks run in part order")
    gm = results.load_result(
        os.path.join(run_dir, "image_gene", "result.json"))
    gdata = gm["categories"]["gen_picks"]["data"]
    ok([im["cut_id"] for im in gdata["images"]]
       == ["s1c1", "s2c1", "s3c1"]
       and len(gdata["cuts"]) == 6,
       "merged gen picks join cuts + images")
    ok(os.path.isfile(os.path.join(run_dir, "slide_remy",
                                   "slides", "s2c1.png"))
       and os.path.isfile(os.path.join(run_dir, "slide_remy",
                                       "slides", "s3c2.props.json")),
       "merge copies slide sidecars up")
    muse = json.load(open(os.path.join(run_dir, "photo_pia",
                                       "usage.json"),
                          encoding="utf-8"))
    ok(muse["prompt_tokens"] == 30
       and muse["completion_tokens"] == 15,
       "node usage sums the clones")
    clones_done = sorted(
        e["agent"] for e in events
        if e.get("ev") == "agent_done" and "@p" in e["agent"])
    ok(clones_done == sorted("%s@p%d" % (n, i)
                             for n in parts.CLONE_NODES
                             for i in (1, 2, 3)),
       "every clone logged start/done")

    # ---- writer checks per clone ----
    gdir = os.path.join(run_dir, "image_gene", "p1")
    ctx = {"producer": "image_gene@p1", "order_id": ORDER,
           "run_id": "rparts", "run_dir": gdir,
           "agent_dir": os.path.join(ROOT, "agents",
                                     "image_gene"),
           "gene_quota": 2}
    foreign = {"cuts": [
        {"cut_id": "s1c1", "decision": "none"},
        {"cut_id": "s1c2", "decision": "none"},
        {"cut_id": "s2c1", "decision": "none"}],
        "images": []}
    r = _tools.write_gen_picks(ctx, {"gen_picks": foreign})
    ok(not r.get("ok") and "cut set" in " ".join(r["errors"]),
       "writer rejects a foreign cut id")
    over = {"cuts": [
        {"cut_id": "s1c1", "decision": "generate",
         "prompt": "Lake at dawn", "reason": "a"},
        {"cut_id": "s1c2", "decision": "generate",
         "prompt": "City at dusk", "reason": "b"}],
        "images": [
            {"cut_id": "s1c1", "file": "gen.png",
             "prompt": "Lake at dawn", "reused": False},
            {"cut_id": "s1c2", "file": "gen.png",
             "prompt": "City at dusk", "reused": False}]}
    ctx1 = dict(ctx, gene_quota=1)
    r = _tools.write_gen_picks(ctx1, {"gen_picks": over})
    ok(not r.get("ok") and "quota" in " ".join(r["errors"]),
       "writer enforces the part quota")
    mixed = {"cuts": [
        {"cut_id": "s1c1", "decision": "generate",
         "prompt": "Lake at dawn", "reason": "a"},
        {"cut_id": "s1c2", "decision": "none"}],
        "images": [
            {"cut_id": "s1c1", "file": "gen.png",
             "prompt": "Lake at dawn", "reused": False}]}
    r = _tools.write_gen_picks(ctx, {"gen_picks": mixed})
    ok(r.get("ok"), "writer accepts own cuts within quota")

    vdir = os.path.join(run_dir, "board_vera", "p1")
    vctx = {"producer": "board_vera@p1", "order_id": ORDER,
            "run_id": "rparts", "run_dir": vdir,
            "agent_dir": os.path.join(ROOT, "agents",
                                      "board_vera")}

    def vobj(ref):
        return {"cuts": [
            {"cut_id": "s1c1", "start_s": 0, "end_s": 15,
             "preset": "full",
             "blocks": [{"kind": "photo", "order": 1,
                         "appear_s": 0,
                         "box": {"x": 64, "y": 64, "w": 1152,
                                 "h": 500},
                         "ref": ref, "reason": "fits"}],
             "on_screen_text": ["T"], "transitions": [],
             "why": "simple"},
            {"cut_id": "s1c2", "start_s": 15, "end_s": 30,
             "preset": "full",
             "blocks": [{"kind": "text", "order": 1,
                         "appear_s": 0,
                         "box": {"x": 64, "y": 64, "w": 1152,
                                 "h": 200},
                         "data": {"lines": ["T"]},
                         "reason": "line"}],
             "on_screen_text": ["T"], "transitions": [],
             "why": "simple"}]}

    r = _tools.write_slide_draft(vctx, {"slide_draft": vobj(
        pick2["ref"])})
    ok(not r.get("ok")
       and "not listed for you" in " ".join(r["errors"]),
       "vera cannot save another part's picture")
    r = _tools.write_slide_draft(vctx, {"slide_draft": vobj(
        pick1["ref"])})
    ok(r.get("ok"), "vera saves her own part's picture: %s"
       % ("" if r.get("ok") else r.get("errors")))

    # ---- generate tool: quota + reuse rows ----
    _media._IMAGE_FN = lambda prompt: (
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "muse-image-1.0",
        0.01)
    try:
        gtmp = os.path.join(tmp, "genclone")
        os.makedirs(gtmp, exist_ok=True)
        gctx = {"producer": "image_gene@p3", "order_id": ORDER,
                "run_id": "rparts", "run_dir": gtmp,
                "gene_quota": 1}
        r = _media.pc_generate_image(gctx, {"prompt": "New hill"})
        ok(r.get("ok") and not r.get("reused_entry"),
           "first generate call works")
        r = _media.pc_generate_image(gctx, {"prompt": "New sea"})
        ok(r.get("error", "").startswith("part quota"),
           "second call hits the part quota")
        r = _media.pc_generate_image(gctx,
                                     {"prompt": "Lake at dawn"})
        ok(r.get("ok") and r.get("reused_entry"),
           "same prompt reuses across parts")
        g1b = _pc.load_entry_by_ref(gen1["ref"])
        agents3 = sorted(a["agent"] for a in
                         g1b.get("recipients", [])
                         if a.get("order_id") == ORDER)
        ok("board_vera@p3" in agents3
           and "slide_remy@p3" in agents3,
           "reuse grants the reusing part")
    finally:
        _media._IMAGE_FN = None
finally:
    _pc.ROOT_OVERRIDE = None
    flow.RUNS_DIR = real_runs

print("fails: %d" % fails)
raise SystemExit(1 if fails else 0)
