"""Helpers that make the screen fix loop converge (2026-11-11). A helper, not a tool (the name starts with _).

- Lock what passed: when check_layout sends work back, every fix item names its cut and, when known, the layers
  (indexes in the timeline it measured) that may change. Everything else is locked: the editor checker refuses a change
  to a locked cut or layer, the designer checker a change to the layout or fill of a locked cut.
- Stable review: check_layout keeps the reviewer's per-cut verdict for cuts that did not change since the last
  iteration, and inspect_screens tells the reviewer which cuts changed and what it said last time.
- Measured items: inspect_screens saves the program's measured items of a timeline (.cache/screen_measures/) so the
  reviewer's checker can refuse a checklist that leaves one out, changes its id or invents numbers.

A layer is identified by (type, slot, n-th layer of that type and slot in the cut), so moving a layer to another place
in the list is no change. Workers' checkers load this file by path (they may run without the project on sys.path)."""

import json
import pathlib

BASIS = "review_basis.json"      # check_layout writes it each iteration: the effective checklist, timeline, plan


# ------------------------------------------------------------------ what may change

def free_of(fix_these: list, causes: tuple = ("redesign", "rebuild")) -> dict:
    """{cut id: None (the whole cut may change) or set of layer indexes} from fix items with "cut" (and "layers")."""
    out: dict = {}
    for x in fix_these or []:
        if not isinstance(x, dict) or x.get("cause", "rebuild") not in causes or not x.get("cut"):
            continue
        cid, lys = str(x["cut"]), x.get("layers")
        if lys is None or cid in out and out[cid] is None:
            out[cid] = None
        else:
            out.setdefault(cid, set()).update(int(i) for i in lys)
    return out


def layer_keys(cut: dict) -> list[tuple]:
    """The identity of every layer of a cut, by index: (type, slot, n)."""
    seen: dict = {}
    out = []
    for ly in cut.get("layers") or []:
        k = (str(ly.get("type")), str(ly.get("slot") or ""))
        seen[k] = seen.get(k, 0) + 1
        out.append((*k, seen[k]))
    return out


def _say(key: tuple) -> str:
    t, slot, n = key
    return f"{t}{f' (slot {slot})' if slot else ''}{f' no. {n}' if n > 1 else ''}"


def _short(v, n: int = 60) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def _text_diff(a: str, b: str) -> str:
    """Where two long strings first differ, as a short "old" -> "new" pair."""
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    lo = max(0, i - 15)
    return f"\"…{a[lo:i + 30]}…\" -> \"…{b[lo:i + 30]}…\""


def _changes(old: dict, new: dict) -> list[str]:
    """The properties that differ between two versions of one layer, each as 'property: old -> new'."""
    out = []
    for k in ("start", "end", "slot"):
        if old.get(k) != new.get(k):
            out.append(f"{k} {_short(old.get(k))} -> {_short(new.get(k))}")
    po, pn = old.get("props") or {}, new.get("props") or {}
    for k in sorted(set(po) | set(pn)):
        if po.get(k) == pn.get(k):
            continue
        if isinstance(po.get(k), str) and isinstance(pn.get(k), str) and max(len(po[k]), len(pn[k])) > 60:
            out.append(f"props.{k} {_text_diff(po[k], pn[k])}")
        else:
            out.append(f"props.{k} {_short(po.get(k))} -> {_short(pn.get(k))}")
    rest = sorted((set(old) | set(new)) - {"start", "end", "slot", "props", "type"})
    for k in rest:
        if old.get(k) != new.get(k):
            out.append(f"{k} {_short(old.get(k))} -> {_short(new.get(k))}")
    return out


def timeline_lock_errors(new_tl: dict, last_tl: dict, free: dict) -> list[str]:
    """The editor's lock: every cut / layer of the last timeline that is not free must stay as it was."""
    errors = []
    new_of = {str(c.get("cut_id")): c for c in (new_tl or {}).get("cuts") or [] if isinstance(c, dict)}
    for old in (last_tl or {}).get("cuts") or []:
        cid = str(old.get("cut_id"))
        if cid not in new_of or free.get(cid, set()) is None:
            continue                                  # a missing cut is the scene check's job; None = whole cut free
        new, ok_idx = new_of[cid], free.get(cid, set())
        if not ok_idx and str(new.get("layout") or "") != str(old.get("layout") or ""):
            errors.append(f"{cid} passed the last check and is locked (not in fix_these), but its layout changed "
                          f"from \"{old.get('layout')}\" to \"{new.get('layout')}\". Set it back to "
                          f"\"{old.get('layout')}\".")
        ok_keys = {k for i, k in enumerate(layer_keys(old)) if i in ok_idx}
        old_by = dict(zip(layer_keys(old), old.get("layers") or []))
        new_by = dict(zip(layer_keys(new), new.get("layers") or []))
        whole = "cut" if not ok_idx else "layer"
        for key, oly in old_by.items():
            if key in ok_keys:
                continue
            nly = new_by.get(key)
            if nly is None:
                errors.append(f"{cid}: the {_say(key)} layer passed the last check and is locked, but it is missing. "
                              f"Put that layer back exactly as it is in {cid} of your_last_timeline.")
                continue
            diff = _changes(oly, nly)
            if diff:
                errors.append(f"{cid}: the {_say(key)} layer is in a {whole} that passed the last check and is locked "
                              f"(not in fix_these). Changed: {'; '.join(diff[:3])}. Set it back to the last values "
                              f"(change only what fix_these names).")
        if not ok_idx:
            for key in new_by:
                if key not in old_by:
                    errors.append(f"{cid} passed the last check and is locked, but it has a new {_say(key)} layer "
                                  f"that was not there last time. Remove this layer.")
    return errors


def _fill_key(fill: list) -> list:
    return sorted((str(f.get("slot")), str(f.get("use")), json.dumps(f.get("lines") or [], ensure_ascii=False),
                   str(f.get("at") or "")) for f in fill or [] if isinstance(f, dict))


def plan_lock_errors(new_plan: dict, last_plan: dict, free_cuts: set) -> list[str]:
    """The designer's lock: a cut not named by a redesign item keeps its layout and fill exactly."""
    errors = []
    new_of = {str(c.get("cut_id")): c for c in (new_plan or {}).get("cuts") or [] if isinstance(c, dict)}
    for old in (last_plan or {}).get("cuts") or []:
        cid = str(old.get("cut_id"))
        new = new_of.get(cid)
        if new is None or cid in free_cuts:
            continue
        if str(new.get("layout")) != str(old.get("layout")):
            errors.append(f"{cid} is not a cut to fix (no redesign item in fix_these names it), so it is locked, but its "
                          f"layout changed from \"{old.get('layout')}\" to \"{new.get('layout')}\". Set it back to "
                          f"\"{old.get('layout')}\" as in your_last_plan.")
        if _fill_key(new.get("fill")) != _fill_key(old.get("fill")):
            was = ", ".join(f"{f.get('slot')}={f.get('use')}" for f in old.get("fill") or [])
            now = ", ".join(f"{f.get('slot')}={f.get('use')}" for f in new.get("fill") or [])
            errors.append(f"{cid} is not a cut to fix, so it is locked, but its fill changed (last time: {was or 'none'}; "
                          f"now: {now or 'none'}). Copy the fill of {cid} from your_last_plan exactly (slot, use, lines, at).")
    return errors


def restore_locked(new_tl: dict, last_tl: dict, free: dict, new_spec: dict | None = None,
                   last_spec: dict | None = None) -> list[str]:
    """The program keeps what passed: every locked cut / layer of the last timeline is copied back into new_tl (in
    place), so the slide builder only has to get the fix_these parts right. A wholly locked cut (and its design_spec
    screen) is taken from the last version as it was; in a cut with free layers the locked layers are taken from the
    last version and the free ones from the new output. -> notes on what was put back."""
    import copy
    notes = []
    old_cuts = [c for c in (last_tl or {}).get("cuts") or [] if isinstance(c, dict)]
    new_of = {str(c.get("cut_id")): c for c in (new_tl or {}).get("cuts") or [] if isinstance(c, dict)}
    merged, whole_locked = [], []
    for old in old_cuts:
        cid = str(old.get("cut_id"))
        ok = free.get(cid, set())
        new = new_of.pop(cid, None)
        if ok is None:                                   # the whole cut is to fix: the new output as it is
            if new is not None:
                merged.append(new)
            continue
        if not ok or new is None:                        # wholly locked (or left out): the last version
            if new is None or new != old:
                notes.append(f"{cid} is locked: taken from your_last_timeline")
            merged.append(copy.deepcopy(old))
            whole_locked.append(cid)
            continue
        old_keys, new_keys = layer_keys(old), layer_keys(new)
        free_keys = {k for i, k in enumerate(old_keys) if i in ok}
        new_by = dict(zip(new_keys, new.get("layers") or []))
        layers, put_back = [], 0
        for k, oly in zip(old_keys, old.get("layers") or []):
            if k in free_keys:
                if k in new_by:
                    layers.append(new_by[k])
            else:
                if new_by.get(k) != oly:
                    put_back += 1
                layers.append(copy.deepcopy(oly))
        layers += [ly for k, ly in zip(new_keys, new.get("layers") or []) if k not in old_keys]
        if put_back:
            notes.append(f"{cid}: {put_back} locked layer(s) taken from your_last_timeline")
        merged.append({**new, "layout": old.get("layout"), "layers": layers})
    merged += list(new_of.values())                       # cuts the last version did not have
    new_tl["cuts"] = merged
    if new_spec is not None and last_spec and whole_locked:
        last_screens = {str(x.get("cut_id")): x for x in last_spec.get("screens") or [] if isinstance(x, dict)}
        screens = [x for x in new_spec.get("screens") or [] if str(x.get("cut_id")) not in whole_locked]
        screens += [copy.deepcopy(last_screens[c]) for c in whole_locked if c in last_screens]
        order = [str(c.get("cut_id")) for c in merged]
        screens.sort(key=lambda x: order.index(str(x.get("cut_id"))) if str(x.get("cut_id")) in order else len(order))
        new_spec["screens"] = screens
    return notes


def locked_summary(last_tl: dict, free: dict) -> list[dict]:
    """What is locked, for the feedback: [{cut, whole, layers: [{index, type, slot, start, end}]}]; the values are
    in your_last_timeline."""
    out = []
    for c in (last_tl or {}).get("cuts") or []:
        cid = str(c.get("cut_id"))
        if free.get(cid, set()) is None:
            continue
        ok = free.get(cid, set())
        lys = [{"index": i, "type": ly.get("type"), "slot": ly.get("slot") or "", "start": ly.get("start"),
                "end": ly.get("end")} for i, ly in enumerate(c.get("layers") or []) if i not in ok]
        out.append({"cut": cid, "whole": not ok, "layers": lys})
    return out


# ------------------------------------------------------------------ stable review

def changed_cuts(old_tl: dict, new_tl: dict, old_plan: dict | None = None, new_plan: dict | None = None) -> list[str]:
    """Cuts of the new timeline whose screen (layout, layers) or plan (layout, fill) differs from the old one."""
    old_of = {str(c.get("cut_id")): c for c in (old_tl or {}).get("cuts") or [] if isinstance(c, dict)}
    po = {str(c.get("cut_id")): c for c in (old_plan or {}).get("cuts") or [] if isinstance(c, dict)}
    pn = {str(c.get("cut_id")): c for c in (new_plan or {}).get("cuts") or [] if isinstance(c, dict)}
    out = []
    for c in (new_tl or {}).get("cuts") or []:
        cid = str(c.get("cut_id"))
        o = old_of.get(cid)
        same = (o is not None and str(o.get("layout") or "") == str(c.get("layout") or "")
                and dict(zip(layer_keys(o), o.get("layers") or [])) == dict(zip(layer_keys(c), c.get("layers") or [])))
        if same and (po or pn):
            a, b = po.get(cid) or {}, pn.get(cid) or {}
            same = str(a.get("layout")) == str(b.get("layout")) and _fill_key(a.get("fill")) == _fill_key(b.get("fill"))
        if not same:
            out.append(cid)
    return out


def previous_basis(files_dir, iteration: int) -> dict | None:
    """The review basis check_layout wrote in the iteration before (blocks/<id>/iter-<n-1>/attempt-*/files/)."""
    if not iteration or iteration < 2:
        return None
    here = pathlib.Path(files_dir)                  # .../blocks/<id>/iter-<n>/attempt-<m>/files
    prev = here.parents[2] / f"iter-{iteration - 1}"
    for a in sorted(prev.glob("attempt-*"), key=lambda p: int(p.name.split("-")[1]), reverse=True):
        f = a / "files" / BASIS
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
    return None


def stable_checklist(checklist: dict, last: dict | None, changed: list[str]) -> tuple[dict, list[str]]:
    """The reviewer's per-cut checklist with the last verdict kept for unchanged cuts: for a cut that did not change,
    the last checklist's entry for that cut (ok, problems) is used and the new one is dropped.
    -> (effective checklist, notes)."""
    if not last:
        return checklist, []
    keep = set(changed)
    last_of = {str(c.get("cut")): c for c in last.get("cuts") or [] if isinstance(c, dict)}
    cuts, notes = [], []
    for c in checklist.get("cuts") or []:
        cid = str(c.get("cut"))
        old = last_of.get(cid)
        if cid in keep or old is None:
            cuts.append(c)
            continue
        if (c.get("problems") or []) != (old.get("problems") or []):
            notes.append(f"{cid} shows the same screen as last time, so the reviewer's last verdict for it stays (the "
                         f"new remarks are not used).")
        cuts.append(old)
    return {**checklist, "cuts": cuts}, notes


# ------------------------------------------------------------------ measured items for the reviewer

MEASURES = pathlib.Path(__file__).resolve().parents[1] / ".cache" / "screen_measures"


def timeline_key(tl: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(tl or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


def save_measures(tl: dict, items: list[dict]) -> None:
    """The program's measured items of a timeline (check_layout.measure_scene), for the reviewer's checker."""
    MEASURES.mkdir(parents=True, exist_ok=True)
    keep = [{k: x.get(k) for k in ("what", "cut", "where", "now", "change_to", "why")} for x in items]
    (MEASURES / f"{timeline_key(tl)}.json").write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")


def save_members(tl: dict, members: dict | None) -> None:
    """{material id: [cut ids]} from the makers' reports (tools/_cuts.py material_cuts) for this timeline, so the
    reviewer's checker sees the same unused candidates of a cut as inspect_screens."""
    if not members:
        return
    MEASURES.mkdir(parents=True, exist_ok=True)
    (MEASURES / f"{timeline_key(tl)}.members.json").write_text(json.dumps(members, ensure_ascii=False), encoding="utf-8")


def load_members(tl: dict) -> dict | None:
    """The material -> cuts map saved for exactly this timeline, or None."""
    f = MEASURES / f"{timeline_key(tl)}.members.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except ValueError:
        return None


def load_measures(tl: dict) -> list[dict] | None:
    """The measured items saved for exactly this timeline, or None when it was not measured."""
    f = MEASURES / f"{timeline_key(tl)}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except ValueError:
        return None


def allowed_changes(plan: dict, L, members: dict | None = None) -> dict:
    """{cut id: what the screen designer may change in that content cut}: the layouts that hold the cut's material
    count (other than the current one), the candidates of that cut not used in it (from slide_plan fill and dropped,
    ids <prefix>-<cut id>-<n>), and the text slots she wrote (use "lines"). L: tools/_layouts.py.
    members: {material id: [cut ids]} from the makers' reports; when given, a material belongs to every cut whose
    report lists it (a material may serve several cuts), otherwise to the cut named in its id."""
    def of_cut(x, cid):
        return cid in members[x] if members and x in members else f"-{cid}-" in x
    cuts = [c for c in (plan or {}).get("cuts") or [] if isinstance(c, dict)]
    ids = set()
    for c in cuts:
        ids |= {str(f.get("use")) for f in c.get("fill") or [] if f.get("use") and f.get("use") != "lines"}
        ids |= {str(d.get("id")) for d in c.get("dropped") or [] if d.get("id")}
    out = {}
    for c in cuts:
        cid, lay = str(c.get("cut_id")), str(c.get("layout") or "")
        if lay in ("title", "end"):
            continue
        fill = c.get("fill") or []
        used = {str(f.get("use")) for f in fill}
        out[cid] = {"layout": lay, "materials": L.material_count(fill),
                    "layouts": L.layouts_for(L.material_count(fill), exclude=(lay,),
                                             kinds=[L.id_kind(u) for u in used if u != "lines"]),
                    "candidates": sorted(x for x in ids if of_cut(x, cid) and x not in used),
                    "text_slots": [str(f.get("slot")) for f in fill if f.get("use") == "lines"]}
    return out
