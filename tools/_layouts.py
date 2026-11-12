"""The layout library (layouts/layouts.json) and the arithmetic around it: which material kind a slot accepts, how
well a material fills a slot ("slot fit"), how large its text ends up, and where the renderer draws a layer that
sits in a slot. A helper, not a tool (the file name starts with _). People add layouts; programs only read them.

Slot fit (the share of the slot's area the material covers when scaled to fit the slot, aspect kept):
- photos: the picture's pixel size (read from the file).
- charts, formulas, routes (contents), steps, numbers: the template is rendered alone on a 1280x720 screen in the
  browser (the same Remotion page as the video) and its content box is measured (union of its visible texts,
  shapes and pictures). The measurement is cached by template + values + theme (.cache/content_box/).
- plain lines (text the designer writes): they are drawn as HTML by the slide builder, so their shape is flexible.
  For the fit they are rendered as big text and measured the same way; the number that matters for them is the text
  size, not the area.
layouts.json still names the slot kinds quote, definition, keyword, timeline and case_card; no worker makes those
materials any more, so those kinds never occur (steps and routes use the kind name "diagram").
The scale k = min(slot w / content w, slot h / content h, K_MAX); fit = (content w * k) * (content h * k) / slot area;
the smallest text after scaling = smallest measured text px * k.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYOUTS = ROOT / "layouts" / "layouts.json"
CACHE = ROOT / ".cache" / "content_box"
W, H = 1280, 720
FPS = 30
K_MAX = 1.25                 # a template is never drawn larger than 1.25x its full-screen size
FIT_OK = 0.70                # slot fit at or above this: the material suits the slot
TEXT_OK = 20.0               # smallest text px at or above this: readable
TEXT_MIN = 16.0              # below this the text is longer than the slot can hold (redesign)
SPECIAL = ("title", "end")   # cuts drawn by TitleCard / EndCard, not by a library layout
COVER = "L13"                # the section cover: drawn whole by SectionCard

# material template -> the kind names that layouts.json "accepts" lists use
KIND = {"bar": "chart", "line": "chart", "curve": "chart", "scatter": "chart", "formula": "formula",
        "numbers": "numbers", "route": "diagram", "steps": "diagram"}
# the slot kinds a material of this project can have, with the names used in messages
KIND_NAMES = {"photo": "photo", "chart": "chart", "formula": "formula", "numbers": "numbers",
              "diagram": "steps or contents", "lines": "text (lines)", "figure": "figure"}
KIND_KO = KIND_NAMES         # old name, kept for older importers
# material template -> the screen template the slide builder uses for it in a slot (others: HtmlSlide)
SCREEN = {"bar": "BarChart", "line": "LineChart", "curve": "Curve", "scatter": "Scatter", "formula": "Formula",
          "route": "RouteMap", "steps": "Steps"}
# screen templates drawn on a virtual 1280x720 screen and scaled into their slot by their measured content box
FITTED = {"BigText", "Formula", "BarChart", "LineChart", "Steps", "NumberCard", "Curve", "Scatter",
          "RouteMap"}
STRIPS = {"Kicker", "SourceTag", "Caption", "Sparkles"}
WHOLE = {"TitleCard", "EndCard", "SectionCard"}


# ------------------------------------------------------------------ library

def library() -> dict:
    """{"frame": {...}, "layouts": {id: layout}} (read fresh: people may edit the file between runs)."""
    d = json.loads(LAYOUTS.read_text(encoding="utf-8"))
    return {"frame": d.get("frame") or {}, "layouts": {x["id"]: x for x in d.get("layouts") or []}}


def slot_of(layout: dict, slot_id: str) -> dict | None:
    return next((s for s in layout.get("slots") or [] if s["id"] == slot_id), None)


def layout_ids() -> list[str]:
    return list(library()["layouts"])


def usable_layout_ids() -> list[str]:
    """Library layouts a designer may choose: not the section cover, and every slot takes a material kind made here
    (L12's main slot takes only quotes and definitions, which no worker makes)."""
    return [lid for lid, x in library()["layouts"].items() if lid != COVER
            and all(any(a in KIND_NAMES for a in s.get("accepts") or []) for s in x.get("slots") or [])]


# ------------------------------------------------------------------ material capacity (2026-11-11)
# A content cut takes 1-3 materials (candidate ids ph-, gn-, ch-); text the designer writes (use "lines") is no
# material. A layout's material capacity is counted over its material slots (every slot whose kind is not "text"):
# a slot shown together (order "together") holds exactly 1; a sequence slot (order "sequence") holds its materials
# one after another, at least 1 and as many as the cut's limit leaves after the layout's other material slots.
# So L10 (one sequence slot) holds 1-3, L11 (main together + side sequence) holds 2-3 (1 fixed + 1-2 in sequence).

MIN_MATERIALS, MAX_MATERIALS = 1, 3


def material_slots(layout: dict) -> list[dict]:
    """The slots that take candidate materials (kind visual, number or card; never text)."""
    return [s for s in layout.get("slots") or [] if s.get("kind") != "text"]


def material_range(layout: dict) -> tuple[int, int]:
    """(least, most) candidate materials this layout holds."""
    mats = material_slots(layout)
    fixed = sum(1 for s in mats if s.get("order") != "sequence")
    seq = sum(1 for s in mats if s.get("order") == "sequence")
    lo = fixed + seq
    return lo, (max(lo, MAX_MATERIALS) if seq else lo)


def sequence_max(layout: dict) -> int:
    """How many materials one sequence slot of this layout may hold (0 when it has none)."""
    lo, hi = material_range(layout)
    return 1 + hi - lo if any(s.get("order") == "sequence" for s in material_slots(layout)) else 0


def capacity_say(layout: dict) -> str:
    """'1', '2-3', ... (the material capacity in words)."""
    lo, hi = material_range(layout)
    return str(lo) if lo == hi else f"{lo}-{hi}"


def holds(layout: dict, n: int) -> bool:
    lo, hi = material_range(layout)
    return lo <= n <= hi


def material_count(fill: list) -> int:
    """The candidate materials of a cut's fill (entries whose use is not "lines")."""
    return sum(1 for f in fill or [] if isinstance(f, dict) and f.get("use") and f.get("use") != "lines")


def id_kind(cand_id: str) -> str | None:
    """The material kind a candidate id tells (photos ph-, generated pictures gn-); None for ch- (any template)."""
    return "photo" if str(cand_id).startswith(("ph-", "gn-")) else None


def layouts_for(n: int, exclude: tuple = (), kinds: list | None = None) -> list[str]:
    """The choosable layouts whose material capacity holds n materials, in library order. kinds: the known kinds of
    the cut's materials (e.g. ["photo"]); when every material's kind is known, every material slot of the layout
    must accept one of them (so a photo cut is never sent to L03's number slot)."""
    lays = library()["layouts"]
    known = [k for k in kinds or [] if k]
    full = bool(kinds) and len(known) == len(kinds)
    return [lid for lid in usable_layout_ids() if lid not in exclude and holds(lays[lid], n)
            and (not full or all(any(accepts(s, k) for k in known) for s in material_slots(lays[lid])))]


def capacity_table() -> dict:
    """{layout id: capacity in words} of every choosable layout."""
    lays = library()["layouts"]
    return {lid: capacity_say(lays[lid]) for lid in usable_layout_ids()}


def describe(layout: dict) -> str:
    """'L05 Picture left + text right: main 600x560 (1.07:1) / text 512x560 (0.91:1)'."""
    bits = []
    for s in layout.get("slots") or []:
        seq = ", in sequence" if s.get("order") == "sequence" else ""
        bits.append(f"{s['id']} {s['w']}x{s['h']} ({s['w'] / s['h']:.2f}:1{seq})")
    return (f"{layout['id']} {layout['name']}: " + " / ".join(bits)
            + f" (holds {capacity_say(layout)} candidate material(s))")


# ------------------------------------------------------------------ materials

def kind_of(material: dict) -> str:
    """photo / chart / formula / numbers / diagram (steps, route) / lines for a material {id, template, values} or {id, file} or {lines}."""
    if material.get("lines") is not None and not material.get("template") and not material.get("file"):
        return "lines"
    if material.get("file") and not material.get("template"):
        return "photo"
    return KIND.get(str(material.get("template")), "figure")


def accepts(slot: dict, kind: str) -> bool:
    acc = slot.get("accepts") or []
    return kind in acc or (kind == "figure" and "figure" in acc)


def accepted_names(slot: dict) -> str:
    """The material kinds a slot takes, in message words (kinds no worker makes any more are left out)."""
    return ", ".join(KIND_NAMES[a] for a in slot.get("accepts") or [] if a in KIND_NAMES) or "none of the materials made here"


def _fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


def photo_size(path: str) -> tuple[int, int] | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def material_layer(material: dict) -> dict | None:
    """The full-screen layer used to measure a json material or plain lines (tools/preview_materials.py mapping)."""
    from tools.preview_materials import to_layers
    if kind_of(material) == "lines":
        return {"type": "BigText", "props": {"lines": list(material.get("lines") or []), "highlight": []}}
    lys = to_layers(material)
    return lys[0] if lys else None


def measure_boxes(layers: list[dict], theme: str = "shoestring") -> list[dict | None]:
    """Content box of each layer drawn alone on a full 1280x720 screen (settled state):
    {"x0","y0","x1","y1","min_px"} or None when it could not be measured. Cached."""
    out: list = [None] * len(layers)
    todo = []
    for i, ly in enumerate(layers):
        key = _fingerprint({"type": ly.get("type"), "props": ly.get("props") or {}, "theme": theme, "v": _src_version()})
        f = CACHE / f"{key}.json"
        if f.is_file():
            try:
                out[i] = json.loads(f.read_text(encoding="utf-8"))
                continue
            except ValueError:
                pass
        todo.append((i, ly, f))
    if todo:
        got = _measure_now([ly for _, ly, _ in todo], theme)
        CACHE.mkdir(parents=True, exist_ok=True)
        for (i, _, f), box in zip(todo, got):
            out[i] = box
            if box:
                f.write_text(json.dumps(box), encoding="utf-8")
    return out


def _src_version() -> int:
    """Newest change of the screen templates (remotion/src): a changed template is measured again."""
    src = ROOT / "remotion" / "src"
    return int(max((p.stat().st_mtime for p in src.rglob("*") if p.is_file()), default=0))


def _measure_now(layers: list[dict], theme: str) -> list[dict | None]:
    """One browser run: each layer gets 3 s alone; the still is taken at 85 % (print mode: settled)."""
    import tempfile
    from functions._common import write_json
    from functions.render_part import CLI, REMOTION, _ensure_bundle, _Files, _localize, _render_slots
    from tools._layout import collect
    if not CLI.is_file():
        return [None] * len(layers)
    sec = 3.0
    lys, jobs = [], []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:   # headless Chrome may still hold profile files
        tmp = pathlib.Path(t)
        for k, ly in enumerate(layers):
            lys.append({"type": ly["type"], "props": ly.get("props") or {}, "start": k * sec, "end": (k + 1) * sec})
            jobs.append({"frame": int((k + 0.85) * sec * FPS), "out": str(tmp / f"m{k}.png"), "measure": True})
        total = len(layers) * sec
        props = {"page": "measure", "duration": total, "width": W, "height": H, "theme": theme, "print": True,
                 "background": [{"style": "plain", "start": 0, "end": total}], "layers": lys, "audio": []}
        build = _ensure_bundle()
        with _Files() as files:
            missing: list = []
            served = _localize(props, files, missing)
            write_json(tmp / "props.json", served)
            write_json(tmp / "jobs.json", jobs)
            with _render_slots:
                subprocess.run(["node", str(ROOT / "tools" / "_stills_measure.mjs"), str(REMOTION), str(build),
                                str(tmp / "props.json"), str(tmp / "jobs.json"), str(tmp / "measures.json")],
                               cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                               timeout=600)
        try:
            raw = json.loads((tmp / "measures.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return [None] * len(layers)
    by_frame = {m["frame"]: m for m in raw if "layers" in m}
    out = []
    for k, ly in enumerate(layers):
        m = by_frame.get(jobs[k]["frame"])
        if not m:
            out.append(None)
            continue
        # the frame shows the background and this one layer
        items = collect(m, 1, [{**lys[k], "start": 0}])
        rs = [it["rect"] for it in items if it["kind"] in ("text", "img", "shape", "box")]
        if not rs:
            out.append(None)
            continue
        texts = [it["px"] for it in items if it["kind"] == "text"]
        out.append({"x0": min(r[0] for r in rs), "y0": min(r[1] for r in rs), "x1": max(r[2] for r in rs),
                    "y1": max(r[3] for r in rs), "min_px": min(texts) if texts else 0})
    return out


def natural(material: dict, theme: str = "shoestring", box: dict | None = None) -> dict | None:
    """The material's natural size: {"w","h","min_px","how"}. box: a measured content box (skips measuring)."""
    if kind_of(material) == "photo":
        size = photo_size(str(material.get("file") or ""))
        return {"w": size[0], "h": size[1], "min_px": 0, "how": "photo file size"} if size else None
    if box is None:
        ly = material_layer(material)
        if not ly:
            return None
        box = measure_boxes([ly], theme)[0]
    if not box:
        return None
    return {"w": max(1, box["x1"] - box["x0"]), "h": max(1, box["y1"] - box["y0"]), "min_px": box.get("min_px", 0),
            "how": "size measured in the browser"}


def fit(nat: dict, slot: dict, k_max: float = K_MAX) -> dict:
    """Scale a natural size into a slot: {"k", "fill" (0-1), "text_px", "drawn_w", "drawn_h"}."""
    k = min(slot["w"] / nat["w"], slot["h"] / nat["h"], k_max)
    dw, dh = nat["w"] * k, nat["h"] * k
    return {"k": round(k, 3), "fill": round(dw * dh / (slot["w"] * slot["h"]), 3),
            "text_px": round(nat.get("min_px", 0) * k, 1), "drawn_w": round(dw), "drawn_h": round(dh)}


# ------------------------------------------------------------------ placing timeline layers

def place_cut(cut: dict, theme: str = "shoestring", lib: dict | None = None) -> list[dict]:
    """The layers of one timeline cut with a "box" for every layer in a slot (what Page.tsx draws):
    {x, y, w, h} the slot on screen; inside it a canvas cw x ch scaled by k at (dx, dy) (clipped to the slot).
    Layers of a cut without a library layout are returned unchanged."""
    lib = lib or library()
    layout = lib["layouts"].get(str(cut.get("layout") or ""))
    layers = [dict(ly) for ly in cut.get("layers") or []]
    if not layout:
        return layers
    if layout["id"] == COVER:
        for ly in layers:
            if ly.get("type") == "SectionCard":
                ly["props"] = {**(ly.get("props") or {}),
                               "boxes": {s["id"]: {k: s[k] for k in ("x", "y", "w", "h")} for s in layout["slots"]}}
        return layers
    fitted = [(i, ly) for i, ly in enumerate(layers)
              if ly.get("type") in FITTED and slot_of(layout, str(ly.get("slot") or ""))]
    boxes = measure_boxes([{"type": ly["type"], "props": ly.get("props") or {}} for _, ly in fitted], theme) if fitted else []
    measured = {i: b for (i, _), b in zip(fitted, boxes)}
    for i, ly in enumerate(layers):
        s = slot_of(layout, str(ly.get("slot") or ""))
        if not s:
            continue
        ly["box"] = box_for(ly, s, measured.get(i))
        if ly.get("type") == "PhotoCard":
            ly["props"] = _photo_in(ly.get("props") or {}, s)
    return layers


def box_for(ly: dict, s: dict, content: dict | None) -> dict:
    x, y, w, h = s["x"], s["y"], s["w"], s["h"]
    if ly.get("type") in FITTED:
        c = content or {"x0": 0, "y0": 0, "x1": W, "y1": H}
        cw, ch = max(1, c["x1"] - c["x0"]), max(1, c["y1"] - c["y0"])
        k = min(w / cw, h / ch, K_MAX)
        dx = w / 2 - k * (c["x0"] + c["x1"]) / 2
        dy = h / 2 - k * (c["y0"] + c["y1"]) / 2
        return {"x": x, "y": y, "w": w, "h": h, "cw": W, "ch": H, "k": round(k, 4), "dx": round(dx, 1), "dy": round(dy, 1)}
    return {"x": x, "y": y, "w": w, "h": h, "cw": w, "ch": h, "k": 1, "dx": 0, "dy": 0}


def _photo_in(props: dict, s: dict) -> dict:
    """A PhotoCard in a slot: the whole picture, as large as the slot allows (aspect kept), centered."""
    size = photo_size(str(props.get("src") or ""))
    w, h = s["w"], s["h"]
    if size:
        k = min(w / size[0], h / size[1])
        pw, ph = int(size[0] * k), int(size[1] * k)
    else:
        pw, ph = w, h
    out = {k: v for k, v in props.items() if k not in ("caption",)}
    return {**out, "x": int((w - pw) / 2), "y": int((h - ph) / 2), "w": pw, "h": ph}


def place_timeline_cuts(cuts: list[dict], theme: str = "shoestring") -> dict:
    """{cut_id: placed layers} for every cut (one library read)."""
    lib = library()
    return {c.get("cut_id"): place_cut(c, theme, lib) for c in cuts}


# ------------------------------------------------------------------ narration words

def word_time(words: list[dict], phrase: str) -> float | None:
    """Start second of the first word of `phrase` in the cut's word timings (edge-tts), matched loosely."""
    want = [w for w in str(phrase or "").split() if w]
    if not want or not words:
        return None
    norm = lambda s: "".join(ch for ch in str(s) if ch.isalnum())
    toks = [norm(w.get("text")) for w in words]
    first = norm(want[0])
    for i, tok in enumerate(toks):
        if tok == first or (first and tok.startswith(first)):
            rest = [norm(x) for x in want[1:]]
            if all(i + j + 1 < len(toks) and toks[i + j + 1].startswith(r) for j, r in enumerate(rest)):
                return float(words[i].get("start") or 0)
    for i, tok in enumerate(toks):
        if first and first in tok:
            return float(words[i].get("start") or 0)
    return None


# ------------------------------------------------------------------ judging a fill (layout_fit, checkers, decision)

AREA_KINDS = {"photo", "chart", "diagram", "formula", "numbers", "timeline", "case_card", "figure"}
TEXT_KINDS = {"lines", "keyword", "quote", "definition"}


def material_key(m: dict) -> dict:
    """What decides a material's shape (the same from a candidate list and from the file server)."""
    k = kind_of(m)
    if k == "photo":
        return {"photo": list(photo_size(str(m.get("file") or "")) or [])}
    if k == "lines":
        return {"lines": list(m.get("lines") or [])}
    return {"template": m.get("template"), "values": m.get("values") or {}}


def fill_key(cut_id: str, layout_id: str, fill: list[tuple[str, dict]]) -> str:
    """Fingerprint of one judged fill: cut, layout, and per slot the material's shape."""
    return _fingerprint({"cut": cut_id, "layout": layout_id,
                         "fill": sorted([[s, json.dumps(material_key(m), sort_keys=True, ensure_ascii=False)]
                                         for s, m in fill])})


FIT_RECORDS = ROOT / ".cache" / "layout_fit"


def save_record(key: str, record: dict) -> None:
    FIT_RECORDS.mkdir(parents=True, exist_ok=True)
    (FIT_RECORDS / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def load_record(key: str) -> dict | None:
    f = FIT_RECORDS / f"{key}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except ValueError:
        return None


def judge_slot(slot: dict, m: dict, nat: dict | None) -> dict:
    """One slot with one material: numbers and a verdict. {"slot","material","kind","fit","text_px","ok","say"}."""
    kind = kind_of(m)
    name = m.get("id") or "text (lines)"
    row = {"slot": slot["id"], "material": name, "kind": kind, "fit": None, "text_px": None, "ok": True}
    if not accepts(slot, kind):
        row["ok"] = False
        row["say"] = (f"Slot {slot['id']} takes only {accepted_names(slot)}. "
                      f"{name} ({KIND_NAMES.get(kind, kind)}) cannot go into this slot.")
        return row
    if not nat:
        row["say"] = f"Slot {slot['id']}: the size of {name} could not be measured, so its fit was not judged."
        return row
    f = fit(nat, slot)
    row["fit"], row["text_px"] = f["fill"], f["text_px"] or None
    ratio_m, ratio_s = nat["w"] / nat["h"], slot["w"] / slot["h"]
    shape = (f"material {nat['w']}x{nat['h']} ({ratio_m:.2f}:1), slot {slot['w']}x{slot['h']} ({ratio_s:.2f}:1)")
    bits = []
    if kind in AREA_KINDS:
        bits.append(f"fills {f['fill']:.0%} of the slot ({shape}, drawn at {f['drawn_w']}x{f['drawn_h']})")
        if f["fill"] < FIT_OK:
            row["ok"] = False
            side = "wider" if ratio_m > ratio_s else "taller"
            bits.append(f"the material is {side} than the slot, so {1 - f['fill']:.0%} of the slot stays empty (target: {FIT_OK:.0%} or more filled)")
    if f["text_px"]:
        tp = f["text_px"]
        bits.append(f"its smallest text is drawn at {tp:g}px")
        if tp < TEXT_MIN:
            row["ok"] = False
            bits.append(f"below {TEXT_MIN:g}px, so the text is too long for this slot")
        elif tp < TEXT_OK:
            row["ok"] = False
            bits.append(f"below the reading size of {TEXT_OK:g}px")
    row["say"] = f"{name} in slot {slot['id']}: " + "; ".join(bits) + "."
    return row


def judge_fill(layout: dict, fill: list[tuple[str, dict]], nats: dict) -> list[dict]:
    """Every slot of the layout: the judged materials, or an empty-slot row. nats: {id(m): natural}."""
    rows = []
    for s in layout.get("slots") or []:
        mine = [m for sid, m in fill if sid == s["id"]]
        if not mine:
            rows.append({"slot": s["id"], "material": None, "kind": None, "fit": 0.0, "text_px": None, "ok": False,
                         "say": f"Slot {s['id']} ({s['w']}x{s['h']}) is empty. If there is nothing to fill it with, pick a layout with fewer slots."})
        for m in mine:
            rows.append(judge_slot(s, m, nats.get(id(m))))
    return rows


def score(rows: list[dict]) -> float:
    """One number to rank fills (higher is better): the worst area fit, text size counted too; refused slots = 0."""
    vals = []
    for r in rows:
        if r["material"] is None or (r["fit"] is None and not r["ok"]):
            vals.append(0.0)
            continue
        if r["kind"] in AREA_KINDS and r["fit"] is not None:
            vals.append(r["fit"])
        if r["text_px"]:
            vals.append(min(1.0, r["text_px"] / 28.0))
        if not r["ok"] and r["fit"] is None:
            vals.append(0.0)
    return round(min(vals), 3) if vals else 0.0


def best_fills(layout: dict, materials: list[dict], nats: dict) -> list[tuple[float, list, list]]:
    """Every way to put all the materials into this layout (each slot filled; a sequence slot takes up to
    sequence_max), best first: [(score, fill, rows)]. Only layouts whose material capacity holds the candidate
    materials given (text lines do not count) get fills."""
    import itertools
    slots = layout.get("slots") or []
    if not slots or not materials:
        return []
    if not holds(layout, sum(1 for m in materials if kind_of(m) != "lines")):
        return []
    seq_cap = sequence_max(layout) or 1
    out = []
    n = len(materials)
    # assign each material a slot index; every slot gets >= 1; together slots get exactly 1
    for combo in itertools.product(range(len(slots)), repeat=n):
        counts = [combo.count(i) for i in range(len(slots))]
        if any(c == 0 for c in counts):
            continue
        if any(c > 1 and slots[i].get("order") != "sequence" for i, c in enumerate(counts)):
            continue
        if any(c > seq_cap for c in counts):
            continue
        fill = [(slots[i]["id"], m) for i, m in zip(combo, materials)]
        if any(not accepts(slots[i], kind_of(m)) for i, m in zip(combo, materials)):
            continue
        rows = judge_fill(layout, fill, nats)
        out.append((score(rows), fill, rows))
        if len(out) > 200:
            break
    out.sort(key=lambda x: -x[0])
    return out


# ------------------------------------------------------------------ section cover

COVER_SECONDS = 3.0


def cover_seconds(cut_seconds: float) -> float:
    """How long the section cover stays on its cut (seconds from the cut start)."""
    return round(min(COVER_SECONDS, max(1.0, float(cut_seconds) * 0.5)), 3)


def add_cover(layers: list[dict], section_card: dict, cut_seconds: float) -> list[dict]:
    """The part's first cut opens with the section cover (layout L13) for its first 3 s: a SectionCard drawn last,
    so it covers the cut's own screen (opaque) and fades out to it. The cut's layers keep their times, so their
    word-timed entrances stay in step with the narration. Times are relative to the cut start."""
    lay = library()["layouts"].get(COVER)
    if not lay or not section_card:
        return layers
    end = cover_seconds(cut_seconds)
    props = {k: section_card.get(k) for k in ("number", "title", "subtitle") if section_card.get(k)}
    props["boxes"] = {s["id"]: {k: s[k] for k in ("x", "y", "w", "h")} for s in lay["slots"]}
    return layers + [{"type": "SectionCard", "start": 0, "end": end, "props": props}]
