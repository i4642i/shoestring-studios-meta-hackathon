"""Site adapter: everything the Shoestring site reads from nextop run records (runs/<id>/).

One module so the record layout (docs/ENGINE_INTERFACE.md) is adjusted in one place:
  run_state(run_id)      Studio bar / Order live card: state, current, cost
  office(run_id)         3D office: one live card per character (seated, bubble, red)
  gallery_cards(orders)  Gallery: finished videos with title, length, cost
  pcs_list / pc_entries / pc_rights   PC tab: the six file servers of a run
Read only, except the small site files under runs/.shoestring/ (pause marks, process ids, thumbnails).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import time

from nextop import records

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
SITE = RUNS / ".shoestring"          # site-only notes per run (ignored by nextop: no status.json)
IMAGE_USD = 0.01                     # muse-image-1.0, per generated image

# The six server PCs of the original, in the original order. "aliases": file server names seen in runs.
PCS = [
    {"id": "source", "name": "Source PC", "aliases": ["source"],
     "holds": "Parsed client documents: markdown, figures, sections.",
     "add": "parser only (the PDF Sam passed on)"},
    {"id": "theory", "name": "Theory PC", "aliases": ["theory"],
     "holds": "Concept explanations, lectures, papers.",
     "add": "Cleo (concept explainer) picks only"},
    {"id": "article", "name": "Article PC", "aliases": ["article", "cases"],
     "holds": "Cases: events, companies, people, films.",
     "add": "Rex (case researcher) picks only"},
    {"id": "image", "name": "Image PC", "aliases": ["image"], "media": True,
     "holds": "Licensed web photos Pia picked: file, URL, license.",
     "add": "Pia (photo researcher) picks only"},
    {"id": "generated", "name": "Generated PC", "aliases": ["generated"], "media": True,
     "holds": "Gene's generated concept images: file, prompt, model.",
     "add": "Gene (image generator) only"},
    {"id": "voice", "name": "Voice PC", "aliases": ["voice"], "media": True,
     "holds": "Wren's narration audio per cut: file, text, seconds.",
     "add": "Wren (narrator) only"},
]

FUNCTION_PHRASES = {
    "parser": "Reading your PDF",
    "split": "Splitting the storyboard into parts",
    "render": "Rendering the part video",
    "gather": "Gathering the parts",
    "assemble": "Assembling the final video",
    "check_design": "Checking the screens",
    "check_layout": "Checking the screens",
}


# ------------------------------------------------------------------ small readers
def _read(p: pathlib.Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: pathlib.Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _tail_line(p: pathlib.Path) -> dict | None:
    """Last complete JSON line of a .jsonl file (reads only the end of the file)."""
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
            chunk = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(chunk.splitlines()):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return None


def run_ok(run_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", run_id or "")) and (RUNS / run_id / "status.json").is_file()


def run_dir(run_id: str) -> pathlib.Path:
    return RUNS / run_id


def site_note(run_id: str) -> dict:
    return _read(SITE / f"{run_id}.json", {}) or {}


def set_site_note(run_id: str, **kw) -> dict:
    note = site_note(run_id)
    note.update(kw)
    _write(SITE / f"{run_id}.json", note)
    return note


# ------------------------------------------------------------------ crew
def load_crew() -> list[dict]:
    data = _read(ROOT / "data" / "crew.json", {}) or {}
    return [c for c in data.get("crew", []) if isinstance(c, dict) and c.get("id")]


def worker_names() -> dict[str, dict]:
    """block/worker id -> {name, title} from workers/<id>/worker.json (the engine's display names)."""
    out = {}
    for p in (ROOT / "workers").glob("*/worker.json"):
        w = _read(p, {}) or {}
        out[p.parent.name] = {"name": str(w.get("name") or p.parent.name), "title": str(w.get("title") or "")}
    return out


def crew_of_block(crew: list[dict]) -> dict[str, str]:
    out = {}
    for c in crew:
        for b in c.get("blocks", []):
            out[b] = c["id"]
    return out


def base_of(block: str) -> str:
    return block.split("@", 1)[0]


def copy_no(block: str) -> str:
    return block.split("@", 1)[1] if "@" in block else ""


# ------------------------------------------------------------------ process tracking
def pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259           # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_tree(pid) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(int(pid))], capture_output=True, timeout=30)
    else:
        try:
            os.killpg(os.getpgid(int(pid)), 15)
        except (ProcessLookupError, PermissionError):
            pass


def process_alive(run_id: str) -> bool:
    return pid_alive(site_note(run_id).get("pid"))


# ------------------------------------------------------------------ cost
def cost_of(run_id: str) -> dict:
    d = run_dir(run_id)
    c = _read(d / "cost.json", {}) or {}
    usage = c.get("usage") or {}
    img = _read(d / "image_cost.json", {}) or {}
    images = int(img.get("images") or 0)
    usd = float(img.get("usd") if img.get("usd") is not None else images * IMAGE_USD)
    return {"llm_calls": int(c.get("calls") or 0), "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0), "images": images,
            "usd": round(usd, 2), "llm_usd": 0.0}


def cost_text(cst: dict) -> str:
    return "$%.2f (qwen free + %d image%s)" % (cst["usd"], cst["images"], "" if cst["images"] == 1 else "s")


# ------------------------------------------------------------------ run state
def _status(run_id: str) -> dict:
    return _read(run_dir(run_id) / "status.json", {}) or {}


def _as_list(v) -> list[str]:
    if isinstance(v, dict):
        return [str(k) for k in v]
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def site_state(run_id: str, st: dict | None = None) -> str:
    """running / paused / review / done / stopped / error (the Studio chip names)."""
    st = st if st is not None else _status(run_id)
    s = str(st.get("status") or "unknown")
    note = site_note(run_id)
    if s == "running":
        if not note.get("pid"):
            # Started outside the site (e.g. `nextop run` in a console): no process to check, so trust
            # nextop's status; reporting "stopped" would offer Resume and start a second process.
            return "running"
        if process_alive(run_id):
            return "pausing" if note.get("pausing") else "running"
        return "paused" if note.get("paused") else "stopped"
    if s == "review":
        return "review"
    if s == "failed":
        return "paused" if note.get("paused") else "error"
    if s == "stopped":
        return "paused" if note.get("paused") else "stopped"
    return s


def run_state(run_id: str) -> dict:
    st = _status(run_id)
    if not st:
        return {"ok": False, "error": "no such run: " + run_id}
    crew = load_crew()
    owner = crew_of_block(crew)
    state = site_state(run_id, st)
    running = _as_list(st.get("running"))
    cur = ""
    for b in running:
        cid = owner.get(base_of(b))
        if cid:
            cur = cid + ("@p" + copy_no(b) if copy_no(b) else "")
            break
    note = site_note(run_id)
    review_who = []
    for b in _as_list(st.get("review")):
        cid = owner.get(base_of(b))
        if cid:
            review_who.append(cid + ("@p" + copy_no(b) if copy_no(b) else ""))
    return {"ok": True, "run_id": run_id, "state": state, "status": st.get("status"), "review_who": review_who,
            "step": bool(st.get("step")),
            "current": cur, "running": running, "completed": _as_list(st.get("done")),
            "failed": st.get("failed") or {}, "review": _as_list(st.get("review")),
            "error": str(st.get("reason") or ""), "cost": cost_of(run_id),
            "cost_text": cost_text(cost_of(run_id)), "pause_each_stage": bool(note.get("step")),
            "started": st.get("started"), "ended": st.get("ended")}


def runs_list() -> list[dict]:
    out = []
    for r in records.list_runs(ROOT):
        if r.path.name.startswith("."):
            continue
        st = _read(r.path / "status.json", {}) or {}
        if "ask" in (_read(r.path / "flow.json", {}) or {}):
            continue                                 # open questions are not productions
        out.append({"run_id": r.run_id, "flow": r.flow, "state": site_state(r.run_id, st),
                    "started": r.started, "ended": r.ended})
    return out


# ------------------------------------------------------------------ office cards
def _short(text: str, n: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def tool_phrase(call: dict | None) -> str:
    """A real tool call as a short plain phrase for the speech bubble."""
    if not call:
        return "Starting…"
    name = str(call.get("name") or "")
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    first = lambda v: (v[0] if isinstance(v, list) and v else v) or ""
    if name == "save_output":
        return "Writing the report…"
    if name == "news_search":
        return "Searching news: " + _short(first(args.get("keywords") or args.get("query")), 40)
    if name == "google_image_search":
        return "Searching photos: " + _short(first(args.get("queries") or args.get("query")), 40)
    if name == "fetch_image":
        return "Fetching photos"
    if name == "generate_image":
        return "Generating an image: " + _short(args.get("prompt"), 40)
    if name == "preview_materials":
        return "Previewing materials"
    if name == "preview_slides":
        return "Previewing slides"
    if name == "inspect_screens":
        return "Checking the screens"
    if name == "voice_lines":
        return "Recording narration"
    m = re.fullmatch(r"([a-z]+)_(get|query|search|upload|share|list)", name)
    if m:
        fs, verb = m.groups()
        fs = {"cases": "article", "materials": "materials"}.get(fs, fs)
        if verb == "get":
            return "Reading " + _short(args.get("address") or fs, 40)
        if verb in ("query", "search"):
            return "Searching %s: %s" % (fs, _short(args.get("question") or args.get("query"), 40))
        if verb == "upload":
            return "Saving to the %s PC" % fs
        if verb == "share":
            return "Sharing %s files" % fs
        return "Listing %s files" % fs
    return _short(name.replace("_", " ").capitalize(), 40) or "Working…"


def _last_tool(d: pathlib.Path, block: str) -> dict | None:
    att = records.attempt_dirs(d / "blocks" / block)
    return _tail_line(att[-1] / "tools.jsonl") if att else None


def _instances(d: pathlib.Path, st: dict) -> list[str]:
    seen = set(_as_list(st.get("done")) + _as_list(st.get("running")) + _as_list(st.get("failed"))
               + _as_list(st.get("review")))
    bd = d / "blocks"
    if bd.is_dir():
        seen.update(p.name for p in bd.iterdir() if p.is_dir())
    return sorted(seen, key=lambda b: (base_of(b), int(copy_no(b)) if copy_no(b).isdigit() else 0))


def office(run_id: str) -> dict:
    d = run_dir(run_id)
    st = _status(run_id)
    if not st:
        return {"ok": False, "error": "no such run: " + run_id}
    state = site_state(run_id, st)
    crew = load_crew()
    names = worker_names()
    running = set(_as_list(st.get("running")))
    done = set(_as_list(st.get("done")))
    failed = st.get("failed") if isinstance(st.get("failed"), dict) else {}
    review = set(_as_list(st.get("review")))
    inst = _instances(d, st)
    employees = []
    for c in crew:
        mine = [b for b in inst if base_of(b) in c.get("blocks", [])]
        card = {"id": c["id"], "stage": "waiting", "bubble": "", "red": False, "seated": False, "still": False,
                "blocks": mine}
        multi = len(c.get("blocks", [])) > 1
        now = [b for b in mine if b in running] if state in ("running", "pausing") else []
        if now:
            bits = []
            for b in now[:3]:
                base = base_of(b)
                who = names.get(base, {}).get("name", "")
                label = ("P" + copy_no(b) + " ") if copy_no(b) else ""
                if multi and who and who != c["name"] and base in names:
                    label = who + " " + label
                phrase = tool_phrase(_last_tool(d, b)) if base in names else FUNCTION_PHRASES.get(base, "Working…")
                bits.append((label + phrase).strip())
            if len(now) > 3:
                bits.append("+%d more" % (len(now) - 3))
            card.update(stage="working", bubble=" · ".join(bits)[:140], seated=True)
        elif any(b in review for b in mine):
            card.update(stage="review", bubble="Waiting for your review", seated=True)
        elif any(b in failed for b in mine):
            b = next(b for b in mine if b in failed)
            card.update(stage="error", bubble="Error: " + _short(failed[b], 80), red=True, seated=True)
        elif mine and all(b in done for b in mine) and (state == "done" or not _more_coming(c, inst, d)):
            card.update(stage="done", bubble="Done ✓", seated=True, still=True)
        elif mine and state in ("paused", "stopped", "review", "error"):
            card.update(stage="paused", bubble="⏸ Paused" if state != "error" else "Stopped", seated=True)
        elif mine:
            n_done = sum(1 for b in mine if b in done)
            card.update(stage="parts", bubble="Done %d/%d" % (n_done, _expected(c, inst, d)), seated=True)
        employees.append(card)
    return {"ok": True, "run_id": run_id, "state": state, "employees": employees}


def _copies(d: pathlib.Path) -> int:
    n = 0
    p = d / "events.jsonl"
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if '"section_expanded"' in line:
                try:
                    n = int(json.loads(line).get("copies") or n)
                except ValueError:
                    pass
    except OSError:
        pass
    return n


def _flow_bases(d: pathlib.Path) -> set[str]:
    f = _read(d / "flow.json", {}) or {}
    return {str(b.get("id")) for b in f.get("blocks", []) if isinstance(b, dict)}


def _expected(c: dict, inst: list[str], d: pathlib.Path) -> int:
    """How many block instances this character will run (copies count once the split happened)."""
    bases = [b for b in c.get("blocks", []) if b in _flow_bases(d)]
    copies = _copies(d)
    total = 0
    for base in bases:
        is_copy = any(base_of(b) == base and "@" in b for b in inst)
        total += copies if (is_copy and copies) else 1
    return max(total, 1)


def _more_coming(c: dict, inst: list[str], d: pathlib.Path) -> bool:
    mine = [b for b in inst if base_of(b) in c.get("blocks", [])]
    return len(mine) < _expected(c, inst, d)


# ------------------------------------------------------------------ gallery
def _video_of(d: pathlib.Path) -> tuple[pathlib.Path | None, dict]:
    for a in reversed(records.attempt_dirs(d / "blocks" / "assemble")):
        v = a / "files" / "video.mp4"
        if v.is_file() and (_read(a / "status.json", {}) or {}).get("status") == "done":
            return v, ((_read(a / "output.json", {}) or {}).get("video") or {})
    return None, {}


def video_path(run_id: str) -> pathlib.Path | None:
    return _video_of(run_dir(run_id))[0]


def thumb_path(run_id: str) -> pathlib.Path | None:
    """A frame of the final video (made once with ffmpeg, kept under runs/.shoestring/)."""
    v = video_path(run_id)
    if not v:
        return None
    out = SITE / f"{run_id}.thumb.jpg"
    if out.is_file() and out.stat().st_mtime >= v.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "3", "-i", str(v), "-frames:v", "1",
                        "-vf", "scale=480:-2", str(out)], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out.is_file() else None


def run_title(run_id: str) -> str:
    inp = _read(run_dir(run_id) / "input.json", {}) or {}
    return str(inp.get("video_title") or inp.get("order") or run_id)[:120]


def gallery_cards(order_of_run: dict[str, str]) -> list[dict]:
    cards = []
    for r in runs_list():
        d = run_dir(r["run_id"])
        v, info = _video_of(d)
        if not v:
            continue
        rid = r["run_id"]
        cst = cost_of(rid)
        oid = order_of_run.get(rid, "")
        cards.append({"order_id": oid or rid, "run_id": rid, "title": run_title(rid),
                      "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r["started"] or 0)),
                      "status": "video", "length_s": info.get("seconds"),
                      "video_url": "api/runs/%s/video" % rid, "thumb_url": "api/runs/%s/thumb" % rid,
                      "log_url": ("api/orders/%s/projectlog" % oid) if oid else "api/runs/%s/events" % rid,
                      "cost": cst, "cost_text": cost_text(cst), "learned": learned_of(rid)})
    return cards


def learned_of(run_id: str) -> dict:
    """What scripts/learn_run.py recorded for a run: {status, workers: n} ({} when not learned)."""
    rec = _read(run_dir(run_id) / "learned.json", {}) or {}
    if not rec:
        return {}
    return {"status": str(rec.get("status") or ""), "workers": len(rec.get("learned_workers") or [])}


# ------------------------------------------------------------------ PCs (file servers)
def _fs_name(run: records.Run, pc: dict) -> str:
    have = run.file_servers()
    return next((a for a in pc["aliases"] if a in have), "")


def latest_run_with_files() -> str:
    for r in runs_list():
        if (run_dir(r["run_id"]) / "file_servers").is_dir():
            return r["run_id"]
    return ""


def _item_file(run: records.Run, fs: str, it: records.ItemInfo) -> pathlib.Path:
    """The stored file of an item (paths in records may point at the folder the run was made in)."""
    p = pathlib.Path(it.path)
    local = run.path / "file_servers" / fs / "files" / p.name
    return local if local.is_file() else p


def pcs_list(run_id: str) -> list[dict]:
    run = records.load_run(run_dir(run_id)) if run_id else None
    out = []
    for pc in PCS:
        row = {k: v for k, v in pc.items() if k != "aliases"}
        fs = _fs_name(run, pc) if run else ""
        items = run.items(fs) if fs else []
        size = 0
        for it in items:
            try:
                size += _item_file(run, fs, it).stat().st_size
            except OSError:
                pass
        tools = _read(run.path / "file_servers" / fs / "tools.json", {}) if fs else {}
        if isinstance(tools, dict):            # {worker: [tool names]}
            tools = sorted({t for v in tools.values() if isinstance(v, list) for t in v})
        row.update(entries=len(items), size_bytes=size, state="active" if items else ("empty" if fs else "not used"),
                   profile="run " + run_id if run_id else "no run", index={},
                   tools=[str(t.get("name") if isinstance(t, dict) else t) for t in (tools or [])][:8],
                   file_server=fs)
        out.append(row)
    return out


def pc_entries(run_id: str, pc_id: str) -> list[dict]:
    pc = next((p for p in PCS if p["id"] == pc_id), None)
    if not pc or not run_id:
        return []
    run = records.load_run(run_dir(run_id))
    fs = _fs_name(run, pc)
    if not fs:
        return []
    crew = load_crew()
    owner = crew_of_block(crew)
    cname = {c["id"]: c["name"] for c in crew}
    out = []
    for it in run.items(fs):
        uploader = next((o for o, v in it.owners.items() if not (v or {}).get("by")), "")
        out.append({"id": it.number, "title": it.title or it.number, "ref": it.address, "order_id": "",
                    "added_by": cname.get(owner.get(base_of(uploader), ""), uploader) or "—",
                    "sections": len((it.map or {}).get("parts", []) or []) if isinstance(it.map, dict) else 0,
                    "figures": 0, "tables": 0, "map": "—", "index": {},
                    "media": {"file": pathlib.Path(it.path).name, "license": it.source[:40]},
                    "format": it.format, "description": it.description, "source": it.source,
                    "url": "api/runs/%s/fs/%s/%s" % (run_id, fs, it.number)})
    return out


def pc_item_file(run_id: str, fs: str, number: str) -> pathlib.Path | None:
    if not run_ok(run_id) or not re.fullmatch(r"[A-Za-z0-9_-]+", fs or "") or not re.fullmatch(r"[0-9A-Za-z_-]+", number or ""):
        return None
    run = records.load_run(run_dir(run_id))
    it = next((i for i in run.items(fs) if i.number == number), None)
    if not it:
        return None
    p = _item_file(run, fs, it)
    return p if p.is_file() else None


def pc_rights(run_id: str) -> dict:
    """Who holds which PC's files in this run (from the item owners: uploaded = W, shared = R)."""
    crew = load_crew()
    owner = crew_of_block(crew)
    rows = {c["id"]: {"agent": c["id"], "name": c["name"], "cells": {p["id"]: None for p in PCS}} for c in crew}
    if run_id:
        run = records.load_run(run_dir(run_id))
        for pc in PCS:
            fs = _fs_name(run, pc)
            if not fs:
                continue
            for it in run.items(fs):
                for o, v in it.owners.items():
                    cid = owner.get(base_of(o))
                    if not cid:
                        continue
                    cell = rows[cid]["cells"][pc["id"]] or {"v": "R", "entries": []}
                    if not (v or {}).get("by"):
                        cell["v"] = "W"
                    if not any(e["doc_id"] == it.number for e in cell["entries"]):
                        cell["entries"].append({"doc_id": it.number, "title": it.title, "ref": it.address})
                    rows[cid]["cells"][pc["id"]] = cell
    return {"order": run_id, "pcs": [p["id"] for p in PCS], "rows": list(rows.values())}
