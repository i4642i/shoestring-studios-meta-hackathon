"""Searches English news (Tavily news search, key TAVILY_API_KEY in .env) and saves each article's text as a .md file
in this block's files folder. The worker reads the results and uploads the articles it will use to a file server
(<file_server>_upload with file, title, source = the article address)."""

import json
import pathlib
import urllib.request

from functions._common import env
from functions._webtext import page_text

NAME = "news_search"
DESC = ("Search English news. Give up to 3 English keywords at once; each returns per_keyword articles (default 3, at most 5). Every article's "
        "text is saved as a .md file in your files folder. Returns per article: title, url, published, file, chars and "
        "the first lines. Read them, then upload the articles you will use with your file server's upload tool "
        "(file = the returned file, title, source = the url). Articles already found in this block are not repeated.")
SCHEMA = {
    "type": "object",
    "properties": {"keywords": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
                   "per_keyword": {"type": "integer", "minimum": 1, "maximum": 5}},
    "required": ["keywords"],
}
URL = "https://api.tavily.com/search"
STOP = [r"(?i)all rights reserved", r"(?i)related articles", r"(?i)copyright", r"©"]
MIN_CHARS = 300          # shorter pages are usually a title and a link only


def _search(keyword: str, n: int) -> list[dict]:
    key = env("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set in .env")
    body = {"query": keyword, "topic": "news", "search_depth": "basic", "max_results": n,
            "include_answer": False, "include_raw_content": True}
    req = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("results") or []


def _text(it: dict) -> str:
    """The article text: Tavily's raw content when it has enough, otherwise the page itself."""
    raw = str(it.get("raw_content") or "").strip()
    if len(raw) >= MIN_CHARS:
        return raw
    try:
        return page_text(it.get("url", ""), stop=STOP)
    except Exception:
        return ""


def run(ctx, args):
    out_dir = pathlib.Path(ctx["files_dir"]) / "news"
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = {json.loads(p.read_text(encoding="utf-8")).get("url") for p in out_dir.glob("*.json")}
    n = int(args.get("per_keyword") or 3)
    results = []
    for kw in [str(k).strip() for k in args["keywords"][:3] if str(k).strip()]:
        try:
            items = _search(kw, n + 3)          # a few extra: some pages cannot be read
        except Exception as e:
            results.append({"keyword": kw, "error": f"search failed ({type(e).__name__}: {e})"})
            continue
        got = 0
        for it in items:
            if got >= n:
                break
            url = it.get("url") or ""
            if not url or url in seen:
                continue
            title = str(it.get("title") or "").strip()
            text = _text(it)
            if len(text) < MIN_CHARS:
                continue
            seen.add(url)
            got += 1
            k = len(list(out_dir.glob("*.md"))) + 1
            path = out_dir / f"article_{k:02d}.md"
            published = it.get("published_date", "")
            path.write_text(f"# {title}\n\n- URL: {url}\n- Date: {published}\n\n{text}\n", encoding="utf-8")
            (out_dir / f"article_{k:02d}.json").write_text(json.dumps({"url": url, "title": title}, ensure_ascii=False),
                                                         encoding="utf-8")
            results.append({"keyword": kw, "title": title, "url": url, "published": published, "file": str(path.resolve()),
                            "chars": len(text), "first_lines": text[:300]})
        if not got:
            results.append({"keyword": kw, "note": "no readable article; try other keywords"})
    return {"articles": results}
