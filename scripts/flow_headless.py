"""Headless Flow tab check: real Chromium layout, no browser needed.

Builds a small harness page from the REAL index.html flow code
(style + flowtab script) and the REAL default flow + catalog, opens
it in headless Edge, and asserts what the user sees: 10 solid + 29
dotted non-degenerate paths, solid labels always on, dotted labels
only on hover/select, 11 nodes pairwise disjoint inside the canvas,
svg size matching the canvas, out-ports inside their footer strip.

Usage: .venv\\Scripts\\python scripts/flow_headless.py
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents._frame import flow as _flow  # noqa: E402

EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

fails = 0


def ok(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails += 1


def main():
    edge = next((p for p in EDGE_PATHS if os.path.isfile(p)), None)
    ok(edge is not None, "edge binary found")
    if edge is None:
        print("1 FAILURES")
        return 1
    page = open(os.path.join(ROOT, "index.html"),
                encoding="utf-8").read()
    styles = re.findall(r"<style>(.*?)</style>", page, re.S)
    ok(len(styles) >= 1, "style block extracted")
    start = page.find("/* Flow tab: visual pipeline editor. */")
    end = page.find("/* Settings: embedding profiles. */")
    ok(start > 0 and end > start, "flowtab script extracted")
    flow_js = page[start:end]
    catalog = _flow.load_catalog()
    default = json.load(open(os.path.join(ROOT, "data", "flows",
                                          "default.json"),
                             encoding="utf-8"))

    def js_str(obj):
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    harness = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>%s</style></head>
<body>
<div class="page" id="p-flow">
<div id="fl-main"><div id="fl-crew"><div id="fl-crewlist"></div></div>
<div id="fl-scroll"><div id="fl-canvas">
<svg id="fl-svg" width="1690" height="710"></svg>
<div id="fl-nodes"></div><div id="fl-linepop"></div>
</div></div></div>
<p id="fl-err"></p><ul id="fl-problems"></ul>
<p id="fl-status"></p><pre id="fl-log"></pre>
<select id="fl-list"></select>
<input id="fl-id"><input id="fl-name"><input id="fl-order">
<button id="fl-save"></button><button id="fl-new"></button>
<button id="fl-run"></button>
<p id="fl-runstate"></p><div id="fl-runs"></div>
</div>
<div id="probe">PENDING</div>
<script>
const esc = (s) => String(s).replace(/&/g, "&amp;")
  .replace(/</g, "&lt;").replace(/>/g, "&gt;");
const CATALOG = %s;
const DEFAULTFLOW = %s;
const api = {
  get: async (u) => {
    if (u === "api/flows/catalog") return CATALOG;
    if (u === "api/flows")
      return {flows: [{id: "default", name: DEFAULTFLOW.name}]};
    if (u === "api/flows/default") return DEFAULTFLOW;
    if (u === "api/flows/runs") return {runs: []};
    throw new Error("stub 404: " + u);
  },
  send: async () => ({errors: []})
};
</script>
<script>
%s
</script>
<script>
(function probe() {
  let tries = 0, clicked = false, settle = 0;
  const timer = setInterval(() => {
    tries++;
    const st = (document.getElementById("fl-status") || {})
      .textContent || "";
    if (!clicked) {
      const probs = (document.getElementById("fl-problems") || {})
        .textContent || "";
      if ((st.indexOf("Loaded") !== 0 || probs.indexOf("Valid") !== 0) &&
          tries <= 600) return;
      // real user path: hidden load, then the Flow tab click
      document.getElementById("p-flow").classList.add("active");
      if (window.__flowShown) window.__flowShown();
      clicked = true;
      return;
    }
    if (++settle < 15) return;
    clearInterval(timer);
    const out = {status: st, clicked: clicked};
    try {
      const svg = document.getElementById("fl-svg");
      const cv = document.getElementById("fl-canvas");
      out.solid = svg.querySelectorAll("path.fl-line").length;
      out.dotted = svg.querySelectorAll("path.fl-pcline").length;
      const span = (d) => {
        const nums = (String(d).match(/-?\\d+(\\.\\d+)?/g) || [])
          .map(Number);
        let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
        for (let i = 0; i + 1 < nums.length; i += 2) {
          x0 = Math.min(x0, nums[i]); x1 = Math.max(x1, nums[i]);
          y0 = Math.min(y0, nums[i + 1]); y1 = Math.max(y1, nums[i + 1]);
        }
        return Math.max(x1 - x0, y1 - y0);
      };
      out.degenerate = 0;
      svg.querySelectorAll("path.fl-line, path.fl-pcline")
        .forEach(p => {
          if (!(span(p.getAttribute("d") || "") > 1)) out.degenerate++;
        });
      out.solidLabels =
        svg.querySelectorAll("text.fl-label").length;
      out.dottedLabels =
        svg.querySelectorAll("text.fl-pclabel").length;
      out.dottedShown =
        svg.querySelectorAll("text.fl-pclabel.on").length;
      const cr = cv.getBoundingClientRect();
      const boxes = [];
      document.querySelectorAll("#fl-nodes .fl-node").forEach(el => {
        const r = el.getBoundingClientRect();
        boxes.push({id: el.dataset.n, x: r.left - cr.left,
                    y: r.top - cr.top, w: r.width, h: r.height});
      });
      out.nodes = boxes.length;
      out.maxH = Math.round(Math.max.apply(
        null, boxes.map(b => b.h).concat([0])));
      out.clash = [];
      for (let i = 0; i < boxes.length; i++)
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i], b = boxes[j];
          if (a.x < b.x + b.w && b.x < a.x + a.w &&
              a.y < b.y + b.h && b.y < a.y + a.h)
            out.clash.push(a.id + "/" + b.id);
        }
      out.outside = boxes.filter(b => b.x < -0.5 || b.y < -0.5 ||
        b.x + b.w > cv.clientWidth + 0.5 ||
        b.y + b.h > cv.clientHeight + 0.5).map(b => b.id);
      out.canvas = [cv.clientWidth, cv.clientHeight,
        +svg.getAttribute("width"), +svg.getAttribute("height")];
      const SW = +svg.getAttribute("width") || 0;
      const SH = +svg.getAttribute("height") || 0;
      out.inside = 0;
      svg.querySelectorAll("path.fl-line, path.fl-pcline")
        .forEach(p => {
          const nums = (p.getAttribute("d").match(/-?\d+(\.\d+)?/g) ||
            []).map(Number);
          for (let i = 0; i + 1 < nums.length; i += 2)
            if (nums[i] >= 0 && nums[i] <= SW &&
                nums[i + 1] >= 0 && nums[i + 1] <= SH) {
              out.inside++;
              break;
            }
        });
      const hit = svg.querySelector("path[data-hover]");
      if (hit) {
        hit.dispatchEvent(new MouseEvent("mouseenter"));
        out.hoverShown =
          svg.querySelectorAll("text.fl-pclabel.on").length;
        hit.dispatchEvent(new MouseEvent("mouseleave"));
        out.unhoverShown =
          svg.querySelectorAll("text.fl-pclabel.on").length;
      }
      const hit2 = svg.querySelector("path[data-hover]");
      if (hit2) {
        hit2.dispatchEvent(
          new MouseEvent("click", {bubbles: true}));
        const pop = document.getElementById("fl-linepop");
        out.popup = pop.style.display === "block" &&
          pop.textContent.indexOf("DELETE LINE") >= 0;
        out.selectShown =
          svg.querySelectorAll("text.fl-pclabel.on").length;
        out.dottedAfterClick =
          svg.querySelectorAll("path.fl-pcline").length;
      }
      out.ports = {rows: 0, edgeOk: 0, spanClear: 0, crewNodes: 0,
                   pcRows: 0, marty: {rows: 0, label: ""}};
      document.querySelectorAll("#fl-nodes .fl-node").forEach(el => {
        const r = el.getBoundingClientRect();
        const nx = r.left - cr.left, ny = r.top - cr.top;
        const rows = el.querySelectorAll("[data-out]");
        const texts = Array.from(el.querySelectorAll("h4, .sub, .req"))
          .map(t => t.getBoundingClientRect());
        rows.forEach(row => {
          const dot = row.querySelector("i");
          const sp = row.querySelector("span");
          if (!dot || !sp) return;
          const dr = dot.getBoundingClientRect();
          const srr = sp.getBoundingClientRect();
          const dcx = dr.left - cr.left + dr.width / 2;
          out.ports.rows++;
          if (Math.abs(dcx - (nx + r.width)) <= 8) out.ports.edgeOk++;
          if (!texts.some(q => srr.left < q.right && q.left < srr.right &&
              srr.top < q.bottom && q.top < srr.bottom))
            out.ports.spanClear++;
        });
        if (el.classList.contains("pcnode")) {
          if (rows.length) out.ports.pcRows++;
          return;
        }
        if (el.dataset.n === "final") return;
        out.ports.crewNodes++;
        if (el.dataset.n === "pd_marty")
          out.ports.marty = {rows: rows.length,
            label: rows.length ?
              rows[0].querySelector("span").textContent : ""};
      });
    } catch (err) {
      out.error = String((err && err.stack) || err);
    }
    document.getElementById("probe").textContent =
      JSON.stringify(out);
  }, 50);
})();
</script>
</body></html>
""" % ("\n".join(styles), js_str(catalog), js_str(default), flow_js)
    tmpd = tempfile.mkdtemp(prefix="flowhead_")
    hp = os.path.join(tmpd, "harness.html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(harness)
    url = "file:///" + hp.replace("\\", "/")
    cmd = [edge, "--headless", "--no-sandbox", "--disable-gpu",
           "--use-angle=swiftshader", "--no-first-run",
           "--disable-extensions",
           "--user-data-dir=" + os.path.join(tmpd, "profile"),
           "--virtual-time-budget=15000",
           "--window-size=1800,1000", "--dump-dom", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        ok(False, "edge headless runs (%s)" % exc)
        print("1 FAILURES")
        return 1
    finally:
        import shutil
        shutil.rmtree(tmpd, ignore_errors=True)
    ok(proc.returncode == 0, "edge headless runs")
    m = re.search(r'<div id="probe">(.*?)</div>', proc.stdout or "",
                  re.S)
    ok(m is not None, "probe output captured")
    if m is None:
        print("STDERR:", (proc.stderr or "")[:500])
        print("STDOUT TAIL:", (proc.stdout or "")[-300:])
        print("1 FAILURES")
        return 1
    try:
        out = json.loads(html.unescape(m.group(1)))
    except ValueError:
        ok(False, "probe output is JSON")
        print("1 FAILURES")
        return 1
    ok(isinstance(out, dict) and out.get("error") is None
       and out.get("status", "").startswith("Loaded"),
       "harness loaded the default flow")
    if not isinstance(out, dict) or out.get("error"):
        print("PROBE ERROR:", (out.get("error") or "?")[:800])
        print("1 FAILURES")
        return 1
    ok(out.get("solid") == 10 and out.get("dotted") == 29,
       "39 paths drawn (10 solid + 29 dotted)")
    ok(out.get("degenerate", -1) == 0, "no degenerate path")
    ok(out.get("solidLabels") == 10, "10 solid labels visible")
    ok(out.get("dottedLabels") == 29 and out.get("dottedShown") == 0,
       "29 dotted labels hidden until hover")
    ok(out.get("nodes") == 11 and out.get("clash") == []
       and out.get("outside") == [],
       "11 nodes disjoint inside the canvas (tallest %spx)" %
       out.get("maxH"))
    cw, ch, sw, sh = out.get("canvas", [0, 0, 0, 0])
    ok(sw > 0 and sh > 0 and sw >= 1690 and sh >= 710
       and abs(cw - sw) <= 2 and abs(ch - sh) <= 2,
       "svg is live and matches the canvas (%dx%d)" % (sw, sh))
    ok(sw > 0 and sh > 0 and out.get("inside", -1) == 39,
       "all 39 paths sit inside the live svg box (%s)" %
       out.get("inside"))
    ok(out.get("hoverShown") == 1 and out.get("unhoverShown") == 0,
       "hover shows exactly one dotted label")
    ok(out.get("popup") is True and out.get("selectShown") == 1
       and out.get("dottedAfterClick") == 29,
       "click selects one dotted line, no duplicates")
    p = out.get("ports", {})
    ok(p.get("rows") == 7 and p.get("edgeOk") == 7
       and p.get("spanClear") == 7 and p.get("pcRows", -1) == 0
       and p.get("crewNodes") == 7,
       "7 out-ports on right edges, labels clear of text")
    m = p.get("marty", {})
    ok(m.get("rows") == 1 and m.get("label") == "Storyboard draft",
       "marty shows one 'Storyboard draft' port")
    if fails:
        print("%d FAILURES" % fails)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
