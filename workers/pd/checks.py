RULES = [
    "audience is not empty.",
    "Part ids are p1, p2, ... in order.",
    "Parts go greeting, intro, body parts (no role), outro, farewell, with exactly one greeting, intro, outro and farewell part.",
    "The heading of every part except greeting and farewell is 25-50 characters long (aim for 30-44).",
    "Every part except greeting and farewell has source_refs: one or more fs://source/... addresses. Greeting and farewell have an empty source_refs list.",
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the output.",
]

import re

# where each special part belongs: index in the part list, and what it is called in the messages
_PLACE = {"greeting": (0, "at the very start", "greeting"), "intro": (1, "right after the greeting", "intro"),
          "outro": (-2, "right before the farewell", "outro"), "farewell": (-1, "at the very end", "farewell")}


def check(outputs):
    b = outputs["brief"]
    parts = b["parts"]
    errors = []
    if not b["audience"].strip():
        errors.append("audience is empty. Copy the order's audience. If the order has none, write in one sentence the "
                      "viewers that fit the customer's text (request.text) and the source document (e.g. 'office "
                      "workers who invest and are new to machine learning in finance').")
    for k, p in enumerate(parts, 1):
        if p["id"] != f"p{k}":
            errors.append(f"part {k} ('{p['heading'][:30]}') has the id '{p['id']}'. Change it to 'p{k}'.")
    errors += _roles(parts)
    errors += _headings(parts)
    errors += _refs(parts)
    errors += _foreign(b)
    return errors


def _roles(parts: list) -> list[str]:
    """Missing, doubled or misplaced greeting/intro/outro/farewell parts, each named."""
    errors = []
    n = len(parts)
    for role, (at, where, name) in _PLACE.items():
        have = [p["id"] for p in parts if p.get("role") == role]
        want = f"p{at + 1 if at >= 0 else n + at + 1}"
        if not have:
            errors.append(f"there is no {name} part (role {role}). Put one {name} part {where} (the {want} place).")
        elif len(have) > 1:
            errors.append(f"there are {len(have)} {name} parts (role {role}: {', '.join(have)}). Keep only the one "
                          f"{where} ({want}); merge the others into it, or set their role to null if they are body parts.")
        elif n >= 4 and parts[at]["id"] != have[0]:
            errors.append(f"the {name} part (role {role}) is at {have[0]}. Move it {where} ({want}) and number the ids "
                          f"again in order.")
    return errors


HEADING_MIN, HEADING_MAX = 25, 50        # accepted range; the mission asks for about 30-44
FIXED = ("greeting", "farewell")


def _headings(parts: list) -> list[str]:
    """Headings of the intro, body and outro parts, measured in characters, with how much to cut or add."""
    errors = []
    for p in parts:
        if p.get("role") in FIXED:
            continue
        h = str(p.get("heading") or "").strip()
        n = len(h)
        if n > HEADING_MAX:
            errors.append(f"{p['id']} heading is {n} characters (\"{h}\"); the limit is {HEADING_MAX} (aim for 30-44). "
                          f"Cut about {n - 40} characters: drop filler words or a side clause and keep the conclusion.")
        elif n < HEADING_MIN:
            errors.append(f"{p['id']} heading is {n} characters (\"{h}\"); the minimum is {HEADING_MIN} (aim for 30-44). "
                          f"Add about {35 - n} characters: write the part's conclusion as a full short sentence.")
    return errors


def _refs(parts: list) -> list[str]:
    """source_refs: source addresses for every part except greeting and farewell, none for those two."""
    errors = []
    for p in parts:
        refs = [str(r) for r in p.get("source_refs") or []]
        if p.get("role") in FIXED:
            if refs:
                errors.append(f"{p['id']} is the {p['role']} part, but source_refs has {', '.join(refs[:3])}. Make "
                              f"source_refs an empty list.")
            continue
        bad = [r for r in refs if not r.startswith("fs://source/")]
        if not refs:
            errors.append(f"{p['id']} ('{str(p.get('heading') or '')[:30]}') has no source_refs. Write the address of the "
                          f"source part that holds this content, from the map of the source list (fs://source/<number>#p<number>).")
        elif bad:
            errors.append(f"{p['id']} source_refs has addresses that are not source addresses: {', '.join(bad[:3])}. Copy "
                          f"addresses from the map of the source list (fs://source/<number>#p<number>).")
    return errors


_FOREIGN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(brief: dict) -> list[str]:
    """Korean, Chinese or Japanese characters, named with the field and the words around them."""
    errors = []
    for where, text in _texts(brief):
        for m in list(_FOREIGN.finditer(text))[:3]:
            ctx = text[max(0, m.start() - 20):m.end() + 20]
            errors.append(f"{where} has Korean, Chinese or Japanese characters: '{m.group()}' ('...{ctx}...'). Replace "
                          f"them with an English word of the same meaning; if none fits, drop the word and fix the sentence.")
    return errors[:8]


def _texts(value, path="brief"):
    """(field path, text) for every string in the brief, e.g. ('brief.parts[p3].covers', '...')."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _texts(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            label = v.get("id") if isinstance(v, dict) and v.get("id") else f"item {i + 1}"
            yield from _texts(v, f"{path}[{label}]")
