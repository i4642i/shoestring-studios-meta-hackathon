"""Voice + video-assembly checks (v8, Phase A). Stdlib only.

Run: python scripts/video_check.py. No model, TTS, image, or speech
calls: the stub voice engine and offline fixtures only. Writes only
to a temp dir.
"""
import json
import os
import struct
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
from agents._frame import pc as _pc
from agents._frame import results, video
from agents._frame.schemas import (validate_anim_picks,
                                   validate_gen_picks,
                                   validate_photo_picks,
                                   validate_render_log,
                                   validate_slide_draft,
                                   validate_style_guide)
from agents._frame.tools import (make_voice, render_slide,
                                 write_anim_picks, write_gen_picks,
                                 write_photo_picks, write_render_log,
                                 write_slide_draft)

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


NARR = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 20,
     "lines": [{"text": "Hello world", "citations": []},
               {"text": "Second line here", "citations": []}]},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 20, "end_s": 40,
     "lines": [{"text": "Plains only", "citations": []}]}]}
BOARD = {"cuts": [
    {"cut_id": "s1c1", "scene_n": 1, "start_s": 0, "end_s": 20,
     "show_what": "Card", "show_why": "Intro",
     "on_screen_text": ["Hello"]},
    {"cut_id": "s1c2", "scene_n": 1, "start_s": 20, "end_s": 40,
     "show_what": "Card", "show_why": "More",
     "on_screen_text": ["Plains"]}]}
GUIDE = {"palette": {"background": "#101418", "text": "#f5f2ea",
                     "accent": "#e0a458"},
         "fonts": {"heading": "sans", "body": "sans"},
         "image_tone": "plain", "rules": ["Keep it calm."]}
SLIDE = {"cuts": [
    {"cut_id": "s1c1", "start_s": 0, "end_s": 20,
     "materials": [{"kind": "text_card", "use": "Card"}],
     "layout": "center", "on_screen_text": ["Hello"],
     "transitions": [], "why": "stub"},
    {"cut_id": "s1c2", "start_s": 20, "end_s": 40,
     "materials": [{"kind": "text_card", "use": "Card"}],
     "layout": "center", "on_screen_text": ["Plains"],
     "transitions": [], "why": "stub"}]}

tmp = tempfile.mkdtemp(prefix="videocheck_")


def wdir(name):
    d = os.path.join(tmp, "runs", "r1", name)
    os.makedirs(d, exist_ok=True)
    return d


def received(d, sender, cat, version, data):
    with open(os.path.join(d, "received.%s.%s.json" % (sender, cat)),
              "w", encoding="utf-8") as f:
        json.dump({"sender": sender, "category": cat,
                   "version": version, "data": data}, f)


def ctx_for(d, producer):
    return {"run_dir": d,
            "agent_dir": os.path.join(ROOT, "agents", producer),
            "producer": producer, "order_id": "ov",
            "run_id": "r1"}

# ---- pure video module ----
ok(video.RENDER_MAX == 3, "render cap is 3")
srt = video.build_srt(NARR)
ok(srt == ("1\n00:00:00,000 --> 00:00:08,000\nHello world\n\n"
           "2\n00:00:08,000 --> 00:00:20,000\nSecond line here\n\n"
           "3\n00:00:20,000 --> 00:00:40,000\nPlains only\n"),
   "subtitle timing exact (proportional word split)")
ok(video.srt_timestamp(3661.5) == "01:01:01,500", "srt clock rolls over")
table = video.build_table(NARR, BOARD, SLIDE, {1: "p1"})
ok(table == {"rows": [
    {"part": "p1", "scene_n": 1, "cut_id": "s1c1", "start_s": 0,
     "end_s": 20, "narration": "Hello world Second line here",
     "screen": "Card", "materials": ["text_card"]},
    {"part": "p1", "scene_n": 1, "cut_id": "s1c2", "start_s": 20,
     "end_s": 40, "narration": "Plains only",
     "screen": "Card", "materials": ["text_card"]}]},
   "storyboard table exact")
asm = video.build_assembly(NARR, {"s1c1": "a.svg", "s1c2": "b.svg"},
                           {"s1c1": "a.wav", "s1c2": "b.wav"})
ok(asm["total_s"] == 40.0 and len(asm["segments"]) == 2
   and asm["segments"][1]["at_s"] == 20.0
   and asm["ffmpeg_cmd"][0] == "ffmpeg"
   and asm["ffmpeg_cmd"][-1] == "video.mp4"
   and "concat=n=2:v=1:a=0[v]" in " ".join(asm["ffmpeg_cmd"]),
   "assembly plan joins in order with one ffmpeg command")
ok(asm["srt"] == srt, "assembly carries the same subtitles")
card = os.path.join(tmp, "card.svg")
video.render_text_card(SLIDE["cuts"][0], GUIDE, card)
svg = open(card, encoding="utf-8").read()
ok(svg.startswith("<svg") and "Hello" in svg
   and "#101418" in svg and "s1c1" in svg,
   "text card renders with the style guide")
card2 = os.path.join(tmp, "card2.svg")
video.render_text_card({"cut_id": "x",
                        "on_screen_text": ["A&B <C>"]}, None, card2)
svg2 = open(card2, encoding="utf-8").read()
ok("A&amp;B &lt;C&gt;" in svg2, "card text is XML-escaped")
ff = video.run_ffmpeg(["ffmpeg", "-version"])
ok(ff.get("ok") is False and "ffmpeg" in ff.get("error", "").lower(),
   "missing ffmpeg fails with a hint, never silently")

# ---- stub voice engine ----
_pc.ROOT_OVERRIDE = tmp
try:
    wctx = ctx_for(wdir("voice_wren"), "voice_wren")
    v1 = make_voice(wctx, {"cut_id": "s1c1",
                           "text": "Hello world this is a test",
                           "plan_seconds": 20})
    ok(v1.get("ok") and v1["seconds"] == 2.4
       and v1["attempt"] == 1 and v1["engine"] == "stub"
       and v1["within_15pct"] is False
       and v1["voice_pc_ref"].endswith("#s1c1"),
       "stub voice returns real durations (words/2.5)")
    clip = v1["voice_pc_ref"]
    entry = _pc.load_entry_by_ref(clip)
    wavp = os.path.join(_pc.entry_dir("voice", entry["doc_id"]),
                        "audio", entry["cuts"]["s1c1"]["file"])
    with wave.open(wavp, "rb") as w:
        secs = round(w.getnframes() / float(w.getframerate()), 1)
    ok(secs == 2.4, "stored WAV length matches the report")
    v2 = make_voice(wctx, {"cut_id": "s1c1",
                           "text": "Hello world this is a test",
                           "plan_seconds": 20})
    ok(v2.get("ok") and v2["attempt"] == 2, "second attempt allowed")
    v3 = make_voice(wctx, {"cut_id": "s1c1",
                           "text": "Hello world this is a test",
                           "plan_seconds": 20})
    ok(v3.get("ok") is False and "2 voice attempts" in
       " ".join(v3.get("errors", [])),
       "third voice attempt refused")
    other = ctx_for(wdir("board_penn"), "board_penn")
    ok(make_voice(other, {"cut_id": "s1c1", "text": "x",
                          "plan_seconds": 1}).get("error")
       == "make_voice is Wren's tool", "voice tool is Wren-only")
    try:
        import kokoro  # noqa: F401
        have_kokoro = True
    except ImportError:
        have_kokoro = False
    if not have_kokoro:
        vk = make_voice(wctx, {"cut_id": "k1", "text": "hi",
                               "plan_seconds": 10, "engine": "kokoro"})
        ok(vk.get("ok") is False and "kokoro" in
           " ".join(vk.get("errors", [])).lower(),
           "kokoro engine names its install hint when absent")
    else:
        ok(True, "kokoro installed here (hint check skipped)")
    heard = _pc.open_ref(entry, clip)
    ok(heard.get("kind") == "voice_clip"
       and heard.get("file", "").endswith(".wav"),
       "voice clip opens via open_ref")

    # ---- render_slide ----
    rdir = wdir("slide_remy")
    rctx = ctx_for(rdir, "slide_remy")
    bad = render_slide(rctx, {"cut_id": "s1c1"})
    ok(bad.get("ok") is False and "need received" in
       " ".join(bad.get("errors", [])),
       "render without inputs refuses")
    received(rdir, "board_vera", "slide_draft", 1, SLIDE)
    received(rdir, "board_penn", "style_guide", 1, GUIDE)
    r1 = render_slide(rctx, {"cut_id": "s1c1"})
    ok(r1.get("ok") and r1["slide_file"] == "slides/s1c1.svg"
       and r1["renders_n"] == 1
       and os.path.isfile(os.path.join(rdir, "slides", "s1c1.svg")),
       "text card renders into the run dir")
    render_slide(rctx, {"cut_id": "s1c1"})
    render_slide(rctx, {"cut_id": "s1c1"})
    r4 = render_slide(rctx, {"cut_id": "s1c1"})
    ok(r4.get("ok") is False and "3 renders" in
       " ".join(r4.get("errors", [])),
       "fourth render refused")

    # ---- v8 validators ----
    ok(validate_style_guide(GUIDE) == [], "style guide accepts")
    ok(validate_style_guide({"palette": {}}) != [],
       "thin guide refuses")
    PH = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                    "reason": "stub"},
                   {"cut_id": "s1c2", "decision": "none",
                    "reason": "stub"}]}
    ok(validate_photo_picks(PH, BOARD) == [], "photo stub accepts")
    ok("cut set" in " ".join(validate_photo_picks(
        {"cuts": PH["cuts"][:1]}, BOARD)),
       "photo dropped cut refuses")
    GE = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                    "reason": "stub"},
                   {"cut_id": "s1c2", "decision": "none",
                    "reason": "stub"}],
          "images": []}
    ok(validate_gen_picks(GE, BOARD) == [], "gene stub accepts")
    many = {"cuts": GE["cuts"],
            "images": [{"cut_id": "s1c1", "file": "g%d.png" % i,
                        "prompt": "p%d" % i, "reused": False}
                       for i in range(7)]}
    ok("6" in " ".join(validate_gen_picks(many, BOARD)),
       "seventh image refuses")
    AN = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                    "reason": "stub"},
                   {"cut_id": "s1c2", "decision": "none",
                    "reason": "stub"}]}
    ok(validate_anim_picks(AN, BOARD) == [], "max stub accepts")
    ok(validate_slide_draft(SLIDE, NARR) == [], "vera draft accepts")
    thin = json.loads(json.dumps(SLIDE))
    thin["cuts"][0]["materials"] = []
    ok("materials" in " ".join(validate_slide_draft(thin, NARR)),
       "material-less cut refuses")
    RL = {"cuts": [{"cut_id": "s1c1", "slide_file": "slides/s1c1.svg",
                    "renders_n": 1, "adjustments": [], "issues": []},
                   {"cut_id": "s1c2", "slide_file": "slides/s1c2.svg",
                    "renders_n": 1, "adjustments": [], "issues": []}]}
    ok(validate_render_log(RL, SLIDE) == [], "remy log accepts")
    badrl = json.loads(json.dumps(RL))
    badrl["cuts"][0]["adjustments"] = [{"field": "text", "was": "a",
                                        "now": "b"}]
    ok("layout" in " ".join(validate_render_log(badrl, SLIDE)).lower()
       or validate_render_log(badrl, SLIDE) != [],
       "content adjustment refuses")

    # ---- v8 writers (stub payloads) ----
    pdir = wdir("photo_pia")
    received(pdir, "board_penn", "storyboard", 2, BOARD)
    pout = write_photo_picks(ctx_for(pdir, "photo_pia"),
                             {"photo_picks": PH})
    ok(pout.get("ok") is True, "pia stub saves")
    gdir = wdir("image_gene")
    received(gdir, "board_penn", "storyboard", 2, BOARD)
    gout = write_gen_picks(ctx_for(gdir, "image_gene"),
                           {"gen_picks": GE})
    ok(gout.get("ok") is True, "gene stub saves")
    mdir = wdir("anim_max")
    received(mdir, "board_penn", "storyboard", 2, BOARD)
    mout = write_anim_picks(ctx_for(mdir, "anim_max"),
                            {"anim_picks": AN})
    ok(mout.get("ok") is True, "max stub saves")
    vdir = wdir("board_vera")
    received(vdir, "voice_wren", "narration", 2, NARR)
    received(vdir, "board_penn", "storyboard", 2, BOARD)
    received(vdir, "board_penn", "style_guide", 1, GUIDE)
    received(vdir, "photo_pia", "photo_picks", 1, PH)
    received(vdir, "image_gene", "gen_picks", 1, GE)
    received(vdir, "anim_max", "anim_picks", 1, AN)
    vout = write_slide_draft(ctx_for(vdir, "board_vera"),
                             {"slide_draft": SLIDE})
    ok(vout.get("ok") is True, "vera text-card draft saves")
    badv = json.loads(json.dumps(SLIDE))
    badv["cuts"][0]["materials"] = [{"kind": "photo",
                                     "use": "No pick backs this"}]
    verrs = write_slide_draft(
        ctx_for(vdir, "board_vera"),
        {"slide_draft": badv}).get("errors", [])
    ok("no photo pick" in " ".join(verrs),
       "unbacked photo material refuses")
    ldir = wdir("slide_remy2")
    received(ldir, "board_vera", "slide_draft", 1, SLIDE)
    lout = write_render_log(ctx_for(ldir, "slide_remy"),
                            {"render_log": RL})
    ok(lout.get("ok") is True, "remy log saves")
    saved = results.load_result(os.path.join(vdir, "result.json"))
    ok(results.check_result(saved) == []
       and "## slide_draft (v1)" in results.render_report(saved),
       "vera envelope + report")
finally:
    _pc.ROOT_OVERRIDE = None

# ---- Phase B: search/pick/generate (fixtures, no network) ----
from agents._frame import media as _media
from agents._frame import runner as _runner

seen_urls = []


def _fake_search(url):
    seen_urls.append(url)
    return {"results": [
        {"title": "Harbor", "url": "https://img.test/h1.jpg",
         "foreign_landing_url": "https://page.test/h1",
         "license": "by", "license_version": "4.0"},
        {"title": "Mill", "url": "https://img.test/m1.jpg",
         "foreign_landing_url": "https://page.test/m1",
         "license": "by-nc", "license_version": "4.0"}]}


def _fake_bytes(url, cap):
    assert url.startswith("https://img.test/")
    return b"\x89PNG\r\n\x1a\n" + b"0" * 16


_gen_calls = []


def _fake_image(prompt):
    _gen_calls.append(prompt)
    return b"\x89PNG\r\n\x1a\nGEN", "muse-image-1.0", 0.01


_media._HTTP_JSON = _fake_search
_media._HTTP_BYTES = _fake_bytes
_media._IMAGE_FN = _fake_image
_pc.ROOT_OVERRIDE = tmp
try:
    pia = ctx_for(wdir("photo_pia2"), "photo_pia")
    s1 = _media.pc_search_images(pia, {"cut_id": "s1c1",
                                      "query": "harbor cranes"})
    ok(len(s1["hits"]) == 2 and s1["queries_used"] == 1
       and "license_type=commercial" in seen_urls[0]
       and "license=" in seen_urls[0].replace("license_type", ""),
       "openverse query filters commercial reuse set")
    _media.pc_search_images(pia, {"cut_id": "s1c1", "query": "again"})
    s3 = _media.pc_search_images(pia, {"cut_id": "s1c1",
                                      "query": "third"})
    ok("error" in s3 and "2 image queries" in s3["error"],
       "third image query refused")
    ok("error" in _media.pc_search_images(
        ctx_for(wdir("x"), "image_gene"), {"cut_id": "c", "query": "q"}),
       "image search is Pia-only")
    pk = _media.pc_pick_image(pia, {"image_url": "https://img.test/h1.jpg",
                                   "page_url": "https://page.test/h1",
                                   "license": "by-4.0",
                                   "reason": "Harbor fits the cut."})
    ok(pk.get("ok") and pk["file"] == "pick.png"
       and pk["ref"].startswith("pc://image/"),
       "licensed pick stored with file + url + license")
    stored = _pc.load_entry_by_ref(pk["ref"])
    ok(stored["license"] == "by-4.0"
       and stored["source_url"] == "https://page.test/h1",
       "pick keeps provenance")
    nc = _media.pc_pick_image(pia, {"image_url": "https://img.test/m1.jpg",
                                   "page_url": "https://page.test/m1",
                                   "license": "by-nc",
                                   "reason": "r"})
    ok("error" in nc and "reuse-permitted" in nc["error"],
       "nc license refused")
    gene = ctx_for(wdir("image_gene2"), "image_gene")
    for i in range(6):
        g = _media.pc_generate_image(gene, {"prompt": "concept %d" % i})
        assert g.get("ok"), g
    ok(len(_gen_calls) == 6, "six images generated")
    g7 = _media.pc_generate_image(gene, {"prompt": "one more"})
    ok("error" in g7 and "6 generated images" in g7["error"],
       "seventh image refused")
    gr = _media.pc_generate_image(gene, {"prompt": "concept 0"})
    ok(gr.get("ok") and gr["reused_entry"] is True
       and gr["cost_usd"] == 0.0 and len(_gen_calls) == 6,
       "same prompt reuses the stored image")
    ok("error" in _media.pc_generate_image(
        ctx_for(wdir("x"), "photo_pia"), {"prompt": "p"}),
       "generation is Gene-only")

    # ---- vision staging + runner attach ----
    tpng = os.path.join(ROOT, "scripts", "_tmpclip", "t", "view.png")
    os.makedirs(os.path.dirname(tpng), exist_ok=True)
    with open(tpng, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"1" * 64)
    vera = ctx_for(wdir("board_vera2"), "board_vera")
    for _ in range(4):
        v = _media.vera_view_image(vera, {"cut_id": "s1c1",
                                          "path": "index.html"})
        assert v.get("ok"), v
    v5 = _media.vera_view_image(vera, {"cut_id": "s1c1",
                                       "path": "index.html"})
    ok("error" in v5 and "viewed 4 files" in v5["error"],
       "fifth view refused")
    ok("error" in _media.vera_view_image(
        vera, {"cut_id": "s1c1", "path": "../outside.png"}),
       "view escapes the repo refused")
    remy = ctx_for(wdir("slide_remy3"), "slide_remy")
    rv = _media.remy_view_slide(remy, {"cut_id": "s1c1",
                                       "path": "index.html"})
    ok(rv.get("ok") and rv["staged"].endswith("index.html"),
       "remy stages a slide view")
    msg = _runner._vision_message(
        [{"path": tpng},
         {"path": os.path.join(ROOT, "index.html")},
         {"path": "/nonexistent/x.png"}])
    kinds = [p.get("type") for p in msg["content"]]
    ok(msg["role"] == "user" and kinds == ["text", "image_url"]
       and msg["content"][1]["image_url"]["url"].startswith(
           "data:image/png;base64,")
       and "Skipped" in msg["content"][0]["text"],
       "vision message attaches raster, names the rest")
    vd = wdir("vdrain")
    with open(os.path.join(vd, "vision_staged.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps({"path": tpng}) + "\n")
        f.write(json.dumps({"path": tpng}) + "\n")
    e1, seen = _runner._vision_drain(vd, 0)
    e2, seen2 = _runner._vision_drain(vd, seen)
    ok(len(e1) == 2 and e2 == [] and seen2 == 2,
       "vision drain is incremental")

    # full loop: vera stages a view, the next chat sees it
    vrun = wdir("board_vera")
    received(vrun, "voice_wren", "narration", 2, NARR)
    received(vrun, "board_penn", "storyboard", 2, BOARD)
    received(vrun, "board_penn", "style_guide", 1, GUIDE)
    received(vrun, "photo_pia", "photo_picks", 1, PH)
    received(vrun, "image_gene", "gen_picks", 1, GE)
    received(vrun, "anim_max", "anim_picks", 1, AN)
    vmd = os.path.join(vrun, "INPUTS.md")
    with open(vmd, "w", encoding="utf-8") as f:
        f.write("# inputs\n")
    calls = []
    real_chat = _runner._chat

    def _canned(model, messages, tools, max_tokens=None,
                timeout=300):
        calls.append(json.loads(json.dumps(messages)))
        if len(calls) == 1:
            tc = {"id": "c1", "type": "function",
                  "function": {"name": "vera_view_image",
                               "arguments": json.dumps(
                                   {"cut_id": "s1c1",
                                    "path": "scripts/_tmpclip/t/"
                                            "view.png"})}}
        else:
            tc = {"id": "c2", "type": "function",
                  "function": {"name": "write_slide_draft",
                               "arguments": json.dumps(
                                   {"slide_draft": SLIDE})}}
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "",
                                         "tool_calls": [tc]}}],
                "usage": {"prompt_tokens": 1,
                          "completion_tokens": 1}}

    _runner._chat = _canned
    try:
        rout = _runner.run(os.path.join(ROOT, "agents", "board_vera"),
                           vrun, {"order_id": "ov"}, vmd)
    finally:
        _runner._chat = real_chat
    saw_img = any(
        isinstance(m.get("content"), list)
        and any(p.get("type") == "image_url" for p in m["content"])
        for m in calls[-1])
    ok(rout.get("ok") is True and len(calls) == 2 and saw_img,
       "staged view reaches the next model call")

    # ---- speech: align + compare + transcribe hook ----
    TURNS = [{"start_s": 2, "end_s": 8, "text": "Hello world"},
             {"start_s": 8, "end_s": 18, "text": "Second line here!"},
             {"start_s": 21, "end_s": 39, "text": "Plains only"}]
    ok(video.align_subs(NARR, TURNS) == (
        "1\n00:00:02,000 --> 00:00:08,400\nHello world\n\n"
        "2\n00:00:08,400 --> 00:00:18,000\nSecond line here\n\n"
        "3\n00:00:21,000 --> 00:00:39,000\nPlains only\n"),
       "turn times narrow the subtitle spans")
    cmp_ = video.compare_transcript(NARR, TURNS)
    ok([c["match"] for c in cmp_] == [True, True],
       "matching transcript verifies")
    badt = [{"start_s": 0, "end_s": 20, "text": "Something else"},
            {"start_s": 21, "end_s": 39, "text": "Plains only"}]
    cmp2 = video.compare_transcript(NARR, badt)
    ok([c["match"] for c in cmp2] == [False, True],
       "misread cut flagged")
    video._TRANSCRIBE_FN = lambda p: TURNS
    try:
        ok(video.transcribe_file("whatever.wav") == TURNS,
           "transcribe hook serves fixtures")
    finally:
        video._TRANSCRIBE_FN = None
    if not _runner.key_present("meta-models/muse-spark-open-1026"):
        try:
            video.transcribe_file(tpng)
            ok(False, "live transcribe without key raises")
        except RuntimeError as exc:
            ok("missing" in str(exc).lower(),
               "live transcribe without key raises")
    else:
        ok(True, "key present here (no-key check skipped)")
finally:
    _media._HTTP_JSON = None
    _media._HTTP_BYTES = None
    _media._IMAGE_FN = None
    _pc.ROOT_OVERRIDE = None

import shutil
shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print("%d FAILURES" % fails)
    sys.exit(1)
print("ALL PASS")
