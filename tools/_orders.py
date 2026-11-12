"""Order folders of the Shoestring site (orders/<id>/): the request form and what the code understands of it.

Shared by Sam's tools (update_form, finalize_and_send) and scripts/server.py, so the form is read, checked and
written in one place. Stdlib only.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORDERS = ROOT / "orders"
ORDER_ID_RE = re.compile(r"^ord-[0-9]{8}-[0-9]{3}$")
FORM_FIELDS = ("audience", "length", "depth", "theme")
MIN_MINUTES, MAX_MINUTES = 0.5, 10.0
SITE_URL_ENV = "SHOESTRING_SITE_URL"        # set by scripts/server.py for the `nextop ask sam` it starts

_WORDS = {"half": 0.5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}


def read_json(p: pathlib.Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: pathlib.Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def order_dir(oid: str) -> pathlib.Path | None:
    """orders/<oid>/ when oid is a well-formed order id with a meta.json, else None."""
    if not ORDER_ID_RE.match(str(oid or "")):
        return None
    d = ORDERS / oid
    return d if (d / "meta.json").is_file() else None


def form_of(d: pathlib.Path) -> dict:
    form = read_json(d / "form.json", {}) or {}
    return {k: str(form.get(k) or "") for k in FORM_FIELDS}


def save_form(d: pathlib.Path, fields: dict) -> dict:
    """Merge fields into form.json (and meta.json answers); returns the whole form."""
    form = form_of(d)
    form.update({k: v for k, v in fields.items() if k in FORM_FIELDS})
    write_json(d / "form.json", form)
    meta = read_json(d / "meta.json", {}) or {}
    meta["answers"] = dict(form)
    write_json(d / "meta.json", meta)
    return form


# ------------------------------------------------------------------ form values the code understands
def parse_minutes(text: str) -> float | None:
    """'10 minutes' -> 10, '90 seconds' -> 1.5, 'about 5 min' -> 5, 'an hour' -> 60. None when no amount."""
    t = str(text or "").lower()
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    num = float(m.group(1)) if m else next((v for w, v in _WORDS.items() if re.search(r"\b%s\b" % w, t)), None)
    if num is None:
        if re.search(r"\b(an|a)\s+hour\b", t):
            return 60.0
        return None
    if re.search(r"\b(s|sec|secs|second|seconds)\b", t) or re.search(r"\d\s*s\b", t):
        return num / 60.0
    if re.search(r"\b(h|hr|hrs|hour|hours)\b", t):
        return num * 60.0
    return num


def length_problem(text: str) -> dict | None:
    """A refusal the model can act on, or None when the length is usable."""
    mins = parse_minutes(text)
    if mins is None:
        return {"where": "update_form.length", "now": text,
                "change_to": "an amount of time, e.g. '5 minutes' or '90 seconds'",
                "why": "the crew plans the video from a length in minutes"}
    if not MIN_MINUTES <= mins <= MAX_MINUTES:
        return {"where": "update_form.length", "now": text,
                "change_to": "ask the client for a length between 30 seconds and 10 minutes; save only a length the client says",
                "why": "the crew makes videos of 0.5 to 10 minutes"}
    return None


def depth_value(text: str) -> str:
    """Free-text depth -> the flow's depth field (overview / key_points / explained / in_depth, '' = PD decides)."""
    t = str(text or "").lower()
    if "overview" in t or "big picture" in t or "big-picture" in t:
        return "overview"
    if "key" in t or "main idea" in t or "essentials" in t:
        return "key_points"
    if "comprehensive" in t or "in depth" in t or "in-depth" in t or "every" in t or "full" in t or "thorough" in t:
        return "in_depth"
    if "explain" in t or "detailed" in t:
        return "explained"
    return ""
