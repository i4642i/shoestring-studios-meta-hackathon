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
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tempfile.tempdir = os.path.join(ROOT, "scripts", "_tmpclip", "t")
from agents._frame import pc as _pc
from agents._frame import flow as _flow
from agents._frame import results, tools, video
from agents._frame.schemas import (validate_anim_picks,
                                   validate_cut_layout,
                                   _cut_set_diff,
                                   validate_gen_picks,
                                   validate_photo_picks,
                                   render_photo_picks_md,
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
     "preset": "main_side",
     "blocks": [
         {"kind": "table",
          "box": {"x": 64, "y": 96, "w": 1088, "h": 300},
          "order": 0, "appear_s": 0, "reason": "Shows the numbers",
          "font_size": 24,
          "data": {"headers": ["Year", "Sales"],
                   "rows": [["2024", "120"], ["2025", "150"]],
                   "reveal": "rows"}},
         {"kind": "text",
          "box": {"x": 64, "y": 460, "w": 1152, "h": 140},
          "order": 1, "appear_s": 2, "reason": "Headline",
          "font_size": 44,
          "data": {"lines": ["Sales grew steadily"]}}],
     "on_screen_text": ["Hello"], "transitions": [],
     "why": "stub"},
    {"cut_id": "s1c2", "start_s": 20, "end_s": 40, "preset": "full",
     "blocks": [
         {"kind": "photo",
          "box": {"x": 64, "y": 170, "w": 560, "h": 378},
          "order": 0, "appear_s": 0,
          "reason": "Plains photo for the line",
          "ref": "pc://image/0123456789ab"},
         {"kind": "source_figure",
          "box": {"x": 648, "y": 170, "w": 504, "h": 378},
          "order": 1, "appear_s": 0,
          "reason": "Source figure for the line",
          "ref": "pc://source/0123456789ab#fig1.1.1"}],
     "on_screen_text": ["Plains"], "transitions": [],
     "why": "stub"}]}

def _png(w, h):
    """Minimal true-color PNG bytes (solid black)."""
    import struct
    import zlib
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = (b"\x00" + b"\x00" * (w * 3)) * h

    def _chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data)
                              & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw))
            + _chunk(b"IEND", b""))



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
long_narr = {"cuts": [{"cut_id": "s9c1", "start_s": 0, "end_s": 60,
                        "lines": [{"text": "One two three four. Five six "
                                           "seven eight nine ten eleven "
                                           "twelve thirteen fourteen.",
                                   "citations": []}]}]}
long_srt = video.build_srt(long_narr)
long_texts = [ln for ln in long_srt.split("\n")
              if ln and ln[0].isalpha()]
ok(len(long_texts) == 2
   and all(len(t.split()) <= 12 for t in long_texts),
   "long lines split into <=12-word subtitle blocks")
body = video._multipart_body("----bound1", "m",
                             b"RIFFdata")
ok(body.endswith(b"\r\n------bound1--\r\n")
   and b"RIFFdata\r\n------bound1--" in body,
   "multipart body separates the blob from the boundary")
table = video.build_table(NARR, BOARD, SLIDE, {1: "p1"})
ok(table == {"rows": [
    {"part": "p1", "scene_n": 1, "cut_id": "s1c1", "start_s": 0,
     "end_s": 20, "narration": "Hello world Second line here",
     "screen": "Card", "materials": ["table", "text"]},
    {"part": "p1", "scene_n": 1, "cut_id": "s1c2", "start_s": 20,
     "end_s": 40, "narration": "Plains only",
     "screen": "Card", "materials": ["pc://image/0123456789ab",
                                     "pc://source/0123456789ab#fig1.1.1"]}]},
   "storyboard table exact")
PINFO = {"parts": [{"no": 1, "part_id": "p1", "title": "h",
                    "seconds": 40, "cuts": ["s1c1", "s1c2"]}]}
ok(video.scene_part_map(PINFO, None, NARR) == {1: "p1"},
   "scene map reads part_info first")
ok(video.scene_part_map(None, {"scenes": [{"n": 1,
                                           "part_id": "p1"}]},
                        NARR) == {1: "p1"},
   "scene map falls back to the draft")
ok(video.build_table(NARR, BOARD, SLIDE,
                     video.scene_part_map(PINFO, None, NARR))
   == table,
   "table identical via merged part info")
asm = video.build_assembly(NARR, {"s1c1": "a.png", "s1c2": "b.png"},
                           {"s1c1": "a.wav", "s1c2": "b.wav"})
joined = " ".join(asm["ffmpeg_cmd"])
ok(asm["total_s"] == 41.1 and len(asm["segments"]) == 2
   and asm["segments"][0]["dur_s"] == 20.8
   and asm["segments"][1]["at_s"] == 20.8
   and asm["ffmpeg_cmd"][0] == "ffmpeg"
   and asm["ffmpeg_cmd"][-1] == "video.mp4"
   and "xfade=" in joined and "acrossfade=" in joined
   and "apad=" in joined,
   "assembly joins with plan lengths + crossfades (one command)")
ok("[2:a]apad=" in joined and "[3:a]apad=" in joined
   and "[1:a]apad=" not in joined,
   "inputs are grouped: video 0-1, audio 2-3 (ffmpeg binds)")
ok("-shortest" not in asm["ffmpeg_cmd"]
   and asm["ffmpeg_cmd"][-3] == "-t",
   "assembly keeps the full slide length")
ok(asm["srt"] == video.build_srt(video.retime_narration(NARR, None)),
   "assembly subtitles follow the retimed cuts")
wavp = os.path.join(tmp, "probe.wav")
with wave.open(wavp, "wb") as _w:
    _w.setnchannels(1)
    _w.setsampwidth(2)
    _w.setframerate(16000)
    _w.writeframes(b"\x00" * 16000 * 2 * 2)
ok(abs(video.wav_seconds(wavp) - 2.0) < 0.01, "wav length measured")
try:
    video.wav_seconds(os.path.join(tmp, "no-such.wav"))
    ok(False, "missing wav raises")
except Exception:
    ok(True, "missing wav raises")
rt = video.retime_narration(NARR, {"s1c1": 5.0, "s1c2": 7.0})
ok(rt["cuts"][0] ["end_s"] == 5.8 and rt["cuts"][1]["start_s"] == 5.8
   and rt["cuts"][1]["end_s"] == 13.6,
   "segments follow measured voice + pad")
asm2 = video.build_assembly(NARR, {"s1c1": "a.png", "s1c2": "b.png"},
                            {"s1c1": "a.wav", "s1c2": "b.wav"},
                            audio_lengths={"s1c1": 5.0, "s1c2": 7.0})
ok(asm2["total_s"] == 13.1 and asm2["segments"][0]["dur_s"] == 5.8
   and asm2["segments"][1]["dur_s"] == 7.8,
   "assembly total follows measured voice")
asm3 = video.build_assembly(NARR, {"s1c1": "a.png", "s1c2": "b.png"},
                            {"s1c1": "a.wav", "s1c2": "b.wav"},
                            clip_files={"s1c1": "c.mp4"})
ok("-stream_loop" in asm3["ffmpeg_cmd"]
   and asm3["segments"][0]["clip"] == "c.mp4"
   and asm3["segments"][1]["clip"] is None,
   "rendered clip preferred, png loop stays the fallback")
recs, rtot = video.build_cut_records(
    NARR, {"s1c1": "a.png"}, {"s1c1": "a.wav", "s1c2": "b.wav"},
    props_map={"s1c1": {"cutId": "s1c1"}},
    voice_refs={"s1c1": "pc://voice/0123456789ab#s1c1"},
    slide_status={"s1c2": "remotion_unavailable"})
ok(rtot == 40.0 and recs[0]["props"] == {"cutId": "s1c1"}
   and recs[0]["slide_status"] == "rendered"
   and recs[0]["voice_ref"] == "pc://voice/0123456789ab#s1c1"
   and recs[1]["props"] is None and recs[1]["slide"] is None
   and recs[1]["slide_status"] == "remotion_unavailable"
   and recs[1]["audio"] == "b.wav",
   "cut records carry props + png + voice, gaps stay null")
long_cut = json.loads(json.dumps(SLIDE["cuts"][0]))
long_cut["start_s"] = 0
long_cut["end_s"] = 45
ok(video.cut_slide_props(long_cut, GUIDE)["seconds"] == 45,
   "no 30 s clamp on cut props")
props = video.cut_slide_props(SLIDE["cuts"][0], GUIDE)
ok(props["cutId"] == "s1c1" and props["seconds"] == 20
   and props["preset"] == "main_side"
   and len(props["blocks"]) == 2
   and props["blocks"][0]["box"]["w"] == 1088
   and props["guide"]["palette"]["accent"] == "#e0a458",
   "cut props carry boxes + guide to Remotion")
ok(video.cut_slide_props(
    SLIDE["cuts"][1], GUIDE)["blocks"][0].get("file") == "",
   "unresolved pc:// ref renders an empty slot, never a fake path")
rmods = os.path.join(tools.REMOTION_DIR, "node_modules")
if os.path.isdir(rmods):
    ok(True, "remotion installed here (skip-path untested)")
else:
    ok(tools._have_remotion() is False,
       "missing remotion detected")
ff = video.run_ffmpeg([video.ffmpeg_exe() or "ffmpeg", "-version"])
ok(ff.get("ok") is True, "bundled ffmpeg answers")
real_exe = video.ffmpeg_exe
video.ffmpeg_exe = lambda: None
try:
    ff2 = video.run_ffmpeg(["ffmpeg", "-version"])
finally:
    video.ffmpeg_exe = real_exe
ok(ff2.get("ok") is False and "ffmpeg" in ff2.get("error", "").lower(),
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
    received(rdir, "board_vera", "slide_draft", 2, SLIDE)
    received(rdir, "board_penn", "style_guide", 1, GUIDE)
    real_have = tools._have_remotion
    tools._have_remotion = lambda: False
    try:
        r1 = render_slide(rctx, {"cut_id": "s1c1"})
    finally:
        tools._have_remotion = real_have
    ok(r1.get("ok") and r1.get("status") == "remotion_unavailable"
       and r1["slide_file"] == "" and r1["renders_n"] == 0
       and "setup_video" in r1.get("note", ""),
       "missing Remotion skips honestly with an install hint")
    side = os.path.join(rdir, "slides", "s1c1.props.json")
    ok(r1.get("props_file") == "slides/s1c1.props.json"
       and os.path.isfile(side)
       and json.load(open(side, encoding="utf-8"))["cutId"] == "s1c1",
       "skipped render still records its props")
    idir = os.path.join(tmp, "storage", "_pc", "image",
                        "entries", "0123456789ab")
    os.makedirs(os.path.join(idir, "files"))
    with open(os.path.join(idir, "files", "pic.jpg"), "wb") as f:
        f.write(b"\xff\xd8fakejpeg")
    with open(os.path.join(idir, "entry.json"), "w",
              encoding="utf-8") as f:
        json.dump({"ref": "pc://image/0123456789ab",
                   "doc_id": "0123456789ab", "file": "pic.jpg"}, f)
    gd = {"cuts": [{"cut_id": "s9c9", "start_s": 0, "end_s": 20,
                    "preset": "full",
                    "blocks": [{"kind": "photo",
                                "box": {"x": 64, "y": 64, "w": 560,
                                        "h": 378},
                                "order": 0, "appear_s": 0,
                                "reason": "t",
                                "ref": "pc://image/0123456789ab"}],
                    "on_screen_text": []}]}
    rdir2 = wdir("slide_remy_img")
    rctx2 = ctx_for(rdir2, "slide_remy")
    received(rdir2, "board_vera", "slide_draft", 2, gd)
    received(rdir2, "board_penn", "style_guide", 1, GUIDE)
    tools._have_remotion = lambda: False
    try:
        ri = render_slide(rctx2, {"cut_id": "s9c9"})
    finally:
        tools._have_remotion = real_have
    pj = json.load(open(os.path.join(rdir2, "slides",
                                     "s9c9.props.json"),
                        encoding="utf-8"))
    ov = video.cut_slide_props(
        SLIDE["cuts"][0], GUIDE,
        {"blocks": {"1": {"font_size": 36, "x": 70}},
         "on_screen_text": {"font": 40, "position": "top"},
         "nope": {"x": 1}})
    ok(ov["blocks"][1]["font_size"] == 36
       and ov["blocks"][1]["box"]["x"] == 70
       and ov["blocks"][0]["font_size"] == 24
       and ov["onScreenTextFont"] == 40
       and ov["onScreenTextPosition"] == "top"
       and "nope" not in ov,
       "overrides move layout only, unknown keys ignored")
    tools._have_remotion = lambda: False
    try:
        ro = render_slide(rctx2, {"cut_id": "s9c9",
                                  "overrides": {"blocks": {"0": {"x": 70}}}})
    finally:
        tools._have_remotion = real_have
    rj = json.load(open(os.path.join(rdir2, "slides",
                                     "s9c9.props.json"),
                        encoding="utf-8"))
    ok(ro.get("ok") and rj["blocks"][0]["box"]["x"] == 70,
       "rendered overrides stick in the props sidecar")
    ok(render_slide(
        rctx2, {"cut_id": "s9c9",
                "overrides": ["x"]}).get("ok") is False,
       "string overrides refuse with the shape hint")
    ok(ri.get("ok") and pj["blocks"][0].get("file") == "s9c9-img0.jpg"
       and os.path.isfile(os.path.join(rdir2, "slides",
                                       "s9c9-img0.jpg")),
       "render copies the picked image into the public dir")
    render_slide(rctx, {"cut_id": "s1c1"})
    render_slide(rctx, {"cut_id": "s1c1"})
    r4 = render_slide(rctx, {"cut_id": "s1c1"})
    ok(r4.get("ok") is False and "3 renders" in
       " ".join(r4.get("errors", [])),
       "fourth render refused")
    rcmd = tools._remotion_render_cmd("o.mp4", {"seconds": 5},
                                            149, "pub")
    ok("--frames=0-149" in rcmd and rcmd[3] == "CutSlide"
       and "--codec=h264" in rcmd,
       "clip render targets the cut's own frames")
    amp = {"title": "Fish & Chips", "seconds": 20}
    acmd = tools._remotion_cmd("o.png", amp, 599, "pub")
    parg = next(a for a in acmd if a.startswith("--props="))
    ok("Fish & Chips" in parg,
       "ampersand survives in the props arg")
    ok(acmd[0].lower().endswith("node")
       or acmd[0].lower().endswith("node.exe")
       or acmd[1] == "remotion",
       "render runs node-direct or npx fallback")
    fe = video.ffmpeg_exe()
    ok(isinstance(fe, str) and os.path.isfile(fe),
       "ffmpeg resolves to a real binary")
    from agents._frame import runner as _runner
    ok(_runner.provider_of("muse-image-1.0")[1]
       == "https://api.meta.ai/v1",
       "image calls route to the Meta images endpoint")
    ok(_pc.image_ext_from_bytes(b"RIFF\x00\x00\x00\x00WEBPrest")
       == ".webp"
       and _pc.image_ext_from_bytes(b"\x89PNG\r\n\x1a\nrest")
       == ".png"
       and _pc.image_ext_from_bytes(b"\xff\xd8rest") == ".jpg"
       and _pc.image_ext_from_bytes(b"??") == ".png",
       "generated bytes sniff to the right extension")
    import struct as _st
    _vp8 = (b"RIFF" + _st.pack("<I", 100) + b"WEBP" + b"VP8 "
            + _st.pack("<I", 20) + b"\x00\x00\x00"
            + b"\x9d\x01\x2a"
            + _st.pack("<H", 640) + _st.pack("<H", 480))
    ok(_pc.media_dims_from_bytes(_vp8) == (640, 480),
       "lossy webp dims parse")
    from agents._frame import media as _media
    mdir = wdir("slide_remy")
    mctx = ctx_for(mdir, "slide_remy")
    os.makedirs(os.path.join(mdir, "slides"), exist_ok=True)
    open(os.path.join(mdir, "slides", "s9.png"),
         "w", encoding="utf-8").write("PNG")
    ok(_media.slide_png(mctx, "slides/s9.png")
       .endswith(os.path.join("slides", "s9.png"))
       and _media.slide_png(mctx, "slides/gone.png") is None,
       "slide lookup hits clone slides, misses honestly")

    # ---- v8 validators ----
    ok(validate_style_guide(GUIDE) == [], "style guide accepts")
    ok(validate_style_guide({"palette": {}}) != [],
       "thin guide refuses")
    PH = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                    "reason": "stub"},
                   {"cut_id": "s1c2", "decision": "use",
                    "kind": "web", "ref": "pc://image/0123456789ab",
                    "file": "pick-1.jpg",
                    "source_url": "https://example.org/pick-1",
                    "license": "cc0", "reason": "Plains photo"}]}
    ok(validate_photo_picks(PH, BOARD) == [], "photo picks accept")
    PHD = {"cuts": [{"cut_id": "s1c1", "decision": "use",
                     "kind": "source_figure",
                     "ref": "pc://source/0123456789ab#fig1.1.1",
                     "file": "fig1.png",
                     "source_url": "pc://source/0123456789ab#fig1.1.1",
                     "license": "cc0", "reason": "Figure",
                     "width": 800, "height": 600, "aspect": 1.33}]}
    ok("- Size: 800x600 (aspect 1.33)" in render_photo_picks_md(PHD),
       "pick markdown carries figure size")
    LIC = {"cuts": [{"cut_id": "s1c1", "decision": "use",
                     "kind": "web", "ref": "pc://image/0123456789ab",
                     "file": "a.jpg", "source_url": "https://x.test/a",
                     "license": "by-sa-2.0", "reason": "Why"},
                    {"cut_id": "s1c2", "decision": "use",
                     "kind": "source_figure",
                     "ref": "pc://source/0123456789ab#fig1.1.1",
                     "file": "fig1.png",
                     "source_url": "pc://source/0123456789ab#fig1.1.1",
                     "license": "internal", "reason": "Figure"}]}
    ok(validate_photo_picks(LIC, BOARD) == [],
       "versioned and internal licenses accept")
    LICB = json.loads(json.dumps(LIC))
    LICB["cuts"][0]["license"] = "by-nc-4.0"
    ok(any("reuse-permitted" in e
           for e in validate_photo_picks(LICB, BOARD)),
       "nc license refuses")
    ok(tools._fit_hint(680, 380, 1130, 1000)
       == "fit w~429 at h=380 or h~602 at w=680 "
          "(e.g. {\"x\": 64, \"y\": 96, \"w\": 429, \"h\": 380})",
       "aspect error names a fitting box plus an example shape")
    bad_reveal = {"cut_id": "s1c1", "preset": "main_side",
                  "blocks": [
                      {"kind": "table",
                       "box": {"x": 64, "y": 96, "w": 1088, "h": 300},
                       "order": 0, "appear_s": 0, "font_size": 24,
                       "reason": "Numbers",
                       "data": {"headers": ["Year"],
                                "rows": [["2024"]],
                                "reveal": "bogus"}}],
                  "on_screen_text": ["Hi"], "transitions": [],
                  "why": "stub"}
    ok(any("must be 'all' or 'rows'" in e
           for e in validate_cut_layout(bad_reveal, 20)),
       "reveal error names the allowed values")
    dupe = json.loads(json.dumps(SLIDE["cuts"][0]))
    dupe["on_screen_text"] = ["Sales grew steadily"]
    ok(any("repeats the on_screen_text line" in e
           for e in validate_cut_layout(dupe, 20)),
       "text block repeating the bottom line refuses")
    dupe2 = json.loads(json.dumps(SLIDE["cuts"][0]))
    dupe2["blocks"].append(json.loads(json.dumps(
        SLIDE["cuts"][0]["blocks"][1])))
    dupe2["blocks"][1]["box"] = {"x": 64, "y": 96, "w": 500,
                                 "h": 100}
    ok(any("repeats the cut s1c1.blocks[1] line" in e
           for e in validate_cut_layout(dupe2, 20)),
       "two text blocks sharing a line refuse")
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
    ok("one per cut" in " ".join(validate_gen_picks(many, BOARD)),
       "images past one-per-cut refuse")
    AN = {"cuts": [{"cut_id": "s1c1", "decision": "none",
                    "reason": "stub"},
                   {"cut_id": "s1c2", "decision": "none",
                    "reason": "stub"}]}
    ok(validate_anim_picks(AN, BOARD) == [], "max stub accepts")
    AU = {"cuts": [{"cut_id": "s1c1", "decision": "use",
                    "template": "table",
                    "values": {"headers": ["Y"],
                               "rows": [["1"]]},
                    "refs": [{"ref": "pc://source/0123456789ab"
                                     "#tab1.1.1",
                              "quote": "| 1 |"}],
                    "reason": "x"},
                   {"cut_id": "s1c2", "decision": "none",
                    "reason": "y"}]}
    ok(validate_anim_picks(AU, BOARD) == [], "max use-pick accepts")
    au_bad1 = json.loads(json.dumps(AU))
    au_bad1["cuts"][0]["template"] = "confetti"
    ok("template" in " ".join(validate_anim_picks(au_bad1, BOARD)),
       "wild template refuses")
    au_bad2 = json.loads(json.dumps(AU))
    au_bad2["cuts"][0]["values"] = {"headers": ["Y"],
                                    "rows": [["1", "2"]]}
    ok("match headers" in " ".join(validate_anim_picks(au_bad2,
                                                       BOARD)),
       "ragged values refuse")
    au_bad3 = json.loads(json.dumps(AU))
    au_bad3["cuts"][1]["values"] = {}
    ok("none pick" in " ".join(validate_anim_picks(au_bad3, BOARD)),
       "none pick with values refuses")
    ok(validate_slide_draft(SLIDE, NARR) == [], "vera draft accepts")
    card = json.loads(json.dumps(SLIDE["cuts"][0]))
    card["preset"] = "card"
    ok("preset" not in " ".join(validate_cut_layout(card, 20)),
       "card preset validates")
    thin = json.loads(json.dumps(SLIDE))
    thin["cuts"][0]["blocks"] = []
    ok("blocks" in " ".join(validate_slide_draft(thin, NARR)),
       "block-less cut refuses")
    over = json.loads(json.dumps(SLIDE))
    over["cuts"][0]["blocks"][1]["box"] = {"x": 64, "y": 96,
                                           "w": 1088, "h": 300}
    ok("overlaps" in " ".join(validate_slide_draft(over, NARR)),
       "overlapping boxes refuse")
    tiny = json.loads(json.dumps(SLIDE))
    tiny["cuts"][0]["blocks"][1]["font_size"] = 12
    ok("font_size" in " ".join(validate_slide_draft(tiny, NARR)),
       "tiny font refuses")
    small = json.loads(json.dumps(SLIDE))
    small["cuts"][0]["blocks"][1]["font_size"] = 24
    ok(">= 32" in " ".join(validate_slide_draft(small, NARR)),
       "24px text refuses (minimum is 32)")
    ok(validate_slide_draft(SLIDE, NARR) == [],
       "table keeps its 24px floor")
    wide = json.loads(json.dumps(SLIDE))
    wide["cuts"][0]["blocks"][1]["data"] = {"lines": ["x" * 100]}
    ok("too wide" in " ".join(validate_slide_draft(wide, NARR)),
       "overflowing text refuses")
    edge = json.loads(json.dumps(SLIDE))
    edge["cuts"][0]["blocks"][0]["box"]["x"] = 0
    ok("safe area" in " ".join(validate_slide_draft(edge, NARR)),
       "unsafe box refuses")
    RL = {"cuts": [{"cut_id": "s1c1", "slide_file": "slides/s1c1.png",
                    "renders_n": 1, "adjustments": [], "issues": []},
                   {"cut_id": "s1c2", "slide_file": "slides/s1c2.png",
                    "renders_n": 1, "adjustments": [], "issues": []}]}
    ok(validate_render_log(RL, SLIDE) == [], "remy log accepts")
    RU = {"cuts": [{"cut_id": "s1c1", "slide_file": "",
                    "status": "remotion_unavailable", "renders_n": 0,
                    "adjustments": [], "issues": ["no remotion"]},
                   {"cut_id": "s1c2", "slide_file": "",
                    "status": "remotion_unavailable", "renders_n": 0,
                    "adjustments": [], "issues": ["no remotion"]}]}
    ok(validate_render_log(RU, SLIDE) == [], "unavailable log accepts")
    badru = json.loads(json.dumps(RU))
    badru["cuts"][0]["renders_n"] = 1
    ok("0 when Remotion" in " ".join(validate_render_log(badru, SLIDE)),
       "unavailable log with renders refuses")
    badrl = json.loads(json.dumps(RL))
    badrl["cuts"][0]["adjustments"] = [{"field": "text", "was": "a",
                                        "now": "b"}]
    ok("layout" in " ".join(validate_render_log(badrl, SLIDE)).lower()
       or validate_render_log(badrl, SLIDE) != [],
       "content adjustment refuses")

    # ---- v8 writers (stub payloads) ----
    seed = _pc.image_store_pick("ov", "https://example.org/pick-1",
                                _png(680, 460), "cc0",
                                "Plains photo", suffix=".png")
    PH["cuts"][1]["ref"] = seed["ref"]
    PH["cuts"][1]["file"] = seed["file"]
    SLIDE["cuts"][1]["blocks"][0]["ref"] = seed["ref"]
    pdir = wdir("photo_pia")
    received(pdir, "board_penn", "storyboard", 2, BOARD)
    pout = write_photo_picks(ctx_for(pdir, "photo_pia"),
                             {"photo_picks": PH})
    ok(pout.get("ok") is True, "pia use-pick saves")
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
    _TROWS = [["Year", "Sales"], ["2024", "120"], ["2025", "150"]]
    sent = _pc.ingest_source(
        "ov", "s.pdf", "2026-10-30T00:00:00", "sales_sam",
        ["1.1 Alpha\nSource alpha text."],
        [{"page": 1, "top": 100, "caption": "Plains photo.",
          "number": "1", "bbox": [0, 100, 800, 700],
          "w": 800, "h": 600, "blob": _png(800, 600)}],
        [{"page": 1, "top": 0, "caption": "Sales by year.",
          "number": "1", "bbox": [0, 0, 100, 50],
          "rows": _TROWS, "markdown": _pc.rows_to_md(_TROWS),
          "blob": None}], 0)
    _pc.set_recipients("source", sent["doc_id"], "ov",
                       ["anim_max", "board_vera"], "sales_sam",
                       kind="full")
    sentry = _pc.load_entry_by_ref(sent["ref"])
    tabref = sent["ref"] + "#" + sentry["tables"][0]["addr"]
    figref = sent["ref"] + "#" + sentry["figures"][0]["addr"]
    SLIDE["cuts"][1]["blocks"][1]["ref"] = figref
    ok(sentry["tables"][0]["addr"].startswith("tab")
       and sentry["figures"][0]["addr"].startswith("fig"),
       "seeded entry carries table + figure addresses")
    ok(_pc.media_dims_from_bytes(_png(12, 34)) == (12, 34)
       and _pc.media_dims_from_bytes(
           b"not an image at all.........") is None,
       "png dims read from bytes, unknown gives none")
    seeded = _pc.load_entry_by_ref(seed["ref"])
    ok(seeded.get("width") == 680 and seeded.get("height") == 460,
       "image entry stores material dims")
    AN2 = {"cuts": [{"cut_id": "s1c1", "decision": "use",
                     "template": "table",
                     "values": {"headers": ["Year", "Sales"],
                                "rows": [["2024", "120"],
                                         ["2025", "150"]]},
                     "refs": [{"ref": tabref,
                               "quote": "| Year | Sales |\n"
                                        "| --- | --- |\n"
                                        "| 2024 | 120 |\n"
                                        "| 2025 | 150 |"}],
                     "reason": "Numbers teach better as a table."},
                    {"cut_id": "s1c2", "decision": "none",
                     "reason": "Photo covers it."}]}
    mdir2 = wdir("anim_max2")
    received(mdir2, "board_penn", "storyboard", 2, BOARD)
    mout2 = write_anim_picks(ctx_for(mdir2, "anim_max"),
                             {"anim_picks": AN2})
    ok(mout2.get("ok") is True, "max table pick saves")
    maxbad1 = json.loads(json.dumps(AN2))
    maxbad1["cuts"][0]["refs"][0]["quote"] = "sales tripled (!)"
    ok("verbatim" in " ".join(write_anim_picks(
        ctx_for(mdir2, "anim_max"),
        {"anim_picks": maxbad1}).get("errors", [])),
       "invented quote refuses")
    maxbad2 = json.loads(json.dumps(AN2))
    maxbad2["cuts"][0]["values"]["rows"][0][1] = "999"
    ok("not in the quoted" in " ".join(write_anim_picks(
        ctx_for(mdir2, "anim_max"),
        {"anim_picks": maxbad2}).get("errors", [])),
       "untraced value refuses")
    STEPS = {"cuts": [{"cut_id": "s1c1", "decision": "use",
                       "template": "steps",
                       "values": {"items": ["Year", "Sales"]},
                       "refs": [{"ref": tabref,
                                 "quote": "| Year | Sales |\n"
                                          "| --- | --- |\n"
                                          "| 2024 | 120 |\n"
                                          "| 2025 | 150 |"}],
                       "reason": "Steps beat a table here."},
                      {"cut_id": "s1c2", "decision": "none",
                       "reason": "Photo covers it."}]}
    ok(write_anim_picks(ctx_for(mdir2, "anim_max"),
                        {"anim_picks": STEPS}).get("ok") is True,
       "steps items traced to the quote")
    badsteps = json.loads(json.dumps(STEPS))
    badsteps["cuts"][0]["values"]["items"] = ["Moon cheese",
                                                      "Green stars"]
    errs = write_anim_picks(ctx_for(mdir2, "anim_max"),
                            {"anim_picks": badsteps}).get("errors", [])
    ok(any("not in the quoted" in e for e in errs),
       "untraced steps item refuses")
    badshape = json.loads(json.dumps(STEPS))
    badshape["cuts"][0]["values"] = {"items": ["only one"]}
    errs2 = write_anim_picks(ctx_for(mdir2, "anim_max"),
                             {"anim_picks": badshape}).get("errors", [])
    ok(any("valid shape e.g." in e for e in errs2),
       "shape error shows a valid example")
    vdir = wdir("board_vera")
    received(vdir, "voice_wren", "narration", 2, NARR)
    received(vdir, "board_penn", "storyboard", 2, BOARD)
    received(vdir, "board_penn", "style_guide", 1, GUIDE)
    received(vdir, "photo_pia", "photo_picks", 1, PH)
    received(vdir, "image_gene", "gen_picks", 1, GE)
    received(vdir, "anim_max", "anim_picks", 2, AN2)
    vout = write_slide_draft(ctx_for(vdir, "board_vera"),
                             {"slide_draft": SLIDE})
    ok(vout.get("ok") is True, "vera layout draft saves")
    badv = json.loads(json.dumps(SLIDE))
    badv["cuts"][0]["blocks"] = [
        {"kind": "photo", "box": {"x": 300, "y": 130, "w": 680,
                                 "h": 460},
         "order": 0, "appear_s": 0, "reason": "No pick backs this",
         "ref": "pc://image/nope"}]
    verrs = write_slide_draft(
        ctx_for(vdir, "board_vera"),
        {"slide_draft": badv}).get("errors", [])
    ok("no photo pick" in " ".join(verrs),
       "unbacked photo block refuses")
    badm = json.loads(json.dumps(SLIDE))
    badm["cuts"][0]["blocks"][0]["data"]["rows"][0][1] = "999"
    ok("!= Max" in " ".join(write_slide_draft(
        ctx_for(vdir, "board_vera"),
        {"slide_draft": badm}).get("errors", [])),
       "vera data differing from Max refuses")
    bads = json.loads(json.dumps(SLIDE))
    bads["cuts"][1]["blocks"].append(
        {"kind": "steps", "box": {"x": 64, "y": 560, "w": 1152,
                                 "h": 90},
         "order": 2, "appear_s": 0, "reason": "No Max pick here",
         "font_size": 26, "data": {"items": ["First", "Second"]}})
    ok("no anim pick" in " ".join(write_slide_draft(
        ctx_for(vdir, "board_vera"),
        {"slide_draft": bads}).get("errors", [])),
       "data block without Max pick refuses")
    badar = json.loads(json.dumps(SLIDE))
    badar["cuts"][1]["blocks"][0]["box"] = {"x": 64, "y": 64,
                                            "w": 680, "h": 100}
    ok("aspect" in " ".join(write_slide_draft(
        ctx_for(vdir, "board_vera"),
        {"slide_draft": badar}).get("errors", [])),
       "wrong-aspect photo box refuses")
    badf = json.loads(json.dumps(SLIDE))
    badf["cuts"][1]["blocks"][1]["ref"] = tabref
    ok("not a figure" in " ".join(write_slide_draft(
        ctx_for(vdir, "board_vera"),
        {"slide_draft": badf}).get("errors", [])),
       "figure block on a table refuses")
    from agents._frame import media as _mediav
    ok(_mediav.VERA_VIEW_CAP == 2, "view budget is 2 per cut")
    vvdir = wdir("board_vera_views")
    vvc = ctx_for(vvdir, "board_vera")
    vvc["producer"] = "board_vera@p1"
    vvc["order_id"] = "oview"
    refs4 = []
    for i in range(4):
        pk = _pc.image_store_pick(
            "oview", "https://example.com/v%d" % i,
            b"\xff\xd8V%d" % i + b"\x00" * 40, "CC0",
            "candidate %d" % i, set_by="photo_pia@p1")
        refs4.append(pk["ref"])
    outs = [_mediav.vera_view_image(
        vvc, {"cut_id": "s1c1", "ref": r}) for r in refs4]
    ok([o.get("ok") is True for o in outs]
       == [True, True, False, False]
       and "already viewed 2 files" in outs[2].get("error", "")
       and outs[1]["views_used"] == 2,
       "4 candidates end with at most 2 views")
    counts = json.load(open(os.path.join(vvdir, "vera_views.json"),
                            encoding="utf-8"))
    ok(counts == {"s1c1": 2}, "view counter stops at 2")
    received(vvdir, "voice_wren", "narration", 2, NARR)
    received(vvdir, "photo_pia", "photo_picks", 1, PH)
    received(vvdir, "image_gene", "gen_picks", 1, GE)
    received(vvdir, "anim_max", "anim_picks", 2, AN2)
    with open(os.path.join(vvdir, "vera_views.json"), "w",
              encoding="utf-8") as f:
        json.dump({"s1c1": 3, "s1c2": 1}, f)
    vok = ctx_for(vvdir, "board_vera")
    ok("budget is 2" in " ".join(write_slide_draft(
        vok, {"slide_draft": SLIDE}).get("errors", [])),
       "writer refuses views over budget")
    ldir = wdir("slide_remy2")
    received(ldir, "board_vera", "slide_draft", 2, SLIDE)
    os.makedirs(os.path.join(ldir, "slides"), exist_ok=True)
    for _c in ("s1c1", "s1c2"):
        open(os.path.join(ldir, "slides", _c + ".png"),
             "w", encoding="utf-8").write("PNG")
    lout = write_render_log(ctx_for(ldir, "slide_remy"),
                            {"render_log": RL})
    ok(lout.get("ok") is True, "remy log saves")
    saved = results.load_result(os.path.join(vdir, "result.json"))
    ok(results.check_result(saved) == []
       and "## slide_draft (v2)" in results.render_report(saved),
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
       and seen_urls[0].startswith(_media.COMMONS_URL)
       and "license_type=commercial" in seen_urls[1]
       and "license=" in seen_urls[1].replace("license_type", ""),
       "commons tried first, openverse second filters reuse set")
    _media.pc_search_images(pia, {"cut_id": "s1c1", "query": "again"})
    s3 = _media.pc_search_images(pia, {"cut_id": "s1c1",
                                      "query": "third"})
    ok("error" in s3 and "2 image queries" in s3["error"],
       "third image query refused")
    def _fake_commons_hit(url):
        seen_urls.append(url)
        if url.startswith(_media.COMMONS_URL):
            return {"query": {"pages": {
                "11": {"title": "File:Dock.jpg", "imageinfo": [{
                    "url": "https://up.test/dock.jpg",
                    "descriptionurl": "https://commons.test/dock",
                    "extmetadata": {"LicenseShortName": {
                        "value": "CC BY 4.0"}}}]}}}}
        return {"results": [
            {"title": "OV", "url": "https://img.test/o1.jpg",
             "foreign_landing_url": "https://page.test/o1",
             "license": "by", "license_version": "4.0"}]}
    _media._HTTP_JSON = _fake_commons_hit
    n_seen = len(seen_urls)
    try:
        cb = _media._search_with_breaker(
            ctx_for(wdir("photo_pia3"), "photo_pia"), "dock", 5, 1000)
    finally:
        _media._HTTP_JSON = _fake_search
    ok(len(cb) == 1 and cb[0]["source"] == "commons"
       and not [u for u in seen_urls[n_seen:]
                if u.startswith(_media.OPENVERSE_URL)],
       "commons hit answers first, openverse never called")
    got_timeout = {}
    _real_get = _media._get_json
    def _rec_get(url, timeout=60):
        got_timeout[url] = timeout
        if url.startswith(_media.OPENVERSE_URL):
            raise RuntimeError("openverse slow: timeout")
        return {"query": {"pages": {}}}
    _media._get_json = _rec_get
    try:
        to = _media._search_with_breaker(
            ctx_for(wdir("photo_pia4"), "photo_pia"), "nodock", 5, 1000)
    finally:
        _media._get_json = _real_get
    ov_urls = [u for u in got_timeout
               if u.startswith(_media.OPENVERSE_URL)]
    ok(to == [] and len(ov_urls) == 1
       and got_timeout[ov_urls[0]] == _media.OPENVERSE_QUICK_TIMEOUT,
       "openverse second leg uses the short timeout")
    def _fake_empty(url):
        seen_urls.append(url)
        if url.startswith(_media.COMMONS_URL):
            return {"query": {"pages": {}}}
        return {"results": []}
    _media._HTTP_JSON = _fake_empty
    try:
        em = _media.pc_search_images(
            ctx_for(wdir("photo_pia5"), "photo_pia"),
            {"cut_id": "s9c9", "query": "zzz nothing here"})
    finally:
        _media._HTTP_JSON = _fake_search
    ok(em.get("hits") == [] and "tip" in em
       and "fewer" in em["tip"] and em["queries_used"] == 1,
       "0-hit search tells Pia to retry with fewer words")
    ok("error" in _media.pc_search_images(
        ctx_for(wdir("x"), "image_gene"), {"cut_id": "c", "query": "q"}),
       "image search is Pia-only")
    ok(_media._json_headers().get("User-Agent")
       and _media._bytes_headers().get("User-Agent"),
       "outbound media calls identify the app")
    ok("Mozilla" in _media._json_headers().get("User-Agent", ""),
       "search UA is browser-like (Cloudflare 1010 bans bots)")
    def _fake_mixed(url):
        seen_urls.append(url)
        if url.startswith(_media.OPENVERSE_URL):
            raise RuntimeError("openverse 403: Forbidden")
        return {"query": {"pages": {
            "3": {"title": "File:Scan.pdf", "imageinfo": [{
                "url": "https://up.test/scan.pdf",
                "descriptionurl": "https://commons.test/scan",
                "extmetadata": {"LicenseShortName": {
                    "value": "CC BY 4.0"}}}]},
            "5": {"title": "File:Photo.jpg", "imageinfo": [{
                "url": "https://up.test/photo.jpg",
                "descriptionurl": "https://commons.test/photo",
                "extmetadata": {"LicenseShortName": {
                    "value": "CC BY 4.0"}}}]}}}}
    _media._HTTP_JSON = _fake_mixed
    try:
        mx = _media.openverse_search("harbor", 5)
    finally:
        _media._HTTP_JSON = _fake_search
    ok(len(mx) == 1 and mx[0]["image_url"].endswith(".jpg")
       and "filetype" in seen_urls[-1] and "bitmap" in seen_urls[-1],
       "commons fallback asks bitmaps only, drops pdf hits")
    ok(_media._retry_after({"retry-after": "10"}) == 10
       and _media._retry_after({}) == 10
       and _media._retry_after({"retry-after": "999"}) == 600
       and _media._retry_after({"retry-after": "junk"}) == 10,
       "429 retry honors retry-after, capped at 600")
    ok(_media._clean_url("https://up.test/f.jpg?utm_source=x&a=1")
       == "https://up.test/f.jpg?a=1",
       "tracking params stripped from file urls")
    _media.IMAGE_PICK_GAP = 0
    try:
        _media._pace_pick(pia)
        _media._pace_pick(pia)
    finally:
        _media.IMAGE_PICK_GAP = 15
    ok(os.path.isfile(os.path.join(wdir("photo_pia2"),
                                  "last_pick_download.json")),
       "paced picks record the last download")
    ok(_media._commons_license("Public domain") == ("pdm", "")
       and _media._commons_license("CC BY-SA 4.0")
       == ("by-sa", "4.0")
       and _media._commons_license("CC BY 3.0") == ("by", "3.0")
       and _media._commons_license("CC BY-NC 4.0") is None
       and _media._commons_license("CC BY-ND 4.0") is None
       and _media._commons_license("") is None,
       "commons licenses map to reusable or refused")
    def _fake_down(url):
        if url.startswith(_media.OPENVERSE_URL):
            raise RuntimeError("openverse 403: Forbidden")
        return {"query": {"pages": {
            "7": {"title": "File:Mill.jpg", "imageinfo": [{
                "url": "https://up.test/mill.jpg",
                "descriptionurl": "https://commons.test/mill",
                "extmetadata": {"LicenseShortName": {
                    "value": "CC BY-SA 4.0"}}}]},
            "9": {"title": "File:Rent.jpg", "imageinfo": [{
                "url": "https://up.test/rent.jpg",
                "descriptionurl": "https://commons.test/rent",
                "extmetadata": {"LicenseShortName": {
                    "value": "CC BY-NC 4.0"}}}]}}}}
    _media._HTTP_JSON = _fake_down
    try:
        fb = _media.openverse_search("old mill", 5)
    finally:
        _media._HTTP_JSON = _fake_search
    ok(len(fb) == 1 and fb[0]["source"] == "commons"
       and fb[0]["license"] == "by-sa"
       and fb[0]["image_url"] == "https://up.test/mill.jpg"
       and "fallback" in fb[0],
       "dead openverse falls back to commons, nc refused")
    nt = []
    _media._HTTP_JSON = _fake_down
    try:
        _media.openverse_search("old mill", 5, _note=nt)
    finally:
        _media._HTTP_JSON = _fake_search
    ok(len(nt) == 1 and "403" in nt[0],
       "fallback recorded in _note for the breaker")
    pk = _media.pc_pick_image(pia, {"image_url": "https://img.test/h1.jpg",
                                   "page_url": "https://page.test/h1",
                                   "license": "by-4.0",
                                   "reason": "Harbor fits the cut."})
    ok(pk.get("ok") and pk["file"] == "pick.png"
       and pk["ref"].startswith("pc://image/"),
       "licensed pick stored with file + url + license")
    ok(_media._license_ok("by 4.0") and _media._license_ok("by-sa 4.0")
       and not _media._license_ok("by-nc 4.0"),
       "spaced licenses read like dashed ones")
    ok(_cut_set_diff(["s1c1"], ["s1c1", "s1c2"], "narration")
       == "cut set must equal the narration "
          "(missing ['s1c2']; extra [])",
       "cut-set error names missing and extra")
    import urllib.request as _urlreq, urllib.error as _urlerr
    tries = []

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b"\x89PNG\r\n\x1a\n" + b"0" * 8

    def _flaky(req, timeout=None):
        tries.append(1)
        if len(tries) < 3:
            raise _urlerr.HTTPError(req.full_url, 429, "Too Many",
                                    {"retry-after": "0"}, None)
        return _FakeResp()

    old_open = _urlreq.urlopen
    old_hook = _media._HTTP_BYTES
    _urlreq.urlopen = _flaky
    _media._HTTP_BYTES = None
    try:
        blob = _media._get_bytes("https://up.test/big.jpg", 100)
    finally:
        _urlreq.urlopen = old_open
        _media._HTTP_BYTES = old_hook
    ok(blob.startswith(b"\x89PNG") and len(tries) == 3,
       "429 waits and retries to success")
    hb = _flow._with_handbook({"md": "# Hi", "items": []}, "anim_max")
    ok("template_values" in hb["md"]
       and hb["items"][-1]["item"] == "handbook",
       "max input carries the handbook")
    same = _flow._with_handbook({"md": "# Hi", "items": []},
                                "board_vera")
    ok(same["md"] == "# Hi" and same["items"] == [],
       "other agents get no handbook block")
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
    for _ in range(2):
        v = _media.vera_view_image(vera, {"cut_id": "s1c1",
                                          "path": "index.html"})
        assert v.get("ok"), v
    v3 = _media.vera_view_image(vera, {"cut_id": "s1c1",
                                       "path": "index.html"})
    ok("error" in v3 and "viewed 2 files" in v3["error"],
       "third view refused")
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
    received(vrun, "anim_max", "anim_picks", 2, AN2)
    vmd = os.path.join(vrun, "INPUTS.md")
    with open(vmd, "w", encoding="utf-8") as f:
        f.write("# inputs\n")
    calls = []
    real_chat = _runner._chat

    def _canned(model, messages, tools, max_tokens=None,
                timeout=300, **kw):
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
