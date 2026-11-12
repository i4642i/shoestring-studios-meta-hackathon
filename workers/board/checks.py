RULES = [
    "source_title is not empty (copy it from the source list as \"title / author, year\").",
    "Every cut_id of the narration appears once, in the narration's order, and no other cut_id appears.",
    "Every field of title_card and end_card is exactly the order's value, letter for letter. title_card.title and end_card.message are not empty.",
    "A cut with form photo needs photo_subject: the real thing to photograph.",
    "Every form except photo, figure and text needs draw: what to draw.",
    "Every materials address is an article address: fs://article/<number> or fs://theory/<number>.",
    "theme is shoestring.",
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the output.",
]

import json
import re

CARDS = (("title_card", "title"), ("end_card", "message"))


def _input(inputs, name):
    """The value of terminal `name` among the inputs (short key first, then any "<block>/<name>" key)."""
    if not inputs:
        return None
    if name in inputs:
        return inputs[name]
    for k, v in inputs.items():
        if k.rpartition("/")[2] == name:
            return v
    return None


def check(outputs, inputs=None):
    v = outputs["visuals"]
    cuts = v["cuts"]
    errors = []
    if not str(v["source_title"]).strip():
        errors.append("source_title is empty. Copy the title and source of the book body md in the input's source list "
                      "letter for letter, as \"title / author, year\".")
    errors += _cut_ids([c["cut_id"] for c in cuts], _input(inputs, "narration"))
    errors += _cards(v, _input(inputs, "request"))
    for c in cuts:
        cid, form = c["cut_id"], c.get("form")
        show = str(c.get("show") or "").strip()
        about = f" This cut's show: \"{show}\"" if show else ""
        if form == "photo" and not str(c.get("photo_subject") or "").strip():
            errors.append(f"{cid} has form photo but photo_subject is empty. Write in one line the real subject to find "
                          f"as a photo (the proper name of a person, company, institution, place or object).{about}")
        if form not in ("photo", "figure", "text") and not str(c.get("draw") or "").strip():
            errors.append(f"{cid} has form {form} but draw is empty. Write in one line what this template draws "
                          f"(only numbers and names found in the narration and the source).{about}")
    for i, m in enumerate(v.get("materials") or []):
        a = str(m.get("address") or "")
        prefix = next((x for x in ("fs://article/", "fs://theory/") if a.startswith(x)), "")
        if not prefix or not a[len(prefix):].strip("/ "):
            errors.append(f"materials item {i + 1} has an address that is not an article address (\"{a}\"). Copy an "
                          f"article address from the input's article or theory list as is (fs://article/<number> or "
                          f"fs://theory/<number>, e.g. fs://article/001).")
    if v.get("theme") != "shoestring":
        errors.append(f"theme is \"{v.get('theme')}\". This channel uses the shoestring colors, so set theme to "
                      f"\"shoestring\".")
    for c in cuts:
        bad = _foreign(c)
        if bad:
            errors.append(f"{c['cut_id']} has Korean, Chinese or Japanese characters: {', '.join(bad)}. Write them in "
                          f"English (proper names in their Latin spelling).")
    bad = _foreign({k: x for k, x in v.items() if k != "cuts"})
    if bad:
        errors.append(f"visuals (fields outside the cuts) has Korean, Chinese or Japanese characters: {', '.join(bad)}. "
                      f"Write them in English (proper names in their Latin spelling).")
    return errors


def _cut_ids(got, narration) -> list[str]:
    """Missing, extra, repeated and out-of-order cut ids, by name (without the narration: repeats only)."""
    out = []
    want = [c["cut_id"] for c in ((narration or {}).get("cuts") or []) if isinstance(c, dict) and c.get("cut_id")]
    for cid in want:
        if cid not in got:
            i = want.index(cid)
            near = f" after {want[i - 1]}" if i else " at the very start"
            out.append(f"cut {cid} is missing from visuals. Every narration cut ({len(want)}) is covered once, so add "
                       f"{cid}{near} with its show, why, form, photo_subject and draw.")
    if want:
        for cid in sorted(set(got) - set(want)):
            out.append(f"cut {cid} is not in the narration. Remove it from visuals.")
    for cid in sorted({x for x in got if got.count(x) > 1}):
        out.append(f"cut {cid} appears {got.count(cid)} times in visuals. Merge them into one.")
    kept = [x for x in dict.fromkeys(got) if x in want]
    if want and not out and kept != want:
        first = next(i for i, (a, b) in enumerate(zip(kept, want)) if a != b)
        out.append(f"the cut order differs from the narration (cut {first + 1} is {kept[first]}, but in the narration it "
                   f"is {want[first]}). Put them in the narration's order ({want[0]} to {want[-1]}).")
    return out


def _cards(v, request) -> list[str]:
    """title_card and end_card copied from the request exactly; title and message never empty."""
    out = []
    for card, key in CARDS:
        given = (request or {}).get(card) if isinstance(request, dict) else None
        mine = v.get(card) or {}
        if isinstance(given, dict):
            for k, want in given.items():
                have = mine.get(k, "")
                if str(have) != str(want or ""):
                    out.append(f"{card}.{k} differs from the order (now: \"{have}\"). Copy the order's value letter for "
                               f"letter: \"{want or ''}\"" + (" (an empty string)." if not want else "."))
        elif not str(mine.get(key) or "").strip():
            out.append(f"{card}.{key} is empty. Copy the order's {card}.{key} exactly as written.")
    return out


_FOREIGN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters anywhere in the value (LaTeX and file paths included)."""
    return sorted(set(_FOREIGN.findall(json.dumps(value, ensure_ascii=False))))[:5]
