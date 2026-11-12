"""The site's main screen: the nextop studio page with the Shoestring ORDER and STUDIO tabs added.

The nextop package is not edited. The page is fetched from the running `nextop studio` (or read from the
installed package when the studio is not reachable), its api/ calls are re-pointed to nx/api/ (which
scripts/server.py forwards to the studio), and the two Shoestring tabs are injected into its menu.
The Shoestring pages themselves are the original homepage (index.html?embed=1) in one frame, so they
keep their own look and code.

Menu: ORDER OFFICE GALLERY | WORKERS FUNCTIONS FLOW FILE SERVERS TOOLS RUNS SETTINGS | ABOUT. ORDER opens first.
ABOUT shows the platform's own about info first, then the Shoestring Studios 2 section (copyright and licenses,
why we build this, open source tables, developer), taken from index.html between the SS-ABOUT marks.
"""
from __future__ import annotations

import pathlib
import urllib.error
import urllib.request

API_PREFIX = "nx/api/"   # the page's studio calls; server.py forwards nx/api/* to <studio>/api/*

# Runs before the studio script: an empty hash opens ORDER (the studio itself would open FLOW).
HEAD_JS = """<script>
  if (!location.hash || location.hash === "#") { try { history.replaceState(null, "", "#order"); } catch (e) { location.hash = "order"; } }
</script>
"""

CSS = """<style>
  /* Shoestring tabs on the platform page */
  nav.main .ss-sep { width: 1px; height: 22px; background: var(--line); margin: 0 6px; flex: 0 0 auto; }
  #p-ss { padding: 0; max-width: none; }
  #p-ss iframe { display: block; width: 100%; border: 0; background: #fff; }
  /* Shoestring section of ABOUT (from index.html #p-about) */
  #p-about .card > p, #p-about .card > ul { max-width: 860px; }
  #p-about .about3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  #p-about .about3c { border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; background: var(--panel); }
  #p-about .about3c h3 { margin: 0 0 8px; }
  #p-about .about3c p { margin: 0; }
  @media (max-width: 1000px) { #p-about .about3 { grid-template-columns: 1fr; } }
  #p-about .credwrap { overflow-x: auto; }
  #p-about .credtab { width: 100%; border-collapse: collapse; font-size: 13px; }
  #p-about .credtab th, #p-about .credtab td { text-align: left; padding: 7px 10px; border-top: 1px solid var(--line); vertical-align: top; }
  #p-about .credtab th { font-size: 11px; letter-spacing: 1px; color: var(--dim); border-top: none; white-space: nowrap; }
  #p-about .crednote { color: var(--dim); font-size: 13px; }
  #p-about ul.credits { font-size: 14px; padding-left: 20px; line-height: 1.6; margin: 0; }
  #p-about ul.credits li { margin-bottom: 8px; }
  #p-about a { color: var(--accent); }
</style>
"""

BODY_JS = """<script>
"use strict";
/* Shoestring 2: ORDER and STUDIO tabs on the platform page. The studio's own router knows only its
   tabs (an unknown hash shows FLOW), so this script runs after it and puts the Shoestring page back. */
(function shoestringTabs() {
  const MINE = ["order", "studio", "gallery"];
  const nav = document.querySelector("nav.main");
  const about = nav.querySelector('[data-tab="about"]');
  const btn = (tab, label) => {
    const b = document.createElement("button");
    b.dataset.ss = tab; b.textContent = label;
    b.onclick = () => { location.hash = tab; };
    return b;
  };
  const sep = () => { const s = document.createElement("span"); s.className = "ss-sep"; return s; };
  // Order: ORDER OFFICE GALLERY | WORKERS FUNCTIONS FLOW FILE SERVERS TOOLS RUNS SETTINGS | ABOUT
  const order = ["workers", "functions", "flow", "file_servers", "tools", "runs", "settings"];
  const first = nav.firstChild;
  nav.insertBefore(btn("order", "ORDER"), first);
  nav.insertBefore(btn("studio", "OFFICE"), first);   // the 3D office; "studio" is the platform app
  nav.insertBefore(btn("gallery", "GALLERY"), first);
  nav.insertBefore(sep(), first);
  order.forEach(t => { const b = nav.querySelector('[data-tab="' + t + '"]'); if (b) nav.insertBefore(b, first); });
  if (about) { nav.insertBefore(sep(), about); nav.appendChild(about); }

  const page = document.createElement("div");
  page.className = "page"; page.id = "p-ss";
  const frame = document.createElement("iframe");
  frame.title = "Shoestring Studios";
  page.appendChild(frame);
  const anchor = document.querySelector(".page");
  anchor.parentNode.insertBefore(page, anchor);

  const mine = () => { const h = location.hash.slice(1).split("/")[0]; return MINE.indexOf(h) >= 0 ? h : ""; };
  function fit() {
    const head = document.querySelector("header");
    frame.style.height = (window.innerHeight - (head ? head.getBoundingClientRect().height : 0)) + "px";
  }
  let loaded = false, want = "";
  frame.addEventListener("load", () => { loaded = true; show(); });
  function show() {
    const tab = mine();
    if (!tab) { page.classList.remove("active"); nav.querySelectorAll("[data-ss]").forEach(b => b.classList.remove("active")); return; }
    document.querySelectorAll(".page.active").forEach(p => { if (p !== page) p.classList.remove("active"); });
    nav.querySelectorAll("[data-tab].active").forEach(b => b.classList.remove("active"));
    nav.querySelectorAll("[data-ss]").forEach(b => b.classList.toggle("active", b.dataset.ss === tab));
    page.classList.add("active");
    fit();
    if (!frame.src) { want = tab; frame.src = "index.html?embed=1#/" + tab; return; }
    if (loaded && want !== tab) { want = tab; frame.contentWindow.postMessage({ kind: "ss-show", tab: tab }, location.origin); }
  }
  window.addEventListener("hashchange", show);   // after the studio's own router
  window.addEventListener("resize", fit);
  // The studio routes once more when its state has loaded (FLOW for our hash): put ORDER/STUDIO back.
  new MutationObserver(() => {
    if (mine() && (!page.classList.contains("active") || nav.querySelector("[data-tab].active"))) show();
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["class"] });
  // Messages from the Shoestring page: its own tab switches, and "Open in RUNS".
  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin || e.source !== frame.contentWindow || !e.data || e.data.kind !== "ss-embed") return;
    if (e.data.tab) {
      want = e.data.tab;
      if (MINE.indexOf(e.data.tab) >= 0 && mine() !== e.data.tab) location.hash = e.data.tab;
    }
    if (e.data.runs !== undefined) location.hash = e.data.runs ? "runs/" + encodeURIComponent(e.data.runs) : "runs";
  });
  show();
})();
/* ABOUT: the platform's about card first, then the Shoestring Studios 2 section below it. */
(function shoestringAbout() {
  const tpl = document.getElementById("ss-about"), page = document.getElementById("p-about");
  if (tpl && page) page.appendChild(tpl.content.cloneNode(true));
})();
</script>
"""


ROOT = pathlib.Path(__file__).resolve().parent.parent
ABOUT_BEGIN, ABOUT_END = "<!-- SS-ABOUT:BEGIN", "<!-- SS-ABOUT:END -->"


def shoestring_about() -> str:
    """The Shoestring Studios 2 part of ABOUT: index.html between the SS-ABOUT marks ('' when they are missing)."""
    try:
        src = (ROOT / "index.html").read_text(encoding="utf-8")
    except OSError:
        return ""
    a, b = src.find(ABOUT_BEGIN), src.find(ABOUT_END)
    if a < 0 or b < a:
        return ""
    return src[src.index("-->", a) + 3:b]


def studio_page(studio_url: str) -> str:
    """The nextop studio page: from the running studio, else the installed package's page."""
    try:
        with urllib.request.urlopen(studio_url, timeout=5) as r:
            return r.read().decode("utf-8")
    except (urllib.error.URLError, OSError, ValueError):
        from nextop.studio import page_path
        return page_path(ROOT).read_text(encoding="utf-8")


def compose(studio_url: str) -> str:
    """The platform page with the Shoestring tabs. Raises ValueError when the page layout is not the expected one."""
    html = studio_page(studio_url)
    n = html.count('"api/')
    if not n:
        raise ValueError("the nextop studio page has no \"api/ calls; the site cannot re-point them")
    html = html.replace('"api/', '"' + API_PREFIX)
    for mark in ("</head>", "</body>", '<nav class="main">'):
        if html.count(mark) != 1:
            raise ValueError("the nextop studio page has %d %s (expected 1)" % (html.count(mark), mark))
    html = html.replace("</head>", HEAD_JS + CSS + "</head>", 1)
    html = html.replace("<title>NAW Studio</title>", "<title>Shoestring Studios</title>", 1)
    about = '<template id="ss-about">' + shoestring_about() + "</template>\n"
    return html.replace("</body>", about + BODY_JS + "</body>", 1)
