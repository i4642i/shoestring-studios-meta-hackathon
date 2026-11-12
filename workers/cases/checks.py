RULES = [
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the output.",
]

def check(outputs):
    errors = []
    bad = _foreign(outputs["cases"])
    if bad:
        errors.append("write English only: remove these Korean/Chinese/Japanese characters " + ", ".join(bad))
    return errors


_FOREIGN = __import__("re").compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters anywhere in the output (LaTeX and file paths included)."""
    import json as _json
    return sorted(set(_FOREIGN.findall(_json.dumps(value, ensure_ascii=False))))[:5]
