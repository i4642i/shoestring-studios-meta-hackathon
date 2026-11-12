"""Gene's image tool: makes pictures with Muse (muse-image-1.0, Meta Model API, key MODEL_API_KEY in .env).

Rules (as in the original Shoestring):
- per part (one gene block copy): at most PER_CUT (2) new pictures per cut: the first and one remake;
- per run: at most RUN_CAP (80) new pictures in all, so one picture per content cut is never blocked;
- the same prompt (sha256 of the trimmed text) reuses the stored picture (.cache/generated/<hash>.png) at no cost
  and without a new call;
- every new picture costs COST_USD; runs/<run_id>/image_cost.json keeps the count, the cost and one row per picture
  (the site shows it as the image cost of the run).
The picture is always copied into this block's files folder (files/generated/<id>.png), so the worker may upload it.
Tests set _IMAGE_FN = lambda prompt: png_bytes to run without the API."""

import base64
import hashlib
import json
import pathlib
import re
import shutil
import threading
import time
import urllib.error
import urllib.request

from functions._common import ROOT, env

NAME = "generate_image"
DESC = ("Make pictures with Muse (muse-image-1.0): items [{id, cut_id, prompt}], up to 3 at a time. id = "
        "gn-<cut_id>-<number>; prompt = one concrete English description of what to draw (subject, setting, light); "
        "the tool adds the style itself (flat 2D vector illustration, never a photo look, no text). Returns per item {id, cut_id, file, reused, cost_usd} or {id, cut_id, error}. "
        "At most 2 new pictures per cut (one remake) and 80 new pictures per run; the same prompt again reuses the stored picture "
        "at no cost.")
SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "cut_id": {"type": "string"}, "prompt": {"type": "string"}},
        "required": ["id", "cut_id", "prompt"]}}},
    "required": ["items"],
}
MODEL = "muse-image-1.0"
PER_CUT = 2                  # new pictures per cut: the first, and one remake when it came out wrong
# Shoestring's picture style (as the original Gene: flat vector, never a photoreal look). Added to every prompt by the
# program, so the worker writes only what to draw.
STYLE = ("Style: flat 2D vector illustration, simple shapes, soft paper texture, muted colors; not a photo, not "
         "photorealistic, not 3D; no text, letters, numbers, logos or watermark in the image.")
URL = "https://api.meta.ai/v1/images/generations"
COST_USD = 0.01
RUN_CAP = 80
CACHE = ROOT / ".cache" / "generated"
_IMAGE_FN = None                       # tests: a function prompt -> PNG bytes
_lock = threading.Lock()               # parallel gene copies run in one process: count and cache under one lock


def _muse_image(prompt: str) -> bytes:
    """One picture from the Meta Model API (OpenAI-compatible images API). Raises RuntimeError with a short reason."""
    key = env("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set (add it to .env); no picture can be generated in this run")
    body = {"model": MODEL, "prompt": prompt, "n": 1, "response_format": "b64_json"}
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"muse-image {e.code}: {e.reason}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f"muse-image unreachable: {e}") from None
    try:
        return base64.b64decode(data["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise RuntimeError(f"muse-image bad reply: {e}") from None


def _cost_file(ctx) -> pathlib.Path:
    return pathlib.Path(ctx["project"]) / "runs" / str(ctx["run_id"]) / "image_cost.json"


def _read_cost(path: pathlib.Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return d
    except (OSError, ValueError):
        pass
    return {"images": 0, "usd": 0.0, "model": MODEL, "items": []}


def _write(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run(ctx, args):
    out_dir = pathlib.Path(ctx["files_dir"]) / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    made_here = out_dir / "made.json"            # cut ids that got a new picture in this block
    results = []
    for it in args["items"][:3]:
        cid, cut, prompt = str(it.get("id") or "").strip(), str(it.get("cut_id") or "").strip(), " ".join(
            str(it.get("prompt") or "").split())
        row = {"id": cid, "cut_id": cut}
        if not re.fullmatch(r"gn-c\d+-\d+", cid) or not cid.startswith(f"gn-{cut}-"):
            results.append({**row, "error": f"id must be gn-{cut or '<cut_id>'}-<number> (got {cid!r})"})
            continue
        if not prompt:
            results.append({**row, "error": "prompt is empty; describe the picture in one English sentence"})
            continue
        prompt = f"{prompt.rstrip('. ')}. {STYLE}"           # the program sets the style, the worker the subject
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        target = out_dir / f"{cid}.png"
        with _lock:
            cached = CACHE / f"{digest}.png"
            if cached.is_file():
                shutil.copyfile(cached, target)
                results.append({**row, "file": str(target.resolve()), "reused": True, "cost_usd": 0})
                continue
            made = json.loads(made_here.read_text(encoding="utf-8")) if made_here.is_file() else []
            if made.count(cut) >= PER_CUT:
                results.append({**row, "error": f"part quota: {cut} already got {PER_CUT} new pictures in this part "
                                                f"(at most {PER_CUT} per cut); use one of them, or another picture of "
                                                f"this scene that fits"})
                continue
            cost_path = _cost_file(ctx)
            cost = _read_cost(cost_path)
            if int(cost.get("images") or 0) >= RUN_CAP:
                results.append({**row, "error": f"run quota: this run already made {RUN_CAP} new pictures "
                                                f"(the most per run); stop generating and save what you have"})
                continue
            try:
                blob = (_IMAGE_FN or _muse_image)(prompt)
            except RuntimeError as e:
                results.append({**row, "error": str(e)})
                continue
            if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":   # Muse replies with WEBP: store a PNG
                try:
                    import io
                    from PIL import Image
                    buf = io.BytesIO()
                    Image.open(io.BytesIO(blob)).convert("RGB").save(buf, "PNG")
                    blob = buf.getvalue()
                except Exception as e:
                    results.append({**row, "error": f"muse-image reply is WEBP and could not be converted: {e}"})
                    continue
            if blob[:8] != b"\x89PNG\r\n\x1a\n" and blob[:3] != b"\xff\xd8\xff":
                results.append({**row, "error": "muse-image bad reply: the data is not a PNG, JPEG or WEBP picture"})
                continue
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(blob)
            shutil.copyfile(cached, target)
            made.append(cut)
            _write(made_here, made)
            cost["images"] = int(cost.get("images") or 0) + 1
            cost["usd"] = round(cost["images"] * COST_USD, 2)
            cost["model"] = MODEL
            cost.setdefault("items", []).append({"prompt_hash": digest[:16], "file": str(target.resolve()),
                                                 "block": str(ctx.get("block") or ""), "time": round(time.time(), 1)})
            _write(cost_path, cost)
        results.append({**row, "file": str(target.resolve()), "reused": False, "cost_usd": COST_USD})
    return {"images": results}
