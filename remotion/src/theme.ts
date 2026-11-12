// 화면 테마(2026-10-16). 타임라인 JSON 의 "theme" 으로 고른다 — 주제에 맞는 옷을 입힌다.
//  finance : 밝지만 단정한 금융·경제 해설(기본) — 흰 바탕, 진회색 글자, 연한 청록 강조(보라 둘째, 분홍 드물게), 장식 없음
//  adshort : 밝고 경쾌한 광고·숏폼 — 노란 종이·민트 사선, 분홍 형광펜, 반짝이
export type Theme = {
  name: string; bg: string; bg2: string; ink: string; sub: string; accent: string; accentSoft: string; warn: string;
  card: string; cardInk: string; cardNum: string; line: string; font: string; decor: boolean; highlight: "marker" | "underline";
  docu?: boolean;
  bar?: string;         // a thin color bar across the top of every screen (the original Shoestring look); empty = none
  dim?: string;         // overlay color (r,g,b) over a background photo; empty = white
  paper?: string;       // page color under everything; empty = white   // 다큐 화면 틀(docu.tsx)을 쓴다 — 카드·그림자 없이 사진 가득, 왼쪽 큰 글자, 형광펜
  accentInk?: string;   // 강조 띠(형광펜·값 표시) 위 글자 색 — 강조 색이 어두우면 흰 글자(흑백 테마). 비우면 ink
  fill?: string;        // 그래프 면 칠·구간 칠·수식 강조 바탕 — 비우면 accent(강조 색이 검정이면 선을 덮으므로 따로)
  photoGrade?: string;  // 배경 사진 색감을 테마가 고정(흑백 테마: mono) — 비우면 장면·페이지·한 편 색감
  // 2026-11-11 soft palette: a deep accent for accent-colored text and small labels on accent, a second and a third
  // accent (with their text colors), and the highlight chip (rose background, dark rose text). Empty = accent / ink
  accentText?: string; accent2?: string; accent2Ink?: string; accent3?: string; accent3Ink?: string; hlBg?: string; hlInk?: string; accent2Soft?: string;
};

// 일본어(가나·한자)는 Pretendard 에 없어 일본 글꼴(Yu Gothic)로 넘어간다 — 한자도 일본식 모양으로(2026-10-17)
const PRETENDARD = "'Pretendard', 'Yu Gothic', 'YuGothic', 'Noto Sans KR', 'Malgun Gothic', sans-serif";

export const THEMES: Record<string, Theme> = {
  // shoestring (2026-11-11): the original Shoestring Studios look from the hackathon video: deep navy page, near-white
  // text, amber accent, a 14px amber bar on top, Inter-style sans (Pretendard's Latin letters are Inter). Small text on
  // amber is navy, never white.
  shoestring: {
    name: "shoestring", bg: "#0F172A", bg2: "#1E293B", ink: "#F8FAFC", sub: "#CBD5E1", accent: "#F59E0B", accentSoft: "#3A2E14",
    warn: "#F87171", card: "#1E293B", cardInk: "#E2E8F0", cardNum: "#FBBF24", line: "#334155",
    font: PRETENDARD, decor: false, highlight: "underline", accentInk: "#0F172A",
    accentText: "#FBBF24", accent2: "#38BDF8", accent2Ink: "#7DD3FC", accent3: "#F472B6", accent3Ink: "#F9A8D4",
    hlBg: "#F59E0B", hlInk: "#0F172A", accent2Soft: "#16324A", bar: "#F59E0B", dim: "15,23,42", paper: "#0F172A",
  },
  //  docu : 밝은 다큐 경제 해설(블룸버그·Vox 결, 2026-10-16 사용자 선택) — 미색 종이, 검정 굵은 글자, 노란 형광펜, 파랑 보조
  docu: {
    name: "docu", bg: "#f4f1ea", bg2: "#e9e4d8", ink: "#111111", sub: "#55524c", accent: "#ffd43b", accentSoft: "#fff3bf",
    warn: "#e8590c", card: "#111111", cardInk: "#ffffff", cardNum: "#111111", line: "#cfc8b8",
    font: PRETENDARD, decor: false, highlight: "marker", docu: true,
  },
  //  mono : 흑백 다큐(2026-10-27 대표님: 노란 테마 말고 세련된 흑백) — 연회색 종이, 검정 글자, 강조는 검정 띠 위 흰 글자, 배경 사진은 흑백
  mono: {
    name: "mono", bg: "#f2f2f0", bg2: "#e3e3e1", ink: "#0e0e0e", sub: "#5f5f5f", accent: "#0e0e0e", accentSoft: "#d9d9d9",
    warn: "#0e0e0e", card: "#0e0e0e", cardInk: "#ffffff", cardNum: "#0e0e0e", line: "#c6c6c4",
    font: PRETENDARD, decor: false, highlight: "marker", docu: true, accentInk: "#ffffff", fill: "#b9b9b7", photoGrade: "mono",
  },
  // finance (2026-11-11 user choice, soft colors from layouts/theme_preview.html): white page, dark text, soft cyan as the
  // main accent (deep cyan for numbers and accent text), purple second, pink only for rare emphasis; highlight chip
  // = rose background with dark rose text. Small text never white on cyan.
  finance: {
    name: "finance", bg: "#ffffff", bg2: "#F4FAFC", ink: "#1F2937", sub: "#4B5563", accent: "#6FC3D6", accentSoft: "#DDF1F6",
    warn: "#DE7C93", card: "#ffffff", cardInk: "#4B5563", cardNum: "#2E8AA3", line: "#D1D5DB",
    font: "'Pretendard', 'Yu Gothic', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif", decor: false, highlight: "underline", accentInk: "#1F2937",
    accentText: "#2E8AA3", accent2: "#A47BA0", accent2Ink: "#7E5279", accent3: "#DE7C93", accent3Ink: "#B9536C", hlBg: "#F6DCE3", hlInk: "#9B3550", accent2Soft: "#EADDEB",
  },
  adshort: {
    name: "adshort", bg: "#f7c948", bg2: "#9fe7df", ink: "#17171c", sub: "#3d3d45", accent: "#ff4d6d", accentSoft: "#ffd6de",
    warn: "#ff4d6d", card: "#1d3a2f", cardInk: "#ffffff", cardNum: "#ffe14d", line: "#17171c",
    font: "'Pretendard', 'Yu Gothic', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif", decor: true, highlight: "marker",
  },
};
