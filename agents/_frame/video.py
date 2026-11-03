"""Phase A video production: Remotion PNG slides, subtitle
timing, the storyboard table, and the ffmpeg assembly seam.

Pure planning functions never touch the network or a model, and
never run ffmpeg. Only run_ffmpeg() executes anything, and only
when an ffmpeg binary is on PATH.
"""

import json
import os
import shutil
import subprocess
import time
from xml.sax.saxutils import escape

RENDER_MAX = 3
VOICE_PAD_S = 0.3  # breathing room after each voice clip ends
XFADE_S = 0.5  # crossfade between cuts (video + audio)


def wav_seconds(path):
    """Real length of a WAV file in seconds. Raises on anything
    unreadable (callers fall back to the planned cut length)."""
    import wave
    with wave.open(path, "rb") as w:
        rate = w.getframerate() or 1
        return w.getnframes() / float(rate)


def retime_narration(narration, audio_lengths):
    """Narration copy whose cut times follow the measured voice:
    each cut lasts its WAV length plus a fade tail and a breath, laid end to end.
    Cuts without a measured length keep their planned duration.
    Planned seconds stay Wren's writing target only."""
    cuts = ((narration or {}).get("cuts") or [])
    out = []
    cursor = 0.0; real = [c for c in cuts if isinstance(c, dict)]; pad = VOICE_PAD_S + (XFADE_S if len(real) > 1 else 0.0)
    for cut in cuts:
        if not isinstance(cut, dict):
            continue
        cid = cut.get("cut_id")
        try:
            start = float(cut.get("start_s", 0))
            end = float(cut.get("end_s", start))
            planned = max(0.0, end - start)
        except (TypeError, ValueError):
            planned = 0.0
        length = None
        if isinstance(audio_lengths, dict):
            try:
                length = float(audio_lengths.get(cid))
            except (TypeError, ValueError):
                length = None
        dur = round(length + pad, 3) \
            if length is not None and length > 0 \
            else round(planned + pad, 3)
        clone = dict(cut)
        clone["start_s"] = round(cursor, 3)
        clone["end_s"] = round(cursor + dur, 3)
        out.append(clone)
        cursor += dur
    return {"cuts": out}


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


def srt_timestamp(seconds):
    """Seconds (float) -> 'HH:MM:SS,mmm'."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


SRT_MAX_WORDS = 12  # one subtitle block holds at most 12 words


def _split_sentences(text):
    """One line -> sentence strings (sentence-end punctuation
    .!?… splits; words never change)."""
    import re
    bits = re.split(r"(?<=[.!?\u2026])\s+", str(text).strip())
    return [b.strip() for b in bits if b.strip()] or [str(text).strip()]


def _block_texts(cut):
    """One cut's lines -> subtitle block texts. Each line keeps
    its own blocks (split at sentence ends, packed to
    SRT_MAX_WORDS; a past-limit sentence cuts at the word
    boundary). Wren's words never change, only the grouping."""
    out = []
    for ln in ((cut or {}).get("lines") or []):
        if not isinstance(ln, dict) \
                or not str(ln.get("text", "")).strip():
            continue
        cur = []
        for sent in _split_sentences(ln["text"]):
            words = sent.split()
            while len(words) > SRT_MAX_WORDS:
                if cur:
                    out.append(" ".join(cur))
                    cur = []
                out.append(" ".join(words[:SRT_MAX_WORDS]))
                words = words[SRT_MAX_WORDS:]
            if not words:
                continue
            if len(cur) + len(words) <= SRT_MAX_WORDS:
                cur += words
            else:
                if cur:
                    out.append(" ".join(cur))
                cur = words
        if cur:
            out.append(" ".join(cur))
    return out


def srt_blocks(narration):
    """(cut, [block texts]): each line split at sentence ends and
    packed into blocks of at most SRT_MAX_WORDS words. A single
    sentence past the limit is cut at the word boundary. Wren's
    words never change, only the grouping."""
    out = []
    for cut in ((narration or {}).get("cuts") or []):
        if not isinstance(cut, dict):
            continue
        out.append((cut, _block_texts(cut)))
    return out


def build_srt(narration):
    """Subtitles from Wren's exact line text. Each cut's blocks
    (lines split at sentence ends into <=12-word groups) split
    its time proportionally by word count (the no-word-
    timestamps fallback). Returns the .srt text."""
    blocks = []
    n = 0
    for cut, texts in srt_blocks(narration):
        start = float(cut.get("start_s", 0))
        end = float(cut.get("end_s", start))
        weights = [max(1, len(t.split())) for t in texts]
        total = sum(weights) or 1
        cursor = start
        for text, w in zip(texts, weights):
            span = (end - start) * w / total
            n += 1
            blocks.append("%d\n%s --> %s\n%s\n"
                          % (n, srt_timestamp(cursor),
                             srt_timestamp(cursor + span),
                             text))
            cursor += span
    return "\n".join(blocks)


def scene_part_map(part_info=None, draft=None, narration=None):
    """scene_n -> part id for the storyboard table. part_info
    (no/title/seconds/cuts per part, attached by part_split to
    every merged clone result) wins; the draft scene map is the
    fallback for runs merged before part_info existed."""
    cuts = {}
    for p in ((part_info or {}).get("parts") or []):
        if not isinstance(p, dict):
            continue
        for cid in (p.get("cuts") or []):
            if isinstance(cid, str):
                cuts[cid] = p.get("part_id", "")
    if cuts and isinstance(narration, dict):
        out = {}
        for c in (narration.get("cuts") or []):
            if isinstance(c, dict) and c.get("cut_id") in cuts \
                    and isinstance(c.get("scene_n"), int):
                out[c["scene_n"]] = cuts[c["cut_id"]]
        if out:
            return out
    out = {}
    for sc in ((draft or {}).get("scenes") or []):
        if isinstance(sc, dict):
            out[sc.get("n")] = sc.get("part_id", "")
    return out


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


OVERRIDE_BLOCK_KEYS = ("font_size", "x", "y", "w", "h",
                        "align")


def _int_or_none(v):
    return v if isinstance(v, int) and not isinstance(v, bool) \
        else None


def apply_overrides(props, overrides):
    """Remy's layout-only pass over rendered props: per-block
    font_size/x/y/w/h/align (blocks addressed by index) and
    on_screen_text font/position. Unknown keys are ignored, so a
    stray field never breaks a render."""
    if not isinstance(overrides, dict):
        return props
    blocks = props.get("blocks")
    bov = overrides.get("blocks")
    if isinstance(blocks, list) and isinstance(bov, dict):
        for j, nb in enumerate(blocks):
            if not isinstance(nb, dict):
                continue
            bo = bov.get(str(j))
            if not isinstance(bo, dict):
                continue
            for k in OVERRIDE_BLOCK_KEYS:
                if k not in bo:
                    continue
                if k == "align":
                    if isinstance(bo[k], str) and bo[k].strip():
                        nb["align"] = bo[k].strip()[:16]
                elif k == "font_size":
                    v = _int_or_none(bo[k])
                    if v is not None and v > 0:
                        nb["font_size"] = v
                else:
                    v = _int_or_none(bo[k])
                    if v is not None and v >= 0:
                        nb["box"][k] = v
    oov = overrides.get("on_screen_text")
    if isinstance(oov, dict):
        v = _int_or_none(oov.get("font"))
        if v is not None and v > 0:
            props["onScreenTextFont"] = v
        pos = oov.get("position")
        if isinstance(pos, str) and pos.strip().lower() \
                in ("top", "bottom"):
            props["onScreenTextPosition"] = pos.strip().lower()
    return props


def cut_slide_props(cut, guide, overrides=None):
    """Cut (slide_draft v2) + style guide -> Remotion CutSlide
    props. Remy's overrides (when given) are applied here, so
    the sidecar render_slide writes is exactly what
    video_production assembles. Shared by render_slide and the
    assembly records."""
    dur = 20
    try:
        dur = int(round(float(cut.get("end_s", 20))
                        - float(cut.get("start_s", 0)))) or 20
    except (TypeError, ValueError):
        pass
    dur = max(dur, 1)
    blocks = []
    for b in (cut.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        box = b.get("box") or {}
        nb = {"kind": b.get("kind"),
              "box": {k: box.get(k) for k in ("x", "y", "w", "h")},
              "order": b.get("order", 0),
              "appear_s": b.get("appear_s", 0),
              "reason": b.get("reason", ""),
              "font_size": b.get("font_size"),
              "data": b.get("data") or {}}
        if b.get("kind") in ("photo", "generated", "source_figure"):
            ref = b.get("ref") or ""
            nb["ref"] = ref
            nb["file"] = "" if ref.startswith("pc://") else ref
        blocks.append(nb)
    props = {"cutId": cut.get("cut_id"), "seconds": dur,
               "preset": cut.get("preset", "full"), "blocks": blocks,
               "onScreenText": cut.get("on_screen_text") or [],
               "onScreenTextFont": 36,
               "onScreenTextPosition": "bottom",
               "guide": guide if isinstance(guide, dict) else {}}
    return apply_overrides(props, overrides)


def build_cut_records(narration, slide_files, audio_files,
                      props_map=None, voice_refs=None,
                      slide_status=None, clip_files=None):
    """Per-cut assembly records: props + slide PNG + voice for
    every cut. Missing sidecars/refs record None, never a guess.
    Returns (records, total_s)."""
    props_map = props_map or {}
    voice_refs = voice_refs or {}
    slide_status = slide_status or {}
    clip_files = clip_files or {}
    records = []
    total = 0.0
    for c in ((narration or {}).get("cuts") or []):
        if not isinstance(c, dict):
            continue
        cid = c.get("cut_id")
        dur = float(c.get("end_s", 0)) - float(c.get("start_s", 0))
        slide = (slide_files or {}).get(cid)
        records.append({
            "cut_id": cid,
            "at_s": round(total, 3),
            "dur_s": round(dur, 3),
            "props": props_map.get(cid),
            "slide": slide,
            "slide_status": slide_status.get(
                cid, "rendered" if slide else "missing"),
            "audio": (audio_files or {}).get(cid),
            "voice_ref": voice_refs.get(cid),
            "clip": clip_files.get(cid),
        })
        total += dur
    return records, round(total, 3)


def build_assembly(narration, slide_files, audio_files,
                   out_name="video", props_map=None,
                   voice_refs=None, slide_status=None,
                   audio_lengths=None, clip_files=None):
    """Pure assembly plan. slide_files/audio_files map cut_id ->
    file path; clip_files maps cut_id -> Remy's per-cut MP4 clip
    when rendered (else the looped slide PNG is used). Every
    segment lasts its measured voice (audio_lengths) plus a
    0.5 s fade tail of silence plus a 0.3 s breath, so the
    0.5 s crossfade (xfade + acrossfade) never touches speech;
    a lone cut keeps just the 0.3 s breath. Audio is apadded to
    the same length. start_s/end_s for the SRT and the cut
    records come from the measured lengths; planned seconds
    remain only Wren's writing target. Execution lives in
    run_ffmpeg() only."""
    timed = retime_narration(narration, audio_lengths)
    segments, _ = build_cut_records(
        timed, slide_files, audio_files, props_map,
        voice_refs, slide_status, clip_files)
    lens = [seg["dur_s"] for seg in segments]
    nseg = len(segments)
    cmd = ["ffmpeg", "-y"]
    for seg in segments:
        clip = (clip_files or {}).get(seg["cut_id"])
        if clip:
            cmd += ["-stream_loop", "-1", "-t", str(seg["dur_s"]),
                    "-i", clip]
        else:
            cmd += ["-loop", "1", "-t", str(seg["dur_s"]), "-i",
                    seg["slide"] or ""]
    for seg in segments:
        cmd += ["-i", seg["audio"] or ""]
    total = round(sum(lens), 3)
    if nseg == 1:
        filt = "[1:a]apad=whole_dur=%s[a]" % lens[0]  # 0:v, 1:a
        cmd += ["-filter_complex", filt, "-map", "0:v", "-map",
                "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-t", str(total),
                out_name + ".mp4"]
    elif nseg:
        filt = []
        for k in range(nseg):
            filt.append("[%d:v]scale=1280:720:flags=lanczos,fps=30,"
                        "format=yuv420p[sv%d]"
                        % (k, k))
            filt.append("[%d:a]apad=whole_dur=%s[ap%d]"
                        % (nseg + k, lens[k], k))
        vcur, acur, run = "[sv0]", "[ap0]", lens[0]
        for k in range(1, nseg):
            off = round(run - k * XFADE_S, 3)
            filt.append("%s[sv%d]xfade=transition=fade:duration=%s"
                        ":offset=%s[xv%d]"
                        % (vcur, k, XFADE_S, off, k))
            vcur = "[xv%d]" % k
            filt.append("%s[ap%d]acrossfade=d=%s:c1=tri:c2=tri[ac%d]"
                        % (acur, k, XFADE_S, k))
            acur = "[ac%d]" % k
            run += lens[k]
        filt.append("%snull[v]" % vcur)
        filt.append("%sanull[a]" % acur)
        total = round(sum(lens) - (nseg - 1) * XFADE_S, 3)
        cmd += ["-filter_complex", ";".join(filt), "-map", "[v]",
                "-map", "[a]", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", "-c:a", "aac", "-t", str(total),
                out_name + ".mp4"]
    return {"segments": segments, "srt": build_srt(timed),
            "ffmpeg_cmd": cmd, "total_s": total}


def ffmpeg_exe():
    """ffmpeg binary: a full build first (PATH, then the pip
    imageio-ffmpeg static build — both carry xfade/acrossfade for
    the assembly crossfades), else the Remotion compositor build
    (minimal: concat only), else None."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        cand = get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - optional video dep
        cand = ""
    if cand and os.path.isfile(cand):
        return cand
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    bundled = os.path.join(root, "video", "remotion",
                           "node_modules", "@remotion",
                           "compositor-win32-x64-msvc",
                           "ffmpeg.exe")
    if os.path.isfile(bundled):
        return bundled
    return None


def run_ffmpeg(cmd, timeout_s=120, cwd=None):
    """Run an ffmpeg command. Returns {ok, ...}; ok False with a
    clear reason when ffmpeg is missing or the run fails."""
    exe = ffmpeg_exe()
    if not exe:
        return {"ok": False,
                "error": "no ffmpeg: install ffmpeg or run "
                         "tools/setup_video.ps1"}
    argv = [exe] + list(cmd[1:]) if cmd and cmd[0] == "ffmpeg" \
        else list(cmd)
    try:
        # stdin closed: ffmpeg must never sit waiting for keyboard input
        done = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=timeout_s, cwd=cwd, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": "ffmpeg failed: %s" % exc}
    if done.returncode != 0:
        return {"ok": False,
                "error": "ffmpeg exit %d: %s"
                % (done.returncode,
                   (done.stderr or "")[-400:])}
    return {"ok": True}


_TRANSCRIBE_FN = None  # fn(path) -> turns (tests inject fixtures)
SKIP_TRANSCRIBE = True  # the live audio API still answers 400: keep
# proportional timing until transcribe_file() is verified fixed, then
# flip back to False so runs use turn-level alignment again.


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
    body = _multipart_body(bound, model, blob)
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


def _multipart_body(bound, model, blob):
    """Multipart request body for one WAV upload. The CRLF between
    the blob and the closing boundary is required: without it the
    audio API answers 400 Bad Request."""
    head = (
        "--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
        "%s\r\n--%s\r\nContent-Disposition: form-data; "
        "name=\"file\"; filename=\"cut.wav\"\r\n"
        "Content-Type: audio/wav\r\n\r\n" % (bound, model, bound)
    ).encode()
    return head + blob + ("\r\n--%s--\r\n" % bound).encode()


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
        texts = _block_texts(cut)
        weights = [max(1, len(t.split())) for t in texts]
        total = sum(weights) or 1
        cursor = start
        for text, w in zip(texts, weights):
            span = (end - start) * w / total
            n += 1
            blocks.append("%d\n%s --> %s\n%s\n"
                          % (n, srt_timestamp(cursor),
                             srt_timestamp(cursor + span),
                             text))
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


ASSEMBLE_TIMEOUT_S = 900


def assemble_run(run_dir, timeout_s=ASSEMBLE_TIMEOUT_S):
    """Turn a finished run's ffmpeg plan (video_production/assembly.json)
    into video_production/video.mp4. One place for every caller: the
    flow's end (automatic), the server's assemble endpoint and the test
    driver. A fresh MP4 always replaces the old one (a re-assembly after
    a fix must not leave the old file). Writes assemble.log
    ({state, ok, seconds, error, bytes}); never raises."""
    vdir = os.path.join(run_dir, "video_production")
    logp = os.path.join(vdir, "assemble.log")

    def _log(rec):
        try:
            with open(logp, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    try:
        with open(os.path.join(vdir, "assembly.json"),
                  encoding="utf-8") as f:
            cmd = json.load(f).get("ffmpeg_cmd", [])
    except (OSError, ValueError) as exc:
        rec = {"state": "failed", "ok": False, "seconds": 0,
               "error": "no assembly plan: %s" % exc}
        _log(rec)
        return rec
    if not cmd:
        rec = {"state": "failed", "ok": False, "seconds": 0,
               "error": "empty assembly plan"}
        _log(rec)
        return rec
    # every input file must be there before ffmpeg starts: a missing
    # slide or voice fails at once with its name (no ffmpeg run on a
    # half-built plan)
    missing = []
    for i, arg in enumerate(cmd[:-1]):
        if arg != "-i":
            continue
        if i >= 2 and cmd[i - 2] == "-f" and cmd[i - 1] == "lavfi":
            continue
        src = cmd[i + 1]
        path = src if os.path.isabs(src) else os.path.join(run_dir, src)
        if not os.path.isfile(path):
            missing.append(src)
    if missing:
        rec = {"state": "failed", "ok": False, "seconds": 0,
               "error": "missing input (%d): %s" % (
                   len(missing), ", ".join(missing[:3]))}
        _log(rec)
        return rec
    _log({"state": "running", "ok": False, "seconds": 0, "error": "",
          "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    t0 = time.time()
    out = run_ffmpeg(cmd, timeout_s=timeout_s, cwd=run_dir)
    rec = {"ok": bool(out.get("ok")),
           "seconds": round(time.time() - t0, 1),
           "error": out.get("error", "")}
    mp = os.path.join(vdir, "video.mp4")
    raw = os.path.join(run_dir, "video.mp4")
    if rec["ok"] and os.path.isfile(raw):
        try:
            os.replace(raw, mp)
        except OSError as exc:
            rec.update(ok=False, error="cannot move video.mp4: %s" % exc)
    if rec["ok"] and not os.path.isfile(mp):
        rec.update(ok=False, error="ffmpeg ended but no video.mp4")
    if rec["ok"]:
        rec["bytes"] = os.path.getsize(mp)
        rp = os.path.join(vdir, "result.json")
        try:
            with open(rp, encoding="utf-8") as f:
                res = json.load(f)
            res["categories"]["video"]["data"]["file"]["size_bytes"] =                 rec["bytes"]
            with open(rp, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    rec["state"] = "done" if rec["ok"] else "failed"
    _log(rec)
    return rec
