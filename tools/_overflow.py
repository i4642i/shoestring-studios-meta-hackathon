"""Measures an HtmlSlide in a real browser (headless Chrome, the same Pretendard font files as Remotion) and lists
what does not fit: elements past the screen edges, text sticking out of its box, text cut off by a clipped box.
Used by tools/preview_slides.py (shown to the slide builder) and workers/editor/checks.py (refuses the save).
A helper, not a tool (the file name starts with _)."""

import json
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONTS = ROOT / "remotion" / "public" / "fonts"
THEMES = ROOT / "remotion" / "src" / "theme.ts"
CHROME = [pathlib.Path(p) for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")]
WEIGHTS = [("Medium", 500), ("SemiBold", 600), ("Bold", 700), ("ExtraBold", 800), ("Black", 900)]
TOLERANCE = 2          # pixels

_SCRIPT = r"""
document.fonts.ready.then(() => {
  const root = document.querySelector('.hs'), R = root.getBoundingClientRect(), out = [];
  const label = e => {
    let n = e.tagName.toLowerCase();
    if (typeof e.className === 'string' && e.className.trim()) n += '.' + e.className.trim().split(/\s+/).join('.');
    const t = (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    return t ? n + ' "' + t + '"' : n;
  };
  const shown = e => { const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const boxed = cs => parseFloat(cs.borderTopWidth) + parseFloat(cs.borderLeftWidth) > 0 ||
    (cs.backgroundColor && !/rgba\(.*, 0\)$|transparent/.test(cs.backgroundColor));
  const leaves = [...root.querySelectorAll('*')].filter(e => shown(e) &&
    (e.tagName === 'IMG' || (![...e.children].length && (e.innerText || '').trim())));
  for (const e of leaves) {
    const r = e.getBoundingClientRect();
    if (!r.width && !r.height) continue;
    const past = [['left', R.left - r.left], ['top', R.top - r.top], ['right', r.right - R.right], ['bottom', r.bottom - R.bottom]]
      .filter(([, v]) => v > TOL).map(([k, v]) => Math.round(v) + 'px past the ' + k + ' edge');
    if (past.length) { out.push(label(e) + ': goes off the screen (' + past.join(', ') + ')'); continue; }
    for (let p = e.parentElement; p && p !== root; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (!boxed(cs)) continue;
      const b = p.getBoundingClientRect();
      const over = [['left', b.left - r.left], ['top', b.top - r.top], ['right', r.right - b.right], ['bottom', r.bottom - b.bottom]]
        .filter(([, v]) => v > TOL).map(([k, v]) => Math.round(v) + 'px past its ' + k);
      if (over.length) out.push(label(e) + ': sticks out of its box ' + label(p) + ' (' + over.join(', ') + ')');
      break;
    }
  }
  for (const e of root.querySelectorAll('*')) {
    if (!shown(e)) continue;
    const cs = getComputedStyle(e);
    if ((cs.overflowY !== 'visible' && e.scrollHeight > e.clientHeight + TOL) ||
        (cs.overflowX !== 'visible' && e.scrollWidth > e.clientWidth + TOL))
      out.push(label(e) + ': text is cut off (' + (e.scrollHeight - e.clientHeight) + 'px hidden); make the box bigger or the text shorter');
  }
  // text styles (the type rules of type_problems): every element with its own text, as the browser computed it
  const probe = document.createElement('div'); probe.style.background = 'var(--hl-bg)'; root.appendChild(probe);
  const hl = getComputedStyle(probe).backgroundColor; probe.remove();
  const ownText = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const texts = [];
  for (const e of root.querySelectorAll('*')) {
    if (!shown(e) || !ownText(e)) continue;
    const cs = getComputedStyle(e), par = e.parentElement, ps = par ? getComputedStyle(par) : cs;
    const inline = cs.display.startsWith('inline') && par && par !== root && ownText(par);
    const marked = inline && (cs.fontWeight !== ps.fontWeight || cs.color !== ps.color || cs.backgroundColor !== ps.backgroundColor);
    const text = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim().replace(/\s+/g, ' ').slice(0, 30);
    texts.push({ text, tag: e.tagName.toLowerCase(), fs: parseFloat(cs.fontSize), fw: parseInt(cs.fontWeight) || 400,
                 ls: cs.letterSpacing === 'normal' ? 0 : parseFloat(cs.letterSpacing) || 0,
                 hangul: /[\uac00-\ud7a3]/.test(text), chip: cs.backgroundColor === hl, inline: !!marked,
                 pfw: parseInt(ps.fontWeight) || 400 });
  }
  const pre = document.createElement('pre'); pre.id = '__ov'; pre.textContent = JSON.stringify({ problems: [...new Set(out)], texts });
  document.body.appendChild(pre);
});
""".replace("TOL", str(TOLERANCE))


def theme_vars(name: str) -> dict:
    """The theme's colors from remotion/src/theme.ts (the same values HtmlSlide gets as CSS variables)."""
    text = THEMES.read_text(encoding="utf-8")
    m = re.search(r"^\s*" + re.escape(name) + r":\s*\{(.*?)\n\s*\},", text, re.S | re.M)
    vals = dict(re.findall(r"(\w+):\s*\"([^\"]*)\"", m.group(1))) if m else {}
    return {"bg": vals.get("bg", "#ffffff"), "bg2": vals.get("bg2", "#eeeeee"), "ink": vals.get("ink", "#111111"),
            "sub": vals.get("sub", "#555555"), "accent": vals.get("accent", "#0f9d6b"),
            "accent-ink": vals.get("accentInk", vals.get("ink", "#111111")), "soft": vals.get("accentSoft", "#dddddd"),
            "line": vals.get("line", "#cccccc"), "font": "'Pretendard', 'Malgun Gothic', sans-serif",
            "accent-text": vals.get("accentText", vals.get("accent", "#0f9d6b")),
            "accent2": vals.get("accent2", vals.get("accent", "#0f9d6b")), "accent2-ink": vals.get("accent2Ink", vals.get("ink", "#111111")),
            "accent3": vals.get("accent3", vals.get("warn", "#d9480f")), "accent3-ink": vals.get("accent3Ink", vals.get("ink", "#111111")),
            "hl-bg": vals.get("hlBg", vals.get("accent", "#0f9d6b")),
            "hl-ink": vals.get("hlInk", vals.get("accentInk", vals.get("ink", "#111111")))}


def measure(html: str, css: str = "", images: dict | None = None, theme: str = "shoestring",
            width: int = 1280, height: int = 720, texts: bool = False):
    """What does not fit in one HtmlSlide (sentences the slide builder can act on). [] = everything fits.
    Returns ["could not measure: ..."] when Chrome is missing or fails (callers treat that as a note, not a failure).
    texts=True: returns (problems, text styles) instead, the styles as the browser computed them
    ([{text, tag, fs, fw, ls, hangul, chip, inline, pfw}], [] when not measured) for type_problems()."""
    got = _measure(html, css, images, theme, width, height)
    return got if texts else got[0]


def _measure(html, css, images, theme, width, height) -> tuple[list[str], list[dict]]:
    chrome = next((p for p in CHROME if p.is_file()), None)
    if chrome is None:
        return ["could not measure: Chrome is not installed"], []
    for name, path in (images or {}).items():
        html = html.replace(f'src="img:{name}"', f'src="{pathlib.Path(str(path)).resolve().as_uri()}"')
    html = re.sub(r"""data-(at|on)=["']?([\d.]+)["']?""", r'data-\1="\2"', html)        # one form: data-on="3.2"
    html = re.sub(r'\sdata-on="[\d.]+"', lambda m: m.group(0) + " data-lit", html)   # measure the lit state too
    v = theme_vars(theme)
    faces = "".join(f"@font-face{{font-family:'Pretendard';font-weight:{w};src:url('{(FONTS / f'Pretendard-{n}.woff2').as_uri()}') format('woff2')}}"
                    for n, w in WEIGHTS if (FONTS / f"Pretendard-{n}.woff2").is_file())
    hs = (".hs{" + "".join(f"--{k}:{val};" for k, val in v.items()) +
          f"font-family:var(--font);color:var(--ink);width:{width}px;height:{height}px;position:relative;overflow:hidden;"
          "word-break:keep-all;background:var(--bg)} .hs *{box-sizing:border-box}")
    page = (f"<!doctype html><html><head><meta charset='utf-8'><style>body{{margin:0}}{faces}{hs}\n{css}</style></head>"
            f"<body><div class='hs'>{html}</div><script>{_SCRIPT}</script></body></html>")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:   # headless Chrome may still hold profile files
        f = pathlib.Path(t) / "slide.html"
        f.write_text(page, encoding="utf-8")
        try:
            r = subprocess.run([str(chrome), "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
                                f"--user-data-dir={pathlib.Path(t) / 'profile'}", "--virtual-time-budget=5000",
                                f"--window-size={width},{height}", "--dump-dom", f.as_uri()],
                               capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return [f"could not measure: {type(e).__name__}"], []
    m = re.search(r'<pre id="__ov">(.*?)</pre>', r.stdout, re.S)
    if not m:
        return ["could not measure: Chrome gave no result"], []
    import html as _html
    got = json.loads(_html.unescape(m.group(1)))
    return list(got.get("problems") or []), list(got.get("texts") or [])


def measure_layer(layer: dict, theme: str, size: tuple[int, int] | None = None, texts: bool = False):
    """measure() for one timeline layer of type HtmlSlide: in a layout slot (size = the slot's w, h, or the layer's
    "box"), else the whole 1280 x 720 screen (an old right slot is 760 wide)."""
    p = layer.get("props") or {}
    box = layer.get("box") or {}
    if size is None and box.get("cw"):
        size = (int(box["cw"]), int(box["ch"]))
    if size is None:
        size = (760 if layer.get("slot") == "right" else 1280, 720)
    return measure(str(p.get("html") or ""), str(p.get("css") or ""), p.get("images") or {}, theme, size[0], size[1],
                   texts)


# ------------------------------------------------------------------ type rules (measured, not judged by an LLM)
# Weight tiers by the CSS font size an HtmlSlide gives a text, in line with the remotion templates (Page.tsx,
# graphics.tsx: big statements 800-900, body labels 600, Kicker 700, SourceTag 600). The templates' own texts
# (Kicker, SourceTag, chart and diagram labels) are drawn by the program and are not checked.
TIERS = [  # (name, smallest CSS px, lowest weight, highest weight, weight to use)
    ("big text", 44, 600, 900, 800),
    ("body text", 28, 500, 700, 600),
    ("small text", 0, 600, 700, 600),
]
EMPHASIS_WEIGHT = (0, 900, 0)        # a marked word inside a line (other weight / color / chip): not thinner than its
                                     # line (the line's weight is the lowest), at most 900
MAX_CHIPS = 2                        # emphasis chips (var(--hl-bg)) on one screen (one HtmlSlide)
TYPE_RULES = ("weight steps (HtmlSlide text, by its CSS font size): big text 44px and up 600-900 (the main statement 800), "
              "body text 28-43px 500-700, small text 27px and below 600-700, a highlighted word inside a line not thinner "
              f"than its line (up to 900); highlight chips (var(--hl-bg)) at most {MAX_CHIPS} on one screen; "
              "letter-spacing 0 or less. The kicker (Kicker 700), the source tag (SourceTag 600, 24px and up) and the "
              "texts of the chart templates are set by the program.")


def tier_of(fs: float) -> tuple:
    return next(t for t in TIERS if fs >= t[1])


def type_problems(texts: list[dict]) -> list[dict]:
    """The type rules on measured text styles -> [{text, property, now, change_to, why}] (computed fixes)."""
    out = []
    for x in texts:
        fw, fs, say = int(x.get("fw") or 400), float(x.get("fs") or 0), str(x.get("text") or "")[:20]
        if x.get("inline"):
            lo, hi, use = EMPHASIS_WEIGHT
            lo = min(max(lo, int(x.get("pfw") or 0)), 900)
            if not lo <= fw <= max(hi, lo):
                to = max(use, lo) if fw < lo else hi
                out.append({"text": say, "property": "font-weight", "now": str(fw), "change_to": str(to),
                            "why": f"A highlighted word inside a line is not thinner than its line ({x.get('pfw')}): {lo}-{max(hi, lo)}."})
        else:
            name, _, lo, hi, use = tier_of(fs)
            if not lo <= fw <= hi:
                to = use if fw < lo else hi
                out.append({"text": say, "property": "font-weight", "now": str(fw), "change_to": str(to),
                            "why": f"{fs:g}px text is {name}, so its weight is {lo}-{hi}."})
        if float(x.get("ls") or 0) > 0.05:          # (ko edition: Korean text only; English: every text)
            out.append({"text": say, "property": "letter-spacing", "now": f"{float(x['ls']):g}px", "change_to": "0",
                        "why": "Wider letter spacing makes the words look scattered (0 or less)."})
    chips = [x for x in texts if x.get("chip")]
    if len(chips) > MAX_CHIPS:
        keep = ", ".join(f'"{x.get("text")}"' for x in chips[:MAX_CHIPS])
        drop = ", ".join(f'"{x.get("text")}"' for x in chips[MAX_CHIPS:])
        out.append({"text": drop, "property": "highlight chips", "now": str(len(chips)), "change_to": str(MAX_CHIPS),
                    "why": f"With many chips it is unclear where to look. Keep only {keep} as chips and remove the chip "
                           f"background from {drop}."})
    return out
