"""Board API checks (STEP 1). Stdlib only.

Run: python scripts/board_check.py. No model, TTS, image, or speech
calls: stub run folders + stub PC entries under a temp dir only.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
from agents._frame import board
from agents._frame import pc as _pc

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


tmp = tempfile.mkdtemp(prefix="boardcheck_")
RUNS = os.path.join(tmp, "runs")
os.makedirs(RUNS)

SID = _pc.content_id("source:board-chapter")
VID = _pc.content_id("voice:ord-board-001")
IID = _pc.content_id("image:https://example.com/pic")
SRC_REF = "pc://source/%s" % SID
VOICE_REF = "pc://voice/%s" % VID
IMG_REF = "pc://image/%s" % IID

STRUCT = {
    "source_ref": SRC_REF,
    "parts": [
        {"id": "p1", "heading": "1.1 First Steps",
         "ref": SRC_REF + "#s1.1", "covers": "basics",
         "keywords": ["alpha"]},
        {"id": "p2", "heading": "1.2 Next Moves",
         "ref": SRC_REF + "#s1.2", "covers": "advanced",
         "keywords": ["beta"]}],
    "links": [{"from": "p1", "to": "p2", "why": "builds up"}],
    "duration": {"total_s": 60, "parts": [
        {"part_id": "p1", "seconds": 30, "why": "intro"},
        {"part_id": "p2", "seconds": 30, "why": "deep"}]}}

DRAFT = {"total_s": 60, "scenes": [
    {"n": 1, "start_s": 0, "end_s": 30, "part_id": "p1",
     "role": "explain", "viewer_learns": "msg one",
     "screen_idea": "card", "narration_points": [],
     "materials": [{"ref": SRC_REF + "#s1.1/p1", "from": "source",
                    "how_used": "core fact"}],
     "handoff": [], "next_link": "then"},
    {"n": 2, "start_s": 30, "end_s": 60, "part_id": "p2",
     "role": "recap", "viewer_learns": "msg two",
     "screen_idea": "card", "narration_points": [],
     "materials": [], "handoff": [], "next_link": ""}],
    "unused_picks": []}

NARR = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 15,
     "lines": [{"text": "Alpha beta.", "citations": []},
               {"text": "Gamma delta.", "citations": []}],
     "words": 4,
     "audio": {"voice_pc_ref": VOICE_REF + "#s1c1",
               "seconds": 14.5},
     "attempts": 1},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 15, "end_s": 30,
     "lines": [{"text": "Second cut line here now.",
                "citations": []}],
     "words": 4,
     "audio": {"voice_pc_ref": VOICE_REF + "#s1c2",
               "seconds": 15.0},
     "attempts": 2},
    {"cut_id": "s2c1", "scene_n": 2, "start_s": 30, "end_s": 60,
     "lines": [{"text": "Third cut speaks.", "citations": []}],
     "words": 3,
     "audio": {"voice_pc_ref": VOICE_REF + "#s2c1",
               "seconds": 29.0},
     "attempts": 1}]}

BOARD = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 15,
     "show_what": "Show a card", "show_why": "Intro",
     "on_screen_text": ["Alpha", "Beta"]},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 15, "end_s": 30,
     "show_what": "Show a chart", "show_why": "Proof",
     "on_screen_text": ["Numbers"]},
    {"cut_id": "s2c1", "scene_n": 2, "start_s": 30, "end_s": 60,
     "show_what": "Show recap", "show_why": "Close",
     "on_screen_text": ["Thanks"]}]}

GUIDE = {"palette": {"background": "#101418", "text": "#f5f2ea",
                     "accent": "#e0a458"},
         "fonts": {"heading": "sans", "body": "sans"},
         "image_tone": "plain", "rules": ["Keep it calm."]}

PHOTO = {"cuts": [
    {"cut_id": "s1c1", "decision": "use", "kind": "web",
     "ref": IMG_REF, "file": "pick.jpg",
     "source_url": "https://example.com/pic", "license": "CC0",
     "reason": "shows alpha"},
    {"cut_id": "s1c2", "decision": "use", "kind": "source_figure",
     "ref": SRC_REF + "#fig1.1", "file": "fig1.png",
     "source_url": "", "license": "CC0",
     "reason": "from the book"},
    {"cut_id": "s2c1", "decision": "none",
     "reason": "no visual needed"}]}

GEN = {"cuts": [
    {"cut_id": "s1c1", "decision": "generate",
     "prompt": "A calm lake at dawn",
     "reason": "needs art"},
    {"cut_id": "s1c2", "decision": "none"},
    {"cut_id": "s2c1", "decision": "none"}],
    "images": [{"cut_id": "s1c1", "file": "gen.png",
                "prompt": "A calm lake at dawn",
                "reused": False}]}

ANIM = {"cuts": [
    {"cut_id": "s1c1", "decision": "use", "template": "bar",
     "values": {"labels": ["a", "b"], "series": [1, 2]},
     "refs": [{"ref": SRC_REF + "#s1.1/p1", "quote": "one two"}],
     "reason": "numbers"},
    {"cut_id": "s1c2", "decision": "none",
     "reason": "no numbers here"},
    {"cut_id": "s2c1", "decision": "none"}]}

SLIDE = {"cuts": [
    {"cut_id": "s1c1", "start_s": 0, "end_s": 15,
     "preset": "main_side",
     "blocks": [
         {"kind": "photo", "box": {"x": 64, "y": 64, "w": 560,
                                  "h": 400},
          "ref": IMG_REF, "reason": "shows alpha"},
         {"kind": "text", "box": {"x": 660, "y": 64, "w": 556,
                                 "h": 200},
          "reason": "caption"}],
     "on_screen_text": ["Alpha"], "transitions": [],
     "why": "photo left"},
    {"cut_id": "s1c2", "start_s": 15, "end_s": 30,
     "preset": "full",
     "blocks": [{"kind": "source_figure",
                 "box": {"x": 64, "y": 64, "w": 1152,
                         "h": 500},
                 "ref": SRC_REF + "#fig1.1",
                 "reason": "book figure"}],
     "on_screen_text": ["Numbers"], "transitions": [],
     "why": "figure only"},
    {"cut_id": "s2c1", "start_s": 30, "end_s": 60,
     "preset": "full",
     "blocks": [{"kind": "text",
                 "box": {"x": 64, "y": 64, "w": 1152,
                         "h": 200},
                 "reason": "closing line"}],
     "on_screen_text": ["Thanks"], "transitions": [],
     "why": "text card"}]}

RLOG = {"cuts": [
    {"cut_id": "s1c1", "slide_file": "slides/s1c1.png",
     "renders_n": 2,
     "adjustments": [{"field": "x", "was": 64, "now": 80}],
     "issues": ["font small"]},
    {"cut_id": "s1c2", "slide_file": "",
     "status": "remotion_unavailable", "renders_n": 0,
     "adjustments": [], "issues": []},
    {"cut_id": "s2c1", "slide_file": "slides/s2c1.png",
     "renders_n": 1, "adjustments": [], "issues": []}]}

ASSEMBLY = {"segments": [
    {"cut_id": "s1c1", "at_s": 0, "dur_s": 15},
    {"cut_id": "s1c2", "at_s": 15, "dur_s": 15},
    {"cut_id": "s2c1", "at_s": 30, "dur_s": 30}],
    "total_s": 60}

USAGE = {"llm_calls": 2, "prompt_tokens": 100,
         "completion_tokens": 50, "tools": {"write_x": 1}}


def wres(run, node, categories, usage=True, report=False):
    ndir = os.path.join(RUNS, run, node)
    os.makedirs(ndir, exist_ok=True)
    res = {"producer": node, "format_version": 1,
           "order_id": "ord-board-001", "run_id": run,
           "created_at": "2026-01-01", "status": "unverified",
           "categories": {
               name: {"version": 1, "data": data}
               for name, data in categories.items()}}
    with open(os.path.join(ndir, "result.json"), "w",
              encoding="utf-8") as f:
        json.dump(res, f)
    if usage:
        with open(os.path.join(ndir, "usage.json"), "w",
                  encoding="utf-8") as f:
            json.dump(USAGE, f)
    if report:
        with open(os.path.join(ndir, "report.md"), "w",
                  encoding="utf-8") as f:
            f.write("# report\n")


def wstatus(run, status):
    with open(os.path.join(RUNS, run, "STATUS.json"), "w",
              encoding="utf-8") as f:
        json.dump(status, f)


NODES = [node for _k, node, _w, _t, _l in board.STAGES]

FULL = [("pd_marty", {"structure": STRUCT}),
        ("plan_ash", {"storyboard_draft": DRAFT}),
        ("voice_wren", {"narration": NARR}),
        ("board_penn", {"storyboard": BOARD,
                        "style_guide": GUIDE}),
        ("photo_pia", {"photo_picks": PHOTO}),
        ("image_gene", {"gen_picks": GEN}),
        ("anim_max", {"anim_picks": ANIM}),
        ("board_vera", {"slide_draft": SLIDE}),
        ("slide_remy", {"render_log": RLOG}),
        ("video_production", {"video": {"file": "video.mp4"}})]

for node, cats in FULL:
    wres("boardfull1", node, cats, report=(node == "pd_marty"))
wstatus("boardfull1", {"run_id": "boardfull1", "flow_id": "default",
                       "order_id": "ord-board-001",
                       "state": "done", "approved": NODES})
vdir = os.path.join(RUNS, "boardfull1", "video_production")
with open(os.path.join(vdir, "assembly.json"), "w",
          encoding="utf-8") as f:
    json.dump(ASSEMBLY, f)
sdir = os.path.join(RUNS, "boardfull1", "slide_remy", "slides")
os.makedirs(sdir, exist_ok=True)
with open(os.path.join(sdir, "s1c1.png"), "wb") as f:
    f.write(b"\x89PNG fake")

for node, cats in FULL[:4]:
    wres("boardpart1", node, cats)
wstatus("boardpart1", {"run_id": "boardpart1", "state": "step_paused",
                       "last": "board_penn",
                       "approved": ["pd_marty", "plan_ash"]})

wres("boarderr1", "pd_marty", {"structure": STRUCT})
wstatus("boarderr1", {"run_id": "boarderr1", "state": "failed",
                      "error": "boom"})
with open(os.path.join(RUNS, "boarderr1", "events.jsonl"), "w",
          encoding="utf-8") as f:
    f.write('{"ev": "agent_start", "agent": "pd_marty"}\n')
    f.write('{"ev": "agent_done", "agent": "pd_marty"}\n')
    f.write('{"ev": "agent_start", "agent": "plan_ash"}\n')

os.makedirs(os.path.join(RUNS, "boardrun1"), exist_ok=True)
wstatus("boardrun1", {"run_id": "boardrun1",
                      "state": "step_paused", "approved": []})
with open(os.path.join(RUNS, "boardrun1", "events.jsonl"), "w",
          encoding="utf-8") as f:
    f.write('{"ev": "agent_start", "agent": "image_gene"}\n')

os.makedirs(os.path.join(RUNS, "boardempty1"), exist_ok=True)
wstatus("boardempty1", {"run_id": "boardempty1"})

os.makedirs(os.path.join(RUNS, "boardcorrupt1", "pd_marty"),
            exist_ok=True)
wstatus("boardcorrupt1", {"run_id": "boardcorrupt1"})
with open(os.path.join(RUNS, "boardcorrupt1", "pd_marty",
                        "result.json"), "w", encoding="utf-8") as f:
    f.write("{not json")

pdir = os.path.join(RUNS, "boardpath1", "slide_remy", "slides")
os.makedirs(pdir, exist_ok=True)
with open(os.path.join(pdir, "a.png"), "wb") as f:
    f.write(b"fake-png")


def wentry(pcname, doc_id, entry):
    edir = _pc.entry_dir(pcname, doc_id)
    os.makedirs(edir, exist_ok=True)
    with open(os.path.join(edir, "entry.json"), "w",
              encoding="utf-8") as f:
        json.dump(entry, f)


_pc.ROOT_OVERRIDE = tmp
try:
    wentry("source", SID, {
        "pc": "source", "doc_id": SID, "ref": SRC_REF,
        "paragraphs": [{"addr": "s1.1/p1", "pages": [3, 4],
                        "text": "one two"}],
        "figures": [{"addr": "fig1.1", "file": "fig1.png",
                     "page": 3}]})
    wentry("voice", VID, {
        "pc": "voice", "doc_id": VID, "ref": VOICE_REF,
        "cuts": {
            "s1c1": {"file": "s1c1-t1.wav", "engine": "piper"},
            "s1c2": {"file": "s1c2-t2.wav", "engine": "piper"},
            "s2c1": {"file": "s2c1-t1.wav", "engine": "piper"}}})

    out = board.build_board("boardfull1", runs_root=RUNS)
    ok(out.get("ok") is True, "full run builds")
    ok(out.get("run_state") == "done", "full run state done")
    got_keys = [s["key"] for s in out["stages"]]
    ok(got_keys == ["marty", "ash", "wren", "penn", "pia", "gene",
                    "max", "vera", "remy", "video"],
       "stage order marty..video")
    by_key = {s["key"]: s for s in out["stages"]}
    ok(all(s["status"] == "ok" for s in out["stages"]),
       "full run: every stage ok")
    ok(by_key["wren"]["label"] == "Lines \u00b7 voice"
       and by_key["wren"]["who"] == "Wren"
       and by_key["video"]["who"] == "Program"
       and by_key["video"]["team"] == "video",
       "stage who/team/label")
    ok(by_key["marty"]["cost"]["llm_calls"] == 2,
       "stage cost passes usage through")
    files = by_key["marty"]["files"]
    ok(files.get("report.md", "").endswith(
        "file?node=pd_marty&name=report.md")
        and "result.json" in files
        and "INPUTS.md" not in files,
       "stage files link existing files only")
    ok(len(out["parts"]) == 2, "two parts")
    p1 = out["parts"][0]
    ok(p1["no"] == 1 and p1["title"] == "1.1 First Steps"
       and p1["time"] == 30 and p1["pages"] == [3, 4],
       "part 1 meta (no/title/time/pages)")
    ok(out["parts"][1]["pages"] == [], "part 2 has no pages")
    ok(len(p1["scenes"]) == 1, "part 1 holds one scene")
    sc1 = p1["scenes"][0]
    ok(sc1["msg"] == "msg one" and sc1["time"] == 30
       and sc1["materials"] == [{"ref": SRC_REF + "#s1.1/p1",
                                 "from": "source"}],
       "scene msg/time/materials")
    ok([c["cut_id"] for c in sc1["cuts"]] == ["s1c1", "s1c2"],
       "scene cuts in start order")
    c1 = sc1["cuts"][0]
    ok(c1["line"] == "Alpha beta. Gamma delta."
       and c1["sec"] == 15 and c1["t0"] == 0,
       "cut line/sec/t0")
    ok(c1["voice"]["file"] == "/api/pcs/voice/entries/%s/media/"
       "s1c1-t1.wav" % VID
       and c1["voice"]["attempts"] == 1
       and c1["voice"]["engine"] == "piper",
       "cut voice file/attempts/engine")
    ok(c1["screen"] == "Show a card"
       and c1["text"] == ["Alpha", "Beta"],
       "cut screen + on-screen text")
    ok(len(c1["pia"]) == 1
       and c1["pia"][0]["file"] == "/api/pcs/image/entries/%s/"
       "media/pick.jpg" % IID
       and c1["pia"][0]["source"] == "https://example.com/pic"
       and c1["pia"][0]["license"] == "CC0"
       and c1["pia"][0]["reason"] == "shows alpha",
       "pia web pick with file URL")
    c2 = sc1["cuts"][1]
    ok(c2["pia"][0]["file"].endswith("/figures/fig1.png")
       and c2["pia"][0]["source"] == SRC_REF + "#fig1.1",
       "pia source-figure pick falls back to ref")
    ok(c1["gene"]["prompt"] == "A calm lake at dawn"
       and c1["gene"]["file"].endswith("/media/gen.png")
       and "/generated/entries/" in c1["gene"]["file"],
       "gene prompt + file URL")
    ok(c2["gene"] is None, "gene none cut gives null")
    ok(c1["max"]["template"] == "bar"
       and c1["max"]["values"]["labels"] == ["a", "b"]
       and c1["max"]["skipped_reason"] is None,
       "max use pick template + values")
    ok(c2["max"]["skipped_reason"] == "no numbers here"
       and c2["max"]["template"] is None,
       "max skipped reason kept")
    ok(c1["vera"]["preset"] == "main_side"
       and c1["vera"]["blocks"][0]["type"] == "photo"
       and c1["vera"]["blocks"][0]["ref"] == IMG_REF
       and c1["vera"]["blocks"][0]["box"]["w"] == 560
       and c1["vera"]["reasons"] == ["shows alpha", "caption"],
       "vera preset + blocks + reasons")
    ok(c1["remy"]["png"].endswith(
        "file?node=slide_remy&path=slides/s1c1.png")
       and c1["remy"]["renders"] == 2
       and c1["remy"]["log"] == ["x: 64 -> 80", "font small"],
       "remy png + renders + log")
    ok(c2["remy"]["png"] is None and c2["remy"]["renders"] == 0
       and c2["remy"]["log"] == [],
       "remy unavailable cut has no png")
    c3 = out["parts"][1]["scenes"][0]["cuts"][0]
    ok(c3["remy"]["png"] is None, "missing slide file gives no png")
    ok(c1["video"] == {"t0": 0, "t1": 15,
                       "subtitle": c1["line"]},
       "video t0/t1/subtitle")
    ok(set(c1["cell_status"]) == set(board.COLUMNS)
       and all(v == "ok" for v in c1["cell_status"].values()),
       "full cut: all 12 cells ok")
    ok(c3["cell_status"]["photo"] == "none",
       "skipped pia cut gives none")
    ok(c2["cell_status"]["image"] == "none"
       and c2["cell_status"]["anim"] == "none",
       "skipped gene/max cuts give none")
    ok(c3["max"]["skipped_reason"] is None,
       "reason-less skip keeps null")
    ok(out["style_guide"]["palette"]["accent"] == "#e0a458",
       "style guide passed through")

    part = board.build_board("boardpart1", runs_root=RUNS)
    pk = {s["key"]: s["status"] for s in part["stages"]}
    ok(pk["marty"] == "ok" and pk["ash"] == "ok"
       and pk["wren"] == "done" and pk["penn"] == "done",
       "partial run: marty/ash ok, wren/penn done")
    ok(all(pk[k] == "wait" for k in
           ("pia", "gene", "max", "vera", "remy", "video")),
       "partial run: pia onward waits")
    pc1 = part["parts"][0]["scenes"][0]["cuts"][0]
    ok(pc1["pia"] == [] and pc1["gene"] is None
       and pc1["max"] is None and pc1["vera"] is None
       and pc1["remy"] is None and pc1["video"] is None,
       "partial run: later columns empty")
    ok(pc1["voice"]["file"] is not None
       and pc1["screen"] == "Show a card",
       "partial run: earlier columns filled")
    ok(all(pc1["cell_status"][c] == "wait" for c in
           ("photo", "image", "anim", "slide_plan",
            "slide_build", "video")),
       "partial run: later cells wait")
    ok(part["style_guide"] is not None, "partial run keeps guide")

    err = board.build_board("boarderr1", runs_root=RUNS)
    ek = {s["key"]: s["status"] for s in err["stages"]}
    ok(err["run_state"] == "failed" and err["run_error"] == "boom"
       and ek["marty"] == "done" and ek["ash"] == "err"
       and ek["wren"] == "wait",
       "failed run marks the crashed stage")
    ok(len(err["parts"]) == 2
       and err["parts"][0]["scenes"] == [],
       "failed run: parts without scenes, no crash")

    run = board.build_board("boardrun1", runs_root=RUNS,
                            running=True)
    rk = {s["key"]: s["status"] for s in run["stages"]}
    ok(rk["gene"] == "run" and rk["pia"] == "wait",
       "running flag marks the live stage")
    idle = board.build_board("boardrun1", runs_root=RUNS)
    ok(all(s["status"] == "wait" for s in idle["stages"]),
       "same run idles without the flag")

    empty = board.build_board("boardempty1", runs_root=RUNS)
    ok(empty.get("ok") is True and empty["parts"] == []
       and empty["style_guide"] is None
       and all(s["status"] == "wait"
               for s in empty["stages"]),
       "empty run: wait everywhere, no crash")

    corrupt = board.build_board("boardcorrupt1", runs_root=RUNS)
    ck = {s["key"]: s["status"] for s in corrupt["stages"]}
    ok(corrupt.get("ok") is True and ck["marty"] == "wait"
       and corrupt["parts"] == [],
       "corrupt result.json counts as missing")

    ok(board.build_board("..", runs_root=RUNS).get("ok")
       is False, "bad run id rejected")
    ok(board.build_board("nosuchrun", runs_root=RUNS).get("ok")
       is False, "missing run rejected")

    good = board.safe_run_path(RUNS, "boardpath1", "slide_remy",
                               "slides/a.png")
    ok(bool(good) and good.endswith("a.png"), "safe path resolves")
    for bad in ("../x.png", "..\\x.png", "/abs.png", "C:/x.png",
                "slides/a.exe", "slides/missing.png",
                "slides/../../x.png", ""):
        ok(board.safe_run_path(RUNS, "boardpath1", "slide_remy",
                               bad) is None,
           "unsafe path rejected: %r" % bad)
    ok(board.safe_run_path(RUNS, "boardpath1", "a/b",
                           "slides/a.png") is None,
       "unsafe node rejected")
    ok(board.safe_run_path(RUNS, "../r", "slide_remy",
                           "slides/a.png") is None,
       "unsafe run id rejected")

    def wsplit(run):
        sdir = os.path.join(RUNS, run, "part_split")
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "split.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"version": 1, "parts": [
                {"no": 1, "part_id": "p1"},
                {"no": 2, "part_id": "p2"}]}, f)

    def wclone(run, node, no):
        pdir = os.path.join(RUNS, run, node, "p%d" % no)
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, "result.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"producer": "%s@p%d" % (node, no),
                       "categories": {}}, f)

    for node, cats in FULL[:4] + FULL[4:9]:
        wres("boardmix1", node, cats)
    wsplit("boardmix1")
    wclone("boardmix1", "photo_pia", 1)
    wclone("boardmix1", "photo_pia", 2)
    wclone("boardmix1", "image_gene", 1)
    wclone("boardmix1", "anim_max", 1)
    wclone("boardmix1", "board_vera", 1)
    wclone("boardmix1", "board_vera", 2)
    wclone("boardmix1", "slide_remy", 1)
    wstatus("boardmix1", {
        "run_id": "boardmix1", "state": "running", "approved": [
            "pd_marty", "plan_ash", "voice_wren", "board_penn",
            "photo_pia@p1", "anim_max@p1", "board_vera@p1",
            "slide_remy@p1"]})
    with open(os.path.join(RUNS, "boardmix1", "events.jsonl"),
              "w", encoding="utf-8") as f:
        f.write('{"ev": "agent_start", "agent": '
                '"image_gene@p2"}\n')

    mix = board.build_board("boardmix1", runs_root=RUNS)
    mk = {s["key"]: s for s in mix["stages"]}
    ok(mk["pia"]["status"] == "done"
       and [p["status"] for p in mk["pia"]["parts"]]
       == ["ok", "done"]
       and mk["pia"]["parts"][0]["clone"] == "photo_pia@p1",
       "mixed parts: p1 ok, p2 done")
    ok([p["status"] for p in mk["gene"]["parts"]]
       == ["done", "run"]
       and [p["status"] for p in mk["max"]["parts"]]
       == ["ok", "wait"]
       and [p["status"] for p in mk["vera"]["parts"]]
       == ["ok", "done"]
       and [p["status"] for p in mk["remy"]["parts"]]
       == ["ok", "wait"],
       "per-part pills run/wait/done/ok")
    ok("parts" not in mk["marty"]
       and "parts" not in mk["wren"],
       "story stages carry no part pills")
    m1 = mix["parts"][0]["scenes"][0]["cuts"][0]
    m3 = mix["parts"][1]["scenes"][0]["cuts"][0]
    ok(m1["part"] == 1 and m3["part"] == 2,
       "cuts carry their part number")
    ok(m1["cell_status"]["photo"] == "ok"
       and m1["cell_status"]["image"] == "done"
       and m1["cell_status"]["anim"] == "ok"
       and m1["cell_status"]["slide_plan"] == "ok"
       and m1["cell_status"]["slide_build"] == "ok",
       "part 1 cells follow their clones")
    ok(m3["cell_status"]["photo"] == "none"
       and m3["cell_status"]["image"] == "run"
       and m3["cell_status"]["anim"] == "wait"
       and m3["cell_status"]["slide_plan"] == "done"
       and m3["cell_status"]["slide_build"] == "wait"
       and m3["cell_status"]["line"] == "ok",
       "part 2 cells mix none/run/wait/done")

    for node, cats in FULL[:4]:
        wres("boardcerr1", node, cats)
    wres("boardcerr1", "photo_pia", {"photo_picks": PHOTO})
    wsplit("boardcerr1")
    wclone("boardcerr1", "photo_pia", 1)
    wstatus("boardcerr1", {"run_id": "boardcerr1",
                           "state": "failed", "error": "boom",
                           "approved": ["pd_marty", "plan_ash",
                                        "voice_wren", "board_penn",
                                        "photo_pia@p1"]})
    with open(os.path.join(RUNS, "boardcerr1", "events.jsonl"),
              "w", encoding="utf-8") as f:
        f.write('{"ev": "agent_start", "agent": '
                '"photo_pia@p2"}\n')
    cerr = board.build_board("boardcerr1", runs_root=RUNS)
    ck = {s["key"]: s for s in cerr["stages"]}
    ok([p["status"] for p in ck["pia"]["parts"]]
       == ["ok", "err"],
       "crashed clone marks err, sibling stays ok")
    ok(cerr["parts"][1]["scenes"][0]["cuts"][0]
       ["cell_status"]["photo"] == "err",
       "crashed part cell shows err")

    cdir = os.path.join(RUNS, "boardpath1", "photo_pia", "p1")
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "b.png"), "wb") as f:
        f.write(b"fake-png")
    ok(board.safe_run_path(RUNS, "boardpath1", "photo_pia@p1",
                           "b.png") is not None,
       "clone file resolves into the part folder")
    ok(board.safe_run_path(RUNS, "boardpath1", "photo_pia@p9",
                           "b.png") is None
       and board.safe_run_path(RUNS, "boardpath1",
                               "pd_marty@p1", "b.png") is None,
       "bad part and non-clone node rejected")
    ok(board.clone_run_dir("photo_pia@p2")
       == os.path.join("photo_pia", "p2")
       and board.clone_run_dir("photo_pia") == "photo_pia"
       and board.clone_run_dir("a/b") is None,
       "clone_run_dir maps ids safely")

    def wjson(path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def wjsonl(path, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    V = os.path.join(RUNS, "boardvrf1")
    os.makedirs(V, exist_ok=True)
    wstatus("boardvrf1", {"run_id": "boardvrf1",
                          "flow_id": "default",
                          "order_id": "ord-board-001",
                          "state": "running",
                          "current": "photo_pia@p1",
                          "approved": ["pd_marty"]})
    wjson(os.path.join(V, "flow.json"), {"id": "default"})
    wjsonl(os.path.join(V, "events.jsonl"), [
        {"at": "09:00:01", "ev": "agent_start",
         "agent": "pd_marty"},
        {"at": "09:00:05", "ev": "agent_done",
         "agent": "pd_marty"},
        {"at": "09:00:06", "ev": "agent_start",
         "agent": "photo_pia@p1"}])
    M = os.path.join(V, "pd_marty")
    wjson(os.path.join(M, "usage.json"),
          {"llm_calls": 2, "prompt_tokens": 100,
           "completion_tokens": 50})
    wjsonl(os.path.join(M, "events.jsonl"), [
        {"t": "09:00:02", "ev": "run_start",
         "agent": "pd_marty"},
        {"t": "09:00:03", "ev": "tool", "step": 1,
         "tool": "pc_read_source", "ok": True,
         "detail": "s1.1"},
        {"t": "09:00:04", "ev": "tool", "step": 2,
         "tool": "write_structure", "ok": True},
        {"t": "09:00:05", "ev": "run_done",
         "usage": {"prompt": 100, "completion": 50}}])
    wjson(os.path.join(M, "inputs_log.json"),
          {"node": "pd_marty", "order_id": "ord-board-001",
           "run_id": "boardvrf1", "received": [
               {"item": "request", "category": "request",
                "from": "sales_sam"}],
           "pc": [{"pc": "source", "kind": "full"}],
           "est_input_tokens": 1200, "sha1": "abc",
           "inputs_md_bytes": 10})
    wjson(os.path.join(M, "inputs_check.json"),
          {"node": "pd_marty", "spec": "expected_inputs.json",
           "ok": True, "missing": [], "extra": [],
           "wrong_part": [], "wrong_kind": []})
    wjsonl(os.path.join(M, "reads_log.jsonl"), [
        {"at": "2026-01-01T09:00:03", "tool": "pc_read_source",
         "pc": "source", "ref": SRC_REF, "section": "s1.1",
         "item": "", "allowed": True, "reason": ""}])
    P1 = os.path.join(V, "photo_pia", "p1")
    wjson(os.path.join(P1, "usage.json"),
          {"llm_calls": 1, "prompt_tokens": 10,
           "completion_tokens": 5})
    wjsonl(os.path.join(P1, "events.jsonl"), [
        {"t": "09:00:07", "ev": "tool", "step": 1,
         "tool": "pc_search_images", "ok": True,
         "detail": "alpha"},
        {"t": "09:00:08", "ev": "tool", "step": 2,
         "tool": "pc_pick_image", "ok": False,
         "error": "no access to this item"}])
    wjson(os.path.join(P1, "inputs_log.json"),
          {"node": "photo_pia@p1", "received": [],
           "pc": [], "est_input_tokens": 0, "sha1": "x",
           "inputs_md_bytes": 0})
    wjson(os.path.join(P1, "inputs_check.json"),
          {"node": "photo_pia@p1", "spec": "expected_inputs.json",
           "ok": False, "missing": ["concept"], "extra": [],
           "wrong_part": [], "wrong_kind": []})
    wjsonl(os.path.join(P1, "reads_log.jsonl"), [
        {"at": "2026-01-01T09:00:07",
         "tool": "pc_search_images", "pc": "image", "ref": "",
         "section": "", "item": "alpha", "allowed": True,
         "reason": ""},
        {"at": "2026-01-01T09:00:08", "tool": "pc_pick_image",
         "pc": "image", "ref": IMG_REF, "section": "",
         "item": "", "allowed": False,
         "reason": "no access to this item"}])
    G2 = os.path.join(V, "image_gene", "p2")
    wjsonl(os.path.join(G2, "events.jsonl"), [
        {"t": "09:00:09", "ev": "run_fail",
         "reason": "writer tool closed"}])

    full = board.build_board("boardvrf1", runs_root=RUNS)
    sm = full["summary"]
    ok(sm["state"] == "running"
       and sm["current"] == "photo_pia@p1"
       and sm["current_who"] == "Pia P1",
       "summary state/current/current_who")
    ok(isinstance(sm["elapsed_s"], int)
       and sm["elapsed_s"] >= 0,
       "summary elapsed seconds")
    ok(sm["cost"] == {"llm_calls": 3, "prompt_tokens": 110,
                      "completion_tokens": 55},
       "summary cost sums every usage.json")
    ok([(e["node"], e["part"]) for e in sm["errors"]]
       == [("image_gene", 2), ("photo_pia", 1)]
       and sm["errors"][0]["reason"] == "writer tool closed"
       and "no access" in sm["errors"][1]["reason"],
       "summary errors list node/part/reason")
    ok(len(sm["spec_failures"]) == 1
       and sm["spec_failures"][0]["node"] == "photo_pia"
       and sm["spec_failures"][0]["part"] == 1
       and sm["spec_failures"][0]["missing"] == ["concept"],
       "summary spec failures list node/part/missing")
    sm2 = board.build_summary("boardvrf1", runs_root=RUNS)
    ok(sm2.get("ok") is True
       and sm2["current_who"] == "Pia P1"
       and sm2["cost"]["llm_calls"] == 3,
       "build_summary matches the board summary")
    ok(board.build_summary("nosuchrun",
                           runs_root=RUNS).get("ok") is False,
       "summary rejects a missing run")

    mv = board.build_verify("boardvrf1", "pd_marty",
                            runs_root=RUNS)
    ok(mv.get("ok") is True and mv["clone"] == "pd_marty"
       and mv["inputs"]["est_input_tokens"] == 1200
       and len(mv["inputs"]["received"]) == 1
       and mv["spec"]["ok"] is True
       and len(mv["reads"]) == 1
       and mv["reads"][0]["allowed"] is True,
       "verify marty inputs/reads/spec")
    mts = [board._ev_time(r) for r in mv["events"]]
    ok(mts == sorted(mts)
       and [r.get("ev") for r in mv["events"]]
       == ["agent_start", "run_start", "tool", "tool",
           "agent_done", "run_done"],
       "verify marty events merge node + run rows in time order")
    mtools = [r for r in mv["events"]
              if r.get("ev") == "tool"]
    ok(all(r.get("phrase") for r in mtools)
       and mtools[0]["phrase"] == "Reading source s1.1"
       and mtools[1]["phrase"] == "Writing report\u2026",
       "verify tool rows carry plain phrases")
    ok(mv["cost"]["usage"]["llm_calls"] == 2
       and mv["cost"]["started"] == "09:00:01"
       and mv["cost"]["finished"] == "09:00:05"
       and mv["files"]["usage.json"].endswith(
           "file?node=pd_marty&name=usage.json")
       and mv["files"]["reads_log.jsonl"].endswith(
           "name=reads_log.jsonl"),
       "verify marty cost/span/file links")
    pv = board.build_verify("boardvrf1", "photo_pia@p1",
                            runs_root=RUNS)
    ok(pv.get("ok") is True and pv["part"] == 1
       and pv["spec"]["ok"] is False
       and pv["spec"]["missing"] == ["concept"]
       and sum(1 for r in pv["reads"]
               if r["allowed"] is False) == 1
       and any(r.get("error") for r in pv["events"]),
       "verify clone id form, spec fail, refused read")
    wv = board.build_verify("boardvrf1", "board_vera",
                            runs_root=RUNS)
    ok(wv.get("ok") is True
       and wv["inputs"] == {"present": False}
       and wv["spec"] == {"present": False}
       and wv["events"] == [] and wv["files"] == {},
       "verify missing stage returns empty sections")
    ok(board.build_verify("boardvrf1", "sales_sam",
                          runs_root=RUNS).get("ok") is False
       and board.build_verify("boardvrf1", "pd_marty", 1,
                              runs_root=RUNS).get("ok")
       is False
       and board.build_verify("boardvrf1", "photo_pia", 0,
                              runs_root=RUNS).get("ok")
       is False
       and board.build_verify("nosuchrun", "pd_marty",
                              runs_root=RUNS).get("ok")
       is False,
       "verify rejects bad node/part/run")
    lf = board.list_run_files("boardvrf1", runs_root=RUNS)
    paths = [e["path"] for e in lf["files"]]
    ok(lf.get("ok") is True and paths == sorted(paths)
       and "STATUS.json" in paths
       and "pd_marty/usage.json" in paths
       and "photo_pia/p1/events.jsonl" in paths
       and [e for e in lf["files"]
            if e["path"] == "STATUS.json"][0]["node"] == "",
       "run files list sorted paths, root node empty")
    ok(board.list_run_files("nosuchrun",
                            runs_root=RUNS).get("ok")
       is False, "run files reject a missing run")
    ok(board.safe_run_path(RUNS, "boardvrf1", "",
                           "STATUS.json") is not None
       and board.safe_run_path(RUNS, "boardvrf1", "",
                               "flow.json") is not None
       and board.safe_run_path(RUNS, "boardvrf1", "",
                               "pd_marty/usage.json")
       is None,
       "run-root files resolve flat only")
finally:
    _pc.ROOT_OVERRIDE = None

print("fails: %d" % fails)
raise SystemExit(1 if fails else 0)
