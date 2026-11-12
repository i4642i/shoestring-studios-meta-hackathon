"""Renders one part with Remotion: the slide builder's timeline (cut by cut) + the narration audio -> part MP4.

The Remotion project is remotion/ (screen templates: BigText, Steps, Formula, BarChart, PhotoCard, ...).
Shared with tools/preview_slides.py (bundle, file server, render slots): change both together.
Local files (photos, figures, voice) are served to Remotion by a small HTTP server for the time of the render.
The voice of each cut comes from the file server "voice" (the narrator uploads one mp3 per cut, title = cut id);
a cut missing there falls back to the audio path in the timing (the narrator's own file)."""

import http.server
import json
import mimetypes
import pathlib
import subprocess
import threading
import urllib.parse

from functions._common import ROOT, pick, write_json

NAME = "render_part"
DESC = "Renders one part (all its cuts, with voice) into an MP4 with Remotion"
TIMEOUT = 1800
FILES_IN = True                  # top point: receives the narrator's voice files (file server voice)
OUTPUTS = [{"name": "rendered", "schema": {
    "type": "object",
    "properties": {"part_id": {"type": "string"}, "file": {"type": "string"}, "seconds": {"type": "number"},
                   "cuts": {"type": "array"}, "left_unfixed": {"type": "array"}},
    "required": ["part_id", "file", "seconds", "cuts"]}}]

BREATH = 0.4                     # seconds after each cut's voice


MAIN_LAYERS = {"BigText", "PhotoCard", "Formula", "BarChart", "LineChart", "Steps", "NumberCard", "TitleCard", "EndCard", "Curve", "Scatter", "Diagram", "RouteMap", "Chips", "HtmlSlide", "SectionCard"}


def _stretch(cut_spans: list) -> list:
    """cut_spans: [(start, end, [layers with absolute start/end], cut_id)] in order. A layer with "span": true stays
    until the next cut that has a main layer of its own (or the end of the piece). Its cues
    [{"cut": id, "props": {...}}] become [{"at": seconds from the layer's start, "props": {...}}]."""
    starts = {cs[3]: cs[0] for cs in cut_spans if len(cs) > 3}
    out = []
    for i, cs in enumerate(cut_spans):
        _, _, lys = cs[0], cs[1], cs[2]
        nxt = next((x[0] for x in cut_spans[i + 1:] if any(y.get("type") in MAIN_LAYERS for y in x[2])),
                   cut_spans[-1][1])
        for ly in lys:
            ly = {**ly, "end": round(nxt, 3)} if ly.get("span") else dict(ly)
            if ly.get("cues"):
                ly["cues"] = [{"at": round(max(0.0, starts.get(c.get("cut"), ly["start"]) - ly["start"] + float(c.get("delay", 0))), 3),
                               "props": c.get("props") or {}} for c in ly["cues"] if c.get("cut") in starts]
            out.append(ly)
    return out


REMOTION = ROOT / "remotion"
CLI = REMOTION / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
_bundle_lock = threading.Lock()
_render_slots = threading.Semaphore(2)     # Chrome instances at once


def _ensure_bundle() -> pathlib.Path:
    build = REMOTION / "build"
    newest = max(p.stat().st_mtime for p in (REMOTION / "src").rglob("*") if p.is_file())
    stamp = build / "index.html"
    with _bundle_lock:
        if not stamp.is_file() or stamp.stat().st_mtime < newest:
            r = subprocess.run(["node", str(CLI), "bundle", "src/index.ts", "--out-dir", "build", "--log=error"],
                               cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=900)
            if r.returncode != 0 or not stamp.is_file():
                raise RuntimeError(f"Remotion bundle failed: {(r.stderr or r.stdout)[-600:]}")
    return build


class _Files:
    """Serves a fixed set of local files at http://127.0.0.1:<port>/f/<n><ext> (CORS open, Range not needed)."""

    def __init__(self):
        self.paths: list[pathlib.Path] = []
        files = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    n = int(pathlib.PurePosixPath(urllib.parse.urlparse(self.path).path).stem)
                    data = files.paths[n].read_bytes()
                except (ValueError, IndexError, OSError):
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(files.paths[n].name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]

    def url(self, path: str) -> str:
        p = pathlib.Path(path)
        self.paths.append(p)
        return f"http://127.0.0.1:{self.port}/f/{len(self.paths) - 1}{p.suffix.lower()}"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()


def _localize(obj, files: _Files, missing: list):
    """Every string that is an existing absolute file path becomes a served URL."""
    if isinstance(obj, dict):
        return {k: _localize(v, files, missing) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_localize(v, files, missing) for v in obj]
    if isinstance(obj, str) and len(obj) < 400 and (obj[1:3] == ":\\" or obj[1:3] == ":/"):
        if pathlib.Path(obj).is_file():
            return files.url(obj)
        missing.append(obj)
    return obj


def run(ctx, inputs):
    lines, vis, tim, tl = pick(inputs, "narration"), pick(inputs, "visuals"), pick(inputs, "timing"), pick(inputs, "timeline")
    text_of = {c["cut_id"]: c["text"] for c in lines["cuts"]}
    piece = {"piece_id": tim["piece_id"], "part_id": tim["piece_id"], "theme": vis.get("theme"),
             "cuts": [{"cut_id": c["cut_id"], "text": text_of.get(c["cut_id"], "")} for c in tim["cuts"]],
             "timing": {c["cut_id"]: c for c in tim["cuts"]}}
    if not CLI.is_file():
        return {"error": "Remotion is not installed (remotion/node_modules missing)"}
    plan = {c["cut_id"]: c for c in tl["cuts"]}
    out = pathlib.Path(ctx["files_dir"])
    out.mkdir(parents=True, exist_ok=True)
    background, layers, audio, cuts, t, spans = [], [], [], [], 0.0, []
    voice = {str(f.get("title") or ""): f["path"] for f in inputs.get("files/voice") or []
             if isinstance(f, dict) and f.get("path") and pathlib.Path(f["path"]).is_file()}
    from tools._layouts import add_cover, place_timeline_cuts
    placed = place_timeline_cuts(tl["cuts"], piece.get("theme") or "shoestring")
    for c in piece["cuts"]:
        tm = (piece.get("timing") or {}).get(c["cut_id"]) or c
        dur = round(float(tm["seconds"]) + BREATH, 3)
        p = plan.get(c["cut_id"], {})
        for b in p.get("background") or [{"style": "plain", "start": 0, "end": dur}]:
            s, e = max(0.0, float(b.get("start", 0))), min(dur, float(b.get("end", dur)))
            background.append({**b, "start": round(t + s, 3), "end": round(t + max(e, s + 0.1), 3)})
        mine = []
        cut_layers = placed.get(c["cut_id"]) or []         # layers in a layout slot carry their box
        if (vis.get("section_card") or {}).get("cut_id") == c["cut_id"]:
            cut_layers = add_cover(cut_layers, vis["section_card"], dur)   # the part's first 3 s: section cover
        for ly in cut_layers:
            s, e = max(0.0, float(ly.get("start", 0))), min(dur, float(ly.get("end", dur)))
            mine.append({**ly, "start": round(t + s, 3), "end": round(t + max(e, s + 0.2), 3)})
        spans.append((t, t + dur, mine, c["cut_id"]))
        audio.append({"src": voice.get(c["cut_id"]) or tm["audio"], "start": round(t, 3)})
        cuts.append({"cut_id": c["cut_id"], "start": round(t, 3), "seconds": dur, "text": c["text"]})
        t += dur
    layers = _stretch(spans)
    props = {"page": piece.get("piece_id") or piece["part_id"], "duration": round(t, 3), "width": 1280, "height": 720,
             "theme": piece.get("theme") or "shoestring", "background": background, "layers": layers, "audio": audio}
    write_json(out / "timeline.json", props)
    build = _ensure_bundle()
    video = out / f"part_{piece.get('piece_id') or piece['part_id']}.mp4"
    with _Files() as files:
        missing = []
        served = _localize(props, files, missing)
        if missing:
            return {"error": f"files in the timeline do not exist: {missing[:5]}"}
        props_file = out / "props.json"
        write_json(props_file, served)
        with _render_slots:
            r = subprocess.run(["node", str(CLI), "render", str(build), "Page", str(video), f"--props={props_file}",
                                "--log=error", "--overwrite", "--concurrency=4"],
                               cwd=REMOTION, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1700)
    if r.returncode != 0 or not video.is_file():
        return {"error": f"Remotion render failed: {(r.stderr or r.stdout)[-800:]}"}
    done = {"part_id": piece.get("piece_id") or piece["part_id"], "file": str(video.resolve()), "seconds": round(t, 2), "cuts": cuts}
    # problems the screen check could not fix in its allowed rounds travel on to the final output (assemble_video)
    passed = inputs.get("check_layout/pass") if isinstance(inputs.get("check_layout/pass"), dict) else None
    if passed and passed.get("left_unfixed"):
        done["left_unfixed"] = passed["left_unfixed"]
    return {"rendered": done}
