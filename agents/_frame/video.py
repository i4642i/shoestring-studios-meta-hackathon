"""Phase A video production: Remotion PNG slides, subtitle
timing, the storyboard table, and the ffmpeg assembly seam.

Pure planning functions never touch the network or a model, and
never run ffmpeg. Only run_ffmpeg() executes anything, and only
when an ffmpeg binary is on PATH.
"""

import os
import shutil
import subprocess
from xml.sax.saxutils import escape

RENDER_MAX = 3
CARD_W = 1280
CARD_H = 720


def _color(guide, key, default):
    try:
        val = ((guide or {}).get("palette") or {}).get(key)
    except AttributeError:
        val = None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return default


def _font(guide, key, default):
    try:
        val = ((guide or {}).get("fonts") or {}).get(key)
    except AttributeError:
        val = None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return default


def render_text_card(cut, guide, out_path):
    """Render one cut's text card as an SVG file. Returns out_path.

    cut: Vera slide_draft cut {cut_id, on_screen_text[], layout}.
    guide: Penn style_guide {palette, fonts}. Missing style falls
    back to safe defaults so a stub guide still renders.
    """
    cut = cut or {}
    lines = cut.get("on_screen_text") or []
    if not isinstance(lines, list):
        raise ValueError("on_screen_text must be a list")
    lines = [str(t) for t in lines[:3]]
    bg = _color(guide, "background", "#101418")
    fg = _color(guide, "text", "#f5f2ea")
    accent = _color(guide, "accent", "#e0a458")
    body = _font(guide, "body", "sans-serif")
    heading = _font(guide, "heading", "sans-serif")
    head = escape(str(cut.get("cut_id", "")))
    Hedge = escape(str(cut.get("layout", "")))
    items = []
    y0 = CARD_H // 2 - (len(lines) - 1) * 44 if lines else CARD_H // 2
    for i, t in enumerate(lines):
        items.append(
            '<text x="640" y="%d" text-anchor="middle" '
            'font-family="%s" font-size="56" fill="%s">%s</text>'
            % (y0 + i * 88, escape(body), fg, escape(t)))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" '
        'height="%d" viewBox="0 0 %d %d">'
        '<rect width="%d" height="%d" fill="%s"/>'
        '<rect x="0" y="0" width="%d" height="14" fill="%s"/>'
        '<text x="48" y="80" font-family="%s" font-size="30" '
        'fill="%s">%s</text>'
        '<text x="48" y="660" font-family="%s" font-size="24" '
        'fill="%s">%s</text>'
        '%s</svg>'
        % (CARD_W, CARD_H, CARD_W, CARD_H, CARD_W, CARD_H, bg,
           CARD_W, accent, escape(heading), accent, head,
           escape(body), accent, Hedge, "".join(items)))
    folder = os.path.dirname(out_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return out_path


def srt_timestamp(seconds):
    """Seconds (float) -> 'HH:MM:SS,mmm'."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def build_srt(narration):
    """Subtitles from Wren's exact line text. Each cut's lines
    split its time proportionally by word count (the no-word-
    timestamps fallback). Returns the .srt text."""
    blocks = []
    n = 0
    for cut in ((narration or {}).get("cuts") or []):
        if not isinstance(cut, dict):
            continue
        start = float(cut.get("start_s", 0))
        end = float(cut.get("end_s", start))
        lines = [ln for ln in (cut.get("lines") or [])
                 if isinstance(ln, dict) and str(ln.get("text",
                                                       "")).strip()]
        weights = [max(1, len(str(ln["text"]).split()))
                   for ln in lines]
        total = sum(weights) or 1
        cursor = start
        for ln, w in zip(lines, weights):
            span = (end - start) * w / total
            n += 1
            blocks.append("%d\n%s --> %s\n%s\n"
                          % (n, srt_timestamp(cursor),
                             srt_timestamp(cursor + span),
                             str(ln["text"]).strip()))
            cursor += span
    return "\n".join(blocks)


def build_table(narration, storyboard, slide_draft, scene_part=None):
    """Final storyboard_table v1: one row per cut. scene_part maps
    scene_n -> part id (from Ash's draft); unknown maps to ''."""
    scene_part = scene_part or {}
    screens = {}
    for c in ((storyboard or {}).get("cuts") or []):
        if isinstance(c, dict) and c.get("cut_id"):
            screens[c["cut_id"]] = c
    slides = {}
    for c in ((slide_draft or {}).get("cuts") or []):
        if isinstance(c, dict) and c.get("cut_id"):
            slides[c["cut_id"]] = c
    rows = []
    for c in ((narration or {}).get("cuts") or []):
        if not isinstance(c, dict):
            continue
        cid = c.get("cut_id")
        scr = screens.get(cid, {})
        sld = slides.get(cid, {})
        mats = []
        for m in (sld.get("blocks") or sld.get("materials") or []):
            if isinstance(m, dict):
                mats.append(m.get("ref") or m.get("kind") or "")
            else:
                mats.append(str(m))
        text = " ".join(str(ln.get("text", ""))
                        for ln in (c.get("lines") or [])
                        if isinstance(ln, dict))
        rows.append({
            "part": str(scene_part.get(c.get("scene_n"), "")),
            "scene_n": c.get("scene_n"),
            "cut_id": cid,
            "start_s": c.get("start_s"),
            "end_s": c.get("end_s"),
            "narration": " ".join(text.split()),
            "screen": scr.get("show_what", ""),
            "materials": mats,
        })
    return {"rows": rows}


def build_assembly(narration, slide_files, audio_files, out_name="video"):
    """Pure assembly plan. slide_files/audio_files map cut_id ->
    file path. Returns {segments, srt, table-ready cuts, ffmpeg_cmd,
    total_s}. Execution lives in run_ffmpeg() only."""
    segments = []
    total = 0.0
    for c in ((narration or {}).get("cuts") or []):
        if not isinstance(c, dict):
            continue
        cid = c.get("cut_id")
        dur = float(c.get("end_s", 0)) - float(c.get("start_s", 0))
        segments.append({
            "cut_id": cid,
            "slide": slide_files.get(cid),
            "audio": audio_files.get(cid),
            "at_s": round(total, 3),
            "dur_s": round(dur, 3),
        })
        total += dur
    cmd = ["ffmpeg", "-y"]
    for seg in segments:
        cmd += ["-loop", "1", "-t", str(seg["dur_s"]), "-i",
                seg["slide"] or ""]
    for seg in segments:
        cmd += ["-i", seg["audio"] or ""]
    nseg = len(segments)
    if nseg:
        vcat = "".join("[%d:v]" % i for i in range(nseg))
        acat = "".join("[%d:a]" % (nseg + i) for i in range(nseg))
        filt = ("%sconcat=n=%d:v=1:a=0[v];"
                "%sconcat=n=%d:v=0:a=1[a]" % (vcat, nseg, acat, nseg))
        cmd += ["-filter_complex", filt, "-map", "[v]", "-map",
                "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", out_name + ".mp4"]
    return {"segments": segments, "srt": build_srt(narration),
            "ffmpeg_cmd": cmd, "total_s": round(total, 3)}


def run_ffmpeg(cmd, timeout_s=120):
    """Run an ffmpeg command. Returns {ok, ...}; ok False with a
    clear reason when ffmpeg is missing or the run fails."""
    if not shutil.which("ffmpeg"):
        return {"ok": False,
                "error": "ffmpeg not on PATH (fallback: install "
                         "ffmpeg or render via Remotion)"}
    try:
        done = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout_s)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": "ffmpeg failed: %s" % exc}
    if done.returncode != 0:
        return {"ok": False,
                "error": "ffmpeg exit %d: %s"
                % (done.returncode,
                   (done.stderr or "")[-400:])}
    return {"ok": True}


_TRANSCRIBE_FN = None  # fn(path) -> turns (tests inject fixtures)


def _norm_words(text):
    import string
    drop = str.maketrans("", "", string.punctuation)
    return (text or "").lower().translate(drop).split()


def transcribe_file(path, fn=None):
    """Turn-level transcript [{start_s, end_s, text}] for one audio
    file. Live path posts multipart to the OpenAI-compatible audio
    API with muse-voice-transcribe-1.0 (turn timestamps only, per
    Meta's speech docs); tests inject fn. First live call verifies
    the shape."""
    call = fn or _TRANSCRIBE_FN
    if call is not None:
        return call(path)
    from . import runner
    model = "muse-voice-transcribe-1.0"
    _, url, _ = runner.provider_of("meta-models/muse-spark-open-1026")
    import json as _json
    import urllib.error
    import urllib.request
    bound = "----shoestring%d" % os.getpid()
    with open(path, "rb") as f:
        blob = f.read()
    body = (
        "--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
        "%s\r\n--%s\r\nContent-Disposition: form-data; "
        "name=\"file\"; filename=\"cut.wav\"\r\n"
        "Content-Type: audio/wav\r\n\r\n" % (bound, model, bound)
    ).encode() + blob + ("--%s--\r\n" % bound).encode()
    req = urllib.request.Request(
        url + "/audio/transcriptions", data=body,
        headers={"Authorization": "Bearer " + runner._key(
            "meta-models/muse-spark-open-1026"),
            "Content-Type": "multipart/form-data; boundary=" + bound},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = _json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("transcribe %s: %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError("transcribe unreachable: %s" % exc)
    turns = []
    for seg in (data.get("segments") or data.get("turns") or []):
        try:
            turns.append({"start_s": float(seg.get("start", 0)),
                          "end_s": float(seg.get("end", 0)),
                          "text": str(seg.get("text", ""))})
        except (TypeError, ValueError):
            continue
    return turns


def _cut_span(cut, turns):
    """Audible span of a cut: the turns overlapping it, clipped to
    the cut; the whole cut when no turn overlaps."""
    start = float(cut.get("start_s", 0))
    end = float(cut.get("end_s", start))
    lo, hi = end, start
    for t in turns or []:
        if not isinstance(t, dict):
            continue
        ts, te = float(t.get("start_s", 0)), float(t.get("end_s", 0))
        if te > start and ts < end:
            lo = min(lo, max(ts, start))
            hi = max(hi, min(te, end))
    if hi <= lo:
        return start, end
    return lo, hi


def align_subs(narration, turns):
    """Subtitles refined by turn times: each cut's lines split
    proportionally by word count across the cut's audible span
    (turns clipped to the cut). Text stays Wren's exact lines."""
    blocks = []
    n = 0
    for cut in ((narration or {}).get("cuts") or []):
        if not isinstance(cut, dict):
            continue
        start, end = _cut_span(cut, turns)
        lines = [ln for ln in (cut.get("lines") or [])
                 if isinstance(ln, dict) and str(ln.get("text",
                                                       "")).strip()]
        weights = [max(1, len(str(ln["text"]).split()))
                   for ln in lines]
        total = sum(weights) or 1
        cursor = start
        for ln, w in zip(lines, weights):
            span = (end - start) * w / total
            n += 1
            blocks.append("%d\n%s --> %s\n%s\n"
                          % (n, srt_timestamp(cursor),
                             srt_timestamp(cursor + span),
                             str(ln["text"]).strip()))
            cursor += span
    return "\n".join(blocks)


def compare_transcript(narration, turns):
    """TTS check: Wren's script vs what transcription heard, per
    cut (normalized words). A mismatch means the TTS misread or
    the mic caught something else."""
    out = []
    for cut in ((narration or {}).get("cuts") or []):
        if not isinstance(cut, dict):
            continue
        start = float(cut.get("start_s", 0))
        end = float(cut.get("end_s", start))
        script = " ".join(str(ln.get("text", ""))
                          for ln in (cut.get("lines") or [])
                          if isinstance(ln, dict))
        heard = " ".join(
            str(t.get("text", "")) for t in (turns or [])
            if isinstance(t, dict)
            and float(t.get("end_s", 0)) > start
            and float(t.get("start_s", 0)) < end)
        sw, hw = _norm_words(script), _norm_words(heard)
        out.append({"cut_id": cut.get("cut_id"),
                    "match": bool(sw) and sw == hw,
                    "script_words": len(sw),
                    "heard_words": len(hw)})
    return out
