import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, Easing, continueRender, delayRender } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import katex from "katex";
import "katex/dist/katex.min.css";
import { FPS, f, useT, isPrint } from "./ctx";

// ---------------------------------------------------------------- 그래픽 담당의 화면 틀(2026-10-16): 수식·막대그래프·3D 막대
// 색·글꼴은 테마가 정한다. 그래픽 담당은 값(수식·숫자)만 넣는다.

const ease = Easing.bezier(0.2, 0.8, 0.2, 1);
// 인쇄 모드 = 심사용 슬라이드 = 장면의 완성 화면(2026-10-23 사용자: "정적인 슬라이드를 먼저 만들고 효과는 그 뒤에").
// 효과(나타남·바뀜·사라짐)는 영상에서만 — 슬라이드에는 장면의 모든 내용이 다 놓인다. 내용을 갈아 끼우는 효과(수식 replace·목록 집중 설명)는
// 각 부품이 인쇄 모드에서 나열로 그린다(아래 Formula·Steps).
const prog = (frame: number, a: number, b: number) => (isPrint() ? 1 : interpolate(frame, [f(a), f(b)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease }));
const useOut = (dur: number) => {
  const frame = useCurrentFrame();
  return isPrint() ? 1 : interpolate(frame, [f(dur) - 7, f(dur)], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
};
const X = 84;
const TOP = 150, BOTTOM = 50;   // 위는 단계 표시·소제목(docu: 46~130px) 아래부터
// 수식은 아래 자막 띠(bottom 48 · 높이 약 64px) 자리를 비워 둔다 — 예전엔 BOTTOM 50 까지 써서 긴 식의 마지막 줄이 띠 뒤로 숨었다(2026-10-24 2화 S05 c05 4회 불통과)
const F_BOTTOM = 130;

// 가운뎃점 '·'(U+00B7)은 KaTeX 가 \cdotp 로 바꿔 	ext{} 안에서 '정의되지 않은 명령' 오류가 난다(한국어 글에 흔함 — 2026-10-24 2화 S05 c05).
// 작은 점 '‧'(U+2027)로 바꿔 그린다('∙'는 굵게 찍혔다). 렌더 전 검사(katex_check.js)도 같은 규칙.
const texSafe = (s: string) => String(s || "").replace(/·/g, "‧");

function tex(src: string) {
  try {
    return katex.renderToString(texSafe(src), { displayMode: true, throwOnError: false, output: "html" });
  } catch {
    return src;
  }
}

// 설명줄 안의 $…$ 는 작은 수식으로(2026-10-20 2화 S07 c03: '$b_T$ = +1(매수 체결)' 이 달러 기호째 글자로 찍혔다)
const inlineTex = (s: string) => String(s || "").split(/(\$[^$]+\$)/g).map((part) => {
  if (part.length > 2 && part.startsWith("$") && part.endsWith("$")) {
    try { return katex.renderToString(texSafe(part.slice(1, -1)), { displayMode: false, throwOnError: false, output: "html" }); } catch { return part; }
  }
  return part.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}).join("");
const Rich: React.FC<{ text: string; style: React.CSSProperties }> = ({ text, style }) =>
  text.includes("$") ? <div style={style} dangerouslySetInnerHTML={{ __html: inlineTex(text) }} /> : <div style={style}>{text}</div>;

// 수식(2026-10-17 확장):
//  - steps: 식 단계(최대 4줄). mode "stack"(기본: 아래로 쌓이고 앞 줄은 흐려짐) | "replace"(같은 자리에서 앞 식이 다음 식으로 바뀜)
//  - stepAt: 단계마다 나타나는 시각(초, 장면 시작 기준 — 비우면 고르게)
//  - highlights: [{term: 강조할 항(LaTeX), at: 시각(초), step: 몇 번째 줄(1부터, 비우면 모든 줄)}] — 그 시각부터 그 항에 형광펜
type Hi = { term: string; at?: number; step?: number };
// 항을 낱말 단위로만 바꾼다(2026-10-20 2화 S13: 'h' 강조가 \Rightarrow 안의 h 까지 감싸 '\Rig h tarrow' 로 깨졌다).
// 항이 영문자로 시작하면 앞이 영문자·역슬래시(명령어 안)일 때, 영문자로 끝나면 뒤가 영문자일 때는 건너뛴다.
export function hiTerm(src: string, term: string, rep: string) {
  const esc = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pre = /^[A-Za-z]/.test(term) ? "(?<![A-Za-z\\\\])" : "";
  const post = /[A-Za-z]$/.test(term) ? "(?![A-Za-z])" : "";
  return src.replace(new RegExp(pre + esc + post, "g"), () => rep);
}
// 식 번호(\tag)는 강의 노트·대본이 식을 가리킬 때 쓰는 것 — 영상 화면에는 "(1)" 이 필요 없어 뺀다(2026-10-17)
const stripDollar = (s: string) => String(s || "").trim().replace(/^\$\$?|\$\$?$/g, "").replace(/\\tag\*?\{[^}]*\}/g, "").trim();

export const Formula: React.FC<{ steps?: string[]; latex?: string; label?: string; notes?: string[]; gap?: number; note?: string;
  mode?: "stack" | "replace"; stepAt?: number[]; highlights?: Hi[]; dur: number }> =
  ({ steps, latex, label, notes = [], gap, note, mode = "stack", stepAt, highlights = [], dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    const list = (steps && steps.length ? steps : latex ? [latex] : []).slice(0, 4).map(stripDollar);
    const every = gap ?? Math.max(0.8, (dur - 1) / Math.max(1, list.length));
    const startOf = (i: number) => (stepAt && typeof stepAt[i] === "number" ? stepAt[i] : 0.2 + i * every);
    const replace = mode === "replace" && !isPrint();   // 슬라이드에는 식을 나열한다 — 같은 자리 갈아 끼우기는 영상에서만(2026-10-23 사용자)
    const size = replace ? (list.some((s) => s.length > 60) ? 52 : 64) : list.length > 2 ? 36 : list.length > 1 ? 44 : 60;
    const now = frame / FPS;
    // 이 줄에 지금 켜진 강조를 입힌다: 항을 \colorbox 로 감싼다(형광펜)
    const withHi = (src: string, i: number) => {
      let s = src;
      for (const h of highlights) {
        const term = stripDollar(h.term);
        if (!term || (!isPrint() && typeof h.at === "number" && now < h.at) || (h.step && h.step !== i + 1)) continue;
        s = hiTerm(s, term, `\\colorbox{${t.fill || t.accent}}{$${term}$}`);
      }
      return s;
    };
    const current = list.reduce((acc, _s, i) => (now >= startOf(i) ? i : acc), 0);
    // 화면 안에 맞추기(2026-10-19 2화 S12: 긴 식 세 줄이 위로는 단계 표시와 겹치고 아래·오른쪽으로는 화면 밖으로 나갔다).
    // 줄마다 넓으면 그 줄만 줄이고, 다 쌓은 높이가 넘치면 전체를 줄인다. 글꼴이 다 불러와진 뒤 잰다.
    const { width, height } = useVideoConfig();
    const root = useRef<HTMLDivElement>(null);
    const [wait] = useState(() => delayRender("fit formula size"));
    const fit = () => {
      const el = root.current;
      if (!el) return;
      // 위 제목(label) 높이도 빼고 잰다 — 빼지 않으면 식 묶음이 넘칠 때 가운데 맞춤이 제목을 위로 밀어 소제목과 겹쳤다(S05 c05)
      const lab = el.querySelector<HTMLElement>("[data-fit-label]");
      const availW = width - X - 80 - 30, availH = height - TOP - F_BOTTOM - (lab ? lab.offsetHeight + 18 : 0);
      el.querySelectorAll<HTMLElement>("[data-fit-line]").forEach((ln) => {
        ln.style.zoom = "1";
        ln.style.zoom = String(Math.min(1, availW / Math.max(1, ln.scrollWidth)));
      });
      const all = el.querySelector<HTMLElement>("[data-fit-all]");
      if (all) {
        all.style.zoom = "1";
        all.style.zoom = String(Math.min(1, availH / Math.max(1, all.scrollHeight)));
      }
    };
    useLayoutEffect(fit);
    useEffect(() => { document.fonts.ready.then(() => { fit(); continueRender(wait); }); }, []);
    return (
      // AbsoluteFill 은 ref 를 넘겨주지 않는다(4.0.535) — 그래서 일반 div 로 같은 채움 상자를 만든다
      <div ref={root} style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", paddingLeft: X, paddingRight: 80, paddingTop: TOP, paddingBottom: F_BOTTOM, opacity: out }}>
        <style>{".katex-display{margin:0 !important} .katex .colorbox{padding:0 4px;border-radius:3px}"}</style>
        {label ? <div data-fit-label><Rich text={label} style={{ fontFamily: t.font, fontWeight: 900, fontSize: 40, color: t.ink, letterSpacing: "-0.03em", marginBottom: 18 }} /></div> : null}
        {replace ? (
          // 같은 칸(grid 1/1)에 겹쳐 두어 상자 높이가 가장 긴 식+설명에 맞는다 — 예전 absolute 는 높이가 고정이라 아래 note 와 겹쳤다
          <div data-fit-all style={{ display: "grid" }}>
            {list.map((s, i) => {
              const a = startOf(i), b = i + 1 < list.length ? startOf(i + 1) : dur + 1;
              const pin = prog(frame, a, a + 0.45), pout = prog(frame, b, b + 0.35);
              const op = Math.max(0, Math.min(pin, 1 - pout));
              return (
                <div key={i} style={{ gridArea: "1 / 1", minWidth: 0, opacity: op, transform: `translateY(${(1 - pin) * 26 - pout * 20}px)`,
                  borderLeft: `8px solid ${t.accent}`, paddingLeft: 22 }}>
                  <div data-fit-line style={{ fontSize: size, color: t.ink, width: "max-content" }} dangerouslySetInnerHTML={{ __html: tex(withHi(s, i)) }} />
                  {notes[i] ? <Rich text={notes[i]} style={{ fontFamily: t.font, fontWeight: 700, fontSize: 28, color: t.sub, marginTop: 10, wordBreak: "keep-all" }} /> : null}
                </div>
              );
            })}
          </div>
        ) : <div data-fit-all>{list.map((s, i) => {
          const at = startOf(i);
          const p = prog(frame, at, at + 0.5);
          const last = isPrint() || (i === current && now >= at);   // 슬라이드는 모든 줄이 진하게(앞 줄을 흐리게 하는 것은 영상 효과)
          // 설명은 식 아래에 — 옆에 두면 긴 식에 밀려 좁은 칸에서 한 글자씩 줄이 바뀌고 화면 밖으로 잘렸다
          return (
            <div key={i} style={{ opacity: p * (last ? 1 : 0.38), transform: `translateY(${(1 - p) * 24}px)`,
              borderLeft: `8px solid ${last ? t.accent : "transparent"}`, paddingLeft: 22, margin: "14px 0" }}>
              <div data-fit-line style={{ fontSize: size, color: t.ink, width: "max-content" }} dangerouslySetInnerHTML={{ __html: tex(withHi(s, i)) }} />
              {notes[i] ? <Rich text={notes[i]} style={{ fontFamily: t.font, fontWeight: 700, fontSize: 24, color: t.sub, marginTop: 6, wordBreak: "keep-all" }} /> : null}
            </div>
          );
        })}</div>}
        {note ? <Rich text={note} style={{ fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub, marginTop: 18 }} /> : null}
      </div>
    );
  };

// ---------------------------------------------------------------- 곡선(2026-10-17): 함수 곡선·정규분포 + 구간 면적 칠하기 + 기준선
type Pt = [number, number];
const normalPts = (mu: number, sigma: number): Pt[] => {
  const out: Pt[] = [];
  for (let i = 0; i <= 120; i++) {
    const x = mu - 4 * sigma + (8 * sigma * i) / 120;
    out.push([x, Math.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * Math.sqrt(2 * Math.PI))]);
  }
  return out;
};
// 그래프 색 이름(2026-10-19 플랫폼 표현력): 테마 색만 고른다 — 아무 색이나 쓰면 화면 톤이 깨진다
// 곡선 그래프 선 수 상한 — 예전 3개(2026-10-22: '가능했던 경로 여러 개 중 하나'를 그릴 수 없었다). 4개 이상이면 기본 선은 가늘게(아래)
const MAX_CURVES = 8;
const tone = (t: any, name?: string, fallback?: string) =>
  ({ ink: t.ink, accent: t.accent, warn: t.warn, sub: t.sub, blue: "#2b5aa8", green: "#2f7d4f", red: "#c92a2a" } as Record<string, string>)[name || ""] || fallback || t.ink;
// 화살표 주석: 글이 점 위(또는 아래)에 놓이고, 짧은 화살표가 점을 가리킨다
const Callout: React.FC<{ x: number; y: number; text: string; W: number; T: number; op: number; t: any }> = ({ x, y, text, W, T, op, t }) => {
  const up = y > T + 90;                       // 위에 자리가 있으면 위에, 없으면 아래에
  const ty = up ? y - 70 : y + 78, left = x > W * 0.65;
  const tx = left ? x - 20 : x + 20;
  const ay = up ? y - 12 : y + 12;
  return <g opacity={op}>
    <line x1={tx} y1={up ? ty + 8 : ty - 26} x2={x} y2={ay} stroke={t.ink} strokeWidth={2.5} />
    <path d={`M${x},${ay} l${up ? -7 : -7},${up ? -12 : 12} l14,0 Z`} fill={t.ink} transform={`rotate(${Math.atan2(ay - (up ? ty + 8 : ty - 26), x - tx) * 180 / Math.PI - 90} ${x} ${ay})`} />
    <text x={tx} y={ty} textAnchor={left ? "end" : "start"} fontFamily={t.font} fontWeight={800} fontSize={24} fill={t.ink} stroke={t.bg} strokeWidth={6} paintOrder="stroke">{text}</text>
  </g>;
};

const fmtNum = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : Number(v.toFixed(2)).toString());
// 눈금 숫자는 폭(span)에 맞춰 자릿수를 정한다 — 99.9~101.1 을 '101·101·99.9' 로 찍던 문제(2026-10-20 2화 S06)
// y 눈금은 축 끝값(여백이 붙은 20.1·58.6 등)이 아니라 1·2·5×10ⁿ 간격의 둥근 값으로(2026-10-22 1화 S02 c06 심사: '눈금이 소수로 어긋나 읽기 어렵다')
const niceTicks = (lo: number, hi: number, want = 5): number[] => {
  const span = hi - lo;
  if (!(span > 0)) return [lo];
  const raw = span / want, mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toFixed(10)));
  return out;
};
const fmtTick = (v: number, span: number) => Number(v.toFixed(span >= 20 ? (Math.abs(v) >= 100 ? 0 : 1) : span >= 2 ? 1 : 2)).toString();   // 끝의 .0 은 떼어 낸다(60.0 → 60, 2026-10-22 심사)

export const Curve: React.FC<{ curves?: { points: Pt[]; label?: string; color?: string; dash?: boolean; axis?: string }[]; dist?: { mu: number; sigma: number; label?: string };
  shade?: { from?: number; to?: number; label?: string; curve?: number }; marks?: { x: number; label?: string }[]; xticks?: { x: number; label: string }[];
  yticks?: boolean; callouts?: { x: number; y: number; text: string }[];
  title?: string; xlabel?: string; ylabel?: string; note?: string; dur: number }> =
  ({ curves = [], dist, shade, marks = [], xticks, yticks, callouts = [], title, xlabel, ylabel, note, dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    // 숫자가 아닌 값이 하나라도 섞이면 축 전체가 NaN 이 돼 곡선이 사라지고 'NaN' 눈금이 찍혔다(2026-10-22 1화 S02 dist: 0.85) — 올바른 분포·점만 쓴다
    const fin = (v: unknown) => typeof v === "number" && Number.isFinite(v);
    const okDist = !!dist && typeof dist === "object" && fin(dist.mu) && fin(dist.sigma) && dist.sigma > 0;
    const all: { points: Pt[]; label?: string; color?: string; dash?: boolean; axis?: string }[] =
      [...(okDist ? [{ points: normalPts(dist!.mu, dist!.sigma), label: dist!.label }] : []), ...curves]
        .map((c) => ({ ...c, points: (c.points || []).filter((p) => Array.isArray(p) && fin(p[0]) && fin(p[1])) }))
        .filter((c) => c.points.length > 1).slice(0, MAX_CURVES);
    if (!all.length) return null;
    // 오른쪽 보조 축(axis: "right", 2026-10-24 2화 S09 c03): 크기가 크게 다른 선(가치 1.0~1.08 과 비용 0~0.14)을 한 축에 그리면 큰 쪽이 평평해져
    // 14회차 같은 불통과가 났다. 오른쪽 축 곡선은 따로 배율을 잡고 오른쪽에 눈금을 단다. 칠하기·주석·세로선은 왼쪽 축 기준.
    const leftC = all.filter((c) => c.axis !== "right"), rightC = all.filter((c) => c.axis === "right");
    const scaleOf = (cs: typeof all, dist0: boolean) => {
      const ys = cs.flatMap((c) => c.points.map((p) => p[1]));
      // 2026-10-17 심사: 0 에서 먼 값(가격·금리)은 0 부터 그리면 화면 위쪽에 납작하게 몰려 '벌어짐'이 안 보였다 → 값이 모두 양수이고 0 에서 멀면 아래를 잘라 확대
      const ymin = Math.min(...ys), ymax = Math.max(...ys);
      const zoom = !dist0 && ymin > 0 && ymin > ymax * 0.35;
      const y0 = zoom ? ymin - (ymax - ymin) * 0.12 : Math.min(0, ...ys), y1 = (zoom ? ymax + (ymax - ymin) * 0.12 : ymax * 1.08) || 1;
      return { y0, y1, base: zoom ? y0 : 0 };
    };
    const xs = all.flatMap((c) => c.points.map((p) => p[0]));
    const { y0, y1, base } = scaleOf(leftC.length ? leftC : all, okDist);
    const rs = rightC.length && leftC.length ? scaleOf(rightC, false) : null;
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const W = 1020, H = 360, L = 70, R = rs ? 90 : 30, T = 20, Bm = 70;   // 오른쪽 축이 있으면 눈금 자리(scenes.curve_label_boxes 와 같은 값)   // 높이 400→360: 제목을 소제목(top 104~130) 아래로 내린 만큼 줄여 아래 자막과 안 겹치게(2026-10-20)
    // 아래 여백 50→70: 가로축 이름을 눈금 아래 줄로 내림 — 맨 오른쪽 눈금('끝'·'20분')과 같은 줄에서 겹치던 문제(2026-10-20, app/video/scenes.curve_label_boxes 와 같은 식)
    const sx = (x: number) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - R);
    const sy = (y: number) => H - Bm - ((y - y0) / (y1 - y0 || 1)) * (H - T - Bm);
    const syR = (y: number) => (rs ? H - Bm - ((y - rs.y0) / (rs.y1 - rs.y0 || 1)) * (H - T - Bm) : sy(y));
    const syOf = (c: { axis?: string }) => (c.axis === "right" ? syR : sy);
    const draw = prog(frame, 0.2, Math.min(2.4, dur * 0.55));
    const colors = all.map((c, i) => tone(t, c.color, [t.ink, t.warn, t.sub][i]));
    const first = all[0].points;
    // shade.curve(1부터): 칠할 곡선 — 기본은 첫 곡선. 다른 곡선의 손실(0 아래) 구간을 칠할 수 없어 같은 불통과가 되풀이됐다(2026-10-23 1화 S03 c12)
    const shPts = (shade && typeof shade.curve === "number" && all[shade.curve - 1]) ? all[shade.curve - 1].points : first;
    const sh = shade ? shPts.filter((p) => p[0] >= (shade.from ?? -Infinity) && p[0] <= (shade.to ?? Infinity)) : [];
    const shBelow = sh.length > 0 && sh.reduce((a, p) => a + p[1], 0) / sh.length < base;   // 기준선 아래 구간이면 이름도 기준선 아래에
    const shadeOp = prog(frame, Math.min(2.4, dur * 0.55), Math.min(3.0, dur * 0.7));
    return (
      <AbsoluteFill style={{ paddingLeft: X - 20, paddingTop: 140, opacity: out }}>
        {title ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 42, color: t.ink, letterSpacing: "-0.03em", marginBottom: 14, paddingLeft: 20 }}>{title}</div> : null}
        {/* 그래프 설명(note)은 제목 바로 아래 — 그래프 밑에 두면 화면 아래 자막 띠와 겹쳐 가려졌다(2026-10-23 1화 S03 c13 심사) */}
        {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub, marginTop: -6, marginBottom: 10, paddingLeft: 20 }}>{note}</div> : null}
        {/* 범례: 곡선이 둘 이상이면 그래프 바깥(제목 아래)에 — 그래프 안에 두면 기준선 이름과 겹쳤다(2026-10-17 시험) */}
        {all.length > 1 ? <div style={{ display: "flex", gap: 34, paddingLeft: 20 + L, marginBottom: 6, opacity: prog(frame, 0.2, 0.6) }}>
          {all.map((c, ci) => c.label ? <div key={ci} style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: t.font, fontWeight: 800, fontSize: 24, color: colors[ci] }}>
            <span style={{ width: 30, height: 7, display: "inline-block", background: c.dash ? `repeating-linear-gradient(90deg, ${colors[ci]} 0 8px, transparent 8px 13px)` : colors[ci] }} />{c.label}{rs && c.axis === "right" ? " (오른쪽 축)" : ""}</div> : null)}
        </div> : null}
        <svg width={W} height={H}>
          <line x1={L} x2={W - R} y1={sy(base)} y2={sy(base)} stroke={t.ink} strokeWidth={2.5} />
          <line x1={L} x2={L} y1={T} y2={H - Bm} stroke={t.line} strokeWidth={2} />
          {/* x 눈금: xticks(글자 눈금, 예: 5월·7월)를 주면 그것만 — 숫자 눈금과 함께 찍혀 '7.5월'이 생기던 문제(2026-10-17 심사) */}
          {(xticks && xticks.length ? xticks.map((k) => ({ x: k.x, s: k.label })) : niceTicks(x0, x1, 4).map((v) => ({ x: v, s: fmtTick(v, x1 - x0) }))).map((k, i) =>
            <text key={i} x={sx(k.x)} y={H - Bm + 28} textAnchor="middle" fontFamily={t.font} fontSize={20} fontWeight={600} fill={t.sub}>{k.s}</text>)}
          {sh.length > 1 ? <path d={`M${sx(sh[0][0])},${sy(base)} ` + sh.map((p) => `L${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ") + ` L${sx(sh[sh.length - 1][0])},${sy(base)} Z`}
            fill={t.fill || t.accent} opacity={0.75 * shadeOp} /> : null}
          {all.map((c, ci) => {
            const n = Math.max(2, Math.ceil(draw * c.points.length));
            const cy = syOf(c);
            const d = c.points.slice(0, n).map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${cy(p[1]).toFixed(1)}`).join(" ");
            // 곡선 하나면 이름을 가장 높은 곳 위에, 둘 이상이면 오른쪽 위 범례로(선 위에 붙은 이름이 선·눈금과 뭉치던 문제, 2026-10-17 심사)
            const top = c.points.reduce((a, p) => (p[1] > a[1] ? p : a), c.points[0]);
            // 가장 높은 곳이 왼쪽 위 세로축 이름 자리면 이름을 곡선 오른쪽 끝으로(2026-10-20 2화 S09B — '가격(예시 모양)'이 '가격(예시 값)'을 덮음)
            const last = c.points[c.points.length - 1];
            const onY = !!ylabel && sx(top[0]) + 14 < L + 16 + ylabel.length * 20 && sy(top[1]) - 8 < T + 34;
            // 선이 4개 이상(가능한 경로 여럿 + 강조 하나, 2026-10-22 S04 c12)이면 색을 안 정했거나 sub 인 선은 가늘게 — 강조 선이 묻히지 않게
            const thin = all.length > 3 && (!c.color || c.color === "sub");
            return <g key={ci}><path d={d} fill="none" stroke={colors[ci]} strokeWidth={thin ? 2.5 : 6} opacity={thin ? 0.55 : 1} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={c.dash ? "14 12" : undefined} />
              {c.label && draw >= 1 && all.length === 1 ? (onY
                ? <text x={sx(last[0])} y={sy(last[1]) - 14} textAnchor="end" fontFamily={t.font} fontWeight={800} fontSize={24} fill={colors[ci]} stroke={t.bg} strokeWidth={6} paintOrder="stroke">{c.label}</text>
                // 가장 높은 곳이 오른쪽 끝 가까이면 이름을 왼쪽으로 붙인다 — 오른쪽으로 내보내면 화면 밖에서 잘렸다(2026-10-22 S04 c05 '기대: …'가 '기'만 보임)
                : sx(top[0]) > W * 0.7
                  ? <text x={sx(top[0]) - 8} y={sy(top[1]) - 16} textAnchor="end" fontFamily={t.font} fontWeight={800} fontSize={24} fill={colors[ci]} stroke={t.bg} strokeWidth={6} paintOrder="stroke">{c.label}</text>
                  : <text x={sx(top[0]) + 14} y={sy(top[1]) - 8} textAnchor="start" fontFamily={t.font} fontWeight={800} fontSize={24} fill={colors[ci]}>{c.label}</text>) : null}</g>;
          })}
          {marks.map((m, i) => <g key={i} opacity={shadeOp}><line x1={sx(m.x)} x2={sx(m.x)} y1={T} y2={sy(base)} stroke={t.ink} strokeDasharray="6 6" strokeWidth={2} />
            {/* 세로축 이름(T+4) 아래에서 시작 — 예전 T+24 는 외곽선까지 겹쳐 'VIX 급등'과 'CUSUM 누적 합'이 포개졌다(2026-10-24 2화 S12 c07). scenes.curve_label_boxes 도 같은 식 */}
            {m.label ? <text x={sx(m.x) + (sx(m.x) > W * 0.7 ? -8 : 8)} y={T + 24 + (ylabel ? 26 : 0) + i * 28} textAnchor={sx(m.x) > W * 0.7 ? "end" : "start"}
              fontFamily={t.font} fontWeight={800} fontSize={22} fill={t.ink} stroke={t.bg} strokeWidth={6} paintOrder="stroke">{m.label}</text> : null}</g>)}
          {shade?.label && sh.length ? <text x={sx(sh[Math.floor(sh.length / 2)][0])} y={shBelow ? sy(base) + 34 : sy(base) - 16} textAnchor="middle" fontFamily={t.font} fontWeight={900} fontSize={26}
            fill={t.ink} opacity={shadeOp}>{shade.label}</text> : null}
          {/* y 숫자 눈금(yticks: true) — 기본은 끔(크기 비교만 필요한 그림이 많다) */}
          {yticks ? niceTicks(y0, y1).map((v, i) => <text key={i} x={L - 10} y={sy(v) + 7} textAnchor="end" fontFamily={t.font} fontSize={19} fontWeight={600} fill={t.sub}>{fmtTick(v, y1 - y0)}</text>) : null}
          {/* 오른쪽 보조 축: 축선과 눈금(오른쪽 축 곡선 색) — 눈금은 yticks 와 상관없이 단다(어느 축 값인지 읽혀야 한다) */}
          {rs ? <line x1={W - R} x2={W - R} y1={T} y2={H - Bm} stroke={t.line} strokeWidth={2} /> : null}
          {rs ? niceTicks(rs.y0, rs.y1).map((v, i) => <text key={`r${i}`} x={W - R + 10} y={syR(v) + 7} textAnchor="start" fontFamily={t.font} fontSize={19} fontWeight={600}
            fill={colors[all.indexOf(rightC[0])]}>{fmtTick(v, rs.y1 - rs.y0)}</text>) : null}
          {callouts.slice(0, 3).map((c, i) => <Callout key={i} x={sx(c.x)} y={sy(c.y)} text={c.text} W={W} T={T} op={shadeOp} t={t} />)}
          {xlabel ? <text x={W - R} y={H - 4} textAnchor="end" fontFamily={t.font} fontSize={20} fill={t.sub}>{xlabel}</text> : null}
          {ylabel ? <text x={L + 6} y={T + 4} fontFamily={t.font} fontSize={20} fill={t.sub}>{ylabel}</text> : null}
        </svg>
      </AbsoluteFill>
    );
  };

// 산점도 + 회귀선(최소제곱): 점이 차례로 찍히고, 그 뒤 선이 그어진다
export const Scatter: React.FC<{ points: Pt[]; fit?: boolean; highlight?: number[]; title?: string; xlabel?: string; ylabel?: string; note?: string; dur: number }> =
  ({ points, fit = true, highlight = [], title, xlabel, ylabel, note, dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    const pts = (points || []).filter((p) => Array.isArray(p) && p.length >= 2).slice(0, 300);
    if (pts.length < 2) return null;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const padx = (x1 - x0) * 0.06 || 1, pady = (y1 - y0) * 0.1 || 1;
    const W = 1020, H = 360, L = 70, R = 30, T = 20, Bm = 50;   // 높이 400→360: 제목을 소제목(top 104~130) 아래로 내린 만큼 줄여 아래 자막과 안 겹치게(2026-10-20)
    const sx = (x: number) => L + ((x - (x0 - padx)) / (x1 - x0 + 2 * padx)) * (W - L - R);
    const sy = (y: number) => H - Bm - ((y - (y0 - pady)) / (y1 - y0 + 2 * pady)) * (H - T - Bm);
    const n = pts.length, mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
    const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0), sxy = pts.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0);
    const slope = sxx ? sxy / sxx : 0, icpt = my - slope * mx;
    const shown = Math.ceil(prog(frame, 0.2, Math.min(2.0, dur * 0.45)) * n);
    const lineP = prog(frame, Math.min(2.0, dur * 0.45), Math.min(2.8, dur * 0.65));
    const lx0 = x0 - padx, lx1 = lx0 + (x1 + padx - lx0) * lineP;
    return (
      <AbsoluteFill style={{ paddingLeft: X - 20, paddingTop: 140, opacity: out }}>
        {title ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 42, color: t.ink, letterSpacing: "-0.03em", marginBottom: 14, paddingLeft: 20 }}>{title}</div> : null}
        {/* 그래프 설명(note)은 제목 바로 아래 — 그래프 밑에 두면 화면 아래 자막 띠와 겹쳐 가려졌다(2026-10-23 1화 S03 c13 심사) */}
        {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub, marginTop: -6, marginBottom: 10, paddingLeft: 20 }}>{note}</div> : null}
        <svg width={W} height={H}>
          <line x1={L} x2={W - R} y1={H - Bm} y2={H - Bm} stroke={t.ink} strokeWidth={2.5} />
          <line x1={L} x2={L} y1={T} y2={H - Bm} stroke={t.ink} strokeWidth={2.5} />
          {pts.slice(0, shown).map((p, i) => <circle key={i} cx={sx(p[0])} cy={sy(p[1])} r={highlight.includes(i + 1) ? 11 : 7}
            fill={highlight.includes(i + 1) ? t.warn : t.ink} opacity={highlight.length && !highlight.includes(i + 1) ? 0.45 : 0.85} />)}
          {fit && lineP > 0 ? <line x1={sx(lx0)} y1={sy(slope * lx0 + icpt)} x2={sx(lx1)} y2={sy(slope * lx1 + icpt)} stroke={t.accent} strokeWidth={8} strokeLinecap="round" /> : null}
          {fit && lineP >= 1 ? <g><rect x={W - R - 190} y={H - Bm - 54} width={180} height={40} fill={t.card} />
            <text x={W - R - 100} y={H - Bm - 26} textAnchor="middle" fontFamily={t.font} fontWeight={800} fontSize={22} fill={t.cardInk}>slope {fmtNum(slope)}</text></g> : null}
          {xlabel ? <text x={W - R} y={H - 6} textAnchor="end" fontFamily={t.font} fontSize={20} fill={t.sub}>{xlabel}</text> : null}
          {ylabel ? <text x={L + 6} y={T + 4} fontFamily={t.font} fontSize={20} fill={t.sub}>{ylabel}</text> : null}
        </svg>
      </AbsoluteFill>
    );
  };

type Bar = { label: string; value: number; display?: string; color?: string };
const pick = (bars: Bar[], highlight?: number | string) =>
  typeof highlight === "number" ? highlight - 1 : highlight ? bars.findIndex((b) => b.label === highlight) : -1;

// 가로 막대: 막대가 자라며 값이 올라간다. highlight(번호 또는 이름)만 강조색, 나머지는 잉크색
export const BarChart: React.FC<{ bars: Bar[]; title?: string; unit?: string; highlight?: number | string; note?: string; values?: boolean; dur: number }> =
  ({ bars, title, unit = "", highlight, note, values = true, dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    const list = (bars || []).slice(0, 7);
    const max = Math.max(...list.map((b) => Math.abs(b.value)), 1e-9);
    const hi = pick(list, highlight);
    const rowH = list.length > 5 ? 58 : 76;
    // 음수가 있으면 0 기준선을 긋고 음수 막대는 왼쪽으로 — 예전엔 절댓값 길이로 오른쪽에만 그려 −37.63 이 +20.43 보다 커 보였다(2026-10-20 2화 S10 c11)
    const negMax = Math.max(0, ...list.map((b) => -b.value)), posMax = Math.max(0, ...list.map((b) => b.value));
    // 양쪽 끝에 값 글자 자리(28%)를 남긴다 — 18%만 남겼을 때 음수 값 글자가 항목 이름 칸을 덮었다(S10 c11)
    const hasNeg = negMax > 0, span = 44, zero = 28 + (negMax / ((negMax + posMax) || 1)) * span;
    return (
      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: X, paddingRight: 90, opacity: out }}>
        {title ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 42, color: t.ink, letterSpacing: "-0.03em", marginBottom: 22 }}>{title}</div> : null}
        {list.map((b, i) => {
          const p = prog(frame, 0.2 + i * 0.15, 1.2 + i * 0.15);
          const on = hi < 0 || hi === i;
          const v = b.value * p;
          const dec = (String(b.value).split(".")[1] || "").length;
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "260px 1fr", alignItems: "center", height: rowH, gap: 18 }}>
              <div style={{ fontFamily: t.font, fontWeight: 800, fontSize: 28, color: on ? t.ink : t.sub, textAlign: "right", wordBreak: "keep-all", lineHeight: 1.15 }}>{b.label}</div>
              {hasNeg ? (() => {
                const w = (Math.abs(b.value) / ((negMax + posMax) || 1)) * span * p, neg = b.value < 0;
                const lab = { position: "absolute" as const, top: "50%", transform: "translateY(-50%)", whiteSpace: "nowrap" as const, fontFamily: t.font, fontWeight: 900, fontSize: 32,
                  color: t.ink, fontVariantNumeric: "tabular-nums", opacity: Math.min(1, p * 1.5) };
                return <div style={{ position: "relative", height: rowH }}>
                  <div style={{ position: "absolute", left: `${zero}%`, top: 0, bottom: 0, width: 3, background: t.ink }} />
                  <div style={{ position: "absolute", top: rowH * 0.19, height: rowH * 0.62, left: `${neg ? zero - w : zero}%`, width: `${w}%`, background: b.color ? tone(t, b.color) : hi === i ? t.accent : on ? t.ink : t.line }} />
                  {values ? <div style={{ ...lab, ...(neg ? { right: `calc(${100 - (zero - w)}% + 14px)` } : { left: `calc(${zero + w}% + 14px)` }) }}>
                    {b.display && p >= 1 ? b.display : `${v.toFixed(dec)}${unit}`}</div> : null}
                </div>;
              })() : (
              <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ height: rowH * 0.62, width: `${(Math.abs(b.value) / max) * 72 * p}%`, background: b.color ? tone(t, b.color) : hi === i ? t.accent : on ? t.ink : t.line }} />
                {values ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 32, color: t.ink, fontVariantNumeric: "tabular-nums", opacity: Math.min(1, p * 1.5) }}>
                  {b.display && p >= 1 ? b.display : `${v.toFixed(dec)}${unit}`}</div> : null}
              </div>)}
            </div>
          );
        })}
        {/* 음수 막대가 있으면 0 기준선 아래에 '0'(2026-10-23 1화 S01 c07 심사: 손익 기준선이 어디인지 알 수 없다) */}
        {hasNeg ? <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 18 }}><div />
          <div style={{ position: "relative", height: 30 }}><div style={{ position: "absolute", left: `${zero}%`, transform: "translateX(-50%)", fontFamily: t.font, fontWeight: 800,
            fontSize: 24, color: t.sub }}>0</div></div></div> : null}
        {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub, marginTop: 16 }}>{note}</div> : null}
      </AbsoluteFill>
    );
  };

// 3D 막대: 바닥 위 막대가 솟고 카메라가 천천히 돈다. 이름·값은 아래 2D 줄로(3D 글자는 흐려 읽기 어렵다)
const Bars3DScene: React.FC<{ list: Bar[]; hi: number; dur: number }> = ({ list, hi, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const max = Math.max(...list.map((b) => Math.abs(b.value)), 1e-9);
  const n = list.length;
  const ang = interpolate(frame, [0, f(dur)], [-0.55, 0.25]);
  return (
    <>
      <ambientLight intensity={0.75} />
      <directionalLight position={[6, 12, 8]} intensity={1.4} />
      <group rotation={[0, ang, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
          <planeGeometry args={[n * 2.2 + 3, 7]} />
          <meshStandardMaterial color={t.bg2} />
        </mesh>
        {list.map((b, i) => {
          const p = prog(frame, 0.2 + i * 0.18, 1.4 + i * 0.18);
          const h = Math.max(0.05, (Math.abs(b.value) / max) * 5.2 * p);
          const x = (i - (n - 1) / 2) * 2.2;
          return (
            <mesh key={i} position={[x, h / 2, 0]}>
              <boxGeometry args={[1.4, h, 1.4]} />
              <meshStandardMaterial color={hi === i ? t.accent : hi < 0 ? t.ink : "#8b8b8b"} roughness={0.55} />
            </mesh>
          );
        })}
      </group>
    </>
  );
};

export const Bars3D: React.FC<{ bars: Bar[]; title?: string; unit?: string; highlight?: number | string; note?: string; dur: number }> =
  ({ bars, title, unit = "", highlight, note, dur }) => {
    const t = useT();
    const { width, height } = useVideoConfig();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    const list = (bars || []).slice(0, 6);
    const hi = pick(list, highlight);
    return (
      <AbsoluteFill style={{ opacity: out }}>
        <ThreeCanvas width={width} height={height} camera={{ position: [0, 6.5, 11.5], fov: 42 }} style={{ position: "absolute", inset: 0 }}
          onCreated={({ camera }) => camera.lookAt(0, 1.6, 0)}>
          <Bars3DScene list={list} hi={hi} dur={dur} />
        </ThreeCanvas>
        {title ? <div style={{ position: "absolute", left: X, top: 60, fontFamily: t.font, fontWeight: 900, fontSize: 42, color: t.ink, letterSpacing: "-0.03em" }}>{title}</div> : null}
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 46, display: "flex", justifyContent: "center", gap: 34, opacity: prog(frame, 1.2, 1.6) }}>
          {list.map((b, i) => (
            <div key={i} style={{ textAlign: "center", fontFamily: t.font }}>
              <div style={{ fontWeight: 900, fontSize: 30, color: hi === i && t.accentInk ? t.accentInk : t.ink, background: hi === i ? t.accent : "transparent", padding: "0 8px" }}>{b.display ?? `${b.value}${unit}`}</div>
              <div style={{ fontWeight: 700, fontSize: 22, color: t.sub }}>{b.label}</div>
            </div>
          ))}
        </div>
        {note ? <div style={{ position: "absolute", right: 34, top: 66, fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub }}>{note}</div> : null}
      </AbsoluteFill>
    );
  };

// ---------------------------------------------------------------- 회사 틀(2026-10-17): 첫 페이지 제목 · 마지막 페이지 슬로건 · 로고
// 매 회차 같은 모양 — 채널 정체성. 값: 제목·부제·슬로건·로고(프로젝트 파일)
export const TitleCard: React.FC<{ title: string; subtitle?: string; kicker?: string; logo?: string; name?: string; source?: string; dur: number }> = ({ title, subtitle, kicker, logo, name, source, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  const p = prog(frame, 0.15, 0.9);
  const bar = prog(frame, 0.6, 1.3);
  const sub = prog(frame, 0.9, 1.5);
  const size = title.length > 22 ? 70 : title.length > 14 ? 84 : 100;
  return (
    <AbsoluteFill style={{ background: t.bg, opacity: out }}>
      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: X, paddingRight: X }}>
        {kicker ? <div style={{ display: "inline-flex", alignSelf: "flex-start", background: t.card, color: t.cardInk, fontFamily: t.font, fontWeight: 800, fontSize: 24,
          padding: "8px 16px", marginBottom: 26, borderLeft: `12px solid ${t.accent}`, opacity: prog(frame, 0, 0.4) }}>{kicker}</div> : null}
        <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: size, lineHeight: 1.12, color: t.ink, letterSpacing: "-0.035em", wordBreak: "keep-all",
          transform: `translateY(${(1 - p) * 40}px)`, opacity: Math.min(1, p * 1.4), maxWidth: 1050 }}>{title}</div>
        <div style={{ height: 16, width: 260, background: t.accent, marginTop: 26, transform: `scaleX(${bar})`, transformOrigin: "left" }} />
        {subtitle ? <div style={{ fontFamily: t.font, fontWeight: 700, fontSize: 32, color: t.sub, marginTop: 22, opacity: sub, wordBreak: "keep-all" }}>{subtitle}</div> : null}
      </AbsoluteFill>
      {source ? <div style={{ position: "absolute", left: X, bottom: 52, right: logo || name ? 360 : X, fontFamily: t.font, fontWeight: 600, fontSize: 24, color: t.sub,
        opacity: prog(frame, 1.1, 1.7), wordBreak: "keep-all" }}>{source}</div> : null}
      {logo ? <img src={logo} style={{ position: "absolute", right: 60, bottom: 46, height: 64, maxWidth: 260, objectFit: "contain", opacity: prog(frame, 0.8, 1.4) }} />
        : name ? <div style={{ position: "absolute", right: 60, bottom: 50, fontFamily: t.font, fontWeight: 900, fontSize: 30, color: t.ink, opacity: prog(frame, 0.8, 1.4) }}>{name}</div> : null}
    </AbsoluteFill>
  );
};

export const EndCard: React.FC<{ slogan: string; logo?: string; name?: string; note?: string; source?: string; dur: number }> = ({ slogan, logo, name, note, source, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  const p = prog(frame, 0.2, 1.0);
  const lg = prog(frame, 0.9, 1.6);
  const size = slogan.length > 30 ? 52 : slogan.length > 18 ? 64 : 80;
  return (
    <AbsoluteFill style={{ background: t.bg, opacity: out, justifyContent: "center", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 12, background: t.accent }} />
      {logo ? <img src={logo} style={{ height: 120, maxWidth: 520, objectFit: "contain", marginBottom: 44, opacity: lg, transform: `scale(${0.92 + 0.08 * lg})` }} />
        : name ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 40, color: t.ink, marginBottom: 40, opacity: lg }}>{name}</div> : null}
      <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: size, lineHeight: 1.2, color: t.ink, letterSpacing: "-0.03em", textAlign: "center", padding: "0 120px",
        wordBreak: "keep-all", opacity: Math.min(1, p * 1.4), transform: `translateY(${(1 - p) * 30}px)` }}>
        <span style={{ background: `linear-gradient(transparent 58%, ${t.fill || t.accent} 58%)`, padding: "0 8px" }}>{slogan}</span>
      </div>
      {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 24, color: t.sub, marginTop: 30, opacity: prog(frame, 1.3, 1.8) }}>{note}</div> : null}
      {source ? <div style={{ position: "absolute", left: 120, right: 120, bottom: 52, textAlign: "center", fontFamily: t.font, fontWeight: 600, fontSize: 24, color: t.sub,
        opacity: prog(frame, 1.3, 1.8), wordBreak: "keep-all" }}>{source}</div> : null}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 도식(2026-10-24)
// 그래프가 아닌 그림 — 축 위의 점과 방향 화살표, 흐름도, 둘의 비교 배치 — 를 그릴 틀이 없어 스토리보드의 도식이 큰 글자로 바뀌었다
// (2화 S05 c06 틱 방향 도식). 좌표는 그림 영역 안 0~100(왼쪽→오른쪽 x, 위→아래 y) — 픽셀을 몰라도 놓을 수 있게.
//  areas  : [{x0, x1, y0, y1, label, color}]  옅게 칠한 구역(예: 상승 구간)
//  nodes  : [{id, x, y, label, shape: circle|box|dot|none, color, sub(아래 작은 글), size}]
//  arrows : [{from, to, label, color, dash, head(기본 true — false 면 연결선·축)}]  from·to 는 node id 또는 [x, y]
//  labels : [{x, y, text, size, color, align: left|center|right}]  자유 글자
//  모든 요소에 at(장면 시작 기준 초)을 주면 그때 나타난다. 비우면 구역 → 점 → 화살표 → 글자 차례로 고르게. 슬라이드(인쇄)에서는 모두 보인다.
//  크기 규칙(상자 폭·원 반지름·글자 폭 어림)은 app/video/scenes.py diagram_boxes 와 같다 — 겹침 검사가 같은 자리를 본다.
type DPt = [number, number];
type DNode = { id?: string; x: number; y: number; label?: string; shape?: string; color?: string; sub?: string; size?: number; at?: number };
type DArrow = { from: string | DPt; to: string | DPt; label?: string; color?: string; dash?: boolean; head?: boolean; at?: number };
type DLabel = { x: number; y: number; text: string; size?: number; color?: string; align?: string; at?: number };
type DArea = { x0: number; x1: number; y0?: number; y1?: number; label?: string; color?: string; at?: number };
const dTextW = (s: string, fs: number) => [...String(s || "")].reduce((a, c) => a + (/[ᄀ-ᇿ㄰-㆏가-힯一-鿿]/.test(c) ? 1 : 0.6), 0) * fs;
const D_W = 1100;
const diagramH = (title?: string, note?: string) => 590 - 140 - (title ? 62 : 0) - (note ? 32 : 0);
// 이름표의 줄바꿈 글자는 여러 줄로 그린다(2026-10-27 S01 c04: 줄바꿈이 한 줄로 이어져 상자가 넓어지고 화면 왼쪽 밖으로 잘림)
const dLines = (s?: string) => String(s || "").split("\n").map((x) => x.trim()).filter((x) => x);
const dLinesW = (s: string | undefined, fs: number) => Math.max(0, ...dLines(s).map((x) => dTextW(x, fs)));
const D_LH = 32;
const nodeHalf = (n: DNode): { hw: number; hh: number; r?: number } => {
  const shape = n.shape || "circle", fs = 26, extra = (Math.max(1, dLines(n.label).length) - 1) * D_LH / 2;
  if (shape === "box") return { hw: Math.max(dLinesW(n.label, fs) / 2 + 22, 40), hh: 34 + extra };
  if (shape === "dot") return { hw: 10, hh: 10 };
  if (shape === "none") return { hw: dLinesW(n.label, fs) / 2 + 4, hh: 18 + extra };
  const r = n.size || Math.max(34, dLinesW(n.label, fs) / 2 + 14, 34 + extra);
  return { hw: r, hh: r, r };
};
export const Diagram: React.FC<{ nodes?: DNode[]; arrows?: DArrow[]; labels?: DLabel[]; areas?: DArea[]; title?: string; note?: string; dur: number }> =
  ({ nodes = [], arrows = [], labels = [], areas = [], title, note, dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    const W = D_W, H = diagramH(title, note), PAD = 30;
    const sx = (x: number) => PAD + (Math.max(0, Math.min(100, x)) / 100) * (W - 2 * PAD);
    const sy = (y: number) => PAD + (Math.max(0, Math.min(100, y)) / 100) * (H - 2 * PAD);
    const ns = (nodes || []).filter((n) => n && typeof n.x === "number" && typeof n.y === "number").slice(0, 30);
    const ars = (arrows || []).slice(0, 40), lbs = (labels || []).slice(0, 20), ars0 = (areas || []).slice(0, 6);
    const byId: Record<string, DNode> = {};
    ns.forEach((n) => { if (n.id != null) byId[String(n.id)] = n; });
    // 나타나는 차례: at 이 없으면 구역 → 점 → 화살표 → 글자 순으로 장면 앞쪽 절반에 고르게
    const seq: any[] = [...ars0, ...ns, ...ars, ...lbs];
    const span = Math.max(0.6, Math.min(dur * 0.5, 0.35 * seq.length));
    const autoAt = new Map<any, number>();
    seq.forEach((e, i) => autoAt.set(e, 0.2 + (span * i) / Math.max(1, seq.length)));
    const op = (e: any) => { const a = typeof e.at === "number" ? e.at : autoAt.get(e) || 0; return prog(frame, a, a + 0.4); };
    const center = (p: string | DPt): DPt => Array.isArray(p) ? [sx(p[0]), sy(p[1])] : byId[String(p)] ? [sx(byId[String(p)].x), sy(byId[String(p)].y)] : [NaN, NaN];
    // 화살표 끝을 점(원·상자) 가장자리에서 멈춘다
    const edge = (p: string | DPt, other: DPt): DPt => {
      const c = center(p);
      if (Array.isArray(p)) return c;
      const n = byId[String(p)], h = nodeHalf(n);
      const dx = other[0] - c[0], dy = other[1] - c[1], len = Math.hypot(dx, dy) || 1;
      const k = h.r ? h.r + 6 : Math.min(dx ? (h.hw + 6) / Math.abs(dx) : Infinity, dy ? (h.hh + 6) / Math.abs(dy) : Infinity) * len;
      const kk = Math.min(k, len * 0.45);
      return [c[0] + (dx / len) * kk, c[1] + (dy / len) * kk];
    };
    return (
      <AbsoluteFill style={{ paddingLeft: X - 20, paddingTop: 140, opacity: out }}>
        {title ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 42, color: t.ink, letterSpacing: "-0.03em", marginBottom: 14, paddingLeft: 20 }}>{title}</div> : null}
        {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub, marginTop: -6, marginBottom: 10, paddingLeft: 20 }}>{note}</div> : null}
        <svg width={W} height={H} style={{ overflow: "visible" }}>
          {ars0.map((a, i) => {
            const x0 = sx(Math.min(a.x0, a.x1)), x1 = sx(Math.max(a.x0, a.x1));
            const y0 = sy(Math.min(a.y0 ?? 0, a.y1 ?? 100)), y1 = sy(Math.max(a.y0 ?? 0, a.y1 ?? 100));
            const c = tone(t, a.color, t.accent);
            return <g key={`a${i}`} opacity={op(a)}>
              <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill={c} opacity={0.18} rx={10} />
              {a.label ? <text x={(x0 + x1) / 2} y={y0 + 28} textAnchor="middle" fontFamily={t.font} fontWeight={700} fontSize={21} fill={t.sub}>{a.label}</text> : null}
            </g>;
          })}
          {ars.map((a, i) => {
            const c0 = center(a.from), c1 = center(a.to);
            if (![...c0, ...c1].every(Number.isFinite)) return null;
            const p0 = edge(a.from, c1), p1 = edge(a.to, c0);
            const c = tone(t, a.color, t.ink), head = a.head !== false;
            const dx = p1[0] - p0[0], dy = p1[1] - p0[1], len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
            const tip = head ? [p1[0] - ux * 14, p1[1] - uy * 14] : p1;
            // 이름표는 화살표 가운데에서 옆(위쪽)으로 띄운다 — 선 위에 얹으면 원·화살촉과 겹쳤다(2026-10-24 시험 렌더)
            let nx = uy, ny = -ux;
            if (ny > 0 || (ny === 0 && nx < 0)) { nx = -nx; ny = -ny; }
            const mx = (p0[0] + p1[0]) / 2 + nx * 18, my = (p0[1] + p1[1]) / 2 + ny * 18;
            const anchor = Math.abs(nx) > 0.35 ? (nx > 0 ? "start" : "end") : "middle";
            return <g key={`r${i}`} opacity={op(a)}>
              <line x1={p0[0]} y1={p0[1]} x2={tip[0]} y2={tip[1]} stroke={c} strokeWidth={5} strokeLinecap="round" strokeDasharray={a.dash ? "12 10" : undefined} />
              {head ? <polygon points={`${p1[0]},${p1[1]} ${p1[0] - ux * 24 - uy * 13},${p1[1] - uy * 24 + ux * 13} ${p1[0] - ux * 24 + uy * 13},${p1[1] - uy * 24 - ux * 13}`} fill={c} /> : null}
              {a.label ? <text x={mx} y={my + (Math.abs(nx) > 0.35 ? 8 : -2)} textAnchor={anchor}
                fontFamily={t.font} fontWeight={800} fontSize={22} fill={t.ink} stroke={t.bg} strokeWidth={6} paintOrder="stroke">{a.label}</text> : null}
            </g>;
          })}
          {ns.map((n, i) => {
            const cx = sx(n.x), cy = sy(n.y), h = nodeHalf(n), c = tone(t, n.color, t.ink), shape = n.shape || "circle";
            return <g key={`n${i}`} opacity={op(n)}>
              {shape === "circle" ? <circle cx={cx} cy={cy} r={h.r} fill={t.paper ? t.card : "#ffffff"} stroke={c} strokeWidth={5} /> : null}
              {shape === "box" ? <rect x={cx - h.hw} y={cy - h.hh} width={2 * h.hw} height={2 * h.hh} rx={10} fill={t.paper ? t.card : "#ffffff"} stroke={c} strokeWidth={5} /> : null}
              {shape === "dot" ? <circle cx={cx} cy={cy} r={10} fill={c} /> : null}
              {n.label ? <text x={cx} y={(shape === "dot" ? cy - 22 : cy + 9) - (dLines(n.label).length - 1) * D_LH / 2} textAnchor="middle" fontFamily={t.font} fontWeight={800} fontSize={26}
                fill={shape === "none" ? c : t.ink}>{dLines(n.label).map((ln, k) => <tspan key={k} x={cx} dy={k ? D_LH : 0}>{ln}</tspan>)}</text> : null}
              {n.sub ? <text x={cx} y={cy + h.hh + 28} textAnchor="middle" fontFamily={t.font} fontWeight={600} fontSize={20} fill={t.sub}>{n.sub}</text> : null}
            </g>;
          })}
          {lbs.map((l, i) => (
            <text key={`l${i}`} x={sx(l.x)} y={sy(l.y)} opacity={op(l)} textAnchor={l.align === "left" ? "start" : l.align === "right" ? "end" : "middle"}
              fontFamily={t.font} fontWeight={800} fontSize={l.size || 24} fill={tone(t, l.color, t.ink)}>
              {/* 줄바꿈(
)은 여러 줄로 — 한 줄로 이어 그려 상자를 가로질렀다(2026-10-27 1화 S08 c03) */}
              {dLines(l.text).map((ln, k) => <tspan key={k} x={sx(l.x)} dy={k ? (l.size || 24) * 1.25 : 0}>{ln}</tspan>)}</text>
          ))}
        </svg>
      </AbsoluteFill>
    );
  };
