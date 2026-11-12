// Renders still pictures of the Page composition (like remotion/stills.mjs) and, in the same browser tab, measures
// what is on screen at that frame: every visible text run, picture, shape and boxed element of every layer, with its
// rendered position, font size and entrance time. tools/_layout.py turns the raw measurements into problems to fix.
// Use: node _stills_measure.mjs <remotion dir> <build dir> <props.json> <jobs.json> <measures out.json>
//   jobs = [{"frame": int, "out": "PNG path", "measure": true|false}, ...]
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const [, , remotionDir, serveUrl, propsFile, jobsFile, measureFile] = process.argv;
const require = createRequire(path.join(remotionDir, "package.json"));
const { openBrowser, renderStill, selectComposition } = require("@remotion/renderer");
const { puppeteerEvaluateWithCatch } = require(path.join(path.dirname(require.resolve("@remotion/renderer")), "puppeteer-evaluate.js"));

// Runs in the page at the rendered frame. Returns JSON {containers: n, layers: [[item, ...] per child of the root]}.
const measurePage = () => {
  const vw = 1280, vh = 720;
  // the composition root: walk down single-child wrappers to the element whose children are the Sequences
  let root = document.querySelector("#remotion-canvas") || document.body, guard = 0;
  while (root && root.children.length === 1 && guard++ < 30) root = root.children[0];
  const containers = [...root.children];
  const det = (m) => Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
  const cssScale = (from) => {
    let k = 1;
    for (let p = from; p; p = p.parentElement) {
      const t = getComputedStyle(p).transform;
      if (t && t !== "none") k *= det(new DOMMatrix(t));
    }
    return k;
  };
  const scaleOf = (el) => {           // rendered px per CSS px at el
    if (el instanceof SVGGraphicsElement && el.ownerSVGElement) {
      // inside the svg: its own CTM (viewBox, transform attributes); outside: CSS transforms of the HTML ancestors
      return det(el.getCTM()) * cssScale(el.ownerSVGElement);
    }
    return cssScale(el);
  };
  const opacityOf = (el) => {
    let op = 1;
    for (let p = el; p && p !== root; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.display === "none" || cs.visibility === "hidden") return 0;
      op *= parseFloat(cs.opacity || "1");
    }
    return op;
  };
  const clipOf = (el) => {            // the visible area of el: the frame and every ancestor that clips
    let c = [0, 0, vw, vh];
    for (let p = el.parentElement; p && p !== root; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.overflowX !== "visible" || cs.overflowY !== "visible") {
        const r = p.getBoundingClientRect();
        c = [Math.max(c[0], r.left), Math.max(c[1], r.top), Math.min(c[2], r.right), Math.min(c[3], r.bottom)];
      }
    }
    return c;
  };
  const cut = (r, c) => [Math.max(r[0], c[0]), Math.max(r[1], c[1]), Math.min(r[2], c[2]), Math.min(r[3], c[3])];
  const ok = (r) => r[2] - r[0] > 1 && r[3] - r[1] > 1;
  const atOf = (el) => {
    for (let p = el; p && p !== root; p = p.parentElement) {
      const v = p.getAttribute ? p.getAttribute("data-at") : null;
      if (v !== null) return parseFloat(v) || 0;
    }
    return 0;
  };
  const clear = (c) => !c || /transparent/.test(c) || /rgba\([^)]*,\s*0\)$/.test(c);
  const filled = (cs) => !clear(cs.backgroundColor) || (cs.backgroundImage && cs.backgroundImage !== "none") ||
    ["Top", "Right", "Bottom", "Left"].some((k) => parseFloat(cs["border" + k + "Width"]) >= 2 && !clear(cs["border" + k + "Color"]));
  const name = (el) => {
    let n = el.tagName.toLowerCase();
    const c = el.getAttribute ? el.getAttribute("class") : null;
    if (c && c.trim()) n += "." + c.trim().split(/\s+/).slice(0, 3).join(".");
    return n;
  };
  const out = [];
  containers.forEach((box) => {
    const items = [], ids = new Map();
    for (const el of [box, ...box.querySelectorAll("*")]) {
      const tag = el.tagName.toLowerCase();
      if (["style", "script", "defs", "filter", "lineargradient", "radialgradient", "clippath", "mask", "br"].includes(tag)) continue;
      if (el.closest("defs,filter,clipPath,mask")) continue;
      const op = opacityOf(el);
      if (op < 0.08) continue;
      const clip = clipOf(el);
      const push = (kind, r, extra) => {
        const rc = cut(r, clip);
        if (!ok(rc)) return;
        const id = items.length;
        ids.set(el, id);
        const anc = [];
        for (let p = el.parentElement; p && p !== box.parentElement; p = p.parentElement) if (ids.has(p)) anc.push(ids.get(p));
        items.push({ id, kind, tag: name(el), rect: rc.map((v) => Math.round(v)), op: +op.toFixed(2), at: atOf(el), anc, ...extra });
      };
      const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
      if (own.length) {
        let r = null;
        const lines = [];
        for (const n of own) {
          const rg = document.createRange();
          rg.selectNodeContents(n);
          for (const q of rg.getClientRects()) {
            if (q.width < 1) continue;
            const l = cut([q.left, q.top, q.right, q.bottom], clip);
            if (ok(l)) lines.push(l.map((v) => Math.round(v)));
            r = r ? [Math.min(r[0], q.left), Math.min(r[1], q.top), Math.max(r[2], q.right), Math.max(r[3], q.bottom)]
                  : [q.left, q.top, q.right, q.bottom];
          }
        }
        if (r) {
          const cs = getComputedStyle(el), fs = parseFloat(cs.fontSize), b = el.getBoundingClientRect();
          const pad = !(el instanceof SVGElement) && filled(cs) ? cut([b.left, b.top, b.right, b.bottom], clip).map((v) => Math.round(v)) : null;
          push("text", r, { text: own.map((n) => n.textContent).join(" ").trim().replace(/\s+/g, " ").slice(0, 40),
                            fs, px: +(fs * scaleOf(el)).toFixed(1), lines, pad });
          continue;
        }
      }
      const b = el.getBoundingClientRect(), r = [b.left, b.top, b.right, b.bottom];
      if (["img", "video", "canvas", "image"].includes(tag)) { push("img", r, {}); continue; }
      if (el instanceof SVGGraphicsElement && ["path", "circle", "rect", "ellipse", "line", "polyline", "polygon"].includes(tag)) {
        push("shape", r, {});
        continue;
      }
      if (!(el instanceof SVGElement)) {
        const cs = getComputedStyle(el);
        if (filled(cs)) push("box", r, { bgc: clear(cs.backgroundColor) ? "" : cs.backgroundColor,
          deco: (cs.backgroundImage && cs.backgroundImage !== "none") ||
                ["Top", "Right", "Bottom", "Left"].some((k) => parseFloat(cs["border" + k + "Width"]) >= 2 && !clear(cs["border" + k + "Color"])) });
      }
    }
    out.push(items);
  });
  return JSON.stringify({ containers: containers.length, layers: out });
};

const inputProps = JSON.parse(fs.readFileSync(propsFile, "utf8"));
const jobs = JSON.parse(fs.readFileSync(jobsFile, "utf8"));
const browser = await openBrowser("chrome");
const results = [];
let current = null;
// renderStill closes its tab right after the screenshot: measure the same tab (same frame) just before that
const newPage = browser.newPage.bind(browser);
browser.newPage = async (...a) => {
  const page = await newPage(...a);
  const close = page.close.bind(page);
  page.close = async (...b) => {
    if (current && current.measure) {
      try {
        const v = await puppeteerEvaluateWithCatch({ page, pageFunction: measurePage, args: [], frame: null, timeoutInMilliseconds: 30000 });
        results.push({ out: current.out, frame: current.frame, ...JSON.parse(v.value) });
      } catch (e) {
        results.push({ out: current.out, frame: current.frame, error: String(e).slice(0, 300) });
      }
      current = null;
    }
    return close(...b);
  };
  return page;
};
try {
  const composition = await selectComposition({ serveUrl, id: "Page", inputProps, puppeteerInstance: browser, logLevel: "error" });
  for (const j of jobs) {
    const frame = Math.max(0, Math.min(composition.durationInFrames - 1, j.frame));
    current = { ...j, frame };
    await renderStill({ composition, serveUrl, output: j.out, frame, inputProps, puppeteerInstance: browser, imageFormat: "png", logLevel: "error", overwrite: true });
    console.log("OK", j.out);
  }
} finally {
  current = null;
  fs.writeFileSync(measureFile, JSON.stringify(results));
  await browser.close({ silent: true });
}
