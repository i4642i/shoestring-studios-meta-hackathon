"""Renders still pictures of a draft timeline (every main layer of every cut, in its settled state) and shows
them to the slide builder as one contact sheet, so it can check overlap, balance, text size and clipping."""

import json
import pathlib
import subprocess

from functions._common import write_json
from functions.render_part import CLI, REMOTION, _ensure_bundle, _Files, _localize, _render_slots, _stretch
from tools._layout import THRESHOLDS, active, analyze
from tools._layouts import cover_seconds, place_timeline_cuts
from tools._overflow import measure_layer

NAME = "preview_slides"
DESC = ("Render your draft timeline as still pictures and look at them before saving. Give the same object you "
        "will save as timeline ({part_id, cuts: [{cut_id, layout, layers, background}]}) and optionally seconds per cut. "
        "You get one picture per main layer (labelled cut and time), for every HtmlSlide a measured list of what does "
        "not fit (off the screen, sticking out of its box, cut off), and for every cut a measured list of layout "
        "problems ('layout', measured on the rendered screen of all layers together). Targets of a good 1280x720 "
        "screen: " + THRESHOLDS + ". Also look for anything the numbers miss (balance, wrong emphasis).")
SCHEMA = {
    "type": "object",
    "properties": {"timeline": {"type": "object"},
                   "seconds": {"type": "object", "description": "cut_id -> cut length in seconds (optional)"},
                   "theme": {"type": "string"}},
    "required": ["timeline"],
}
MAIN = {"BigText", "PhotoCard", "Formula", "BarChart", "LineChart", "Steps", "NumberCard", "TitleCard", "EndCard",
        "Curve", "Scatter", "Diagram", "RouteMap", "HtmlSlide", "SectionCard"}
FPS = 30
MAX_TILES = 12
MEASURE_JS = pathlib.Path(__file__).with_name("_stills_measure.mjs")


def _sheet(tiles: list[tuple[str, str]], out: pathlib.Path) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    w, h, bar, cols = 640, 360, 26, 2
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, (h + bar) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for k, (label, png) in enumerate(tiles):
        x, y = (k % cols) * w, (k // cols) * (h + bar)
        draw.rectangle([x, y, x + w, y + bar], fill="#222222")
        draw.text((x + 8, y + 4), label, fill="white", font=font)
        im = Image.open(png).convert("RGB").resize((w, h))
        sheet.paste(im, (x, y + bar))
        draw.rectangle([x, y + bar, x + w - 1, y + bar + h - 1], outline="#999999")
    sheet.save(out, quality=82)
    return out.read_bytes()


def section_cover(ctx: dict) -> dict:
    """{cut_id: seconds the section cover hides that cut's screen} for this scene (copy number of the block), from
    the split's pieces; {} when the scene has no section cover or the records cannot be read."""
    try:
        run_dir = pathlib.Path(ctx["project"]) / "runs" / str(ctx["run_id"])
        k = int(str(ctx.get("block") or "").partition("@")[2] or 0)
    except (KeyError, ValueError, TypeError):
        return {}
    if not k:
        return {}
    for a in sorted((run_dir / "blocks" / "split").glob("attempt-*/pieces.json"), reverse=True):
        try:
            pieces = json.loads(a.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if k > len(pieces):
            return {}
        piece = pieces[k - 1] or {}
        sc = (piece.get("visuals") or {}).get("section_card") or {}
        if not sc.get("cut_id"):
            return {}
        tm = {c.get("cut_id"): c for c in (piece.get("timing") or {}).get("cuts") or []}
        secs = float((tm.get(sc["cut_id"]) or {}).get("seconds") or 6.0) + 0.4
        return {sc["cut_id"]: cover_seconds(secs)}
    return {}


def _layout_report(path: pathlib.Path, props: dict, spans: list, cover: dict | None = None) -> tuple:
    """Per cut: layout problems and the measured values (from the measurements taken while rendering the stills)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "could not measure the layout (no measurements from the renderer)", {}
    probs, measured = {}, {}
    for t0, t1, _, cid in spans:
        mine = [(m, *active(props, m["frame"])) for m in raw
                if "layers" in m and t0 * FPS <= m["frame"] < t1 * FPS]
        if not mine:
            continue
        got, info = analyze(mine, t0, float((cover or {}).get(cid) or 0))
        measured[str(cid)] = info
        if got:
            probs[str(cid)] = got
    return probs, measured


def run(ctx, args):
    tl = args["timeline"]
    if not isinstance(tl, dict) or not isinstance(tl.get("cuts"), list) or not tl["cuts"]:
        return {"error": "timeline must be {part_id, cuts: [{cut_id, layers}]} - the object you will save"}
    if not CLI.is_file():
        return {"error": "Remotion is not installed"}
    secs = args.get("seconds") or {}
    out = pathlib.Path(ctx["files_dir"]) / "preview"
    out.mkdir(parents=True, exist_ok=True)
    background, layers, jobs, labels, t, spans = [], [], [], [], 0.0, []
    theme = args.get("theme") or "shoestring"
    placed = place_timeline_cuts(tl["cuts"], theme)     # layers in a layout slot get their box on the screen
    for c in tl["cuts"]:
        lys = placed.get(c.get("cut_id")) or c.get("layers") or []
        dur = float(secs.get(c.get("cut_id"), 0) or 0) or max([float(x.get("end", 0)) for x in lys] + [3.0])
        for b in c.get("background") or [{"style": "plain", "start": 0, "end": dur}]:
            background.append({**b, "start": t + float(b.get("start", 0)), "end": t + min(dur, float(b.get("end", dur)))})
        mains, mine = [], []
        for li, ly in enumerate(lys):      # "_ref": which layer of which cut (the decision maps measurements back)
            s, e = float(ly.get("start", 0)), min(dur, float(ly.get("end", dur)))
            mine.append({**ly, "_ref": [c.get("cut_id"), li], "start": round(t + s, 3), "end": round(t + max(e, s + 0.2), 3)})
            if ly.get("type") in MAIN:
                mains.append((s, e, ly["type"]))
        spans.append((t, t + dur, mine, c.get("cut_id")))
        for s, e, typ in mains:
            if len(jobs) >= MAX_TILES:
                break
            mid = t + (s + e) / 2
            png = out / f"{c.get('cut_id', 'cut')}_{len(jobs):02d}.png"
            jobs.append({"frame": int(mid * FPS), "out": str(png), "measure": True})
            labels.append(f"{c.get('cut_id')}  {s:.1f}-{e:.1f}s  {typ}")
        t += dur
    layers = _stretch(spans)
    for ly in layers:                     # one more picture for every focus change (cue) of a scene's screen
        for cue in ly.get("cues") or []:
            if len(jobs) >= MAX_TILES:
                break
            at = ly["start"] + cue["at"] + 0.8
            png = out / f"cue_{len(jobs):02d}.png"
            jobs.append({"frame": int(at * FPS), "out": str(png), "measure": True})
            labels.append(f"{ly['type']} cue at {cue['at']:.1f}s {json.dumps(cue['props'], ensure_ascii=False)[:40]}")
    tiles = len(jobs)
    for t0, t1, _, cid in spans:          # every cut is measured, also one without a picture of its own
        if not any(t0 * FPS <= j["frame"] < t1 * FPS for j in jobs):
            jobs.append({"frame": int((t0 + t1) / 2 * FPS), "out": str(out / f"{cid}_m.png"), "measure": True})
    props = {"page": str(tl.get("part_id") or "preview"), "duration": round(t, 3), "width": 1280, "height": 720,
             "theme": args.get("theme") or "shoestring", "print": True, "background": background, "layers": layers, "audio": []}
    build = _ensure_bundle()
    with _Files() as files:
        missing = []
        served = _localize(props, files, missing)
        if missing:
            return {"error": f"these files do not exist: {missing[:5]}"}
        write_json(out / "props.json", served)
        write_json(out / "jobs.json", jobs)
        (out / "measures.json").unlink(missing_ok=True)
        with _render_slots:
            r = subprocess.run(["node", str(MEASURE_JS), str(REMOTION), str(build), str(out / "props.json"),
                                str(out / "jobs.json"), str(out / "measures.json")],
                               cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=600)
    done = [(lab, j["out"]) for lab, j in zip(labels, jobs[:tiles]) if pathlib.Path(j["out"]).is_file()]
    if r.returncode != 0 or not done:
        return {"error": f"preview render failed: {(r.stderr or r.stdout)[-500:]}"}
    data = _sheet(done, out / "sheet.jpg")
    overflow = {}
    for c in tl["cuts"]:
        for ly in placed.get(c.get("cut_id")) or c.get("layers") or []:
            if ly.get("type") == "HtmlSlide":
                got = [x for x in measure_layer(ly, args.get("theme") or "shoestring") if not x.startswith("could not measure")]
                if got:
                    overflow[str(c.get("cut_id"))] = got
    cover = args.get("cover") if isinstance(args.get("cover"), dict) else section_cover(ctx)
    layout, measured = _layout_report(out / "measures.json", props, spans, cover)
    clean = not overflow and isinstance(layout, dict) and not layout
    return {"pictures": [lab for lab, _ in done],
            "overflow": overflow or ("everything fits (measured in a browser)" if clean else
                                     "nothing sticks out (measured in a browser); see 'layout'"),
            "layout": layout if layout or not isinstance(layout, dict) else "every cut meets the layout targets (measured)",
            "measured": measured,
            "note": "One picture per main layer, in its final placed state. 'overflow' and 'layout' are measured, not "
                    "guessed: fix every item in them (bigger box, shorter text, larger or smaller font within the rules, "
                    "fewer elements, moved or enlarged content). Targets: " + THRESHOLDS + ". Then save (or preview "
                    "once more).",
            "_images": [{"address": f"preview:{tl.get('part_id')}", "mime": "image/jpeg", "data": data}]}
