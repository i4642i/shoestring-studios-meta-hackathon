"""Sam's post-check (assigned task): the order sheet and the PDF hand-off are copies of the run input.

The program knows every value (the same rules the old intake function applied), so it computes the expected
value of each field and refuses any difference, naming the field, what was saved and the exact value to save.
Run input values that are wrong in themselves (length out of range, missing title, missing files) are reported
as problems of the order; Sam cannot fix them.
"""

import json
import pathlib

RULES = [
    "request.text is the run input order, word for word (spaces at the start and end do not count; empty when it is empty).",
    "request.audience and request.theme are the run input audience and theme as given (empty when empty).",
    "request.length_s is the run input length_min times 60, rounded to whole seconds.",
    "request.depth is the run input depth as given (empty when empty).",
    "request.voice is the run input voice; when it is empty: final if order contains 'final', 'natural voice' or "
    "'deliver', else draft.",
    "request.title_card is {title: video_title, subtitle: subtitle, channel: channel, logo: logo} and "
    "request.end_card is {message: closing, channel: channel, logo: logo}, all from the run input as given.",
    "pdf.path is the run input pdf exactly; pdf.title is the run input book_title (empty when empty).",
]

ROOT = pathlib.Path(__file__).resolve().parents[2]
FINAL_WORDS = ("final", "natural voice", "deliver")
DEPTHS = ("", "overview", "key_points", "explained", "in_depth")


def _s(inputs: dict, key: str) -> str:
    return str(inputs.get(key) or "").strip()


def _path(value: str) -> pathlib.Path:
    p = pathlib.Path(value)
    return p if p.is_absolute() else ROOT / p


def expected(inputs: dict) -> tuple[dict, list[str]]:
    """The order sheet and PDF hand-off the run input gives, and the problems of the run input itself."""
    problems = []
    text = _s(inputs, "order")
    try:
        minutes = float(inputs.get("length_min"))
    except (TypeError, ValueError):
        minutes = None
        problems.append(f"the run input length_min is {inputs.get('length_min')!r}, not a number of minutes (0.5-10)")
    if minutes is not None and not 0.5 <= minutes <= 10:
        problems.append(f"the run input length_min is {minutes:g}; it must be between 0.5 and 10 minutes")
    for k in ("video_title", "closing"):
        if not _s(inputs, k):
            problems.append(f"the run input {k} is empty (first slide title / last slide closing message)")
    logo = _s(inputs, "logo")
    if logo and not _path(logo).is_file():
        problems.append(f"the run input logo file is not found: {logo}")
    depth = _s(inputs, "depth")
    if depth not in DEPTHS:
        problems.append(f"the run input depth is {depth!r}; it must be overview, key_points, explained or in_depth")
    voice = _s(inputs, "voice") or ("final" if any(w in text for w in FINAL_WORDS) else "draft")
    if voice not in ("draft", "final"):
        problems.append(f"the run input voice is {voice!r}; it must be draft or final")
    pdf = str(inputs.get("pdf") or "")
    if not pdf.strip():
        problems.append("the run input pdf is empty")
    elif not _path(pdf.strip()).is_file() or _path(pdf.strip()).suffix.lower() != ".pdf":
        problems.append(f"the run input pdf is not a PDF file: {pdf}")
    channel = _s(inputs, "channel")
    want = {
        "request": {
            "text": text, "audience": _s(inputs, "audience"),
            "length_s": int(round(minutes * 60)) if minutes is not None else None, "depth": depth,
            "theme": _s(inputs, "theme"), "voice": voice,
            "title_card": {"title": _s(inputs, "video_title"), "subtitle": _s(inputs, "subtitle"),
                           "channel": channel, "logo": logo},
            "end_card": {"message": _s(inputs, "closing"), "channel": channel, "logo": logo}},
        "pdf": {"path": pdf, "title": _s(inputs, "book_title")},
    }
    return want, problems


def _diff(where: str, got, want, errors: list[str]) -> None:
    if isinstance(want, dict):
        got = got if isinstance(got, dict) else {}
        for k, v in want.items():
            _diff(f"{where}.{k}", got.get(k), v, errors)
        extra = sorted(set(got) - set(want))
        if extra:
            errors.append(f"{where} has fields the order sheet does not have: {extra}; remove them")
        return
    if want is None:
        return
    if isinstance(want, str) and isinstance(got, str) and where != "pdf.path":
        same = got.strip() == want
    else:
        same = got == want
    if not same:
        errors.append(f"{where} is {json.dumps(got, ensure_ascii=False)}; save exactly "
                      f"{json.dumps(want, ensure_ascii=False)} (copied from the run input)")


def check(outputs, inputs=None):
    want, problems = expected(inputs or {})
    if problems:            # the run input itself is wrong: no save can pass, the studio must correct the order
        return [f"order problem, not yours to fix: {p}. The order cannot be handed over as it is; the studio must "
                f"correct the run input and run it again." for p in problems]
    errors = []
    for terminal in ("request", "pdf"):
        _diff(terminal, outputs.get(terminal), want[terminal], errors)
    return errors
