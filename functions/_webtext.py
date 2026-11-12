"""Article text of a web page, with the standard library only (used by the news search tool)."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "Mozilla/5.0 (naw-shoestring news reader)"


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"}
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre", "td", "br", "div"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_article = 0
        self.all: list[str] = []
        self.article: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "article":
            self.in_article += 1
        if tag in self.BLOCK:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "article" and self.in_article:
            self.in_article -= 1
        if tag in self.BLOCK:
            self._add("\n")

    def handle_data(self, data):
        if not self.skip:
            self._add(data)

    def _add(self, text: str) -> None:
        self.all.append(text)
        if self.in_article:
            self.article.append(text)


def _lines(text: str) -> list[str]:
    return [x for x in (" ".join(line.split()) for line in text.splitlines()) if x]


def extract_text(page: str, min_line: int = 25, stop: list[str] | None = None) -> str:
    """Visible text without menus and scripts; short lines dropped; the <article> part when it holds at least half
    of the long text; cut at the first line matching a stop pattern (copyright notices and the like)."""
    p = _TextParser()
    p.feed(page)

    def long_lines(text: str) -> list[str]:
        lines = _lines(text)
        kept = [x for x in lines if len(x) >= min_line]
        return kept or lines

    page_lines = long_lines("".join(p.all))
    article_lines = long_lines("".join(p.article)) if "".join(p.article).strip() else []
    size = sum(map(len, page_lines))
    chosen = article_lines if article_lines and sum(map(len, article_lines)) * 2 >= size else page_lines
    patterns = [re.compile(s) for s in (stop or [])]
    out = []
    for line in chosen:
        if any(pt.search(line) for pt in patterns):
            break
        out.append(line)
    return "\n\n".join(out)


def page_text(url: str, timeout: float = 30.0, min_line: int = 25, stop: list[str] | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"page answered HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"page not reachable ({getattr(e, 'reason', e)})") from None
    return extract_text(raw.decode(charset, "replace"), min_line, stop)
