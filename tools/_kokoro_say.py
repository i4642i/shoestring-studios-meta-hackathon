"""Kokoro text-to-speech, run by the project's Python (requirements-voice.txt) or KOKORO_PYTHON (functions/_common.py).
A helper, not a tool (the file name starts with _). It loads the model once and voices many lines:

  python _kokoro_say.py jobs.json
  jobs.json: {"voice": "af_heart", "lines": [{"text": "...", "wav": "C:/.../c01.wav"}, ...]}

For each line it writes the .wav (24 kHz) and prints one JSON line: {"wav", "seconds", "words": [{text, start, end}]}."""

import json
import sys

import soundfile
import torch
from kokoro import KPipeline

RATE = 24000


def main(path: str) -> None:
    job = json.load(open(path, encoding="utf-8"))
    voice = job.get("voice") or "af_heart"
    pipe = KPipeline(lang_code="b" if voice.startswith("b") else "a")     # a: American English, b: British
    for line in job["lines"]:
        parts, words, off = [], [], 0.0
        for r in pipe(line["text"], voice=voice):
            a = r.audio.detach().cpu()
            parts.append(a)
            for t in (r.tokens or []):
                if t.start_ts is not None:
                    words.append({"text": t.text, "start": round(off + t.start_ts, 3),
                                  "end": round(off + (t.end_ts or t.start_ts), 3)})
            off += len(a) / RATE
        soundfile.write(line["wav"], torch.cat(parts).numpy(), RATE)
        print(json.dumps({"wav": line["wav"], "seconds": round(off, 3), "words": words}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
