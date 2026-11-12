RULES = [
    "cuts lists every content cut of the scene (every visuals cut that is not the title or end card) exactly once, in scene order, and no other cut.",
    "Every content cut has exactly one generated picture (never empty).",
    "A material id is gn-<cut_id>-1 with the first cut it is listed in (e.g. gn-c03-1). One picture may be listed in several cuts; then it keeps that id and is the identical object in each of them.",
    "Every material must have been looked at with preview_materials in the exact form you save; a material changed after its preview must be looked at again.",
    "file must be a picture file generate_image returned (inside the project folder).",
    "prompt is the English prompt the picture was generated from.",
    "Write English only: no Korean, Chinese or Japanese characters in why_fit or prompt.",
]

from tools.preview_materials import was_seen
from tools._cuts import check_report
import pathlib

PROJECT = pathlib.Path(__file__).resolve().parents[2]
PICTURES = (".png", ".jpg", ".jpeg", ".webp")
OUT = "gen_candidates"


def check(outputs, inputs=None):
    errors, materials = check_report(outputs[OUT], inputs, "gn", allow_null=False)
    for m in materials:
        mid = m.get("id")
        path = pathlib.Path(m.get("file") or "")
        if not path.is_file() or path.suffix.lower() not in PICTURES:
            errors.append(f"{mid}: file {m.get('file')!r} is not a picture file; write the file generate_image returned")
            continue
        try:
            path.resolve().relative_to(PROJECT)
        except ValueError:
            errors.append(f"{mid}: file {path} is outside the project; write the file generate_image returned")
        if not was_seen(m):
            errors.append(f"{mid}: look at it with preview_materials first (in the exact form you save; "
                          f"a material changed after its preview must be looked at again)")
        if not str(m.get("prompt") or "").strip():
            errors.append(f"{mid}: prompt is empty; write the prompt you gave generate_image for this picture")
    bad = _foreign({"c": [(m.get("why_fit", ""), m.get("prompt", "")) for m in materials]})
    if bad:
        errors.append("write English only: remove these Korean/Chinese/Japanese characters " + ", ".join(bad))
    return errors


_FOREIGN = __import__("re").compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters in why_fit and prompt."""
    import json as _json
    return sorted(set(_FOREIGN.findall(_json.dumps(value, ensure_ascii=False))))[:5]
