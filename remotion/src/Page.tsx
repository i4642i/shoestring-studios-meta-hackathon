import React from "react";
import { AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEMES } from "./theme";
import { FPS, T, f, useT, setPrint, isPrint } from "./ctx";
import { prettyProps } from "./symbols";
import { DOCU } from "./docu";
import { HtmlSlide } from "./html";
import { Formula, BarChart, Bars3D, TitleCard, EndCard, Curve, Scatter, Diagram } from "./graphics";

// ---------------------------------------------------------------- 타임라인 규격(Remotion 판)
// AI 직원은 이 JSON 만 쓴다. 화면 틀(type)은 아래 COMPONENTS 에 있는 것만. 색·장식은 theme 이 정한다.
export type Layer = { type: string; start: number; end: number; props?: Record<string, any> };
export type Bg = { style: "plain" | "grid" | "paper" | "stripes" | "gradient" | "photo" | "video"; start: number; end: number; src?: string; dim?: number };
export type PageProps = {
  page: string; duration: number; width?: number; height?: number; theme?: string; print?: boolean;
  background: Bg[]; layers: Layer[]; audio: { src: string; start?: number; volume?: number; loop?: boolean }[];
};


const usePop = (delay = 0, soft = false) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return isPrint() ? 1 : spring({ frame: frame - f(delay), fps, config: soft ? { damping: 20, stiffness: 120 } : { damping: 11, stiffness: 140, mass: 0.7 } });
};
const useOut = (dur: number) => {
  const frame = useCurrentFrame();
  return isPrint() ? 1 : interpolate(frame, [f(dur) - 8, f(dur)], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
};

// ---------------------------------------------------------------- 배경
const Noise: React.FC<{ opacity?: number }> = ({ opacity = 0.18 }) => (
  <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, mixBlendMode: "multiply", opacity }}>
    <filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch" /><feColorMatrix type="saturate" values="0" /></filter>
    <rect width="100%" height="100%" filter="url(#n)" />
  </svg>
);

const Background: React.FC<{ bg: Bg; index?: number }> = ({ bg }) => {
  const t = useT();
  const frame = useCurrentFrame();
  if ((bg.style === "photo" || bg.style === "video") && bg.src) {
    const z = interpolate(frame, [0, f(bg.end - bg.start)], [1, 1.06]);
    const media = bg.style === "photo"
      ? <Img src={bg.src} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${z})` }} />
      : <OffthreadVideo src={bg.src} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />;
    return <AbsoluteFill>{media}<AbsoluteFill style={{ background: `rgba(${t.dim || "255,255,255"},${bg.dim ?? 0.55})` }} /></AbsoluteFill>;
  }
  if (bg.style === "grid") {
    const drift = (frame * 0.25) % 48;
    return (
      <AbsoluteFill style={{ background: t.bg }}>
        <AbsoluteFill style={{ backgroundImage: `linear-gradient(${t.line} 1px, transparent 1px), linear-gradient(90deg, ${t.line} 1px, transparent 1px)`,
          backgroundSize: "48px 48px", backgroundPosition: `${drift}px ${drift}px`, opacity: 0.55 }} />
      </AbsoluteFill>
    );
  }
  if (bg.style === "stripes") {
    const shift = (frame * 0.6) % 80;
    return <AbsoluteFill style={{ background: `repeating-linear-gradient(135deg, ${t.bg2} ${shift}px, ${t.bg2} ${shift + 40}px, ${t.bg} ${shift + 40}px, ${t.bg} ${shift + 80}px)` }} />;
  }
  if (bg.style === "gradient") {
    return <AbsoluteFill style={{ background: `linear-gradient(135deg, ${t.bg} 0%, ${t.bg2} 100%)` }} />;
  }
  if (bg.style === "paper") {
    return <AbsoluteFill style={{ background: t.bg }}><Noise opacity={t.decor ? 0.18 : 0.06} /></AbsoluteFill>;
  }
  return <AbsoluteFill style={{ background: t.bg }} />;
};

// ---------------------------------------------------------------- 화면 틀
// 위쪽 작은 꼬리표(장·단계 이름)
const Kicker: React.FC<{ text: string; dur: number }> = ({ text, dur }) => {
  const t = useT();
  const p = usePop(0, true);
  const out = useOut(dur);
  return (
    <div style={{ position: "absolute", left: 80, top: 56, display: "flex", alignItems: "center", gap: 12, opacity: out * p, transform: `translateX(${(1 - p) * -30}px)` }}>
      <div style={{ width: 10, height: 34, background: t.accent, borderRadius: 3 }} />
      <div style={{ fontFamily: t.font, fontWeight: 700, fontSize: 26, color: t.sub, letterSpacing: "0.02em" }}>{text}</div>
    </div>
  );
};

// 큰 글자: 줄마다 차례로. highlight 낱말은 테마에 따라 밑줄(금융) 또는 형광펜(광고)
const BigText: React.FC<{ lines: string[]; highlight?: string[]; size?: number; align?: "center" | "left"; dur: number }> =
  ({ lines, highlight = [], size = 72, align = "center", dur }) => {
    const out = useOut(dur);
    return (
      <AbsoluteFill style={{ justifyContent: "center", alignItems: align === "center" ? "center" : "flex-start", padding: "0 90px", opacity: out }}>
        {lines.map((ln, i) => <PopLine key={i} text={ln} delay={i * 0.3} highlight={highlight} size={size} align={align} />)}
      </AbsoluteFill>
    );
  };

const PopLine: React.FC<{ text: string; delay: number; highlight: string[]; size: number; align: string }> = ({ text, delay, highlight, size, align }) => {
  const t = useT();
  const p = usePop(delay, !t.decor);
  const frame = useCurrentFrame();
  const under = interpolate(frame, [f(delay + 0.35), f(delay + 0.75)], [0, 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ fontFamily: t.font, fontWeight: 800, fontSize: size, lineHeight: 1.3, color: t.ink, letterSpacing: "-0.02em",
      transform: `translateY(${(1 - p) * 26}px)`, opacity: Math.min(1, p * 1.3), textAlign: align as any, wordBreak: "keep-all" }}>
      {splitHighlight(text, highlight).map((pt, i) => !pt.hl ? <span key={i}>{pt.t}</span>
        : t.highlight === "marker"
          ? <span key={i} style={{ background: `linear-gradient(transparent 55%, ${t.accent}88 55%)`, padding: "0 6px" }}>{pt.t}</span>
          // highlighted words: accent text color (deep accent when the theme has one) with an accent underline
          : <span key={i} style={{ color: t.accentText || t.accent, backgroundImage: `linear-gradient(${t.accent}, ${t.accent})`, backgroundRepeat: "no-repeat",
              backgroundSize: `${under}% 6px`, backgroundPosition: "0 96%", paddingBottom: 4 }}>{pt.t}</span>)}
    </div>
  );
};

function splitHighlight(text: string, words: string[]) {
  if (!words.length) return [{ t: text, hl: false }];
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`);
  return text.split(re).filter(Boolean).map((t) => ({ t, hl: words.includes(t) }));
}

// 숫자 카드: 숫자가 올라가며 등장
const NumberCard: React.FC<{ items: { value: string; label: string; tone?: "accent" | "warn" }[]; title?: string; note?: string; dur: number }> = ({ items, title, note, dur }) => {
  const t = useT();
  const p = usePop(0, true);
  const out = useOut(dur);
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: out }}>
      {title ? <div style={{ fontFamily: t.font, fontWeight: 700, fontSize: 34, color: t.sub, marginBottom: 24, opacity: p }}>{title}</div> : null}
      <div style={{ display: "flex", gap: 30 }}>
        {items.map((it, i) => {
          const q = spring({ frame: frame - f(0.2 + i * 0.25), fps: FPS, config: { damping: 18 } });
          const tone = it.tone === "warn" ? t.warn : t.accent;
          return (
            <div key={i} style={{ background: t.card, borderRadius: 22, padding: "30px 48px", minWidth: 280, textAlign: "center",
              boxShadow: t.decor ? "0 18px 0 rgba(0,0,0,0.18)" : "0 12px 32px rgba(20,35,59,0.10)", borderTop: `6px solid ${tone}`,
              transform: `translateY(${(1 - q) * 40}px)`, opacity: Math.min(1, q * 1.3) }}>
              <div style={{ fontFamily: t.font, fontWeight: 800, fontSize: 96, color: t.decor ? t.cardNum : t.cardNum, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{countUp(it.value, q)}</div>
              <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 28, color: t.cardInk, marginTop: 14 }}>{it.label}</div>
            </div>
          );
        })}
      </div>
      {note ? <div style={{ fontFamily: t.font, fontSize: 22, color: t.sub, marginTop: 26, opacity: p }}>{note}</div> : null}
    </AbsoluteFill>
  );
};

function countUp(value: string, p: number) {
  const m = value.match(/^([^0-9]*)([0-9][0-9,]*\.?[0-9]*)(.*)$/);
  if (!m) return value;
  const num = parseFloat(m[2].replace(/,/g, ""));
  const decimals = (m[2].split(".")[1] || "").length;
  const v = (num * Math.min(1, p)).toFixed(decimals);
  return `${m[1]}${m[2].includes(",") ? Number(v).toLocaleString() : v}${m[3]}`;
}

// 단계: 가로로 이어진 단계 표시, active 는 강조
type StepItem = string | { label: string; img?: string; desc?: string };
// 단계: 항목마다 그림(선택)·번호·이름. active 가 있으면 그 자리를 크게 강조하고, 그 항목에 img·desc 가 있으면 아래에 집중 카드(그림+한 줄 설명)
const Steps: React.FC<{ items: StepItem[]; active?: number; gap?: number; numbered?: boolean; dur: number }> = ({ items, active, gap = 0.5, numbered = true, dur }) => {
  const t = useT();
  const out = useOut(dur);
  const frame = useCurrentFrame();
  // 번호는 동그라미 배지 하나만 — 이름 앞에 직원이 붙인 ①·1.·1)·(1)·1단계 는 지운다("2가 두 개나 들어가네")
  const bare = (s: string) => (s || "").replace(/^\s*(?:[①-⑳⓵-⓾❶-❿]|\(?\d{1,2}\s*(?:[.)\]:]|단계)|\d{1,2}\s+(?=\S))\s*/, "");
  const list = items.map((x) => (typeof x === "string" ? { label: bare(x) } : { ...x, label: bare(x.label) }));
  const focus = active ? list[active - 1] : undefined;
  const spot = !!(focus && (focus.img || focus.desc));
  const many = list.length > 4;
  const fp = spring({ frame: frame - f(0.25), fps: FPS, config: { damping: 18 } });
  return (
    <AbsoluteFill style={{ justifyContent: spot ? "flex-start" : "center", alignItems: "center", paddingTop: spot ? 120 : 0, opacity: out }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", flexWrap: "wrap", rowGap: 18, columnGap: 12, padding: "0 50px", maxWidth: 1280 }}>
        {list.map((s, i) => {
          const q = spring({ frame: frame - f(i * gap), fps: FPS, config: t.decor ? { damping: 10, stiffness: 150 } : { damping: 18 } });
          const on = active === undefined || active === i + 1;
          const small = spot || many;
          return (
            <React.Fragment key={i}>
              {i > 0 ? <div style={{ width: (small ? 18 : 46) * q, height: 4, background: t.line, borderRadius: 2 }} /> : null}
              <div style={{ display: "flex", alignItems: "center", gap: 10, background: t.card, borderRadius: t.decor ? 999 : 16, padding: small ? "10px 16px" : "22px 30px",
                border: `3px solid ${on ? t.accent : t.line}`, boxShadow: "0 10px 26px rgba(20,35,59,0.08)", opacity: Math.min(1, q * 1.4) * (on ? 1 : 0.55),
                transform: `translateY(${(1 - q) * 30}px) scale(${active === i + 1 ? 1.06 : 1})` }}>
                {s.img && !spot ? <Img src={s.img} style={{ width: 54, height: 54, borderRadius: 12, objectFit: "cover" }} /> : null}
                {numbered ? <span style={{ background: on ? (t.accentText || t.accent) : t.line, color: t.accentInk && t.paper ? t.accentInk : "#fff", borderRadius: 999, width: small ? 36 : 46, height: small ? 36 : 46, display: "inline-flex",
                  alignItems: "center", justifyContent: "center", fontFamily: t.font, fontWeight: 800, fontSize: small ? 20 : 26 }}>{i + 1}</span> : null}
                <span style={{ fontFamily: t.font, fontWeight: 700, fontSize: small ? 22 : list.length > 3 ? 30 : 34, color: t.ink, whiteSpace: "nowrap" }}>{s.label}</span>
              </div>
            </React.Fragment>
          );
        })}
      </div>
      {spot && focus ? (
        <div style={{ marginTop: 34, display: "flex", alignItems: "center", gap: 34, background: t.card, borderRadius: 26, padding: 26, width: 980,
          boxShadow: "0 16px 40px rgba(20,35,59,0.14)", borderLeft: `8px solid ${t.accent}`, opacity: fp, transform: `translateY(${(1 - fp) * 30}px)` }}>
          {focus.img ? <Img src={focus.img} style={{ width: 380, height: 250, borderRadius: 18, objectFit: "cover", flexShrink: 0 }} /> : null}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: t.font, fontWeight: 800, fontSize: 44, color: t.ink, wordBreak: "keep-all" }}>{focus.label}</div>
            {focus.desc ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 30, color: t.sub, marginTop: 14, lineHeight: 1.4, wordBreak: "keep-all" }}>{focus.desc}</div> : null}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
const Chips = Steps;   // 예전 이름

// 선 그래프: 점들이 왼쪽부터 그려지고, 마지막 값에 표시. label·note 로 '예시' 표기
const LineChart: React.FC<{ points: number[]; label?: string; note?: string; markLast?: string; tone?: "accent" | "warn"; dur: number }> =
  ({ points, label, note, markLast, tone = "accent", dur }) => {
    const t = useT();
    const frame = useCurrentFrame();
    const out = useOut(dur);
    const W = 760, H = 330, pad = 30, top = 64;   // 위쪽은 마지막 값 표시가 잘리지 않게 넉넉히
    const min = Math.min(...points), max = Math.max(...points);
    const xy = points.map((v, i) => [pad + (i / (points.length - 1)) * (W - pad * 2), H - pad - ((v - min) / (max - min || 1)) * (H - pad - top)]);
    const prog = interpolate(frame, [f(0.2), f(Math.min(2.4, dur * 0.6))], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const n = Math.max(2, Math.ceil(prog * points.length));
    const path = xy.slice(0, n).map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    const color = tone === "warn" ? t.warn : t.accent;
    const [lx, ly] = xy[n - 1];
    return (
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: out }}>
        {label ? <div style={{ fontFamily: t.font, fontWeight: 700, fontSize: 32, color: t.ink, marginBottom: 10 }}>{label}</div> : null}
        <div style={{ background: t.card, borderRadius: 22, padding: 22, boxShadow: "0 12px 32px rgba(20,35,59,0.10)" }}>
          <svg width={W} height={H}>
            {[0.25, 0.5, 0.75].map((g) => <line key={g} x1={pad} x2={W - pad} y1={pad + g * (H - pad * 2)} y2={pad + g * (H - pad * 2)} stroke={t.line} strokeWidth={1} />)}
            <path d={`${path} L${lx},${H - pad} L${pad},${H - pad} Z`} fill={color} opacity={0.10} />
            <path d={path} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
            <circle cx={lx} cy={ly} r={9} fill={color} />
            {markLast && prog >= 1 ? <text x={lx - 14} y={ly - 20} textAnchor="end" fontFamily={t.font} fontWeight={800} fontSize={30} fill={tone === "warn" ? color : (t.accentText || color)}>{markLast}</text> : null}
          </svg>
        </div>
        {note ? <div style={{ fontFamily: t.font, fontSize: 20, color: t.sub, marginTop: 12 }}>{note}</div> : null}
      </AbsoluteFill>
    );
  };

// 하단 자막
const Caption: React.FC<{ text: string; dur: number }> = ({ text, dur }) => {
  const t = useT();
  const p = usePop(0, true);
  const out = useOut(dur);
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 44, opacity: out }}>
      <div style={{ background: t.card, color: t.ink, borderRadius: 14, padding: "12px 26px", fontFamily: t.font, fontWeight: 600, fontSize: 28,
        boxShadow: "0 8px 22px rgba(20,35,59,0.12)", transform: `translateY(${(1 - p) * 24}px)`, opacity: p, maxWidth: 1050, textAlign: "center", wordBreak: "keep-all" }}>{text}</div>
    </AbsoluteFill>
  );
};

// 사진 스티커(누끼): 흰 테두리 + 등장
const Sticker: React.FC<{ src: string; x?: number; y?: number; w?: number; dur: number }> = ({ src, x = 820, y = 80, w = 420, dur }) => {
  const t = useT();
  const p = usePop(0, !t.decor);
  const out = useOut(dur);
  const frame = useCurrentFrame();
  const wobble = t.decor ? Math.sin(frame / 12) * 1.5 : 0;
  const outline = "drop-shadow(5px 0 0 #fff) drop-shadow(-5px 0 0 #fff) drop-shadow(0 5px 0 #fff) drop-shadow(0 -5px 0 #fff) drop-shadow(0 14px 18px rgba(0,0,0,0.20))";
  return <Img src={src} style={{ position: "absolute", left: x, top: y, width: w, filter: outline, opacity: out, transform: `scale(${p}) rotate(${wobble}deg)` }} />;
};

// 반짝이(광고 테마에서만)
const Sparkles: React.FC<{ dur: number }> = () => {
  const t = useT();
  const frame = useCurrentFrame();
  if (!t.decor) return null;
  const spots = [[120, 110, 34], [1130, 90, 26], [1040, 600, 30], [190, 560, 22]];
  return (
    <AbsoluteFill>
      {spots.map(([x, y, s], i) => {
        const k = 0.6 + 0.4 * Math.sin((frame + i * 9) / 7);
        return <svg key={i} width={s * 2} height={s * 2} style={{ position: "absolute", left: x, top: y, transform: `scale(${k}) rotate(${frame * 2 + i * 30}deg)` }}
          viewBox="-10 -10 20 20"><path d="M0,-10 L2,-2 L10,0 L2,2 L0,10 L-2,2 L-10,0 L-2,-2 Z" fill={t.accent} /></svg>;
      })}
    </AbsoluteFill>
  );
};

// 사진 카드: 사진·영상 한 장을 둥근 카드로(천천히 확대), 아래 설명 한 줄
const PhotoCard: React.FC<{ src: string; caption?: string; x?: number; y?: number; w?: number; h?: number; video?: boolean; dur: number }> =
  ({ src, caption, x, y, w = 760, h = 430, video, dur }) => {
    const t = useT();
    const p = usePop(0, true);
    const out = useOut(dur);
    const frame = useCurrentFrame();
    const z = interpolate(frame, [0, f(dur)], [1, 1.07]);
    const pos: React.CSSProperties = x === undefined ? { left: (1280 - w) / 2, top: y ?? (720 - h) / 2 - (caption ? 24 : 0) } : { left: x, top: y ?? 120 };
    return (
      <div style={{ position: "absolute", ...pos, width: w, opacity: out * Math.min(1, p * 1.3), transform: `translateY(${(1 - p) * 30}px)` }}>
        <div style={{ width: w, height: h, borderRadius: 22, overflow: "hidden", boxShadow: "0 16px 40px rgba(20,35,59,0.18)", border: `6px solid ${t.card}` }}>
          {video ? <OffthreadVideo src={src} muted style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${z})` }} />
            : <Img src={src} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${z})` }} />}
        </div>
        {caption ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 24, color: t.sub, textAlign: "center", marginTop: 14 }}>{caption}</div> : null}
      </div>
    );
  };

// 출처·필수 표기: 화면 왼쪽 아래 작은 글씨(읽을 수 있게 충분히 크게)
// font_size: at least 24 px so the source stays readable in a video (smaller values are raised)
const SourceTag: React.FC<{ text: string; dur: number; font_size?: number }> = ({ text, dur, font_size }) => {
  const t = useT();
  const out = useOut(dur);
  const p = usePop(0, true);
  const fs = Math.max(24, Number(font_size) || 24);
  return (
    <div style={{ position: "absolute", left: 40, bottom: 26, fontFamily: t.font, fontSize: fs, fontWeight: 600, color: t.sub, background: `${t.card}e6`,
      borderRadius: 8, padding: "6px 12px", whiteSpace: "pre-line", lineHeight: 1.3, opacity: out * p }}>{text}</div>
  );
};

// 지도·진행 위치(2026-10-26): 스토리보드의 '전체 지도'와 '지금 위치' — 경유지를 굽은 길 위에 차례로 놓고, 지나온 곳은 체크, 지금 자리는 핀으로 강조.
// stops: [이름...](최대 8), current: 지금 자리 번호(1부터, 없으면 출발점 강조 없음), visited: [번호...](지나온 곳 — 비우면 current 앞은 전부), title, note
const RouteMap: React.FC<{ stops: string[]; current?: number; visited?: number[]; title?: string; note?: string; dur: number }> =
  ({ stops = [], current, visited, title, note, dur }) => {
    const t = useT();
    const out = useOut(dur);
    const frame = useCurrentFrame();
    const list = (stops || []).map((s) => String(s)).filter(Boolean).slice(0, 8);
    const n = list.length;
    if (!n) return null;
    const W = 1120, H = 330, L = 70, R = 70;
    const top = title ? 196 : 160;
    const xs = list.map((_, i) => (n === 1 ? W / 2 : L + ((W - L - R) * i) / (n - 1)));
    const ys = list.map((_, i) => H / 2 + (i % 2 ? 46 : -46));   // 지그재그로 굽은 길
    const d = xs.map((x, i) => (i ? `C${(xs[i - 1] + x) / 2},${ys[i - 1]} ${(xs[i - 1] + x) / 2},${ys[i]} ${x},${ys[i]}` : `M${x},${ys[i]}`)).join(" ");
    const draw = isPrint() ? 1 : interpolate(frame, [0, f(Math.min(1.6, dur * 0.5))], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const done = new Set<number>(visited && visited.length ? visited : current ? list.map((_, i) => i + 1).filter((k) => k < current) : []);
    const fs = n > 6 ? 20 : n > 4 ? 24 : 28;
    return (
      <AbsoluteFill style={{ opacity: out, alignItems: "center" }}>
        {title ? <div style={{ position: "absolute", top: 120, left: 80, fontFamily: t.font, fontWeight: 900, fontSize: 40, color: t.ink, letterSpacing: "-0.03em" }}>{title}</div> : null}
        <svg width={W} height={H} style={{ position: "absolute", top, overflow: "visible" }}>
          <path d={d} fill="none" stroke={t.line} strokeWidth={10} strokeLinecap="round" strokeDasharray="1 22" />
          <path d={d} fill="none" stroke={t.accent} strokeWidth={10} strokeLinecap="round" pathLength={1} strokeDasharray={`${draw} 1`} opacity={0.9} />
          {list.map((name, i) => {
            const k = i + 1, on = current === k, was = done.has(k);
            const at = (i / Math.max(1, n - 1)) * Math.min(1.6, dur * 0.5);
            const p = isPrint() ? 1 : spring({ frame: frame - f(at), fps: FPS, config: { damping: 14 } });
            const r = on ? 26 : 18;
            const above = i % 2 === 0;
            return (
              <g key={i} transform={`translate(${xs[i]},${ys[i]}) scale(${p})`} opacity={Math.min(1, p * 1.3)}>
                <circle r={r} fill={on ? t.accent : was ? t.accent : (t.paper ? t.card : "#ffffff")} stroke={on || was ? t.accent : t.line} strokeWidth={5} opacity={was && !on ? 0.75 : 1} />
                {was && !on ? <path d="M-9,0 L-3,6 L10,-8" fill="none" stroke={t.paper ? t.accentInk || "#ffffff" : "#ffffff"} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" /> : null}
                {on ? <path d="M0,-60 C-18,-60 -26,-44 -26,-34 C-26,-20 0,-2 0,-2 C0,-2 26,-20 26,-34 C26,-44 18,-60 0,-60 Z" fill={t.warn} transform="translate(0,-18)" /> : null}
                {on ? <circle cy={-54} r={8} fill={t.paper ? t.ink : "#ffffff"} /> : null}
                <text y={above ? -(on ? 84 : 40) : (on ? 56 : 52)} textAnchor="middle" fontFamily={t.font} fontWeight={on ? 900 : 700} fontSize={on ? fs + 4 : fs}
                  fill={on ? t.ink : was ? t.sub : t.sub}>{name}</text>
              </g>
            );
          })}
        </svg>
        {note ? <div style={{ position: "absolute", top: top + H + 10, fontFamily: t.font, fontWeight: 600, fontSize: 22, color: t.sub }}>{note}</div> : null}
      </AbsoluteFill>
    );
  };


// Section cover (layout L13, 2026-11-11): the first screen of a part. Pale diagonal shapes (cyan-pale triangle on the
// left, lavender and rose triangles top right), the part title and one line in dark text on the left, a very large
// part number in deep cyan. boxes = the L13 slots of layouts/layouts.json, put in by the program (tools/_layouts.py).
type SBox = { x: number; y: number; w: number; h: number };
const SectionCard: React.FC<{ number?: string; title: string; subtitle?: string; boxes?: Record<string, SBox>; dur: number }> =
  ({ number, title, subtitle, boxes = {}, dur }) => {
    const t = useT();
    const out = useOut(dur);
    const p = usePop(0, true);
    const q = usePop(0.25, true);
    const nb = boxes.number || { x: 700, y: 140, w: 460, h: 340 };
    const tb = boxes.title || { x: 80, y: 200, w: 600, h: 190 };
    const sb = boxes.subtitle || { x: 80, y: 400, w: 600, h: 90 };
    const tsize = title.length > 18 ? 56 : title.length > 10 ? 66 : 76;
    return (
      <AbsoluteFill style={{ background: t.paper || "#ffffff", opacity: out }}>
        <svg width={1280} height={720} style={{ position: "absolute", inset: 0 }}>
          <polygon points="0,0 199,0 944,720 0,720" fill={t.accentSoft} />
          <polygon points="514,0 1120,0 1280,247 1280,411" fill={t.accent2Soft || t.bg2} />
          <polygon points="1120,0 1280,0 1280,247" fill={t.hlBg || t.accentSoft} />
        </svg>
        {number ? <div style={{ position: "absolute", left: nb.x, top: nb.y, width: nb.w, height: nb.h, display: "flex", alignItems: "center",
          justifyContent: "center", fontFamily: t.font, fontWeight: 900, fontSize: Math.round(nb.h * 0.86), lineHeight: 1, letterSpacing: "-0.05em",
          color: t.accentText || t.accent, opacity: p, transform: `translateY(${(1 - p) * 30}px)` }}>{number}</div> : null}
        <div style={{ position: "absolute", left: tb.x, top: tb.y, width: tb.w, height: tb.h, display: "flex", alignItems: "flex-end",
          fontFamily: t.font, fontWeight: 900, fontSize: tsize, lineHeight: 1.15, color: t.ink, letterSpacing: "-0.03em", wordBreak: "keep-all",
          opacity: q, transform: `translateY(${(1 - q) * 30}px)` }}>{title}</div>
        {subtitle ? <div style={{ position: "absolute", left: sb.x, top: sb.y, width: sb.w, height: sb.h, fontFamily: t.font, fontWeight: 700,
          fontSize: 30, lineHeight: 1.35, color: "#374151", wordBreak: "keep-all", opacity: q }}>{subtitle}</div> : null}
      </AbsoluteFill>
    );
  };

const COMPONENTS: Record<string, React.FC<any>> = { Kicker, BigText, NumberCard, Steps, Chips, LineChart, Caption, Sticker, Sparkles, PhotoCard, SourceTag, Formula, BarChart, Bars3D, TitleCard, EndCard, Curve, Scatter, Diagram, RouteMap, HtmlSlide, SectionCard };

// One screen per scene: a spanned layer may carry cues [{at: seconds from the layer start, props: {...}}]; from each
// cue on, its props replace the layer's (e.g. Steps.active, RouteMap.current, BarChart.highlight, BigText.highlight),
// so the focus moves with the narration without the screen entering again (2026-11-09)
const Cued: React.FC<{ C: React.FC<any>; base: Record<string, any>; cues?: { at: number; props: Record<string, any> }[]; dur: number }> =
  ({ C, base, cues, dur }) => {
    const frame = useCurrentFrame();
    let now = { ...base };
    for (const c of [...(cues || [])].sort((x, y) => x.at - y.at)) {
      if (frame >= f(c.at)) now = { ...now, ...(c.props || {}) };
    }
    return <C {...prettyProps(now)} dur={dur} />;
  };

// Side layout (2026-11-09): a layer with "slot" is drawn in a virtual box (w x 720) scaled down by k into its half:
// left = the picture (a whole 1280-wide screen), right = short text (an 800-wide screen)
const SLOTS: Record<string, { x: number; y: number; w: number; k: number }> = {
  left: { x: 24, y: 150, w: 1280, k: 0.6 },
  right: { x: 800, y: 150, w: 760, k: 0.6 },
};

export const Page: React.FC<PageProps> = (props) => {
  setPrint(!!props.print);   // 심사용 슬라이드: 효과를 끄고 배치 완료 상태로
  const theme = THEMES[props.theme || "finance"] || THEMES.finance;
  // 다큐 테마는 같은 이름의 화면 틀을 다큐 판으로 바꿔 끼운다 — 타임라인 JSON 규격은 그대로
  const comps = theme.docu ? { ...COMPONENTS, ...DOCU.components } : COMPONENTS;
  const Bgc = theme.docu ? DOCU.Background : Background;
  // 일본어는 낱말 사이 띄어쓰기가 없어 '낱말 단위로만 줄바꿈(keep-all)'이면 줄이 안 바뀌고 화면 밖으로 나간다 — 가나가 있으면 글자 단위 줄바꿈(일본어 줄바꿈 규칙)으로(2026-10-17)
  const ja = /[぀-ヿ]/.test(JSON.stringify(props.layers || []));
  return (
  <T.Provider value={theme}>
    <AbsoluteFill style={{ background: theme.docu ? theme.bg : theme.paper || "#ffffff" }}>
      {ja ? <style>{"*{word-break:normal !important;line-break:strict;overflow-wrap:anywhere;}"}</style> : null}
      {props.background.map((bg, i) => (
        <Sequence key={`b${i}`} from={f(bg.start)} durationInFrames={Math.max(1, f(bg.end - bg.start))}><Bgc bg={bg} index={i} /></Sequence>
      ))}
      {props.layers.map((ly, i) => {
        const C = comps[ly.type];
        if (!C) return null;
        // 화면 글자 속 수식 기호(S_t·\Delta 등)는 여기 한 곳에서 다듬는다(symbols.ts) — 부품마다 따로 하면 빠지는 곳이 생긴다
        const body = (ly as any).cues && (ly as any).cues.length
          ? <Cued C={C} base={ly.props || {}} cues={(ly as any).cues} dur={ly.end - ly.start} />
          : <C {...prettyProps(ly.props || {})} dur={ly.end - ly.start} />;
        // Layout slot (2026-11-11): the program puts "box" on a layer that sits in a slot of a library layout
        // (tools/_layouts.py place_cut): the slot x, y, w, h on screen, and inside it a canvas cw x ch scaled by k at dx, dy
        const lb = (ly as any).box;
        if (lb) {
          return <Sequence key={`l${i}`} from={f(ly.start)} durationInFrames={Math.max(1, f(ly.end - ly.start))}>
            <div style={{ position: "absolute", left: lb.x, top: lb.y, width: lb.w, height: lb.h, overflow: "hidden" }}>
              <div style={{ position: "absolute", left: lb.dx || 0, top: lb.dy || 0, width: lb.cw, height: lb.ch,
                transform: `scale(${lb.k ?? 1})`, transformOrigin: "0 0" }}>{body}</div>
            </div>
          </Sequence>;
        }
        const box = SLOTS[(ly as any).slot];
        return <Sequence key={`l${i}`} from={f(ly.start)} durationInFrames={Math.max(1, f(ly.end - ly.start))}>
          {box ? <div style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: 720, transform: `scale(${box.k})`,
            transformOrigin: "0 0", overflow: "hidden" }}>{body}</div> : body}
        </Sequence>;
      })}
      {theme.docu ? <DOCU.Finish /> : null}
      {theme.bar ? <div style={{ position: "absolute", left: 0, top: 0, width: 1280, height: 14, background: theme.bar }} /> : null}
      {props.audio.map((a, i) => (
        <Sequence key={`a${i}`} from={f(a.start || 0)}><Audio src={a.src} volume={a.volume ?? 1} loop={!!a.loop} /></Sequence>
      ))}
    </AbsoluteFill>
  </T.Provider>
  );
};
