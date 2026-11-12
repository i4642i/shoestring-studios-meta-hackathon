RULES = [
    "cuts lists every content cut of the scene (every visuals cut that is not the title or end card) exactly once, in scene order, and no other cut.",
    "Every content cut has exactly one material (never empty); when no chart, number, formula, steps or route fits a cut, its material is a text card.",
    "A material id is ch-<cut_id>-1 with the first cut it is listed in (e.g. ch-c03-1). One material may be listed in several cuts; then it keeps that id and is the identical object in each of them.",
    "Every material must have been looked at with preview_materials in the exact form you save; a material changed after its preview must be looked at again.",
    "template is one of: numbers, bar, line, curve, scatter, formula, steps, route, text.",
    "Required values: numbers needs 1-4 items; bar needs 1-6 bars; line needs points; curve needs curves or dist; scatter needs points; formula needs 1-3 lines; steps needs 2-6 items; route needs 1-8 stops; text needs 1-3 lines.",
    "text lines are 1 to 3 non-empty strings.",
    "Every chart and formula material needs refs (the source address and the quote the values come from); text, steps and route need none.",
    "Every formula line must be valid LaTeX.",
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the output.",
]

from tools.preview_materials import was_seen
from tools._cuts import check_report
import json
import pathlib
import subprocess

OUT = "chart_candidates"
PREFIX = "ch"
NEED = {"numbers": ["items"], "bar": ["bars"], "line": ["points"], "curve": ["curves|dist"], "scatter": ["points"],
        "formula": ["lines"], "steps": ["items"], "route": ["stops"], "text": ["lines"]}
REFS_NEEDED = ["numbers", "bar", "line", "curve", "scatter", "formula"]
REMOTION = pathlib.Path(__file__).resolve().parents[2] / "remotion"


def _katex(lines):
    try:
        r = subprocess.run(["node", str(REMOTION / "katex_check.js")], input=json.dumps(lines, ensure_ascii=False),
                           cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", timeout=60)
        return json.loads(r.stdout or "[]")
    except Exception:
        return []


def check(outputs, inputs=None):
    errors, materials = check_report(outputs[OUT], inputs, PREFIX, allow_null=False)
    for m in materials:
        errors += _material(m)
    bad = _foreign(outputs[OUT])
    if bad:
        errors.append("write English only: remove these Korean/Chinese/Japanese characters " + ", ".join(bad))
    return errors


def _material(m) -> list[str]:
    errors = []
    mid = m.get("id")
    t = m.get("template", "")
    if t not in NEED:
        return [f"{mid}: template must be one of {sorted(NEED)}"]
    v = m.get("values") or {}
    for key in NEED[t]:
        alts = key.split("|")
        if not any(v.get(a) not in (None, "", [], {}) for a in alts):
            errors.append(f"{mid}: a {t} needs values.{' or values.'.join(alts)}")
    if t in REFS_NEEDED and not m.get("refs"):
        errors.append(f"{mid}: a {t} needs refs (the source address and the quote the values come from)")
    if t == "steps" and isinstance(v.get("items"), list) and not 2 <= len(v["items"]) <= 6:
        n = len(v["items"])
        how = f"merge neighbouring items so there are {n - 6} fewer (6 at most)" if n > 6 else "write at least two steps"
        errors.append(f"{mid}: steps has {n} items; the range is 2-6. {how[0].upper() + how[1:]}, then preview again.")
    if t == "numbers" and isinstance(v.get("items"), list) and len(v["items"]) > 4:
        errors.append(f"{mid}: numbers has {len(v['items'])} items; 4 at most. Keep the ones the line says, then preview again.")
    if t == "bar" and isinstance(v.get("bars"), list) and len(v["bars"]) > 6:
        errors.append(f"{mid}: bar has {len(v['bars'])} bars; 6 at most. Keep the ones the line compares, then preview again.")
    if t == "route" and isinstance(v.get("stops"), list) and len(v["stops"]) > 8:
        errors.append(f"{mid}: route has {len(v['stops'])} stops; 8 at most. Merge or shorten the contents, then "
                      f"preview again.")
    if t in ("formula", "text") and v.get("lines") and not isinstance(v["lines"], list):
        errors.append(f"{mid}: values.lines must be a list of " + ("LaTeX lines" if t == "formula" else "short lines"))
    if t == "formula" and isinstance(v.get("lines"), list):
        if len(v["lines"]) > 3:
            errors.append(f"{mid}: formula has {len(v['lines'])} lines; 3 at most. Keep the key defining formula "
                          f"first and drop the rest, then preview again.")
        for e in _katex([str(x) for x in v["lines"]]):
            errors.append(f"{mid}: formula line {e['i'] + 1} is not valid LaTeX: {e['error']}")
    if t == "text" and isinstance(v.get("lines"), list) and v["lines"]:
        lines = v["lines"]
        if not 1 <= len(lines) <= 3:
            errors.append(f"{mid}: a text card has {len(lines)} lines; write 1 to 3 short lines.")
        if any(not isinstance(x, str) or not x.strip() for x in lines):
            errors.append(f"{mid}: every text line must be a non-empty string (words from the cut's line).")
    if not was_seen(m):
        errors.append(f"{mid}: look at it with preview_materials first (in the exact form you save; "
                      f"a material changed after its preview must be looked at again)")
    return errors


_FOREIGN = __import__("re").compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters anywhere in the output (LaTeX and file paths included)."""
    import json as _json
    return sorted(set(_FOREIGN.findall(_json.dumps(value, ensure_ascii=False))))[:5]
