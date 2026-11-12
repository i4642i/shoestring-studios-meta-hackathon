RULES = [
    "Scene numbers n are 1, 2, 3, ... in order.",
    "Every scene's part_id is a part id of the brief (p1, p2, ...).",
    "Every case scene (role case) has a link; other scenes have none.",
    "Every materials address is an article address: fs://article/<number> or fs://theory/<number>.",
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the output.",
]

import re


def check(outputs, inputs=None):
    sb = outputs["storyboard"]
    scenes = sb["scenes"]
    errors = []
    for k, sc in enumerate(scenes, 1):
        if sc.get("n") != k:
            errors.append(f"scene {k} (part_id {sc.get('part_id')}, role {sc.get('role')}) has n {sc.get('n')}. "
                          f"Change it to {k}.")
    brief = (inputs or {}).get("brief") or {}
    known = [p.get("id") for p in brief.get("parts") or [] if p.get("id")]
    for k, sc in enumerate(scenes, 1):
        pid = str(sc.get("part_id", ""))
        if known and pid not in known:
            errors.append(f"scene {k} (n {sc.get('n')}) has a part_id that is not in the brief: '{pid}'. Write the id "
                          f"of the brief part this scene comes from, one of {', '.join(known)}.")
        elif not known and not re.fullmatch(r"p\d+", pid):
            errors.append(f"scene {k} (n {sc.get('n')}) has a part_id that is not a part id: '{pid}'. Copy the id of "
                          f"the brief part this scene comes from (p1, p2, ...) as is.")
    for k, sc in enumerate(scenes, 1):
        link = str(sc.get("link") or "").strip()
        if sc.get("role") == "case" and not link:
            errors.append(f"scene {k} (role case, part_id {sc.get('part_id')}) has no link. Write in one sentence which "
                          f"claim of the scene right before it this case shows.")
        elif sc.get("role") != "case" and link:
            errors.append(f"scene {k} (role {sc.get('role')}) has a link, but only case scenes have one. Remove its link.")
    for k, m in enumerate(sb.get("materials") or [], 1):
        a = str(m.get("address") or "")
        if not (a.startswith("fs://article/") or a.startswith("fs://theory/")):
            errors.append(f"materials item {k} has an address that is not an article address: '{a}'. Copy an address "
                          f"from the file server lists in the input as is: fs://article/<number> for a case article, "
                          f"fs://theory/<number> for an explanation article. The source document (fs://source/...) "
                          f"does not go in materials.")
    errors += _foreign(sb)
    return errors


_FOREIGN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(storyboard: dict) -> list[str]:
    """Korean, Chinese or Japanese characters, named with the field and the words around them."""
    errors = []
    for where, text in _texts(storyboard):
        for m in list(_FOREIGN.finditer(text))[:3]:
            ctx = text[max(0, m.start() - 20):m.end() + 20]
            errors.append(f"{where} has Korean, Chinese or Japanese characters: '{m.group()}' ('...{ctx}...'). Replace "
                          f"them with an English word of the same meaning; if none fits, drop the word and fix the sentence.")
    return errors[:8]


def _texts(value, path="storyboard"):
    """(field path, text) for every string, e.g. ('storyboard.scenes[scene 3].points[item 2]', '...')."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _texts(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            label = f"scene {v['n']}" if isinstance(v, dict) and "n" in v else f"item {i + 1}"
            yield from _texts(v, f"{path}[{label}]")
