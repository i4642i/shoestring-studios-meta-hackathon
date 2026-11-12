"""Turns the raw on-screen measurements of tools/_stills_measure.mjs (taken in the same browser tab that renders the
preview pictures) into layout problems per cut, written for the slide builder: where, the measured value, the target
and how to fix it. Checks: screen use, smallest text, overlaps, blank start. A helper, not a tool (name starts with _).

Targets a good 1280x720 screen meets (also stated in tools/preview_slides.py DESC):
- screen use: the main content (everything except the Kicker / SourceTag / Caption strips and thin edge bars) spans
  at least 55% of the height (396 px) and 65% of the width (832 px) (not asked of TitleCard / EndCard / BigText, which
  also may leave one side empty), and no side is left empty much more than its opposite side
  (an empty band over 200 px at the top/bottom or 260 px at the left/right that is 120 px / 160 px larger than the
  band on the opposite side means the content is packed to one side).
- text size: every visible text is at least 22 px tall as rendered (a slot layer is drawn at 0.6x, so 22 px there
  needs a 37 px font in its CSS/props).
- overlaps: no two visible texts/pictures (or boxes of different layers) cover each other by more than 4 px.
- blank start: something is on screen within 0.5 s of the cut start, the main content within 1.0 s, and by 1.0 s
  at least 25% of the content (by area of text lines and pictures) is on screen.
"""

import math

W, H = 1280, 720
FPS = 30
MIN_PX = 22.0                        # the B1 limit of check_layout (2026-11-11)
USE_H, USE_W = 0.55, 0.65
BAND_V, BAND_H = 200, 260            # an empty band at one edge larger than this ...
SKEW_V, SKEW_H = 120, 160            # ... and larger than the opposite band by this much = packed to one side
OVERLAP_PX = 4
FIRST_ANY, FIRST_MAIN = 0.5, 1.0
SHOWN_EARLY = 0.25                   # share of the cut's content (by area) on screen by FIRST_MAIN
STRIPS = {"Kicker", "SourceTag", "Caption", "Sparkles"}
STATEMENT = {"TitleCard", "EndCard", "BigText", "SectionCard"}   # one centered statement: only the balance rules apply
EDGE_LINE = 16
SLOTS = {"left": (24, 150, 1280 * 0.6, 720 * 0.6), "right": (800, 150, 760 * 0.6, 720 * 0.6)}
NAMES = {"Kicker": "the kicker (Kicker)", "SourceTag": "the source tag (SourceTag)", "Caption": "the caption (Caption)"}

THRESHOLDS = (f"screen use: the main content (not Kicker/SourceTag/Caption) spans >= {int(USE_H * 100)}% of the height "
              f"and >= {int(USE_W * 100)}% of the width, with no one-sided empty band (> {BAND_V} px at the top/bottom "
              f"or > {BAND_H} px at the left/right; TitleCard/EndCard/BigText: top/bottom balance only); "
              f"text >= {int(MIN_PX)} px as rendered; overlaps <= {OVERLAP_PX} px; something on screen by "
              f"{FIRST_ANY} s and the main content by {FIRST_MAIN} s after the cut starts, with at least "
              f"{SHOWN_EARLY:.0%} of the screen's content (by area) on screen by then")


def _f(s: float) -> int:
    return int(math.floor(s * FPS + 0.5))      # Math.round in ctx.ts (non-negative values)


def active(props: dict, frame: int) -> tuple[int, list]:
    """How many background Sequences and which layers are mounted at a frame (the order of the root's children)."""
    on = lambda x: _f(x["start"]) <= frame < _f(x["start"]) + max(1, _f(x["end"] - x["start"]))
    return sum(1 for b in props["background"] if on(b)), [ly for ly in props["layers"] if on(ly)]


def _area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def _inter(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def _union(rs):
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]


def _who(it) -> str:
    typ = it["layer"]
    slot = it["slot"]
    where = NAMES.get(typ, typ) + (" (left slot)" if slot == "left" else " (right slot)" if slot == "right" else
                                   f" ({slot} slot)" if slot else "")
    if it["kind"] == "text":
        return f'the text "{it["text"][:24]}" in {where}'
    return f"the {'picture' if it['kind'] == 'img' else 'box'} ({it['tag']}) in {where}"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def collect(measure: dict, n_bg: int, layers: list) -> list:
    """The visible items of all layers, each tagged with its layer, slot and absolute entrance time.
    Backdrops (full-screen fills, boxes in the page background color) are dropped."""
    conts = measure.get("layers") or []
    if len(conts) < n_bg + len(layers):
        layers = layers + [{"type": "?", "start": 0}] * (n_bg + len(layers) - len(conts))
    backdrop = set()
    for items in conts[:n_bg]:
        backdrop |= {it.get("bgc") for it in items if it["kind"] == "box" and it.get("bgc")}
    out = []
    for li, items in enumerate(conts[n_bg:n_bg + len(layers)]):
        ly = layers[li]
        box = ly.get("box")
        slot = ly.get("slot") if (box or ly.get("slot") in SLOTS) else None
        if box:                               # a slot of a library layout (tools/_layouts.py place_cut)
            sx, sy, sw, sh = box["x"], box["y"], box["w"], box["h"]
        else:
            sx, sy, sw, sh = SLOTS[slot] if slot else (0, 0, W, H)
        for it in items:
            big = _area(it["rect"]) >= 0.85 * sw * sh
            if it["kind"] in ("box", "shape") and big:
                if it.get("bgc"):
                    backdrop.add(it["bgc"])
                continue
            out.append({**it, "layer": ly.get("type", "?"), "slot": slot, "li": li, "ref": ly.get("_ref"),
                        "lstart": float(ly.get("start", 0)),
                        "appear": float(ly.get("start", 0)) + float(it.get("at") or 0)})
    return [it for it in out if not (it["kind"] == "box" and not it.get("deco") and it.get("bgc") in backdrop)]


def _edge_line(it) -> bool:
    """A thin decorative bar along an edge of the frame (e.g. an EndCard's top accent line): not content."""
    x0, y0, x1, y1 = it["rect"]
    thin = min(x1 - x0, y1 - y0) <= EDGE_LINE
    return it["kind"] in ("box", "shape") and thin and (x0 <= 4 or y0 <= 4 or x1 >= W - 4 or y1 >= H - 4)


def space(items: list) -> tuple[list, dict]:
    main = [it for it in items if it["layer"] not in STRIPS] or items
    rs = [it["rect"] for it in main if it["kind"] in ("text", "img", "box", "shape") and not _edge_line(it)]
    if not rs:
        return ["Nothing is visible on the screen. Put text or a picture into this cut."], {}
    statement = all(it["layer"] in STATEMENT for it in main)
    x0, y0, x1, y1 = _union(rs)
    top, bottom, left, right = y0, H - y1, x0, W - x1
    uh, uw = (y1 - y0) / H, (x1 - x0) / W
    info = {"content_box": [x0, y0, x1, y1], "height_use": f"{uh:.0%}", "width_use": f"{uw:.0%}"}
    msgs = []
    box = f"content spans x {x0}-{x1}, y {y0}-{y1}"
    if uh < USE_H and not statement:
        msgs.append(f"The content uses only {uh:.0%} of the screen height ({box}; {top}px empty at the top, {bottom}px "
                    f"at the bottom). Make the text, pictures or diagrams larger, or widen the line spacing, so it uses "
                    f"{USE_H:.0%} ({int(USE_H * H)}px) of the height or more.")
    if bottom > BAND_V and bottom - top > SKEW_V:
        msgs.append(f"The content is packed at the top and {bottom}px at the bottom is empty (top margin {top}px, {box}). "
                    f"Center it vertically (bottom margin {BAND_V}px or less) or make it larger to fill down.")
    if top > BAND_V and top - bottom > SKEW_V:
        msgs.append(f"The content is packed at the bottom and {top}px at the top is empty (bottom margin {bottom}px, {box}). "
                    f"Move it up or make it larger (top margin {BAND_V}px or less).")
    if uw < USE_W and not statement:
        msgs.append(f"The content uses only {uw:.0%} of the screen width ({box}; {left}px empty at the left, {right}px "
                    f"at the right). Spread it out or make it larger so it uses {USE_W:.0%} ({int(USE_W * W)}px) of the "
                    f"width or more.")
    if right > BAND_H and right - left > SKEW_H and not statement:
        msgs.append(f"The content is packed at the left and {right}px at the right is empty (left margin {left}px, {box}). "
                    f"Center it horizontally, make the text larger, or put a related picture or diagram in the empty "
                    f"space, so the right margin is {BAND_H}px or less.")
    if left > BAND_H and left - right > SKEW_H and not statement:
        msgs.append(f"The content is packed at the right and {left}px at the left is empty (right margin {right}px, {box}). "
                    f"Center it horizontally, make the text larger, or put a related picture or diagram in the empty "
                    f"space, so the left margin is {BAND_H}px or less.")
    return msgs, info


def text_size(items: list) -> tuple[list, dict]:
    texts = sorted((it for it in items if it["kind"] == "text"), key=lambda it: it["px"])
    if not texts:
        return [], {}
    info = {"smallest_text": f'{texts[0]["px"]:g}px "{texts[0]["text"][:24]}"'}
    small = [it for it in texts if it["px"] < MIN_PX - 0.05]
    msgs = []
    for it in small[:5]:
        scale = round(it["px"] / it["fs"], 2) if it.get("fs") else 1.0
        need = math.ceil(MIN_PX / scale - 0.01) if scale > 0 else int(MIN_PX)
        if it["layer"] == "HtmlSlide":
            how = (f"this slot is drawn at {scale:g}x, so raise the CSS font size from {it['fs']:g}px to {need}px or more"
                   if scale < 0.98 else f"raise the CSS font size from {it['fs']:g}px to {need}px or more")
        elif it["slot"]:
            how = (f"this part ({it['layer']}) is scaled to its slot at {scale:g}x, so its font size cannot be set "
                   f"directly. Use fewer items or shorter text, or a layout that holds this material larger")
        else:
            how = f"the font size of this part ({it['layer']}) cannot be set directly; use fewer items or shorter text, or another screen template"
        msgs.append(f"{_cap(_who(it))} is only {it['px']:g}px (minimum {MIN_PX:g}px): {how}.")
    if len(small) > 5:
        msgs.append(f"{len(small) - 5} more texts are smaller than {MIN_PX:g}px. Enlarge them the same way.")
    return msgs, info


def overlap_pairs(items: list) -> list:
    """[(a, b, w, h)]: visible texts / pictures / boxes covering each other by more than OVERLAP_PX (one per pair)."""
    cand = [it for it in items if it["kind"] in ("text", "img", "box")]
    out, seen = [], set()
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if a["li"] == b["li"] and (a["id"] in b["anc"] or b["id"] in a["anc"]):
                continue
            kinds = {a["kind"], b["kind"]}
            if "box" in kinds and a["li"] == b["li"]:
                continue                      # a card behind text inside one slide is a design choice
            # text against text of one layer: the glyph lines; across layers: the whole label (with its padded
            # background, e.g. a Caption box and a SourceTag box)
            own = lambda it: [it["pad"]] if a["li"] != b["li"] and it.get("pad") else it.get("lines") or [it["rect"]]
            pairs = [_inter(x, y) for x in own(a) for y in own(b)]
            w, h = max(pairs, key=lambda p: min(p))
            if min(w, h) <= OVERLAP_PX:
                continue
            key = (a["text"] if a["kind"] == "text" else a["tag"], b["text"] if b["kind"] == "text" else b["tag"])
            if key in seen:
                continue
            seen.add(key)
            out.append((a, b, w, h))
    return out


def overlaps(items: list) -> list:
    msgs = []
    for a, b, w, h in overlap_pairs(items):
        up = a if a["rect"][1] <= b["rect"][1] else b
        down = b if up is a else a
        msgs.append(f"{_cap(_who(a))} and {_who(b)} overlap ({w}px wide x {h}px high; at y "
                    f"{up['rect'][1]}-{up['rect'][3]} / y {down['rect'][1]}-{down['rect'][3]}). Move one of them "
                    f"{h + 8}px or more up or down, or {w + 8}px or more sideways, so they are apart.")
    return msgs[:6]


def blank_start(items: list, cut_start: float) -> tuple[list, dict]:
    if not items:
        return [], {}
    first = min(it["appear"] for it in items) - cut_start
    main = [it for it in items if it["layer"] not in STRIPS]
    first_main = (min(it["appear"] for it in main) - cut_start) if main else first
    weight = lambda it: sum(_area(r) for r in it.get("lines") or [it["rect"]])
    total = sum(weight(it) for it in items) or 1
    early = sum(weight(it) for it in items if it["appear"] - cut_start <= FIRST_MAIN)
    info = {"first_visible_s": round(max(0.0, first), 2), "main_visible_s": round(max(0.0, first_main), 2),
            f"shown_by_{FIRST_MAIN:g}s": f"{early / total:.0%}"}
    msgs = []
    if first > FIRST_ANY:
        late = min(items, key=lambda it: it["appear"])
        msgs.append(f"The screen is empty for the first {first:.1f} s of the cut (the first thing to appear: {_who(late)}, "
                    f"data-at {late.get('at') or 0:g}). Make the first element appear within {FIRST_ANY:g} s by setting "
                    f"its data-at to {FIRST_ANY:g} or less, or add a title or picture that shows from the cut's start.")
    elif first_main > FIRST_MAIN:
        late = min(main, key=lambda it: it["appear"])
        strips = sorted({NAMES.get(it["layer"], it["layer"]) for it in items if it["appear"] - cut_start <= FIRST_MAIN})
        msgs.append(f"For the first {first_main:.1f} s of the cut only {', '.join(strips)} is visible; the main content "
                    f"appears at {first_main:.1f} s ({_who(late)}). Pull its data-at forward so the first element of "
                    f"the main content appears within {FIRST_MAIN:g} s.")
    elif early / total < SHOWN_EARLY:
        later = [it for it in items if it["appear"] - cut_start > FIRST_MAIN]
        big = max(later, key=weight)
        now = [it for it in items if it["appear"] - cut_start <= FIRST_MAIN]
        names = ", ".join(f'"{it["text"][:14]}"' if it["kind"] == "text" else it["tag"] for it in now[:3])
        msgs.append(f"In the first {FIRST_MAIN:g} s of the cut only {early / total:.0%} of the screen's content is "
                    f"visible ({names}). The largest content, {_who(big)}, appears only at "
                    f"{big['appear'] - cut_start:.1f} s, so the screen looks nearly empty until then. Set its data-at to "
                    f"{FIRST_MAIN:g} or less so it shows from the start, and delay only what comes later "
                    f"({SHOWN_EARLY:.0%} or more within the first {FIRST_MAIN:g} s).")
    return msgs, info


def opening(frames: list) -> list:
    """The cut's opening screen, from the items of every measured frame of the cut: the strips plus the main layers
    that start first. A main layer that starts later is a planned change of screen (the next item of a sequence slot,
    a support shown when the narration names it), not a late start, so it is left out of the blank-start check
    (before 2026-11-11 each frame was judged alone, and the second screen of a sequence slot read as "the main content
    comes at 6 s")."""
    every = [it for items in frames for it in items]
    mains = [it for it in every if it["layer"] not in STRIPS]
    first = min((it["lstart"] for it in mains), default=None)
    out, seen = [], set()
    for it in every:
        if it["layer"] not in STRIPS and first is not None and it["lstart"] > first + 0.01:
            continue
        key = (it["layer"], round(it["lstart"], 2), it.get("text") or it.get("tag"), tuple(it["rect"]))
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def analyze(measures: list, cut_start: float, hidden_until: float = 0.0) -> tuple[list, dict]:
    """measures: [(raw measurement, n_bg, active layers)] taken inside one cut -> (problems, measured values).
    hidden_until: seconds from the cut start during which the program's section cover hides the cut's own screen
    (layout L13 on a part's first cut); the blank start counts from the moment the cover is gone."""
    probs, info, frames = [], {}, []
    for raw, n_bg, layers in measures:
        items = collect(raw, n_bg, layers)
        frames.append(items)
        for fn in (space, text_size):
            m, i = fn(items)
            probs += m
            info.update(i)
        probs += overlaps(items)
    m, i = blank_start(opening(frames), cut_start + hidden_until)
    probs += m
    info.update(i)
    out, seen = [], set()
    for p in probs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out, info
