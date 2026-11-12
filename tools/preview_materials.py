"""Renders materials (charts, formulas, steps, contents, text cards, photos) as still pictures, the way the slide
builder would place them, and shows them to the maker so it can check overlap, clipping, text size and that the
picture says what it should. Every material shown here is remembered, so the maker's checker can refuse a save
that holds a material nobody looked at (or one changed after it was looked at)."""

import hashlib
import json
import pathlib
import subprocess

from functions._common import write_json
from functions.render_part import CLI, REMOTION, _ensure_bundle, _Files, _localize, _render_slots

NAME = "preview_materials"
DESC = ("Render up to 6 of your materials as pictures and look at them before saving. Give each material exactly "
        "as you will save it: [{id, template, values}] for charts, formulas, steps, contents and text cards, or "
        "[{id, file}] for photos. A material used in several cuts is looked at once. Check: shapes or text covering "
        "each other, anything cut off, text too small or too large, and that the picture shows what the cut needs. "
        "Fix, then look again. Every material you save must have been looked at in its final form.")
SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 6, "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "template": {"type": "string"}, "values": {"type": "object"},
                       "file": {"type": "string"}},
        "required": ["id"]}},
        "theme": {"type": "string"}},
    "required": ["items"],
}
SEEN = pathlib.Path(__file__).resolve().parents[1] / ".cache" / "previewed"
FPS = 30
SECONDS = 3.0           # each material gets 3 s; the picture is taken at 85 % (animations have settled)


def fingerprint(cand: dict) -> str:
    """What makes a material look the way it does: the photo file, or the template and its values."""
    if cand.get("file"):
        p = pathlib.Path(cand["file"])
        key = {"file": str(p.resolve()) if p.exists() else str(p), "size": p.stat().st_size if p.is_file() else -1}
    else:
        key = {"template": cand.get("template"), "values": cand.get("values") or {}}
    return hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


def was_seen(cand: dict) -> bool:
    return (SEEN / fingerprint(cand)).is_file()


def to_layers(cand: dict) -> list[dict]:
    """The same template -> screen mapping the slide builder follows (workers/editor/mission.md)."""
    if cand.get("file"):
        return [{"type": "PhotoCard", "props": {"src": cand["file"]}}]
    t, v = cand.get("template"), dict(cand.get("values") or {})
    simple = {"numbers": "NumberCard", "bar": "BarChart", "line": "LineChart", "curve": "Curve", "scatter": "Scatter",
              "steps": "Steps", "route": "RouteMap"}
    if t in simple:
        return [{"type": simple[t], "props": v}]
    if t == "formula":
        return [{"type": "Formula", "props": {"steps": v.get("lines") or [], "label": v.get("label", "")}}]
    if t == "text":
        return [{"type": "BigText", "props": {"lines": [str(x) for x in v.get("lines") or []]}}]
    return []


def _sheet(tiles: list[tuple[str, str]], out: pathlib.Path) -> bytes:
    """Two pictures per row at 800x450 each: large enough to see overlap and small text."""
    from PIL import Image, ImageDraw, ImageFont
    w, h, bar, cols = 800, 450, 28, 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, (h + bar) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    for k, (label, png) in enumerate(tiles):
        x, y = (k % cols) * w, (k // cols) * (h + bar)
        draw.rectangle([x, y, x + w, y + bar], fill="#222222")
        draw.text((x + 8, y + 4), label, fill="white", font=font)
        sheet.paste(Image.open(png).convert("RGB").resize((w, h)), (x, y + bar))
        draw.rectangle([x, y + bar, x + w - 1, y + bar + h - 1], outline="#999999")
    sheet.save(out, quality=85)
    return out.read_bytes()


def run(ctx, args):
    if not CLI.is_file():
        return {"error": "Remotion is not installed"}
    items = args["items"][:6]
    out = pathlib.Path(ctx["files_dir"]) / "material_preview"
    out.mkdir(parents=True, exist_ok=True)
    layers, jobs, labels, problems, shown = [], [], [], [], []
    t = 0.0
    for cand in items:
        lys = to_layers(cand)
        if not lys:
            problems.append(f"{cand.get('id')}: unknown template {cand.get('template')!r} and no file")
            continue
        if cand.get("file") and not pathlib.Path(cand["file"]).is_file():
            problems.append(f"{cand.get('id')}: file does not exist")
            continue
        for ly in lys:
            layers.append({**ly, "start": round(t, 3), "end": round(t + SECONDS, 3)})
        # one file per material, named by its id: looking again overwrites it, so the folder holds the latest only
        png = out / f"{''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in str(cand.get('id')))}.png"
        jobs.append({"frame": int((t + SECONDS * 0.85) * FPS), "out": str(png)})
        labels.append(f"{cand.get('id')}  {cand.get('template') or 'photo'}")
        shown.append(cand)
        t += SECONDS
    if not jobs:
        return {"error": "; ".join(problems) or "nothing to show"}
    props = {"page": "materials", "duration": round(t, 3), "width": 1280, "height": 720,
             "theme": args.get("theme") or "shoestring", "print": True,
             "background": [{"style": "plain", "start": 0, "end": round(t, 3)}], "layers": layers, "audio": []}
    build = _ensure_bundle()
    with _Files() as files:
        missing = []
        served = _localize(props, files, missing)
        if missing:
            return {"error": f"these files do not exist: {missing[:5]}"}
        write_json(out / "props.json", served)
        write_json(out / "jobs.json", jobs)
        with _render_slots:
            r = subprocess.run(["node", "stills.mjs", str(build), str(out / "props.json"), str(out / "jobs.json")],
                               cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=600)
    done = [(lab, j["out"], c) for lab, j, c in zip(labels, jobs, shown) if pathlib.Path(j["out"]).is_file()]
    if r.returncode != 0 or not done:
        return {"error": f"preview render failed: {(r.stderr or r.stdout)[-500:]}"}
    SEEN.mkdir(parents=True, exist_ok=True)
    for _, _, c in done:
        (SEEN / fingerprint(c)).write_text(str(c.get("id")), encoding="utf-8")
    data = _sheet([(lab, png) for lab, png, _ in done], out / "sheet.jpg")
    res = {"pictures": [lab for lab, _, _ in done],
           "note": "One picture per material as it would appear on screen. If something overlaps, is cut off or is "
                   "hard to read, change the values (shorter labels, fewer items, box instead of circle, other "
                   "positions) and look again. A changed material must be looked at again before saving.",
           "_images": [{"address": "materials:" + ",".join(str(c.get('id')) for _, _, c in done),
                        "mime": "image/jpeg", "data": data}]}
    if problems:
        res["problems"] = problems
    return res
