RULES = [
    "Cut ids are c01, c02, ... in order.",
    "No brackets ( ) [ ] { } < > in a cut's text (it is read aloud).",
    "Every cut's audio is the file voice_lines made from that cut's current text and returned; if you change the text, voice it again.",
    "seconds is the measured value voice_lines returned.",
    "Every cut is voiced with the voice the narration names.",
    "Write English only: no Korean, Chinese or Japanese characters in the lines.",
]

import json
import pathlib
import re

_BRACKETS = re.compile(r"[()\[\]{}<>]")
_FOREIGN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def check(outputs):
    n = outputs["narration"]
    cuts = n["cuts"]
    voice = n.get("voice")
    errors, other_voice = [], {}
    for k, c in enumerate(cuts, 1):
        if c["cut_id"] != f"c{k:02d}":
            errors.append(f"cut {k} has the id '{c['cut_id']}'. Change it to 'c{k:02d}'.")
    for c in cuts:
        cid, text = c["cut_id"], c["text"]
        for m in list(_BRACKETS.finditer(text))[:2]:
            errors.append(f"the {cid} line has a bracket: '{m.group()}' ('...{_around(text, m.start(), m.end())}...'). "
                          f"Lines are read aloud, so remove the bracket. If the words inside are needed, write them into "
                          f"the sentence (e.g. 'Sharpe ratio (SR)' -> 'Sharpe ratio'), and voice the changed cut again.")
        for m in list(_FOREIGN.finditer(text))[:3]:
            errors.append(f"the {cid} line has Korean, Chinese or Japanese characters: '{m.group()}' "
                          f"('...{_around(text, m.start(), m.end())}...'). Replace them with an English word of the same "
                          f"meaning, then voice {cid} again.")
        errors += _audio(c, other_voice)
    for used, ids in other_voice.items():
        if used != voice:
            errors.append(f"the narration's voice is {voice}, but {', '.join(ids)} were voiced with voice {used}. Voice "
                          f"these cuts again with voice {voice} (if the order's voice is {used}, fix the narration's voice).")
    return errors


def _audio(c: dict, voices: dict) -> list[str]:
    """The cut's audio must be voice_lines' file for this exact text, with its measured seconds; the voice it was made
    with goes into voices (voice -> cut ids) so mismatches are reported once."""
    cid = c["cut_id"]
    given = str(c.get("audio") or "").strip()
    audio = pathlib.Path(given) if given else None
    meta = audio.with_suffix(".json") if audio and audio.name else None
    if not meta or not audio.is_file() or not meta.is_file():
        return [f"the audio file of {cid} was not found (written: '{c.get('audio') or ''}'). Voice {cid} with "
                f"voice_lines and write the audio and seconds it returns as they are."]
    m = json.loads(meta.read_text(encoding="utf-8"))
    errors = []
    said, now = m.get("text", "").strip(), c["text"].strip()
    if said != now:
        at = next((i for i, (a, b) in enumerate(zip(said, now)) if a != b), min(len(said), len(now)))
        errors.append(f"the {cid} line changed after it was voiced (different from character {at + 1}: voiced "
                      f"'...{said[max(0, at - 12):at + 20]}...', now '...{now[max(0, at - 12):at + 20]}...'). Voice {cid} "
                      f"again with voice_lines from the current line and write the audio and seconds it returns.")
    elif abs(float(m.get("seconds") or 0) - float(c["seconds"])) > 0.05:
        errors.append(f"{cid} has seconds {c['seconds']} but the measured value is {m.get('seconds')}. Change seconds "
                      f"to {m.get('seconds')}.")
    voices.setdefault(m.get("voice"), []).append(cid)
    return errors


def _around(text: str, start: int, end: int) -> str:
    return text[max(0, start - 20):end + 20]
