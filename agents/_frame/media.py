"""Phase B media tools: Openverse search/pick, muse-image
generation, vision staging for Vera/Remy. Stdlib only.

Live I/O goes through injectable hooks (_HTTP_JSON, _HTTP_BYTES,
_IMAGE_FN) so tests run offline with fixtures; the default path
uses urllib. Nothing is fetched without its key, and every cap
refuses with a clear error naming the cap.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

from . import pc
from . import readlog

OPENVERSE_URL = "https://api.openverse.org/v1/images/"
OPENVERSE_LICENSES = "by,by-sa,cc0,pdm"  # minus by-nd (we crop)
IMAGE_QUERY_CAP = 2  # Openverse queries per cut per run
OPENVERSE_PER_MIN = 20  # shared Openverse queue default
GEN_IMAGE_CAP = 6  # generated images per run
GEN_IMAGE_COST = 0.01  # USD per muse-image, flat
VERA_VIEW_CAP = 2  # candidate files viewed per cut per run
IMAGE_FETCH_CAP = 20 * 1024 * 1024  # 20 MB per download
LICENSE_OK = ("cc0", "pdm", "by", "by-sa")

_HTTP_JSON = None  # fn(url) -> parsed JSON (tests inject fixtures)
_HTTP_BYTES = None  # fn(url, cap) -> bytes (tests inject fixtures)
_IMAGE_FN = None  # fn(prompt) -> (blob, model, cost_usd)

_RATE_LOCK = threading.Lock()
_RATE_CALLS = deque()  # monotonic timestamps of recent searches
_GEN_LOCK = threading.Lock()
_GEN_INFLIGHT = {}  # prompt doc_id -> Event while one clone generates


def _rate_cap_from_ctx(ctx):
    cap = ((ctx or {}).get("flow_settings") or {}).get(
        "openverse_per_min", OPENVERSE_PER_MIN)
    if isinstance(cap, bool) or not isinstance(cap, int) \
            or cap <= 0:
        return OPENVERSE_PER_MIN
    return cap


def _acquire_openverse_slot(per_min, now_fn=time.monotonic,
                            sleep_fn=time.sleep):
    """One shared Openverse queue: block until a call fits inside
    the per-minute cap. now/sleep injectable for tests."""
    if per_min is None or per_min <= 0:
        return
    while True:
        with _RATE_LOCK:
            now = now_fn()
            while _RATE_CALLS and _RATE_CALLS[0] <= now - 60:
                _RATE_CALLS.popleft()
            if len(_RATE_CALLS) < per_min:
                _RATE_CALLS.append(now)
                return
            wait = 60 - (now - _RATE_CALLS[0]) + 0.01
        sleep_fn(max(wait, 0.01))


def _gen_claim(doc_id):
    """True when this caller becomes the prompt's generator;
    False when another clone already generates it (wait)."""
    with _GEN_LOCK:
        if doc_id in _GEN_INFLIGHT:
            return False
        _GEN_INFLIGHT[doc_id] = threading.Event()
        return True


def _gen_wait(doc_id, timeout=600):
    with _GEN_LOCK:
        ev = _GEN_INFLIGHT.get(doc_id)
    if ev is not None:
        ev.wait(timeout)


def _gen_release(doc_id):
    with _GEN_LOCK:
        ev = _GEN_INFLIGHT.pop(doc_id, None)
    if ev is not None:
        ev.set()


def _reuse_generated(ctx, producer, doc_id):
    """The stored image for this prompt (+rows for the caller),
    or None when no entry exists yet."""
    try:
        entry = pc.load_entry_by_ref(
            pc.entry_ref("generated", doc_id))
    except (OSError, ValueError, KeyError):
        return None
    try:
        pc.set_recipients(
            "generated", doc_id, (ctx or {}).get("order_id", ""),
            pc.media_grantees("generated", producer), producer,
            kind="full")
    except (OSError, ValueError) as exc:
        return {"error": "reuse grant failed: %s" % exc}
    return {"ok": True, "ref": entry["ref"],
            "file": entry.get("file", ""), "reused_entry": True,
            "model": entry.get("model", ""),
            "cost_usd": 0.0}


def _owns(ctx, base):
    """True when the caller is base or one of its part clones
    (base@pN): clones use the base tools unchanged."""
    prod = (ctx or {}).get("producer", "")
    return prod == base or \
        re.fullmatch(re.escape(base) + r"@p\d+", prod or "") \
        is not None


def _get_json(url):
    if _HTTP_JSON is not None:
        return _HTTP_JSON(url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("openverse %s: %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError("openverse unreachable: %s" % exc)


def _get_bytes(url, cap):
    if _HTTP_BYTES is not None:
        return _HTTP_BYTES(url, cap)
    req = urllib.request.Request(url, headers={"Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read(cap + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("download %s: %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError("download unreachable: %s" % exc)
    if len(blob) > cap:
        raise RuntimeError("file over %d bytes" % cap)
    return blob


def _counter(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _counter_save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _log_research(ctx, obj):
    d = (ctx or {}).get("run_dir", "")
    if not d:
        return
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "research.jsonl"), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError:
        pass


def openverse_search(query, limit=5, per_min=None):
    """Openverse image search (commercial reuse set, no nd). Hits
    are never stored; only picks are. Calls queue through the
    shared per-minute limiter."""
    _acquire_openverse_slot(
        OPENVERSE_PER_MIN if per_min is None else per_min)
    qs = urllib.parse.urlencode({
        "q": query, "license": OPENVERSE_LICENSES,
        "license_type": "commercial", "page_size": limit,
        "fields": "id,title,url,foreign_landing_url,license,"
                  "license_version,thumbnail"})
    data = _get_json(OPENVERSE_URL + "?" + qs)
    out = []
    for h in (data.get("results", []) or [])[:limit]:
        out.append({"title": h.get("title", ""),
                    "image_url": h.get("url", ""),
                    "page_url": h.get("foreign_landing_url", ""),
                    "license": (h.get("license") or "").lower(),
                    "license_version": h.get("license_version", "")})
    return out


def _license_ok(lic):
    # strip version suffixes ("by-4.0" -> "by")
    parts = (lic or "").lower().split("-")
    core = "-".join(p for p in parts
                    if p and not p[0].isdigit())
    return core in LICENSE_OK


@readlog.logged("image")
def pc_search_images(ctx, args):
    """Pia's photo search: Openverse hits into the run log (never
    stored). At most 2 queries per cut per run."""
    if not _owns(ctx, "photo_pia"):
        return {"error": "pc_search_images is Pia's tool"}
    cut_id = ((args or {}).get("cut_id") or "").strip()
    q = ((args or {}).get("query") or "").strip()
    if not cut_id or not q:
        return {"error": "give {cut_id, query}"}
    try:
        limit = min(10, max(1, int((args or {}).get("max_results", 5))))
    except (TypeError, ValueError):
        limit = 5
    countp = os.path.join(ctx["run_dir"], "image_queries.json")
    counts = _counter(countp)
    n = int(counts.get(cut_id, 0)) + 1
    if n > IMAGE_QUERY_CAP:
        return {"error": "cut %s already used %d image queries"
                % (cut_id, IMAGE_QUERY_CAP)}
    try:
        hits = openverse_search(q, limit,
                                _rate_cap_from_ctx(ctx))
    except RuntimeError as exc:
        return {"error": str(exc)}
    counts[cut_id] = n
    _counter_save(countp, counts)
    _log_research(ctx, {"ev": "search", "query": q,
                        "tool": "pc_search_images", "cut_id": cut_id,
                        "hits": hits})
    return {"query": q, "cut_id": cut_id, "hits": hits,
            "queries_used": n}


@readlog.logged("image")
def pc_pick_image(ctx, args):
    """Pia's pick: download one licensed photo into the Image PC
    (file + source URL + license + reason, always credited)."""
    if not _owns(ctx, "photo_pia"):
        return {"error": "pc_pick_image is Pia's tool"}
    args = args or {}
    missing = [k for k in ("image_url", "page_url", "license",
                           "reason")
               if not (args.get(k) or "").strip()]
    if missing:
        return {"error": "missing: " + ", ".join(missing)}
    lic = args["license"].strip()
    if not _license_ok(lic):
        return {"error": "license %r is not reuse-permitted "
                "(want cc0/pdm/by/by-sa, never nd/nc)" % lic}
    try:
        blob = _get_bytes(args["image_url"].strip(),
                          IMAGE_FETCH_CAP)
    except RuntimeError as exc:
        return {"error": str(exc)}
    suffix = ".png" if blob[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
    try:
        saved = pc.image_store_pick(
            ctx.get("order_id", ""), args["page_url"].strip(), blob,
            lic, args["reason"].strip(),
            set_by=(ctx or {}).get("producer", "photo_pia"),
            suffix=suffix)
    except (OSError, ValueError) as exc:
        return {"error": "store failed: %s" % exc}
    _log_research(ctx, {"ev": "pick", "ref": saved["ref"],
                        "tool": "pc_pick_image"})
    return {"ok": True, "ref": saved["ref"], "file": saved["file"],
            "reused_entry": saved["reused_entry"],
            "deduped": saved.get("deduped", False)}


def _muse_image(prompt):
    """muse-image-1.0 via the OpenAI-compatible images API.
    Returns (png_blob, model, cost_usd). First live call verifies
    the shape; tests inject _IMAGE_FN."""
    from . import runner
    model = "muse-image-1.0"
    _, url, _ = runner.provider_of("meta-models/muse-spark-open-1026")
    body = {"model": model, "prompt": prompt, "n": 1,
            "response_format": "b64_json"}
    req = urllib.request.Request(
        url + "/images/generations", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + runner._key(
            "meta-models/muse-spark-open-1026"),
            "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("muse-image %s: %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError("muse-image unreachable: %s" % exc)
    try:
        import base64
        blob = base64.b64decode((data["data"][0]["b64_json"]))
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError("muse-image bad reply: %s" % exc)
    return blob, model, GEN_IMAGE_COST


@readlog.logged("generated")
def pc_generate_image(ctx, args):
    """Gene's image call: at most 6 per run; the same prompt
    reuses the stored image without a new call."""
    if not _owns(ctx, "image_gene"):
        return {"error": "pc_generate_image is Gene's tool"}
    prompt = ((args or {}).get("prompt") or "").strip()
    if not prompt:
        return {"error": "give {prompt}"}
    producer = (ctx or {}).get("producer", "image_gene")
    quota = (ctx or {}).get("gene_quota")
    cap = GEN_IMAGE_CAP if quota is None else quota
    doc_id = pc.content_id("generated:" + prompt)
    reused = _reuse_generated(ctx, producer, doc_id)
    if reused is not None:
        return reused
    countp = os.path.join(ctx["run_dir"], "gen_images.json")
    counts = _counter(countp)
    n = int(counts.get("n", 0)) + 1
    if n > cap:
        if quota is None:
            return {"error": "run already used %d generated images"
                    % GEN_IMAGE_CAP}
        return {"error": "part quota allows %d new images"
                % quota}
    if not _gen_claim(doc_id):
        _gen_wait(doc_id)
        reused = _reuse_generated(ctx, producer, doc_id)
        if reused is not None:
            return reused
        if not _gen_claim(doc_id):
            return {"error": "another part is generating this "
                             "prompt; call again"}
    try:
        if _IMAGE_FN is not None:
            blob, model, cost = _IMAGE_FN(prompt)
        else:
            blob, model, cost = _muse_image(prompt)
    except RuntimeError as exc:
        _gen_release(doc_id)
        return {"error": str(exc)}
    try:
        saved = pc.generated_store(ctx.get("order_id", ""), prompt,
                                   blob, cost, model,
                                   set_by=producer)
    except (OSError, ValueError) as exc:
        _gen_release(doc_id)
        return {"error": "store failed: %s" % exc}
    _gen_release(doc_id)
    counts["n"] = n
    _counter_save(countp, counts)
    return {"ok": True, "ref": saved["ref"], "file": saved["file"],
            "reused_entry": False, "model": model, "cost_usd": cost}


def _resolve_view(ctx, args):
    """A viewable file: {ref} (a stored pick/figure: resolved to
    its file) or {path} (must exist under the repo root)."""
    ref = ((args or {}).get("ref") or "").strip()
    if ref:
        try:
            entry = pc.load_entry_by_ref(ref)
        except (OSError, ValueError, KeyError) as exc:
            return None, "no such ref: %s" % exc
        if not pc.entry_parts_allow(
                entry, (ctx or {}).get("producer", ""),
                (ctx or {}).get("order_id", ""), ref):
            return None, "no access to this item"
        sub = {"image": "files", "generated": "files"}.get(
            entry.get("pc"), "figures")
        fname = entry.get("file", "")
        if not fname:
            return None, "entry has no viewable file"
        full = os.path.join(pc.entry_dir(entry.get("pc"),
                                         entry.get("doc_id")),
                            sub, fname)
        if not os.path.isfile(full):
            return None, "stored file is missing"
        return full, ""
    path = ((args or {}).get("path") or "").strip()
    if not path:
        return None, "give {ref} or {path}"
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    full = os.path.abspath(os.path.join(root, path))
    if not full.startswith(root + os.sep):
        return None, "path must stay inside the repo"
    if not os.path.isfile(full):
        return None, "no such file: %s" % path
    return full, ""


def _stage_view(ctx, tool, cut_id, full):
    line = {"tool": tool, "cut_id": cut_id, "path": full,
            "at": time.strftime("%H:%M:%S")}
    with open(os.path.join(ctx["run_dir"], "vision_staged.jsonl"),
              "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


@readlog.logged()
def vera_view_image(ctx, args):
    """Vera opens one chosen candidate file and looks at it
    (vision). She picks from descriptions first; at most 2 files
    per cut per run."""
    if not _owns(ctx, "board_vera"):
        return {"error": "vera_view_image is Vera's tool"}
    cut_id = ((args or {}).get("cut_id") or "").strip()
    if not cut_id:
        return {"error": "give {cut_id} plus {ref} or {path}"}
    countp = os.path.join(ctx["run_dir"], "vera_views.json")
    counts = _counter(countp)
    n = int(counts.get(cut_id, 0)) + 1
    if n > VERA_VIEW_CAP:
        return {"error": "cut %s already viewed %d files"
                % (cut_id, VERA_VIEW_CAP)}
    full, err = _resolve_view(ctx, args)
    if err:
        return {"error": err}
    counts[cut_id] = n
    _counter_save(countp, counts)
    staged = _stage_view(ctx, "vera_view_image", cut_id, full)
    return {"ok": True, "staged": staged["path"], "views_used": n}


def remy_view_slide(ctx, args):
    """Remy looks at one rendered slide with vision (raster PNG
    in live runs; the render cap governs re-renders)."""
    if not _owns(ctx, "slide_remy"):
        return {"error": "remy_view_slide is Remy's tool"}
    cut_id = ((args or {}).get("cut_id") or "").strip()
    if not cut_id:
        return {"error": "give {cut_id} plus {ref} or {path}"}
    full, err = _resolve_view(ctx, args)
    if err:
        return {"error": err}
    staged = _stage_view(ctx, "remy_view_slide", cut_id, full)
    return {"ok": True, "staged": staged["path"]}


MEDIA_TOOLS = {
    "pc_search_images": (
        pc_search_images,
        "Pia's photo search (Openverse, commercial reuse set). "
        "Hits stay in the run log; at most 2 queries per cut.",
        {"type": "object",
         "properties": {"cut_id": {"type": "string"},
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"}},
         "required": ["cut_id", "query"],
         "additionalProperties": False},
    ),
    "pc_pick_image": (
        pc_pick_image,
        "Pia's pick: download one licensed photo into the Image "
        "PC with file, source URL, license, and reason.",
        {"type": "object",
         "properties": {"image_url": {"type": "string"},
                        "page_url": {"type": "string"},
                        "license": {"type": "string"},
                        "reason": {"type": "string"}},
         "required": ["image_url", "page_url", "license",
                      "reason"],
         "additionalProperties": False},
    ),
    "pc_generate_image": (
        pc_generate_image,
        "Gene's image call (muse-image). At most 6 per run; the "
        "same prompt reuses the stored image.",
        {"type": "object",
         "properties": {"prompt": {"type": "string"}},
         "required": ["prompt"], "additionalProperties": False},
    ),
    "vera_view_image": (
        vera_view_image,
        "Vera opens one candidate file with vision. At most 4 "
        "files per cut.",
        {"type": "object",
         "properties": {"cut_id": {"type": "string"},
                        "ref": {"type": "string"},
                        "path": {"type": "string"}},
         "required": ["cut_id"], "additionalProperties": False},
    ),
    "remy_view_slide": (
        remy_view_slide,
        "Remy looks at one rendered slide with vision.",
        {"type": "object",
         "properties": {"cut_id": {"type": "string"},
                        "ref": {"type": "string"},
                        "path": {"type": "string"}},
         "required": ["cut_id"], "additionalProperties": False},
    ),
}
