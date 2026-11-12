RULES = [
    "Every narration cut appears in timeline.cuts once, in narration order, and there are no other cuts. part_id is slide_plan's part_id.",
    "Each cut's layout equals that cut's layout in slide_plan.",
    "Every layer type is a known template: Kicker, BigText, PhotoCard, Formula, BarChart, LineChart, Steps, NumberCard, TitleCard, EndCard, SectionCard, Caption, SourceTag, Curve, Scatter, RouteMap, HtmlSlide.",
    "Required props: Kicker text; BigText lines; PhotoCard src; Formula steps; BarChart bars; LineChart points; Steps items; NumberCard items; TitleCard title; EndCard slogan; SectionCard title; Caption text; SourceTag text; Curve curves or dist; Scatter points; RouteMap stops; HtmlSlide html.",
    "Every layer has 0 <= start < end, and end is at most the cut's screen_seconds in timing (voice seconds + 0.4).",
    "TitleCard props are only title, subtitle, kicker, logo; EndCard props are only slogan, name, logo.",
    "A TitleCard or EndCard logo and a PhotoCard src must be local files.",
    "Every Formula line is valid LaTeX.",
    "BigText size is a number from 28 to 140 (or left out), and BigText has at most 3 lines (merge lines; never drop words).",
    "Words decided before you stay exactly as decided: a text slot (use lines) shows exactly the Screen Designer's lines (only line breaks may differ), the Kicker shows slide_plan's title, the SourceTag slide_plan's source; you add no words of your own.",
    "Highlight chips (var(--hl-bg)) hold only the words of slide_plan's highlight for that cut; no highlight, no chip.",
    "Layout cuts (L01-L11): for every slot of slide_plan's fill, the main layer of that material carries that slot id in slot. No main layer outside a slot, no slot the layout does not have. The program sets position and size from the slot, so a PhotoCard has no x, y, w, h or caption.",
    "A slot shown together has one main layer; a sequence slot has as many layers as fill has materials, one after another without overlapping, each starting when its at word is said (timing words).",
    "Material and layer kind match, by candidate id: photos (ph-) and generated pictures (gn-) are PhotoCard or an HtmlSlide that uses that picture; Max's materials (ch-) use their screen template (BarChart, LineChart, Curve, Scatter, Formula, Steps, RouteMap), NumberCard or HtmlSlide; text (use lines) is HtmlSlide or BigText.",
    "HtmlSlide: no scripts or event handlers; nothing loaded from the web (http, @import, url()); font-size 22px or more; every img:<name> has a real file in images; main elements have data-at.",
    "HtmlSlide: nothing sticks out when measured in a browser at the slot size (out of the slot, out of its box, clipped).",
    "HtmlSlide text weight and letter-spacing (measured in a browser): big text (44px and up) 600-900, body (28-43px) 500-700, small text (27px and below) 600-700, a highlighted word in a line not thinner than its line; letter-spacing 0 or less; at most 2 highlight chips (var(--hl-bg)) on one screen.",
    "With rebuild feedback, only the cuts and layers named in fix_these change; the program copies the rest (locked) back from your_last_timeline when you save.",
    "The first main layer of a cut starts within 0.5 s (no blank screen).",
    "No fs:// address on screen.",
    "No span and no cues.",
    "Every cut has layers, and a main layer.",
    "design_spec has one screen for every screen cut (a cut with a content main layer that is not TitleCard, EndCard or SectionCard) and none for other cuts.",
    "Each design_spec screen has exactly one element with role main (the others support, label, source or caption); no font_size between 1 and 21.",
    "Write English only: no Korean, Chinese or Japanese characters anywhere in the timeline.",
]

import importlib.util
import json
import pathlib
import re
import subprocess

REMOTION = pathlib.Path(__file__).resolve().parents[2] / "remotion"
NEED = {"Kicker": ["text"], "BigText": ["lines"], "PhotoCard": ["src"], "Formula": ["steps"], "BarChart": ["bars"],
        "LineChart": ["points"], "Steps": ["items"], "NumberCard": ["items"], "TitleCard": ["title"],
        "EndCard": ["slogan"], "Caption": ["text"], "SourceTag": ["text"], "Curve": ["curves|dist"],
        "Scatter": ["points"], "RouteMap": ["stops"], "HtmlSlide": ["html"],
        "SectionCard": ["title"]}
MAIN = {"BigText", "PhotoCard", "Formula", "BarChart", "LineChart", "Steps", "NumberCard", "TitleCard", "EndCard",
        "Curve", "Scatter", "RouteMap", "HtmlSlide", "SectionCard"}
WHOLE = {"TitleCard", "EndCard", "SectionCard"}
SEQ_TOL = 0.6           # seconds a sequence item may start away from its word
CARD_KEYS = {"TitleCard": {"title", "subtitle", "kicker", "logo"}, "EndCard": {"slogan", "name", "logo"}}
FOCUS = {"Steps": {"active"}, "RouteMap": {"current"}, "BarChart": {"highlight"}, "BigText": {"highlight"}}
W, H = 1280, 720
BREATH = 0.4            # seconds after each cut's voice (functions/render_part.py)
LAYOUT_NAMES = {"title": "title card (TitleCard)", "end": "end card (EndCard)"}
TYPE_PROPS = ("font-weight", "letter-spacing")     # other rows of _overflow.type_problems count highlight chips


def _num(v) -> str:
    """A number as a short string (2 decimals at most)."""
    return f"{round(float(v), 2):g}"


def _input(inputs, name):
    """The value of terminal `name` among the inputs (short key first, then any "<block>/<name>" key)."""
    if not inputs:
        return None
    if name in inputs:
        return inputs[name]
    for k, v in inputs.items():
        if k.rpartition("/")[2] == name:
            return v
    return None


def _cuts_of(value) -> list:
    return [c for c in ((value or {}).get("cuts") or []) if isinstance(c, dict) and c.get("cut_id")]


def _katex(lines):
    try:
        r = subprocess.run(["node", str(REMOTION / "katex_check.js")], input=json.dumps(lines, ensure_ascii=False),
                           cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", timeout=60)
        return json.loads(r.stdout or "[]")
    except Exception:
        return []


def _lib():
    """tools/_layouts.py, loaded by path (the checker may run without the project on sys.path)."""
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / "_layouts.py"
    spec = importlib.util.spec_from_file_location("naw_layouts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(outputs, inputs=None):
    L = _lib()
    layouts = L.library()["layouts"]
    errors = []
    tl = outputs["timeline"]
    plan = {c["cut_id"]: c for c in _cuts_of(_input(inputs, "slide_plan"))}
    _restore(outputs, inputs, plan)                 # locked parts back from the last version, before any check
    cuts = tl["cuts"]
    narration = _input(inputs, "narration")
    visuals = _input(inputs, "visuals") or {}
    theme = str(visuals.get("theme") or "shoestring")
    plan = {c["cut_id"]: c for c in _cuts_of(_input(inputs, "slide_plan"))}
    timing = {c["cut_id"]: c for c in _cuts_of(_input(inputs, "timing"))}
    seconds = {k: c.get("seconds") for k, c in timing.items() if isinstance(c.get("seconds"), (int, float))}
    errors += _scene(tl, narration, _input(inputs, "slide_plan"), plan, seconds)

    screen_cuts = []
    for c in cuts:
        cid, mains = c["cut_id"], []
        lay = str(c.get("layout") or "")
        want = str((plan.get(cid) or {}).get("layout") or "")
        layout = layouts.get(lay) if lay not in ("title", "end") else None
        if want and lay != want:
            errors.append(f"{cid}: layout is \"{lay}\". Copy the layout slide_plan chose, \"{want}\", and fill the slots "
                          f"of that layout.")
        shown = (timing.get(cid) or {}).get("screen_seconds")       # = voice seconds + BREATH (split_parts)
        limit = float(shown) if isinstance(shown, (int, float)) else (seconds[cid] + BREATH if cid in seconds else None)
        for i, ly in enumerate(c["layers"]):
            t, p = ly["type"], ly.get("props") or {}
            slot_txt = f", slot {ly.get('slot')}" if ly.get("slot") else ""
            at = f"{cid} layer {i + 1} ({t}{slot_txt})"
            if t not in NEED:
                errors.append(f"{cid} layer {i + 1}: type \"{t}\" is not a known template. Change it to one of "
                              f"{', '.join(NEED)}.")
                continue
            for k in NEED[t]:
                if not any(p.get(a) not in (None, "", [], {}) for a in k.split("|")):
                    names = " or ".join("props." + a for a in k.split("|"))
                    errors.append(f"{at}: {names} is empty. Put in the value to show on screen.")
            errors += _times(at, ly, limit, seconds.get(cid))
            extra = sorted(set(p) - CARD_KEYS.get(t, set(p)))
            if extra:
                errors.append(f"{at} has fields that are not in the order: {', '.join(extra)}. This card uses only "
                              f"{', '.join(sorted(CARD_KEYS[t]))}; remove them.")
            if t in CARD_KEYS and p.get("logo") and not pathlib.Path(str(p["logo"])).is_file():
                errors.append(f"{at}: the logo file is not on this computer (\"{p['logo']}\"). Copy the logo path of the "
                              f"visuals card as it is, or remove logo if it is empty.")
            if t == "PhotoCard" and p.get("src") and not pathlib.Path(str(p["src"])).is_file():
                errors.append(f"{at}: the src file is not on this computer (\"{p['src']}\"). Copy the path (local file "
                              f"path, not an fs:// address) of that picture from the image or generated file list.")
            if t == "Formula" and isinstance(p.get("steps"), list):
                for e in _katex([str(x) for x in p["steps"]]):
                    n = e["i"] + 1
                    line = str(p["steps"][e["i"]]) if e["i"] < len(p["steps"]) else ""
                    errors.append(f"{at}: line {n} does not read as LaTeX (\"{line}\": {e['error']}). Fix that line "
                                  f"(in JSON a backslash is written as two, \\\\).")
            if t == "BigText" and p.get("size") is not None:
                sz = p["size"]
                if not isinstance(sz, (int, float)) or isinstance(sz, bool):
                    errors.append(f"{at}: size is not a number ({sz!r}). Write a number from 28 to 140, or remove size "
                                  f"for automatic size.")
                elif not 28 <= sz <= 140:
                    to = "28 or more" if sz < 28 else "140 or less"
                    errors.append(f"{at}: size is {_num(sz)}. It must be from 28 to 140: change it to {to}, or remove "
                                  f"size for automatic size.")
            if t == "PhotoCard" and not ly.get("slot"):
                errors += _photo_box(at, p)
            if t == "BigText" and isinstance(p.get("lines"), list) and len(p["lines"]) > 3:
                n = len(p["lines"])
                errors.append(f"{at} has {n} lines. At most 3: merge them into 3 lines (keep every word; only the line "
                              f"breaks change).")
            if t == "HtmlSlide":
                found = _html(p)
                errors += [f"{at}: {e}" for e in found]
                s = L.slot_of(layout, str(ly.get("slot"))) if layout else None
                size = (s["w"], s["h"]) if s else None
                where = f" at the slot size {size[0]}x{size[1]}" if size else ""
                if not any("img:" in e for e in found):       # measure in a browser (pictures present): nothing may stick out
                    probs, texts = _measure()(ly, theme, size, texts=True)
                    errors += [f"{at}: measured in a browser{where}, it overflows: {e}. Reduce size, margins or line "
                               f"breaks so it fits inside its box and the slot (keep every word)."
                               for e in probs if not e.startswith("could not measure")]
                    errors += _chips(at, texts, (plan.get(cid) or {}).get("highlight") or [])
                    errors += [f"{at}, text \"{x['text']}\": {x['property']} is {x['now']}. Change it to "
                               f"{x['change_to']}. {x['why']}" if x["property"] in TYPE_PROPS else
                               f"{at} has {x['now']} highlight chips. At most {x['change_to']}. {x['why']}"
                               for x in _type_rules()(texts)]
            if ly.get("span"):
                errors.append(f"{at} has span. Every cut gets its own screen, so remove span.")
            if ly.get("cues"):
                errors.append(f"{at} has cues. Remove cues and set the emphasis with props or data-on "
                              f"(Steps active, RouteMap current, BarChart highlight, BigText highlight).")
            if t in MAIN:
                mains.append((ly["start"], ly["end"], t, ly.get("slot") or None, i))

        what = _needs(cid, plan.get(cid), seconds.get(cid))
        if not c["layers"]:
            errors.append(f"{cid} has no layers. Make this cut's screen and add its layers{what}.")
        elif not mains:
            have = ", ".join(ly["type"] for ly in c["layers"])
            errors.append(f"{cid} has no main layer (now: {have}). Add a material layer for every slot of slide_plan{what}.")
        if mains and min(m[0] for m in mains) > 0.5:
            first = min(mains, key=lambda m: m[0])
            errors.append(f"{cid}: the first main layer ({first[2]}) starts at {_num(first[0])} s, so the screen is empty "
                          f"until then. Move start to 0.5 or less (e.g. 0).")
        shown = re.findall(r"fs://[^\s\"'<>)\]]+", json.dumps(c["layers"], ensure_ascii=False))
        if shown:
            errors.append(f"{cid}: the screen shows an fs:// address ({', '.join(sorted(set(shown))[:3])}). Change it to "
                          f"something viewers recognise: the document title and page (e.g. \"p. 26\") or the site name.")
        errors += _words(cid, c["layers"], plan.get(cid) or {})
        if lay in ("title", "end"):
            errors += _whole(cid, lay, c["layers"], mains, visuals)
        elif layout:
            errors += _slots(cid, layout, c["layers"], mains, plan.get(cid) or {}, timing.get(cid) or {}, L)
        if any(m[2] not in WHOLE for m in mains):
            screen_cuts.append(cid)
    errors += _spec(outputs, screen_cuts)
    errors += _foreign_all(tl)
    errors += _locked(tl, inputs, plan)
    return errors


def _flat(s) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _layer_text(ly) -> str:
    """The words a text layer shows: BigText lines, or the visible text of an HtmlSlide."""
    p = ly.get("props") or {}
    if ly["type"] == "BigText":
        return " ".join(str(x) for x in p.get("lines") or [])
    if ly["type"] == "HtmlSlide":
        import html as H
        body = re.sub(r"<style.*?</style>", " ", str(p.get("html") or ""), flags=re.S | re.I)
        return H.unescape(re.sub(r"<[^>]+>", " ", body))
    return str(p.get("text") or "")


def _words(cid, layers, plan_cut) -> list[str]:
    """Words decided before the slide builder stay as decided (the designer's lines, kicker, source)."""
    out = []
    fill = plan_cut.get("fill") or []
    for sid in dict.fromkeys(str(f.get("slot")) for f in fill if f.get("use") == "lines"):
        entries = [f for f in fill if str(f.get("slot")) == sid]          # in order (a sequence slot: one per item)
        texts = [(i, ly) for i, ly in enumerate(layers) if str(ly.get("slot") or "") == sid
                 and ly["type"] in ("BigText", "HtmlSlide")]
        for f, (i, ly) in zip(entries, texts):
            if f.get("use") != "lines":
                continue
            want = " / ".join(str(x) for x in f.get("lines") or [])
            got = " ".join(_layer_text(ly).split())
            if _flat(got) != _flat(want):
                out.append(f"{cid} layer {i + 1} ({ly['type']}, slot {sid}) shows \"{got[:80]}\", but the "
                           f"Screen Designer's lines for this slot are \"{want[:80]}\". The words are decided before "
                           f"you: show exactly these words (you may change only line breaks, size, weight and position).")
    for t, key in (("Kicker", "title"), ("SourceTag", "source")):
        want = str(plan_cut.get(key) or "").strip()
        if not want:
            continue
        for i, ly in enumerate(layers):
            if ly["type"] == t and _flat((ly.get("props") or {}).get("text")) != _flat(want):
                out.append(f"{cid} layer {i + 1} ({t}): text is \"{(ly.get('props') or {}).get('text')}\". Copy "
                           f"slide_plan's {key} exactly: \"{want}\".")
    return out


def _chips(at, texts, highlight) -> list[str]:
    """Highlight chips hold only the designer's highlight words."""
    words = [_flat(w) for w in highlight if _flat(w)]
    bad = [str(x.get("text") or "") for x in texts or [] if x.get("chip")
           and not any(w in _flat(x.get("text")) or _flat(x.get("text")) in w for w in words)]
    if not bad:
        return []
    allowed = ", ".join(f'"{w}"' for w in highlight) if words else "none (slide_plan has no highlight for this cut)"
    return [f"{at}: highlight chip on {', '.join(chr(34) + b + chr(34) for b in bad)}, which is not a highlight word "
            f"of slide_plan (allowed: {allowed}). The Screen Designer picks the words to stress: remove the chip "
            f"background from these words (keep the words)."]


def _feedback(inputs) -> dict:
    """The rebuild feedback of check_layout, {} without it (the first pass, and after a redesign: then the editor
    builds the scene again from the designer's new plan)."""
    for name in ("check_layout/rebuild",):
        v = _input(inputs, name)
        if isinstance(v, dict) and isinstance(v.get("your_last_timeline"), dict):
            return v
    return {}


def _free(fb, plan, R) -> dict:
    """What may change: the cuts / layers of fix_these, and every cut whose slide_plan entry differs from the plan the
    last timeline was built on (any field: layout, fill, title, source, highlight), so the lock never asks for old
    words that the new plan replaced."""
    free = R.free_of(fb.get("fix_these") or [])
    last_plan = {str(c.get("cut_id")): c for c in (fb.get("your_last_plan") or {}).get("cuts") or [] if isinstance(c, dict)}
    for cid, c in plan.items() if last_plan else ():
        old = last_plan.get(str(cid))
        if old is None or json.dumps(old, sort_keys=True) != json.dumps(c, sort_keys=True):
            free[str(cid)] = None
    return free


def _restore(outputs, inputs, plan) -> None:
    """Copy every locked cut / layer back from your_last_timeline (and wholly locked design_spec screens from
    your_last_spec) into the output in place: the slide builder rewrites the whole scene, the program keeps what
    passed. The platform saves the same objects the checker gets, so the saved output is the merged one."""
    fb = _feedback(inputs)
    if not fb:
        return
    R = _review()
    R.restore_locked(outputs["timeline"], fb["your_last_timeline"], _free(fb, plan, R),
                     outputs.get("design_spec"), fb.get("your_last_spec"))


def _locked(tl, inputs, plan) -> list[str]:
    """Lock what passed: after check_layout sent the screens back, only the cuts / layers named in fix_these (and
    cuts whose slide_plan the designer changed) may change; the rest stays as in your_last_timeline."""
    fb = _feedback(inputs)
    if not fb:
        return []
    R = _review()
    return R.timeline_lock_errors(tl, fb["your_last_timeline"], _free(fb, plan, R))   # a safety net after _restore


def _review():
    """tools/_review.py (loaded by path: the checker may run without the project on sys.path)."""
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / "_review.py"
    spec = importlib.util.spec_from_file_location("naw_review", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _whole(cid, lay, layers, mains, visuals) -> list[str]:
    """title / end cuts: one card layer that fills the screen."""
    card = {"title": "TitleCard", "end": "EndCard"}[lay]
    out = []
    others = [m for m in mains if m[2] != card]
    if not any(m[2] == card for m in mains):
        out.append(f"{cid} is a {lay} cut, drawn with one {card} layer (0 s to the end of the cut). Add a {card}.")
    if others:
        out.append(f"{cid} is a {lay} cut, so it holds only one {card}. Remove the {', '.join(m[2] for m in others)} "
                   f"layers.")
    return out


def _kind_ok(use: str, t: str) -> bool:
    if use == "lines":
        return t in ("HtmlSlide", "BigText")
    return t in {"ph-": {"PhotoCard", "HtmlSlide"},
                 "gn-": {"PhotoCard", "HtmlSlide"},
                 "ch-": {"BarChart", "LineChart", "Curve", "Scatter", "Formula", "NumberCard", "Steps", "RouteMap", "HtmlSlide", "BigText"}}.get(use[:3], set())


def _slots(cid, layout, layers, mains, plan_cut, timing_cut, L) -> list[str]:
    """A library layout: every slot of slide_plan's fill has its layer(s) in that slot, nothing outside a slot."""
    out = []
    lid = layout["id"]
    slots = {s["id"]: s for s in layout["slots"]}
    fill = plan_cut.get("fill") or []
    ids = ", ".join(slots)
    for ly in layers:
        sl = ly.get("slot")
        if ly["type"] in WHOLE:
            out.append(f"{cid} is a layout {lid} cut, so it does not use {ly['type']}. Remove this layer and put a "
                       f"material in each slot.")
        elif ly["type"] in MAIN and not sl:
            out.append(f"{cid}: the {ly['type']} layer has no slot. Write in slot the id of this material's slot among "
                       f"the slots of {lid} ({ids}) (the slot sets position and size).")
        elif sl and sl not in slots:
            out.append(f"{cid}: the slot \"{sl}\" of the {ly['type']} layer is not a slot of {lid}. Change it to one of "
                       f"{ids}.")
        elif sl and ly["type"] not in MAIN:
            out.append(f"{cid}: a {ly['type']} layer does not go in a slot (kicker, source and caption are drawn in fixed "
                       f"places). Remove slot.")
        if ly["type"] == "PhotoCard" and sl:
            given = [k for k in ("x", "y", "w", "h", "caption") if (ly.get("props") or {}).get(k) not in (None, "")]
            if given:
                out.append(f"{cid}: the PhotoCard in slot {sl} has {', '.join(given)}. The program fits a picture in a "
                           f"slot to the slot size, so remove these values (explanations go in a text slot).")
    for sid, s in slots.items():
        want = [f for f in fill if f.get("slot") == sid]
        got = sorted([m for m in mains if m[3] == sid], key=lambda m: m[0])
        if not want:
            continue
        seq = s.get("order") == "sequence"
        uses = ", ".join(str(f.get("use")) for f in want)
        if not got:
            out.append(f"{cid}: slot {sid} is empty. slide_plan put {uses} in this slot. Add that material's layer with "
                       f"\"slot\": \"{sid}\".")
            continue
        if not seq and len(got) > 1:
            out.append(f"{cid}: slot {sid} has {len(got)} main layers ({', '.join(m[2] for m in got)}). This slot shows "
                       f"only {uses}; merge them into one layer.")
            continue
        if seq and len(got) != len(want):
            out.append(f"{cid}: slot {sid} shows materials one after another; slide_plan has {len(want)} materials "
                       f"({uses}) but there are {len(got)} layers. Add one layer per material, one after another "
                       f"without overlapping in time.")
            continue
        for f, m in zip(want, got):
            if not _kind_ok(str(f.get("use") or ""), m[2]):
                out.append(f"{cid}: the material of slot {sid} is {f.get('use')} but the layer is {m[2]}. Use the screen "
                           f"template that fits the material (photo or generated picture: PhotoCard; chart or formula: "
                           f"its chart template; contents, steps: RouteMap, Steps; numbers: NumberCard or HtmlSlide; "
                           f"text: HtmlSlide or BigText).")
        if seq:
            out += _seq_times(cid, sid, want, got, timing_cut, L)
    return out


def _seq_times(cid, sid, want, got, timing_cut, L) -> list[str]:
    """A sequence slot: items one after another, each starting at its word."""
    out = []
    words = timing_cut.get("words") or []
    for k, (f, m) in enumerate(zip(want, got)):
        t0 = 0.0 if k == 0 else L.word_time(words, f.get("at") or "")
        if t0 is not None and abs(m[0] - t0) > SEQ_TOL:
            when = "the first material at 0 s" if k == 0 else f"the line says \"{f.get('at')}\" at {_num(t0)} s, so it shows then"
            prev = f" (and the end of the material before it {_num(t0)})" if k else ""
            out.append(f"{cid}: material {k + 1} of slot {sid} ({f.get('use')}, {m[2]}) starts at {_num(m[0])} s; "
                       f"{when}. Set start to {_num(t0)}{prev}.")
        if k + 1 < len(got) and got[k + 1][0] < m[1] - 0.05:
            out.append(f"{cid}: material {k + 1} of slot {sid} ({_num(m[0])}-{_num(m[1])} s) overlaps the next one "
                       f"(start {_num(got[k + 1][0])} s). Set the end of the first to {_num(got[k + 1][0])}.")
        elif k + 1 < len(got) and got[k + 1][0] > m[1] + 0.6:
            out.append(f"{cid}: material {k + 1} of slot {sid} ends at {_num(m[1])} s and the next starts at "
                       f"{_num(got[k + 1][0])} s, so the slot goes empty. Extend the end of the first to "
                       f"{_num(got[k + 1][0])}.")
    return out


def _scene(tl, narration, slide_plan, plan, seconds) -> list[str]:
    """Every cut of this scene's narration is in the timeline once, in order, and part_id is slide_plan's."""
    out = []
    want = [c["cut_id"] for c in _cuts_of(narration)]
    got = [c["cut_id"] for c in tl["cuts"]]
    if want:
        scene = ", ".join(want)
        for cid in want:
            if cid not in got:
                out.append(f"timeline has no cut {cid} (the cuts of this scene: {scene}; each must be in timeline.cuts "
                           f"once). Make the layers of {cid} and add it to cuts"
                           f"{_needs(cid, plan.get(cid), seconds.get(cid))}.")
        for cid in sorted(set(got) - set(want)):
            out.append(f"cut {cid} is not a cut of this scene (the cuts of this scene: {scene}). Remove it from timeline.")
        for cid in sorted({x for x in got if got.count(x) > 1}):
            out.append(f"cut {cid} is in timeline {got.count(cid)} times. Keep only one.")
        kept = [x for x in got if x in want]
        if not out and kept != want:
            out.append(f"the cut order differs from the narration (now: {', '.join(kept)}). Put them in the order {scene}.")
    part = str((slide_plan or {}).get("part_id") or "")
    if not part and narration and narration.get("piece_id"):
        part = str(narration["piece_id"]).split("-s")[0]
    if part and str(tl.get("part_id") or "") != part:
        out.append(f"timeline part_id is \"{tl.get('part_id') or ''}\". Copy slide_plan's part_id (\"{part}\") as it is.")
    return out


def _needs(cid, plan_cut, secs) -> str:
    """What a cut's screen needs, from slide_plan and timing (as a parenthesis, or "")."""
    bits = []
    if plan_cut:
        lay = plan_cut.get("layout") or ""
        bits.append(f"slide_plan: {LAYOUT_NAMES.get(lay, lay)}")
        fill = plan_cut.get("fill") or []
        if fill:
            bits.append("slots: " + ", ".join(f"{f.get('slot')}={f.get('use')}" for f in fill))
    if isinstance(secs, (int, float)):
        bits.append(f"it lasts {_num(secs)} s, so layers run from 0 to {_num(secs + BREATH)} s")
    return f" ({'; '.join(bits)})" if bits else ""


def _times(at, ly, limit, secs) -> list[str]:
    """0 <= start < end <= cut length + 0.4, with the values and the numbers to use."""
    s, e = ly["start"], ly["end"]
    out = []
    if s < 0 or e <= s:
        end_to = _num(limit) if limit is not None else _num(max(e, max(s, 0) + 1))
        out.append(f"{at}: the times do not work (start {_num(s)}, end {_num(e)}). start must be 0 or more and less than "
                   f"end. E.g. start {_num(max(s, 0)) if s < e else 0}, end {end_to}.")
    elif limit is not None and e > limit + 0.05:
        out.append(f"{at}: end is {_num(e)} s, {_num(e - limit)} s past the end of the cut (cut length {_num(secs)} s + "
                   f"{BREATH} = {_num(limit)} s). Set end to {_num(limit)} or less.")
    return out


def _photo_box(at, p) -> list[str]:
    """PhotoCard pixels inside 1280 x 720, with how far past and the values to use."""
    box = {k: p.get(k) for k in ("x", "y", "w", "h") if p.get(k) is not None}
    bad = [k for k, v in box.items() if not isinstance(v, (int, float)) or isinstance(v, bool)]
    if bad:
        return [f"{at}: {k} is not a number ({box[k]!r}). Write a number of pixels (e.g. 260)." for k in bad]
    out = []
    for pos, size, full, edge, axis in (("x", "w", W, "right", "width"), ("y", "h", H, "bottom", "height")):
        if pos in box and size in box and box[pos] > 1 and box[size] > 1 and box[pos] + box[size] > full:
            a, b = box[pos], box[size]
            over = a + b - full
            out.append(f"{at}: the photo goes {_num(over)}px past the {edge} edge ({pos} {_num(a)} + {size} {_num(b)} = "
                       f"{_num(a + b)}, screen {axis} {full}). Set {size} to {_num(full - a)} or less, or move {pos} to "
                       f"{_num(max(full - b, 0))} or less.")
    return out


_FOREIGN = re.compile("[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def _foreign(value) -> list[str]:
    """Korean, Chinese or Japanese characters anywhere in the value (LaTeX and file paths included)."""
    return sorted(set(_FOREIGN.findall(json.dumps(value, ensure_ascii=False))))[:5]


def _foreign_all(tl) -> list[str]:
    out = []
    for c in tl["cuts"]:
        bad = _foreign(c)
        if bad:
            out.append(f"{c['cut_id']}: write English only; replace these Korean/Chinese/Japanese characters: "
                       f"{', '.join(bad)}.")
    rest = _foreign({k: v for k, v in tl.items() if k != "cuts"})
    if rest:
        out.append(f"timeline: write English only; replace these Korean/Chinese/Japanese characters: {', '.join(rest)}.")
    return out


def _selector_at(css: str, pos: int) -> str:
    """The CSS selector whose block holds position pos."""
    start = css.rfind("{", 0, pos)
    if start < 0:
        return ""
    prev = max(css.rfind("}", 0, start), css.rfind("{", 0, start), css.rfind(";", 0, start))
    return " ".join(css[prev + 1:start].split())


def _small_fonts(html: str, css: str) -> list[str]:
    """Where a font-size below 22px is: "CSS .src 18px" or "HTML <span class="tag"> 18px"."""
    out = []
    for m in re.finditer(r"font-size\s*:\s*([\d.]+)px", css):
        if float(m.group(1)) < 22:
            out.append(f"CSS {_selector_at(css, m.start()) or '(no selector)'} {_num(m.group(1))}px")
    for tag in re.finditer(r"<(\w+)([^>]*)>", html):
        st = re.search(r"style\s*=\s*\"([^\"]*)\"", tag.group(2))
        for m in re.finditer(r"font-size\s*:\s*([\d.]+)px", st.group(1) if st else ""):
            if float(m.group(1)) < 22:
                cls = re.search(r"class\s*=\s*\"([^\"]*)\"", tag.group(2))
                el = f"<{tag.group(1)}{' class=' + chr(34) + cls.group(1) + chr(34) if cls else ''}>"
                out.append(f"HTML {el} {_num(m.group(1))}px")
    return out


def _html(p) -> list[str]:
    """HtmlSlide: no scripts or web addresses, readable font sizes, every img: name given in images as a real file."""
    out = []
    html, css, images = str(p.get("html") or ""), str(p.get("css") or ""), p.get("images") or {}
    both = html + css
    hit = re.search(r"<script|javascript:|on\w+\s*=", both, re.I)
    if hit:
        out.append(f"it has a script or event handler (\"{hit.group(0)}\"). Motion is set only with data-at and data-on; "
                   f"remove this part.")
    hit = re.search(r"https?://\S{0,40}|@import|url\(", both, re.I)
    if hit:
        out.append(f"it loads something from the web (\"{hit.group(0)}\"). The screen cannot load anything from the "
                   f"web; remove it. Pictures go in with <img src=\"img:name\"> and images.")
    small = _small_fonts(html, css)
    if small:
        out.append(f"text smaller than 22px is hard to read in a video: {', '.join(small)}. Make it 22px or more "
                   f"(kicker and source 22-24px).")
    for name in re.findall(r'src="img:([^"]+)"', html):
        path = images.get(name)
        if not path:
            out.append(f"the file of picture img:{name} is not in images. Add {{\"{name}\": the path of that picture from "
                       f"the image or generated file list}} to images.")
        elif not pathlib.Path(str(path)).is_file():
            out.append(f"the file of picture img:{name} is not on this computer (images path \"{path}\"). Copy the path "
                       f"(local file path) of that picture from the image or generated file list as it is.")
    if not re.search(r"data-at=", html):
        out.append("there is no data-at. Put data-at=\"0\" on the main element and, on the other main elements, the "
                   "second the line says them (timing words).")
    return out


def _overflow():
    """tools/_overflow.py (loaded by path: the checker may run without the project on sys.path)."""
    path = pathlib.Path(__file__).resolve().parents[2] / "tools" / "_overflow.py"
    spec = importlib.util.spec_from_file_location("naw_overflow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _measure():
    return _overflow().measure_layer


def _type_rules():
    return _overflow().type_problems


def _spec(outputs, screen_cuts) -> list[str]:
    """design_spec: one entry per screen cut, one main element, at most 2 supporting ones, readable type."""
    out = []
    listed = [x["cut_id"] for x in outputs["design_spec"]["screens"]]
    spec = {x["cut_id"]: x for x in outputs["design_spec"]["screens"]}
    screens = ", ".join(screen_cuts) or "none"
    for cid in screen_cuts:
        if cid not in spec:
            out.append(f"design_spec has no screen {cid}. Write one per screen cut ({screens}): add intent, layout, "
                       f"elements and emphasis for {cid}.")
    for cid in sorted({x for x in listed if listed.count(x) > 1}):
        out.append(f"design_spec has {cid} {listed.count(cid)} times. Merge them into one.")
    for cid, x in spec.items():
        if cid not in screen_cuts:
            out.append(f"design_spec entry {cid} is not a screen cut (a title or end card cut, or a cut with no content "
                       f"screen in timeline). The screen cuts are {screens}; remove entry {cid}.")
        mains = [e["name"] for e in x["elements"] if e["role"] == "main"]
        if not mains:
            out.append(f"design_spec {cid} has no element with role main. Set role main on the one element the viewer "
                       f"should see first.")
        elif len(mains) > 1:
            out.append(f"design_spec {cid} has {len(mains)} elements with role main ({', '.join(mains)}). Keep main only "
                       f"on the one the viewer should see first and make the other {len(mains) - 1} support or label.")
        for e in x["elements"]:
            if 0 < e["font_size"] < 22:
                out.append(f"design_spec {cid} '{e['name']}': font_size is {e['font_size']}px. Make it 22px or more and "
                           f"fix the HTML and CSS the same way (0 for a picture or chart).")
    return out
