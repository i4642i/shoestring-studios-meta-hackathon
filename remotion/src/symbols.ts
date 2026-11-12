// 화면 글자 속 수식 기호 다듬기(2026-10-24 2화 S05·S10·S13: 'S_t', 'K_{t-1}', '\Delta p_t' 가 밑줄·중괄호·역슬래시째 찍혀
// 회차마다 '기호가 오타처럼 보인다' 지적이 나왔다). 직원이 매번 $…$ 로 감싸기를 기억하게 두지 않고, 그리는 쪽에서 한 번에 바꾼다.
//  - 단순한 아래첨자 S_t · K_{t-1} → 유니코드 아래첨자(Sₜ · Kₜ₋₁) — SVG 글자(그래프)에서도 똑같이 보인다. 바꿀 수 없는 글자가 섞이면 그대로 둔다
//  - 자주 쓰는 기호 명령 \Delta · \sigma · \times … → Δ σ ×
//  - $…$ 안(그 자리에서 KaTeX 로 그린다), 수식 틀의 식 줄(steps·latex·강조 항 term), 파일 경로(src·img·file·url)는 건드리지 않는다
const SUB: Record<string, string> = {
  "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
  "+": "₊", "-": "₋", "−": "₋", "=": "₌", "(": "₍", ")": "₎",
  a: "ₐ", e: "ₑ", h: "ₕ", i: "ᵢ", j: "ⱼ", k: "ₖ", l: "ₗ", m: "ₘ", n: "ₙ", o: "ₒ", p: "ₚ", r: "ᵣ", s: "ₛ", t: "ₜ", u: "ᵤ", v: "ᵥ", x: "ₓ",
};
const CMD: Record<string, string> = {
  Delta: "Δ", delta: "δ", theta: "θ", Theta: "Θ", phi: "φ", varphi: "φ", Sigma: "Σ", sum: "Σ", sigma: "σ", mu: "μ", alpha: "α", beta: "β",
  gamma: "γ", lambda: "λ", pi: "π", rho: "ρ", tau: "τ", epsilon: "ε", varepsilon: "ε", omega: "ω", Omega: "Ω",
  times: "×", cdot: "·", div: "÷", pm: "±", geq: "≥", ge: "≥", leq: "≤", le: "≤", neq: "≠", ne: "≠", approx: "≈", infty: "∞",
  to: "→", rightarrow: "→", Rightarrow: "⇒", leftarrow: "←",
};
const SKIP_KEYS = new Set(["steps", "latex", "term", "src", "img", "file", "url", "image", "logo"]);

const sub = (s: string) => {
  const out = [...s].map((c) => SUB[c]);
  return out.every(Boolean) ? out.join("") : null;
};

export function prettySymbols(text: string): string {
  if (!text || (!text.includes("_") && !text.includes("\\"))) return text;
  return text.split(/(\$[^$]+\$)/g).map((part) => {
    if (part.length > 2 && part.startsWith("$") && part.endsWith("$")) return part;
    let s = part.replace(/\\([A-Za-z]+)/g, (m, name) => CMD[name] ?? m);
    // 글자(1~2자, 그리스 문자 포함) 바로 뒤 _x 또는 _{…} — 앞뒤가 영문·숫자로 이어지는 낱말(파일 이름 s09_c01 등)은 건드리지 않는다
    s = s.replace(/(^|[^A-Za-z0-9_])([A-Za-zΑ-Ωα-ω]{1,2})_(\{([^{}]{1,10})\}|([A-Za-z0-9]))(?![A-Za-z0-9])/g,
      (m, pre, base, _g, braced, single) => {
        const t = sub(String(braced ?? single).replace(/\s+/g, ""));
        return t ? pre + base + t : m;
      });
    return s;
  }).join("");
}

export function prettyProps(v: any, key = ""): any {
  if (SKIP_KEYS.has(key)) return v;
  if (typeof v === "string") return prettySymbols(v);
  if (Array.isArray(v)) return v.map((x) => prettyProps(x, key));
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, prettyProps(x, k)]));
  return v;
}
