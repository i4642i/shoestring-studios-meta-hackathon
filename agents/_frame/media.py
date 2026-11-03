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
COMMONS_URL = "https://commons.wikimedia.org/w/api.php"
# Cloudflare in front of api.openverse.org answers 403 (error
# 1010, "browser signature banned") to bot signatures and hangs
# them; a browser UA is required. Verified live 2026-11-02.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36")


# Wikimedia (commons API + upload.wikimedia.org) wants a descriptive
# User-Agent with a contact, and rate-limits generic browser strings
# from scripts (429 on 13 of 15 downloads in run 043822). Openverse
# still needs the browser UA (Cloudflare), so the UA is picked per host.
WIKIMEDIA_UA = ("ShoestringStudios/0.1 "
                "(https://github.com/i4642i/shoestring-studios-meta-hackathon; "
                "ksh4642@nextopologix.com) python-urllib")


def _ua_for(url):
    try:
        host = urllib.parse.urlsplit(url or "").netloc.lower()
    except ValueError:
        host = ""
    if host.endswith("wikimedia.org") or host.endswith("wikipedia.org"):
        return WIKIMEDIA_UA
    return USER_AGENT


def _json_headers(url=""):
    return {"Accept": "application/json",
            "User-Agent": _ua_for(url)}


def _bytes_headers(url=""):
    return {"Accept": "image/*", "User-Agent": _ua_for(url)}
OPENVERSE_LICENSES = "by,by-sa,cc0,pdm"  # minus by-nd (we crop)
IMAGE_QUERY_CAP = 2  # Openverse queries per cut per run
OPENVERSE_PER_MIN = 20  # shared Openverse queue default
GEN_IMAGE_CAP = 6  # generated images per run
GEN_IMAGE_COST = 0.01  # USD per muse-image, flat
VERA_VIEW_CAP = 2  # candidate files viewed per cut per run
IMAGE_FETCH_CAP = 20 * 1024 * 1024  # 20 MB per download
IMAGE_PICK_GAP = 8  # seconds between pick downloads, machine-wide
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


def _get_json(url, timeout=60):
    if _HTTP_JSON is not None:
        return _HTTP_JSON(url)
    req = urllib.request.Request(url, headers=_json_headers(url))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("openverse %s: %s" % (exc.code, exc.reason))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError("openverse unreachable: %s" % exc)


def _retry_after(headers, default=10):
    """Seconds to wait on HTTP 429 (Retry-After, capped at 600)."""
    try:
        return min(600, max(1, int(str(
            (headers or {}).get("retry-after", default)).strip())))
    except (TypeError, ValueError, AttributeError):
        return default


def _get_bytes(url, cap, timeout=60, _tries=3):
    if _HTTP_BYTES is not None:
        return _HTTP_BYTES(url, cap)
    req = urllib.request.Request(url, headers=_bytes_headers(url))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            blob = r.read(cap + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and _tries > 1:
            time.sleep(_retry_after(exc.headers))
            return _get_bytes(url, cap, timeout, _tries - 1)
        if exc.code == 429:
            raise RuntimeError("download 429 rate-limited after retries; "
                               "try this pick again later, the photo exists")
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


OPENVERSE_TIMEOUT = 70  # live: success takes ~60 s here
OPENVERSE_TRIES = 2
OPENVERSE_QUICK_TIMEOUT = 25  # Commons-first: Openverse is the slow leg


def _get_openverse(url, timeout=None, tries=None):
    """GET with retry. Returns (data, error)."""
    if timeout is None:
        timeout = OPENVERSE_TIMEOUT
    if tries is None:
        tries = OPENVERSE_TRIES
    err = RuntimeError("openverse unreachable: no attempt")
    for _ in range(max(1, tries)):
        try:
            return _get_json(url, timeout=timeout), None
        except RuntimeError as exc:
            err = exc
    return None, err


def openverse_search(query, limit=5, per_min=None, _note=None,
                     _timeout=None, _tries=None, _fallback=True):
    """Openverse image search (commercial reuse set, no nd). Hits
    are never stored; only picks are. Calls queue through the
    shared per-minute limiter. With _fallback=False an Openverse
    failure raises instead of falling back to Commons. See _search_with_breaker."""
    _acquire_openverse_slot(
        OPENVERSE_PER_MIN if per_min is None else per_min)
    qs = urllib.parse.urlencode({
        "q": query, "license": OPENVERSE_LICENSES,
        "license_type": "commercial", "page_size": limit,
        "fields": "id,title,url,foreign_landing_url,license,"
                  "license_version,thumbnail"})
    try:
        data, exc = _get_openverse(OPENVERSE_URL + "?" + qs,
                                   timeout=_timeout, tries=_tries)
        if data is None:
            raise exc
    except RuntimeError as exc:
        if not _fallback:
            raise
        falls = commons_search(query, limit)
        for h in falls:
            h["source"] = "commons"
            h["fallback"] = str(exc)
        if _note is not None:
            _note.append(str(exc))
        return falls
    out = []
    for h in (data.get("results", []) or [])[:limit]:
        out.append({"title": h.get("title", ""),
                    "image_url": h.get("url", ""),
                    "page_url": h.get("foreign_landing_url", ""),
                    "license": (h.get("license") or "").lower(),
                    "license_version": h.get("license_version", ""),
                    "source": "openverse"})
    return out


def _commons_license(short):
    """(license, version) for a Commons LicenseShortName, or
    None when not reusable (NC/ND/unknown)."""
    import re as _re
    s = (short or "").lower()
    if not s or "nc" in s or "nd" in s:
        return None
    m = _re.search(r"(\d+\.\d+)", s)
    ver = m.group(1) if m else ""
    if "public domain" in s or "cc0" in s:
        return ("pdm", ver)
    if "by-sa" in s or ("by" in s and "sa" in s):
        return ("by-sa", ver)
    if "by" in s:
        return ("by", ver)
    return None


def _clean_url(url):
    """Drop tracking query params (utm_*) from a file URL."""
    try:
        u = urllib.parse.urlsplit(url or "")
        q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
        q = [(k, v) for k, v in q
             if not k.lower().startswith("utm_")]
        return urllib.parse.urlunsplit(
            (u.scheme, u.netloc, u.path,
             urllib.parse.urlencode(q), u.fragment))
    except ValueError:
        return url


def commons_search(query, limit=5):
    """Wikimedia Commons fallback: freely licensed images, no
    key, same hit shape as openverse_search."""
    qs = urllib.parse.urlencode({
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": query + " filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|extmetadata",
        # a 1280 px thumbnail instead of the original: a few hundred
        # KB from the thumb cache, not a 20 MB file from upload
        "iiurlwidth": 1280})
    data = _get_json(COMMONS_URL + "?" + qs)
    out = []
    pages = (data.get("query", {}) or {}).get("pages", {}) or {}
    for _id in sorted(pages, key=str):
        pg = pages[_id] or {}
        info = (pg.get("imageinfo") or [{}])[0] or {}
        url = info.get("url", "") or ""
        if not urllib.parse.urlparse(url).path.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp",
                 ".tif", ".tiff", ".gif")):
            continue  # scans/books (pdf, djvu) are not photos
        meta = info.get("extmetadata") or {}
        short = ((meta.get("LicenseShortName") or {}).get("value")
                 or "")
        lic = _commons_license(short)
        if lic is None:
            continue
        license, ver = lic
        out.append({"title": pg.get("title", ""),
                    "image_url": _clean_url(info.get("thumburl")
                                            or info.get("url", "")),
                    "page_url": info.get("descriptionurl", ""),
                    "license": license,
                    "license_version": ver,
                    "source": "commons"})
        if len(out) >= limit:
            break
    return out


def _license_ok(lic):
    # strip version suffixes ("by-4.0"/"by 4.0" -> "by")
    parts = (lic or "").lower().replace(" ", "-").split("-")
    core = "-".join(p for p in parts
                    if p and not p[0].isdigit())
    return core in LICENSE_OK


def _search_with_breaker(ctx, query, limit, per_min):
    """Commons first (~1 s a call); Openverse second with a short
    timeout. After 2 failed Openverse calls in this run skip it
    so a dead API cannot stall the run."""
    try:
        first = commons_search(query, limit)
    except RuntimeError:
        first = []
    if first:
        return first
    deadp = os.path.join(ctx["run_dir"], "openverse_dead.json")
    try:
        dead = int(_counter(deadp).get("n", 0))
    except (TypeError, ValueError):
        dead = 0
    if dead >= 2:
        return first  # Commons already empty; nothing more to try
    try:
        return openverse_search(query, limit, per_min,
                                _timeout=OPENVERSE_QUICK_TIMEOUT,
                                _tries=1, _fallback=False)
    except RuntimeError:
        _counter_save(deadp, {"n": dead + 1})
        return first


@readlog.logged("image")
def pc_search_images(ctx, args):
    """Pia's photo search: Commons-first hits into the run log (never
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
        hits = _search_with_breaker(ctx, q, limit,
                                _rate_cap_from_ctx(ctx))
    except RuntimeError as exc:
        return {"error": str(exc)}
    counts[cut_id] = n
    _counter_save(countp, counts)
    _log_research(ctx, {"ev": "search", "query": q,
                        "tool": "pc_search_images", "cut_id": cut_id,
                        "hits": hits})
    out = {"query": q, "cut_id": cut_id, "hits": hits,
           "queries_used": n}
    if not hits:
        out["tip"] = ("0 hits: retry with fewer, more general words "
                      "(1-2 common nouns naming something visible)")
    return out


def _pace_pick(ctx):
    """One pick download per IMAGE_PICK_GAP seconds for the whole
    machine (parts run in parallel and share one IP): bursts get
    upload.wikimedia.org throttling everyone. The mark lives in the
    Image PC folder, not the clone's run dir."""
    try:
        if not (ctx or {}).get("run_dir", ""):
            return
        from . import pc as _pc
        mark = os.path.join(_pc.pc_dir("image"), "_last_download.json")
        now = time.time()
        try:
            last = float(_counter(mark).get("at", 0))
        except (TypeError, ValueError):
            last = 0
        wait = IMAGE_PICK_GAP - (now - last)
        if wait > 0:
            time.sleep(wait)
        _counter_save(mark, {"at": time.time()})
    except OSError:
        pass


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
        _pace_pick(ctx)
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
    _, url, _ = runner.provider_of(model)
    body = {"model": model, "prompt": prompt, "n": 1,
            "response_format": "b64_json"}
    req = urllib.request.Request(
        url + "/images/generations", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + runner._key(model),
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
    """Gene's image call: at most the part quota (one image per
    cut of the part, from the split plan; GEN_IMAGE_CAP only when
    no split plan exists); the same prompt reuses the stored image
    without a new call."""
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
    if ref.startswith("#"):
        # a bare figure/table fragment means the order's own source
        ref = (pc.order_entry_ref((ctx or {}).get("order_id", ""))
               or "") + ref
    if ref:
        try:
            entry = pc.load_entry_by_ref(ref)
            _pcn, _doc, frag = pc.parse_ref(ref)
        except (OSError, ValueError, KeyError) as exc:
            return None, "no such ref: %s" % exc
        if not pc.entry_parts_allow(
                entry, (ctx or {}).get("producer", ""),
                (ctx or {}).get("order_id", ""), ref):
            return None, "no access to this item"
        sub = {"image": "files", "generated": "files"}.get(
            entry.get("pc"), "figures")
        fname = entry.get("file", "")
        if frag and entry.get("pc") == "source":
            # a Source entry has no single file: #figN.M.K is one of its
            # figures, #tabN.M.K a table (viewable through its figure)
            figs = entry.get("figures") or []
            hit = next((f for f in figs if f.get("addr") == frag), None)
            if hit is None:
                tab = next((t for t in (entry.get("tables") or [])
                            if t.get("addr") == frag), None)
                if tab and tab.get("figure"):
                    hit = next((f for f in figs
                                if f.get("addr") == tab["figure"]), None)
            if hit and hit.get("file"):
                fname, sub = hit["file"], "figures"
            else:
                return None, ("%s is not a figure of this source "
                              "(figures: %s)" % (frag, ", ".join(
                                  f.get("addr", "") for f in figs[:12])))
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
        got = slide_png(ctx, path)
        if got is not None:
            return got, ""
        return None, "no such file: %s" % path
    return full, ""


def slide_png(ctx, slide_file):
    """Existing slide PNG for a render_log slide_file: a repo
    path as given, else the run's slides dirs (clone slides/,
    then node slides/). None when missing."""
    sf = slide_file.strip() if isinstance(slide_file, str) else ""
    if not sf:
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    cands = [sf]
    rd = (ctx or {}).get("run_dir", "")
    if rd:
        base = os.path.basename(sf)
        cands.append(os.path.join(rd, "slides", base))
        cands.append(os.path.join(os.path.dirname(
            os.path.abspath(rd)), "slides", base))
    for c in cands:
        if os.path.isabs(c):
            if os.path.isfile(c):
                return c
            continue
        full = os.path.abspath(os.path.join(root, c))
        if full.startswith(root + os.sep) \
                and os.path.isfile(full):
            return full
    return None


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
        "Gene's image call (muse-image). At most this part's quota "
        "(one per cut, in the split plan); the same prompt reuses "
        "the stored image.",
        {"type": "object",
         "properties": {"prompt": {"type": "string"}},
         "required": ["prompt"], "additionalProperties": False},
    ),
    "vera_view_image": (
        vera_view_image,
        "Vera opens one candidate file with vision. At most 2 "
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
