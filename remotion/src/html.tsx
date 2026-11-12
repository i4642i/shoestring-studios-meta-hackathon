// HtmlSlide (2026-11-09): the slide builder designs a whole screen in HTML + CSS.
// Motion is driven by the frame (deterministic), not by CSS animations:
//   data-at="1.5"    the element enters (fade + rise) 1.5 s after the layer starts
//   data-on="3.2"    from 3.2 s the attribute data-lit is added (style it with [data-lit] in the CSS: the focus moves)
// Images: src="img:<name>" takes the file from props.images[name] (local paths are served by the renderer).
// Theme colors and the font are CSS variables: --bg --bg2 --ink --sub --accent --accent-ink --soft --line --font,
// and (2026-11-11) --accent-text --accent2 --accent2-ink --accent3 --accent3-ink --hl-bg --hl-ink.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { f, useT, isPrint } from "./ctx";

// values may come quoted ("1.5", '1.5') or bare (1.5): HTML allows all three
const AT = /data-at=["']?([\d.]+)["']?/g;
const ON = /data-on=["']?([\d.]+)["']?/g;
// one form for the CSS selectors below: data-at="1.5"
const quoteAttrs = (html: string) =>
  html.replace(/data-(at|on)=["']?([\d.]+)["']?/g, (_m, k, v) => `data-${k}="${v}"`);

export const HtmlSlide: React.FC<{ html: string; css?: string; images?: Record<string, string>; dur: number }> =
  ({ html, css = "", images = {}, dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const print = isPrint();
    html = quoteAttrs(html);
    const times = Array.from(new Set(Array.from(html.matchAll(AT)).map((m) => m[1])));
    const enter = times.map((s) => {
      const p = print ? 1 : interpolate(frame, [f(+s), f(+s) + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
      return `[data-at="${s}"]{opacity:${p.toFixed(3)};transform:translateY(${((1 - p) * 24).toFixed(1)}px)}`;
    }).join("\n");
    let body = html.replace(ON, (all, s) => (print || frame >= f(+s) ? `${all} data-lit` : all));
    body = body.replace(/src="img:([^"]+)"/g, (all, name) => (images[name] ? `src="${images[name]}"` : all));
    const out = print ? 1 : interpolate(frame, [f(dur) - 8, f(dur)], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const vars = `.hs{--bg:${t.bg};--bg2:${t.bg2};--ink:${t.ink};--sub:${t.sub};--accent:${t.accent};` +
      `--accent-ink:${t.accentInk || t.ink};--soft:${t.accentSoft};--line:${t.line};--font:${t.font};` +
      `--accent-text:${t.accentText || t.accent};--accent2:${t.accent2 || t.accent};--accent2-ink:${t.accent2Ink || t.ink};` +
      `--accent3:${t.accent3 || t.warn};--accent3-ink:${t.accent3Ink || t.ink};--hl-bg:${t.hlBg || t.accent};--hl-ink:${t.hlInk || t.accentInk || t.ink};` +
      `font-family:var(--font);color:var(--ink);width:100%;height:100%;position:relative;overflow:hidden;word-break:keep-all}` +
      `.hs *{box-sizing:border-box}`;
    return (
      <AbsoluteFill style={{ opacity: out }}>
        <style>{vars + "\n" + css + "\n" + enter}</style>
        <div className="hs" dangerouslySetInnerHTML={{ __html: body }} />
      </AbsoluteFill>
    );
  };
