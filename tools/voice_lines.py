"""The narrator's own dubbing tool: voices the given cuts and returns the real playing time of each file.

Voice: Kokoro (local and free), American English female voice af_heart. "draft" and "final" use the same voice.
Each cut is written to files/voice/<cut_id>.mp3 (a new call replaces it), with <cut_id>.json next to it
(the exact text, seconds, voice, word timings) so the checker can tell the file matches the final text."""

import json
import pathlib
import re

from functions._common import KOKORO_VOICE, speak_kokoro_many

NAME = "voice_lines"
DESC = ("Dub cuts and measure them: give voice (draft or final, from the order) and the cuts [{cut_id, text}] to voice "
        "(all at first, later only the cuts you changed). Returns each cut's real seconds and audio file, and, for "
        "information only, the totals over every cut voiced so far in this task (voice time, 0.4 s pause per cut, video "
        "length). Put seconds and audio exactly as returned into the narration. The video is as long as its lines; "
        "nothing has to fit a length.")
PAUSE = 0.4                      # silence after each cut's voice in the video (render_part BREATH)
SCHEMA = {
    "type": "object",
    "properties": {
        "voice": {"type": "string", "enum": ["draft", "final"]},
        "cuts": {"type": "array", "minItems": 1, "maxItems": 80, "items": {
            "type": "object",
            "properties": {"cut_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["cut_id", "text"]}},
    },
    "required": ["voice", "cuts"],
}


def run(ctx, args):
    out_dir = pathlib.Path(ctx["files_dir"]) / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)
    done, todo = [], []
    for c in args["cuts"]:
        text = c["text"].strip()
        if not text:
            done.append({"cut_id": c["cut_id"], "error": "empty text"})
            continue
        cid = re.sub(r"[^A-Za-z0-9_-]", "_", c["cut_id"])
        todo.append((c["cut_id"], text, out_dir / f"{cid}.mp3"))
    if todo:
        try:
            res = speak_kokoro_many([(t, p) for _c, t, p in todo], KOKORO_VOICE)
        except Exception as e:
            return {"error": f"voice failed: {e}"}
        for (cut_id, text, mp3), (secs, words) in zip(todo, res):
            meta = {"cut_id": cut_id, "text": text, "seconds": round(secs, 2), "voice": args["voice"], "words": words}
            (mp3.with_suffix(".json")).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            done.append({"cut_id": cut_id, "seconds": round(secs, 2), "audio": str(mp3.resolve()), "chars": len(text)})
    return {"cuts": done, "all_voiced_so_far": _totals(out_dir)}


def _totals(out_dir: pathlib.Path) -> dict:
    """Totals over every cut voiced so far in this block (the latest file per cut id), computed here so the
    worker never adds them up. A cut voiced earlier but no longer in the narration still counts."""
    secs = {}
    for f in sorted(out_dir.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            secs[m.get("cut_id") or f.stem] = float(m.get("seconds") or 0)
        except (OSError, ValueError):
            continue
    voice = round(sum(secs.values()), 1)
    pause = round(PAUSE * len(secs), 1)
    return {"cut_ids": sorted(secs), "cut_count": len(secs), "voice_seconds": voice, "pause_seconds": pause,
            "video_seconds": round(voice + pause, 1),
            "note": "For information only: the video length follows the lines; no length has to be met."}
