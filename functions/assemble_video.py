"""Joins the part videos (Remotion MP4s with voice) in order into one MP4 and writes subtitles (SRT)."""

import pathlib
import subprocess

from functions._common import ffmpeg, media_seconds, pick, write_json

NAME = "assemble_video"
DESC = "Joins every part video into one MP4 and writes subtitles"
TIMEOUT = 1800
OUTPUTS = [{"name": "video", "schema": {
    "type": "object",
    "properties": {"file": {"type": "string"}, "srt": {"type": "string"}, "seconds": {"type": "number"},
                   "parts": {"type": "integer"}, "cuts": {"type": "integer"},
                   "left_unfixed": {"type": "array"}},
    "required": ["file", "srt", "seconds", "parts", "cuts"]}}]


def _ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"


def _chunks(text, size=32):
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > size and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out or [text]


def run(ctx, inputs):
    parts = pick(inputs, "gathered")
    out = pathlib.Path(ctx["files_dir"])
    out.mkdir(parents=True, exist_ok=True)
    lst = out / "list.txt"
    lst.write_text("".join(f"file '{pathlib.Path(p['file']).as_posix()}'\n" for p in parts), encoding="utf-8")
    video = out / "video.mp4"
    r = subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-ar", "44100", "-b:a", "160k", str(video)], capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": f"joining failed: {r.stderr[-400:]}"}
    srt, base, n = [], 0.0, 0
    for p in parts:
        for c in p["cuts"]:
            n += 1
            pieces = _chunks(c["text"])
            total = sum(len(x) for x in pieces) or 1
            start, speak = base + c["start"], max(0.5, c["seconds"] - 0.4)
            for x in pieces:
                end = start + speak * len(x) / total
                srt.append((start, end, x))
                start = end
        base += p["seconds"]
    sub = out / "captions.srt"
    sub.write_text("".join(f"{k}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n" for k, (a, b, t) in enumerate(srt, 1)), encoding="utf-8")
    lst.unlink()
    write_json(out / "parts.json", parts)
    video_out = {"file": str(video.resolve()), "srt": str(sub.resolve()), "seconds": round(media_seconds(video), 1),
                 "parts": len(parts), "cuts": n}
    # screen problems the screen check could not fix in its allowed rounds (functions/check_layout.py), made visible
    left = [{"part": p.get("part_id"), **x} for p in parts for x in p.get("left_unfixed") or []]
    if left:
        video_out["left_unfixed"] = left
    return {"video": video_out}
