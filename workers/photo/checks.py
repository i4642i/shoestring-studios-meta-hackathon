RULES = [
    "cuts lists every content cut of the scene (every visuals cut that is not the title or end card) exactly once, in scene order, and no other cut.",
    "Each content cut has at most one photo: material is one photo, or null when no photo fits (no reason written).",
    "A material id is ph-<cut_id>-1 with the first cut it is listed in (e.g. ph-c03-1). One photo may be listed in several cuts; then it keeps that id and is the identical object in each of them.",
    "Every material must have been looked at with preview_materials in the exact form you save; a material changed after its preview must be looked at again.",
    "file must be a local file a tool returned.",
    "A web photo (kind web) needs source_url (the image_url you fetched, starting with http).",
    "A source figure (kind source_figure) needs ref (its fs://source/... address).",
    "Write English only: no Korean, Chinese or Japanese characters in why_fit.",
]

from tools.preview_materials import was_seen
from tools._cuts import check_report
import pathlib

OUT = "photo_candidates"


def check(outputs, inputs=None):
    errors, materials = check_report(outputs[OUT], inputs, "ph", allow_null=True)
    for m in materials:
        mid = m.get("id")
        if not was_seen(m):
            errors.append(f"{mid}: look at it with preview_materials first (in the exact form you save; "
                          f"a material changed after its preview must be looked at again)")
        if not pathlib.Path(m.get("file") or "").is_file():
            errors.append(f"{mid}: file must be a local file a tool returned")
        if m.get("kind") == "web" and not (m.get("source_url") or "").startswith("http"):
            errors.append(f"{mid}: a web photo needs source_url (the image_url you fetched)")
        if m.get("kind") == "source_figure" and not (m.get("ref") or "").startswith("fs://"):
            errors.append(f"{mid}: a source figure needs ref (its fs://source/... address)")
    bad = _foreign({"c": [m.get("why_fit", "") for m in materials]})
    if bad:
        errors.append("write English only: remove these Korean/Chinese/Japanese characters " + ", ".join(bad))
    return errors


_FOREIGN = __import__("re").compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters anywhere in the output (LaTeX and file paths included)."""
    import json as _json
    return sorted(set(_FOREIGN.findall(_json.dumps(value, ensure_ascii=False))))[:5]
