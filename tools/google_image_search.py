"""Google image search through Serper.dev (Google Images results, no site limit). Key: SERPER_API_KEY in .env.
Falls back to Google Custom Search (GOOGLE_API_KEY + GOOGLE_CSE_ID) when no Serper key is set."""

import re
import urllib.error
import urllib.parse

from functions._common import env, http_json

NAME = "google_image_search"
DESC = ("Search Google Images. Give up to 6 queries at once (one per cut is fine); each returns 8 hits (per_query: 1-10) "
        "with title, image url, page url, site and size. Pick by title, site and size, then call fetch_image.")
SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
                   "per_query": {"type": "integer", "minimum": 1, "maximum": 10}},
    "required": ["queries"],
}


def _serper(key: str, q: str, n: int) -> list[dict]:
    korean = bool(re.search(r"[가-힣]", q))
    body = {"q": q, "num": max(10, n), **({"gl": "kr", "hl": "ko"} if korean else {})}
    r = http_json("https://google.serper.dev/images", body, {"X-API-KEY": key}, timeout=30)
    return [{"title": it.get("title", ""), "image_url": it.get("imageUrl", ""), "page_url": it.get("link", ""),
             "site": it.get("domain") or it.get("source", ""), "width": it.get("imageWidth"),
             "height": it.get("imageHeight")} for it in r.get("images", [])[:n]]


def _cse(key: str, cx: str, q: str, n: int) -> list[dict]:
    params = urllib.parse.urlencode({"key": key, "cx": cx, "q": q, "searchType": "image", "num": n,
                                     "safe": "active", "imgSize": "large"})
    r = http_json("https://www.googleapis.com/customsearch/v1?" + params, timeout=30)
    return [{"title": it.get("title", ""), "image_url": it.get("link", ""),
             "page_url": (it.get("image") or {}).get("contextLink", ""), "site": it.get("displayLink", ""),
             "width": (it.get("image") or {}).get("width"), "height": (it.get("image") or {}).get("height")}
            for it in r.get("items", [])]


def run(ctx, args):
    serper, gkey, cx = env("SERPER_API_KEY"), env("GOOGLE_API_KEY"), env("GOOGLE_CSE_ID")
    if not serper and not (gkey and cx):
        return {"error": "image search is not set up (SERPER_API_KEY missing in .env). "
                         "Use source figures only, or decide 'none' for cuts that need a web photo."}
    n = int(args.get("per_query") or 8)
    out = {}
    for q in args["queries"][:6]:
        try:
            out[q] = _serper(serper, q, n) if serper else _cse(gkey, cx, q, n)
        except urllib.error.HTTPError as e:
            return {"error": f"image search failed ({e.code}): {e.read(200).decode('utf-8', 'replace')}"}
        except Exception as e:           # network
            return {"error": f"image search unreachable: {e}"}
    return {"results": out}
