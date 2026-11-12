import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, Img, OffthreadVideo, interpolate, spring, useCurrentFrame, Easing, delayRender, continueRender } from "remotion";
import { FPS, f, useT, isPrint } from "./ctx";

// ---------------------------------------------------------------- 밝은 다큐 화면 틀(2026-10-16, 블룸버그·Vox 경제 해설 결)
// 같은 타임라인 JSON(type·props)을 받아 다르게 그린다. 원칙:
//  - 상자·둥근 카드·그림자 대신 사진을 화면 가득, 천천히 밀고 당긴다(켄 번스).
//  - 글자는 왼쪽에 크고 굵게, 낱말이 아래에서 올라온다. 강조는 노란 형광펜이 그어진다.
//  - 사진 위 글자는 왼쪽만 종이색으로 번지게 해 읽히게 한다(사진 전체를 하얗게 덮지 않는다).

const ease = Easing.bezier(0.2, 0.8, 0.2, 1);
// 인쇄 모드 = 심사용 슬라이드 = 장면의 완성 화면(2026-10-23 사용자: "정적인 슬라이드를 먼저 만들고 효과는 그 뒤에").
// 효과(나타남·바뀜·사라짐)는 영상에서만 — 슬라이드에는 장면의 모든 내용이 다 놓인다. 내용을 갈아 끼우는 효과(수식 replace·목록 집중 설명)는
// 각 부품이 인쇄 모드에서 나열로 그린다(아래 Formula·Steps).
const prog = (frame: number, a: number, b: number) => (isPrint() ? 1 : interpolate(frame, [f(a), f(b)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease }));
const useOut = (dur: number) => {
  const frame = useCurrentFrame();
  return isPrint() ? 1 : interpolate(frame, [f(dur) - 7, f(dur)], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
};
const W = 1280, H = 720, X = 84;

type Bg = { style: string; start: number; end: number; src?: string; dim?: number;
  move?: string; focus?: string; speed?: string; grade?: string; from?: number; fade?: string };

// 색감(2026-10-19 플랫폼 표현력): 한 편 안에서 사진 색을 하나로 맞춘다 — 회사·페이지가 고르고, 장면이 따로 바꿀 수 있다
export const GRADES: Record<string, string> = {
  natural: "none",
  warm: "sepia(0.18) saturate(1.06) hue-rotate(-6deg) brightness(1.02)",
  cool: "saturate(0.88) hue-rotate(10deg) brightness(1.02) contrast(1.02)",
  mono: "grayscale(1) contrast(1.06)",
  muted: "saturate(0.62) contrast(0.96) brightness(1.03)",
  vivid: "saturate(1.28) contrast(1.06)",
  film: "sepia(0.12) saturate(0.85) contrast(1.1) brightness(0.98)",
};
// 사진의 중심(움직임의 기준점이자 잘리는 쪽): 인물·물건이 한쪽에 있으면 그쪽으로
const FOCUS: Record<string, string> = { center: "50% 50%", left: "22% 50%", right: "78% 50%", top: "50% 22%", bottom: "50% 78%" };
const SPEED: Record<string, number> = { slow: 0.5, normal: 1, fast: 1.8 };

// 배경: 사진·영상은 가득 + 천천히 움직이기(켄 번스). move 를 비우면(auto) 페이지 안 순번으로 방향을 바꾼다.
// move: in(다가감)·out(물러남)·left·right·up·down(그쪽으로 흐름)·still(멈춤), focus: 기준점, speed: slow·normal·fast, from: 영상 시작 초.
// fade: 글자 쪽 종이 번짐 — left(기본)·right·center·none. dim 은 번짐 세기
const Background: React.FC<{ bg: Bg; index?: number }> = ({ bg, index = 0 }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const len = Math.max(1, f(bg.end - bg.start));
  if ((bg.style === "photo" || bg.style === "video") && bg.src) {
    const k = interpolate(frame, [0, len], [0, 1]);
    const sp = SPEED[bg.speed || "normal"] ?? 1;
    const mv = bg.move || "auto";
    let z = 1, dx = 0, dy = 0;
    if (mv === "auto") {
      const inward = index % 2 === 0;
      z = inward ? 1.04 + 0.08 * k : 1.12 - 0.08 * k;
      dx = (index % 3 === 0 ? -1 : index % 3 === 1 ? 1 : 0) * 26 * k;
    } else if (mv === "in") { z = 1.03 + 0.1 * sp * k; }
    else if (mv === "out") { z = 1.03 + 0.1 * sp * (1 - k); }
    else if (mv === "still") { z = 1.02; }
    else {
      z = 1.08 + 0.05 * sp;                       // 흐르는 만큼 가장자리가 드러나지 않게 키운다
      const amp = 34 * sp;
      if (mv === "left") dx = amp * (1 - 2 * k);
      if (mv === "right") dx = -amp * (1 - 2 * k);
      if (mv === "up") dy = amp * 0.7 * (1 - 2 * k);
      if (mv === "down") dy = -amp * 0.7 * (1 - 2 * k);
    }
    const cut = interpolate(frame, [0, 5], [1.06, 1], { extrapolateRight: "clamp" });   // 컷이 바뀔 때 살짝 당겨 들어오는 맛
    const origin = FOCUS[bg.focus || "center"] || FOCUS.center;
    const style: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover", objectPosition: origin, transformOrigin: origin,
      transform: `scale(${z * cut}) translate(${dx}px, ${dy}px)`, filter: GRADES[bg.grade || "natural"] || "none" };
    // 번짐 하한 0.6(2026-10-17 2차 심사: dim 0.35 같은 낮은 값이면 어두운 사진 위 검은 글자가 묻혔다)
    const fade = Math.min(0.86, Math.max(0.72, (bg.dim ?? 0.5) * 1.3));   // 2026-10-17 심사: 흰 번짐이 세서 사진이 회색 안개처럼 씻김 → 상한·폭을 줄임
    const paper = (a: number) => paperOf(t, a);
    const side = bg.fade || "left";
    const veil = side === "none" ? null
      : side === "center" ? `radial-gradient(ellipse 58% 62% at 50% 50%, ${paper(0.86 * fade)} 0%, ${paper(0.6 * fade)} 45%, ${paper(0)} 100%)`
      : `linear-gradient(${side === "right" ? 270 : 90}deg, ${paper(0.92 * fade)} 0%, ${paper(0.72 * fade)} 30%, ${paper(0)} 56%)`;
    return (
      <AbsoluteFill style={{ overflow: "hidden", background: t.bg }}>
        {bg.style === "photo" ? <Img src={bg.src} style={style} />
          : <OffthreadVideo src={bg.src} muted style={style} startFrom={Math.max(0, Math.round((bg.from || 0) * FPS))} />}
        {veil ? <AbsoluteFill style={{ background: veil }} /> : null}
      </AbsoluteFill>
    );
  }
  // 사진이 없는 화면: 민무늬 미색 종이(2026-10-17 심사: 모눈이 '교육자료·노트 템플릿'으로 읽혀 매 회차 감점 → 격자 뺌)
  return <AbsoluteFill style={{ background: t.bg }} />;
};

// 마감: 필름 결 + 가장자리 살짝 어둡게(화면이 '만든 영상'처럼 보이게)
const Finish: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at center, rgba(0,0,0,0) 60%, rgba(0,0,0,0.16) 100%)" }} />
      <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, opacity: 0.07, mixBlendMode: "multiply" }}>
        <filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={frame % 8} /><feColorMatrix type="saturate" values="0" /></filter>
        <rect width="100%" height="100%" filter="url(#g)" />
      </svg>
    </AbsoluteFill>
  );
};

// 형광펜: 낱말 뒤에 노란 띠가 왼쪽부터 그어진다.
// 2026-10-17 심사(형광이 단어 밖으로 잘림·베이스라인 아래로 처짐·프레임마다 두께가 다름): 띠 위치를 줄 높이(%)가 아니라 글자 크기(em)로 고정하고,
// 낱말이 올라오는 '가림 상자'(overflow hidden) 바깥에 그려 좌우가 잘리지 않게 한다.
// 종이색 번짐 — 테마 바탕색으로(흑백 테마에서 미색이 남지 않게, 2026-10-27)
export const paperOf = (t: { bg: string }, a: number) => {
  const h = (t.bg || "#f4f1ea").replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};
const MarkerBar: React.FC<{ at: number }> = ({ at }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const p = prog(frame, at, at + 0.35);
  // 2차(2026-10-17 밤): 아래 절반 띠가 '밑줄이 글자를 가로지른다·처진다'로 읽혀 → 글자 몸통 전체 뒤를 칠하는 형광펜 블록으로 통일
  // dark bar with white letters (mono): cover the whole glyph, or the white parts outside the bar vanish (2026-11-09)
  const cover = t.accentInk ? { top: "-0.04em", height: "1.16em" } : { top: "0.16em", height: "0.84em" };
  return <span style={{ position: "absolute", left: "-0.06em", right: "-0.06em", ...cover, background: t.accent,
    transform: `scaleX(${p})`, transformOrigin: "left", zIndex: 0 }} />;
};
const Marker: React.FC<{ children: React.ReactNode; at: number }> = ({ children, at }) => {
  const t = useT();
  const frame = useCurrentFrame();
  // 강조 띠가 어두운 테마(흑백)는 띠가 지나간 뒤 글자를 흰색으로
  const ink = t.accentInk && prog(frame, at, at + 0.35) > 0.5 ? t.accentInk : undefined;
  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <MarkerBar at={at} />
      <span style={{ position: "relative", zIndex: 1, color: ink }}>{children}</span>
    </span>
  );
};

function parts(text: string, words: string[]) {
  if (!words.length) return [{ t: text, hl: false }];
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`);
  return text.split(re).filter(Boolean).map((t) => ({ t, hl: words.includes(t) }));
}

// 낱말이 아래에서 올라오는 한 줄
const RiseLine: React.FC<{ text: string; delay: number; highlight: string[]; size: number }> = ({ text, delay, highlight, size }) => {
  const t = useT();
  const frame = useCurrentFrame();
  let k = 0;
  const tokens: { t: string; hl: boolean; i: number }[] = [];
  for (const pt of parts(text, highlight)) {
    if (pt.hl) tokens.push({ t: pt.t, hl: true, i: k++ });
    else for (const w of pt.t.split(/(\s+)/).filter(Boolean)) tokens.push({ t: w, hl: false, i: /\s/.test(w) ? -1 : k++ });
  }
  return (
    // 한 줄이 넘치면 줄 길이를 고르게 나눈다(text-wrap: balance) — 마지막 낱말 하나만 다음 줄로 떨어져 '충격'·'손실'이 홀로 남던 문제(2026-10-23 1화 S03 c03 심사 4회)
    <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: size, lineHeight: 1.18, color: t.ink, letterSpacing: "-0.035em", wordBreak: "keep-all", textWrap: "balance" } as React.CSSProperties}>
      {tokens.map((tk, j) => {
        if (tk.i < 0) return <span key={j}>{tk.t}</span>;
        const at = delay + tk.i * 0.07;
        const p = prog(frame, at, at + 0.45);
        const word = <span style={{ display: "inline-block", transform: `translateY(${(1 - p) * 105}%)` }}>{tk.t}</span>;
        const clip = <span style={{ display: "inline-block", overflow: "hidden", verticalAlign: "bottom", paddingBottom: "0.06em", position: "relative", zIndex: 1 }}>{word}</span>;
        // 강조 띠가 어두운 테마(흑백)는 띠가 지나간 뒤 그 낱말을 흰 글자로 — 검정 띠 위 검정 글자가 사라졌다(2026-10-27 S01 v5 c05)
        const onBar = t.accentInk && prog(frame, at + 0.3, at + 0.65) > 0.5;
        return tk.hl ? (
          <span key={j} style={{ position: "relative", display: "inline-block", verticalAlign: "bottom", color: onBar ? t.accentInk : undefined }}><MarkerBar at={at + 0.3} />{clip}</span>
        ) : <React.Fragment key={j}>{clip}</React.Fragment>;
      })}
    </div>
  );
};

// 큰 글자. place: left(기본)·center·right — 글자 덩어리를 놓는 쪽(사진의 빈 쪽에 맞춘다), vpos: middle(기본)·top·bottom
const BigText: React.FC<{ lines: string[]; highlight?: string[]; size?: number; place?: string; vpos?: string; lineAt?: number[]; lift?: number; dur: number }> =
  ({ lines, highlight = [], size, place = "left", vpos = "middle", lineAt, lift = 0, dur }) => {
  const t = useT();   // 글자 뒤 종이색 번짐이 테마 바탕색을 쓴다(2026-10-27 흑백 테마)
  const out = useOut(dur);
  const longest = Math.max(...lines.map((l) => l.length));
  const fs = size ?? (longest > 18 ? 66 : longest > 12 ? 78 : 92);
  const right = place === "right", center = place === "center";
  const pad = center ? { paddingLeft: 170, paddingRight: 170 } : right ? { paddingLeft: 420, paddingRight: X } : { paddingLeft: X, paddingRight: 420 };
  // lift(2026-10-27): 같은 장면에 자막 띠가 있으면 아래 글자를 그만큼 올린다 — v3 c04 에서 자막 띠가 질문을 가렸다
  const vert = vpos === "top" ? { justifyContent: "flex-start", paddingTop: 128 } : vpos === "bottom" ? { justifyContent: "flex-end", paddingBottom: 96 + lift } : { justifyContent: "center" };
  // 줄이 많으면(필수 표기를 나눈 다섯 줄 등) 글자 덩어리가 위 띠·소제목과 아래 자막 띠 사이를 넘어 소제목을 덮었다(2026-10-24 2화 S09 c05).
  // 글꼴이 다 불러와진 뒤 실제 높이를 재서, 쓸 수 있는 높이(위 150px·아래 자막 띠 130px 를 뺀 자리)를 넘으면 그만큼 줄인다 — 수식 틀과 같은 방식
  const box = useRef<HTMLDivElement>(null);
  const [wait] = useState(() => delayRender("fit big text height"));
  const fit = () => {
    const el = box.current;
    if (!el) return;
    el.style.zoom = "1";
    const avail = 720 - (vpos === "top" ? 128 : 150) - 130 + 60;   // +60: 덩어리 안쪽 위아래 여백(30+30)은 번짐 자리라 겹쳐도 된다
    el.style.zoom = String(Math.min(1, avail / Math.max(1, el.offsetHeight)));
  };
  useLayoutEffect(fit);
  useEffect(() => { document.fonts.ready.then(() => { fit(); continueRender(wait); }); }, []);
  return (
    <AbsoluteFill style={{ ...vert, alignItems: center ? "center" : right ? "flex-end" : "flex-start", ...pad, opacity: out }}>
      {/* 글자 덩어리 뒤에만 부드러운 종이색 번짐(2026-10-17 2차 심사 최다 지적: 사진의 어두운·복잡한 부분에 검은 글자가 묻힘).
          종이 바탕에서는 같은 색이라 보이지 않는다 */}
      <div ref={box} style={{ position: "relative", padding: right ? "30px 40px 30px 60px" : "30px 60px 30px 40px", ...(right ? { marginRight: -40 } : { marginLeft: center ? 0 : -40 }),
        textAlign: center ? "center" : right ? "right" : "left" }}>
        {/* 가장자리가 직선으로 보이면 '카드'가 되므로 흐린 덩어리로 — 경계가 보이지 않게 */}
        <div style={{ position: "absolute", inset: "10px 20px 10px 10px", background: paperOf(t, 0.8), filter: "blur(30px)", borderRadius: 60 }} />
        <div style={{ position: "relative" }}>
          {/* lineAt(2026-10-27): 줄마다 나레이션에서 그 말을 하는 순간(조립이 화면 배치 담당의 lineSay 로 계산) — 없으면 0.25초 간격 */}
          {lines.map((ln, i) => <RiseLine key={i} text={ln} delay={typeof lineAt?.[i] === "number" ? (lineAt[i] as number) : i * 0.25} highlight={highlight} size={fs} />)}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// 단계 띠(2026-10-18 사용자 요청): 지금 무슨 이야기를 하는 중인지 — 스토리보드 단계 제목('2단계 · 시시포스와 메타전략')이 페이지 내내 왼쪽 위에 남는다.
// 같은 단계가 다음 페이지로 이어지면 움직임 없이 그대로(페이지가 바뀌어도 깜빡이지 않게), 새 단계 첫 페이지만 닦이며 들어온다.
const Section: React.FC<{ text: string; enter?: boolean; dur: number }> = ({ text, enter }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const p = enter ? prog(frame, 0.1, 0.6) : 1;
  return (
    <div style={{ position: "absolute", left: X, top: 46, display: "flex", alignItems: "stretch", clipPath: `inset(0 ${(1 - p) * 100}% 0 0)` }}>
      <div style={{ width: 12, background: t.accent }} />
      <div style={{ background: t.card, color: t.cardInk, fontFamily: t.font, fontWeight: 800, fontSize: 24, padding: "9px 18px", letterSpacing: "0.01em" }}>{text}</div>
    </div>
  );
};

// 꼬리표: 검은 띠에 흰 글자, 왼쪽 위. sub 면 단계 띠 아래 작은 글(장면 소제목)
const Kicker: React.FC<{ text: string; sub?: boolean; dur: number }> = ({ text, sub, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  const p = prog(frame, 0, 0.4);
  if (sub) {
    return <div style={{ position: "absolute", left: X + 12, top: 104, fontFamily: t.font, fontWeight: 800, fontSize: 21, color: t.ink, opacity: out * Math.min(1, p * 1.5),
      background: paperOf(t, 0.82), padding: "4px 12px" }}>{text}</div>;
  }
  return (
    <div style={{ position: "absolute", left: X, top: 54, display: "flex", alignItems: "stretch", opacity: out, clipPath: `inset(0 ${(1 - p) * 100}% 0 0)` }}>
      <div style={{ width: 12, background: t.accent }} />
      <div style={{ background: t.card, color: t.cardInk, fontFamily: t.font, fontWeight: 800, fontSize: 22, padding: "8px 16px", letterSpacing: "0.01em" }}>{text}</div>
    </div>
  );
};

function countUp(value: string, p: number) {
  // 연도·날짜(2023.3, 1998, 2023-03)는 세어 올라가지 않는다 — 중간값 '1552.4'·'2020.6'이 틀린 연도처럼 보였다(2026-10-17 심사)
  if (/^\s*(1[89]|20)\d{2}(\s*[.\-/년]\s*\d{1,2}(\s*[.\-/월]\s*\d{1,2})?)?\s*[년월일.]?\s*$/.test(String(value))) return value;
  const m = String(value).match(/^([^0-9]*)([0-9][0-9,]*\.?[0-9]*)(.*)$/);
  if (!m) return value;
  const num = parseFloat(m[2].replace(/,/g, ""));
  const decimals = (m[2].split(".")[1] || "").length;
  const v = (num * Math.min(1, p)).toFixed(decimals);
  return `${m[1]}${m[2].includes(",") ? Number(v).toLocaleString() : v}${m[3]}`;
}

// 숫자: 상자 없이 아주 큰 숫자 + 노란 밑줄 + 이름
const NumberCard: React.FC<{ items: { value: string; label: string; tone?: string }[]; title?: string; note?: string; dur: number }> = ({ items, title, note, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  // 최대 6개까지 다 그린다 — 예전엔 4개에서 잘라 다섯째 값이 말없이 사라졌다(2026-10-24 2화 S13 c05 y₃, 회차마다 '큰 숫자' 불통과).
  // 6개를 넘으면 저장 검사가 막는다(scenes._check).
  const list = (items || []).slice(0, 6);
  const big = list.length === 1 ? 230 : list.length === 2 ? 190 : list.length === 3 ? 140 : list.length === 4 ? 110 : list.length === 5 ? 92 : 80;
  const gap = list.length > 4 ? 36 : list.length > 2 ? 48 : 80;
  const colW = Math.floor((1280 - X * 2 - gap * (list.length - 1)) / Math.max(1, list.length));   // 칸 폭을 정해 화면 밖으로 안 나가게
  const hasAccent = list.some((x) => x.tone === "accent");   // 하나라도 있으면 '지금 여기' 표시 — 그 항목만 노랑, 나머지는 흐리게(2026-10-19)
  const isNum = (v: string) => /^[^0-9가-힣]*[0-9][0-9.,]*\s*[%배x×개명원달러년월일초분시점]*$/.test(String(v || "").trim());
  return (
    <AbsoluteFill style={{ justifyContent: "center", paddingLeft: X, paddingRight: X, opacity: out }}>
      {title ? <div style={{ fontFamily: t.font, fontWeight: 800, fontSize: 30, color: t.sub, marginBottom: 6, opacity: prog(frame, 0, 0.3) }}>{title}</div> : null}
      <div style={{ display: "flex", gap, alignItems: "flex-end" }}>
        {list.map((it, i) => {
          const p = prog(frame, 0.15 + i * 0.3, 1.1 + i * 0.3);
          const bar = prog(frame, 0.7 + i * 0.3, 1.1 + i * 0.3);
          const num = isNum(it.value);
          const dimmed = hasAccent && it.tone !== "accent";
          const len = String(it.value || "").length;
          // 숫자가 아닌 값(낱말)은 숫자보다 작게, 칸 폭에 맞춰 — '그대로'가 '95%'를 덮던 문제
          const fs = num ? Math.min(big, Math.floor(colW / Math.max(1.6, len * 0.62))) : Math.min(big * 0.55, Math.floor(colW / Math.max(2, len * 1.05)));
          return (
            <div key={i} style={{ opacity: Math.min(1, p * 2) * (dimmed ? 0.45 : 1), width: colW, minWidth: 0 }}>
              <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: fs, lineHeight: 0.95, color: it.tone === "warn" ? t.warn : t.ink, letterSpacing: num ? "-0.05em" : "-0.03em",
                fontVariantNumeric: "tabular-nums", transform: `translateY(${(1 - p) * 40}px)`, whiteSpace: "nowrap" }}>{it.value /* 세어 올라가는 효과는 뺐다 — 중간값('5 대 34')이 찍혀 숫자가 스스로를 반박했다(2026-10-17 2차 심사) */}</div>
              <div style={{ height: 14, background: dimmed ? t.line : t.accent, marginTop: 10, transform: `scaleX(${bar})`, transformOrigin: "left", width: "100%" }} />
              <div style={{ fontFamily: t.font, fontWeight: 700, fontSize: list.length > 2 ? 26 : 32, color: t.ink, marginTop: 14, lineHeight: 1.3, wordBreak: "keep-all" }}>{it.label}</div>
            </div>
          );
        })}
      </div>
      {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 22, color: t.sub, marginTop: 30, opacity: prog(frame, 1, 1.4) }}>{note}</div> : null}
    </AbsoluteFill>
  );
};

type StepItem = string | { label: string; img?: string; desc?: string; at?: number };
const bare = (s: string) => (s || "").replace(/^\s*(?:[①-⑳⓵-⓾❶-❿]|\(?\d{1,2}\s*(?:[.)\]:]|단계)|\d{1,2}\s+(?=\S))\s*/, "");

// 단계: 왼쪽에 큰 번호 01·02·03 목록. active 가 있으면 그 줄만 진하게 + 형광펜, 그 항목 그림이 오른쪽 절반을 채운다
// pin 목록(2026-10-19): 장면이 바뀌어도 같은 목록이 남고 형광펜만 옮겨 간다. enter:false 면 이미 나온 항목은 움직임 없이 바로 그려지고,
// exit:false 면 장면 끝에서 사라지지 않는다(다음 장면이 같은 목록을 이어받는다).
// numbered: false = 순서가 아닌 나열·대비라 01·02 를 붙이지 않는다(2026-10-19 2화 S02 "값이 존재한 날/알 수 있었던 날"에 번호가 붙어 순서처럼 보였다)
const Steps: React.FC<{ items: StepItem[]; active?: number; enter?: boolean; exit?: boolean; numbered?: boolean; dur: number }> = ({ items, active, enter = true, exit = true, numbered = true, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out0 = useOut(dur);
  const out = exit === false ? 1 : out0;
  const list = items.map((x) => (typeof x === "string" ? { label: bare(x) } : { ...x, label: bare(x.label) }));
  const focus = active ? list[active - 1] : undefined;
  const wipe = prog(frame, 0.05, 0.6);
  const n = list.length;
  const fs = n > 5 ? 38 : n > 4 ? 44 : focus?.img ? 52 : 70;
  return (
    <AbsoluteFill style={{ opacity: out }}>
      {focus?.img ? (
        <div style={{ position: "absolute", left: W * 0.52, top: 0, width: W * 0.48, height: H, overflow: "hidden", clipPath: `inset(0 0 0 ${(1 - wipe) * 100}%)` }}>
          <Img src={focus.img} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${1.1 - 0.06 * interpolate(frame, [0, f(dur)], [0, 1])})` }} />
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 10, background: t.accent }} />
        </div>
      ) : null}
      {/* 사진 위에서도 읽히게 목록 뒤에 종이색 번짐(2026-10-17: 어두운 사진 위에서 항목 이름이 안 보였다) */}
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${paperOf(t, 0.9)} 0%, ${paperOf(t, 0.75)} ${focus?.img ? 40 : 38}%, ${paperOf(t, 0)} ${focus?.img ? 52 : 62}%)` }} />
      {/* 위쪽 150px 은 단계 띠·소제목 자리 — 목록이 길어도 그 위로 올라가 겹치지 않게(2026-10-22 1화 S06 c10 소제목이 01 항목 위에 겹침) */}
      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: X, paddingRight: focus?.img ? W * 0.5 : 200, paddingTop: 150, paddingBottom: 40 }}>
        {list.map((s, i) => {
          const on = isPrint() || active === undefined || active === i + 1;   // 슬라이드는 모든 항목 진하게(다른 항목 흐리기는 영상 효과)
          // 항목마다 at(장면 시작부터 초)을 주면 그 말이 나올 때 나타난다 — 말과 상관없이 0.5초 안에 셋이 몰려 뜨던 문제(2026-10-17 심사)
          const rawAt = typeof (items[i] as any)?.at === "number" ? (items[i] as any).at : undefined;
          const at = rawAt !== undefined ? Math.max(0, rawAt) : 0.1 + i * 0.18;
          const p = enter === false && (rawAt === undefined || rawAt <= 0) ? 1 : prog(frame, at, at + 0.5);
          const isFocus = active === i + 1;
          return (
            <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 26, marginBottom: 22, opacity: Math.min(1, p * 1.5) * (on ? 1 : 0.6), transform: `translateX(${(1 - p) * -40}px)` }}>
              {numbered ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: fs * 0.62, color: on ? t.ink : t.sub, fontVariantNumeric: "tabular-nums", minWidth: fs * 0.9 }}>{String(i + 1).padStart(2, "0")}</div> : null}
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: fs, color: t.ink, letterSpacing: "-0.03em", lineHeight: 1.12, wordBreak: "keep-all" }}>
                  {isFocus ? <Marker at={0.35}>{s.label}</Marker> : s.label}
                </div>
                {(isFocus || isPrint()) && s.desc ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 28, color: t.sub, marginTop: 10, lineHeight: 1.35, wordBreak: "keep-all",
                  opacity: prog(frame, 0.45, 0.8) }}>{s.desc}</div> : null}
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// 선 그래프: 상자 없이 종이 위에 굵은 검은 선, 아래 노란 면, 마지막 값은 검은 꼬리표
const LineChart: React.FC<{ points: number[]; label?: string; note?: string; markLast?: string; tone?: string; dur: number }> = ({ points, label, note, markLast, tone, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  // 아래 글(note)은 곡선·막대처럼 제목 바로 아래로, 그만큼 그래프를 줄인다(2026-10-27 S01: 그래프 아래 글이 자막 띠(608px~)에 가려 잘렸다)
  const CW = 1060, CH = note ? 336 : 370, pad = 10, top = 70;
  const min = Math.min(...points), max = Math.max(...points);
  const xy = points.map((v, i) => [pad + (i / (points.length - 1)) * (CW - pad * 2 - 120), CH - pad - ((v - min) / (max - min || 1)) * (CH - pad - top)]);
  const pr = prog(frame, 0.2, Math.min(2.6, dur * 0.6));
  const nn = Math.max(2, Math.ceil(pr * points.length));
  const path = xy.slice(0, nn).map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lx, ly] = xy[nn - 1];
  const color = tone === "warn" ? t.warn : t.ink;
  return (
    <AbsoluteFill style={{ paddingLeft: X, paddingTop: 140, opacity: out }}>
      {label ? <div style={{ fontFamily: t.font, fontWeight: 900, fontSize: 44, color: t.ink, letterSpacing: "-0.03em", marginBottom: note ? 4 : 20 }}>{label}</div> : null}
      {note ? <div style={{ fontFamily: t.font, fontWeight: 600, fontSize: 20, color: t.sub, marginBottom: 12 }}>{note}</div> : null}
      {/* overflow visible: 끝 값 표시(markLast)가 바닥 가까이에서 그래프 영역 밖으로 나가도 잘리지 않게(2026-10-27 S01 '-62%') */}
      <svg width={CW} height={CH} style={{ overflow: "visible" }}>
        <line x1={pad} x2={CW - 120} y1={CH - pad} y2={CH - pad} stroke={t.ink} strokeWidth={3} />
        <path d={`${path} L${lx},${CH - pad} L${pad},${CH - pad} Z`} fill={t.fill || t.accent} opacity={0.55} />
        <path d={path} fill="none" stroke={color} strokeWidth={7} strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={lx} cy={ly} r={11} fill={color} />
        {markLast && pr >= 1 ? (
          <g><rect x={lx + 18} y={ly - 26} width={markLast.length * 22 + 28} height={52} fill={t.card} />
            <text x={lx + 32} y={ly + 11} fontFamily={t.font} fontWeight={900} fontSize={32} fill={t.cardInk}>{markLast}</text></g>
        ) : null}
      </svg>
    </AbsoluteFill>
  );
};

// 자막: 왼쪽 아래 검은 띠
const Caption: React.FC<{ text: string; dur: number }> = ({ text, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  const p = prog(frame, 0, 0.3);
  return (
    <div style={{ position: "absolute", left: X, bottom: 48, maxWidth: 1000, opacity: out, clipPath: `inset(0 ${(1 - p) * 100}% 0 0)` }}>
      <div style={{ background: t.card, color: t.cardInk, fontFamily: t.font, fontWeight: 700, fontSize: 30, padding: "12px 22px", wordBreak: "keep-all", lineHeight: 1.35 }}>{text}</div>
    </div>
  );
};

// 사진 카드: 둥근 모서리·테두리 없이, 옆으로 닦이며 들어오는 사진 + 아래 작은 설명
// w·h·x·y 는 픽셀(1280×720). 1 이하의 값은 화면 비율로 읽는다(1 = 화면 전체) — 2026-10-18 S02: 비율을 넣었다가 폭 1픽셀 카드가 돼 사진이 사라졌다
const px = (v: number | undefined, full: number) => (typeof v === "number" ? (v > 0 && v <= 1 ? v * full : v) : undefined);
const PhotoCard: React.FC<{ src: string; caption?: string; x?: number; y?: number; w?: number; h?: number; video?: boolean; dur: number }> = ({ src, caption, x: x0, y: y0, w: w0, h: h0, video, dur }) => {
  // 안전 영역(2026-10-19 S08: 카드가 w1101·h648·y36 으로 단계 띠 위를 덮고 아래 설명 줄이 화면 밖으로 잘림): 왼쪽 위 단계 띠·소제목 구역(y<150, x<560)과
  // 아래 출처·자막 구역(y>650)을 침범하지 않게 크기와 자리를 맞춘다. 모델이 어떤 값을 넣어도 화면이 깨지지 않는다.
  const capH = caption ? 44 : 0;
  const w = Math.min(px(w0, W) ?? 820, 1200);
  const x = px(x0, W), y = px(y0, H);
  const left = Math.max(40, Math.min(x ?? W - w - 70, W - 40 - w));
  const minTop = left < 560 ? 150 : 40;                           // 띠·소제목 쪽(왼쪽)을 덮을 때만 위를 비운다
  const h = Math.min(px(h0, H) ?? 470, 650 - capH - minTop);
  const top = Math.max(minTop, Math.min(y ?? (H - h) / 2 - (caption ? 20 : 0), 650 - capH - h));
  const t = useT();
  const frame = useCurrentFrame();
  const out = useOut(dur);
  const wipe = prog(frame, 0, 0.55);
  const z = 1.1 - 0.07 * interpolate(frame, [0, f(dur)], [0, 1]);
  const style: React.CSSProperties = { width: "100%", height: "100%", objectFit: "cover", transform: `scale(${z})` };
  return (
    <div style={{ position: "absolute", left, top, width: w, opacity: out }}>
      <div style={{ width: w, height: h, overflow: "hidden", clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)`, boxShadow: "0 24px 50px rgba(0,0,0,0.22)" }}>
        {video ? <OffthreadVideo src={src} muted style={style} /> : <Img src={src} style={style} />}
      </div>
      {caption ? <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14, opacity: prog(frame, 0.4, 0.7) }}>
        <div style={{ width: 22, height: 6, background: t.accent }} />
        <div style={{ fontFamily: t.font, fontWeight: 700, fontSize: 24, color: t.ink }}>{caption}</div></div> : null}
    </div>
  );
};

// 출처·필수 표기: 오른쪽 아래 작은 글씨(사진 위에서도 읽히게 종이색 바탕)
const SourceTag: React.FC<{ text: string; dur: number }> = ({ text, dur }) => {
  const t = useT();
  const frame = useCurrentFrame();
  // 장면 내내 보인다(2026-10-17 2차 심사: 2.5초 뒤 사라지니 '출처가 있다가 없어진다·급히 만든 인상' 지적 → 작고 진한 띠로 계속). 어떤 사진 위에서도 읽힌다
  const vis = prog(frame, 0, 0.3) * useOut(dur);
  return <div style={{ position: "absolute", right: 34, bottom: 22, fontFamily: t.font, fontSize: 18, fontWeight: 700, color: "#ffffff", background: "rgba(17,17,17,0.72)",
    padding: "4px 10px", opacity: vis }}>{text}</div>;
};

const Sparkles: React.FC = () => null;   // 다큐에는 반짝이를 쓰지 않는다

export const DOCU = {
  Background, Finish,
  components: { BigText, Kicker, Section, NumberCard, Steps, Chips: Steps, LineChart, Caption, PhotoCard, SourceTag, Sparkles } as Record<string, React.FC<any>>,
};
export { FPS };
