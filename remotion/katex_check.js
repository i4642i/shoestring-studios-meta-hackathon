// 렌더 전 수식 검사(2026-10-17): 표준 입력으로 받은 LaTeX 목록을 KaTeX 로 해석해 보고, 해석 못 하는 것만 오류로 돌려준다.
//   입력: ["\\frac{a}{b}", ...]   출력: [{"i": 번호, "error": "..."}]
const katex = require("katex");
let buf = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (buf += d));
process.stdin.on("end", () => {
  const list = JSON.parse(buf || "[]");
  const out = [];
  list.forEach((src, i) => {
    try {
      // 가운뎃점 '·'(U+00B7)은 KaTeX 가 \cdotp 로 바꿔 글자 안에서 오류가 난다 — 렌더(graphics.tsx texSafe)와 같이 '‧'로 바꿔 본다(2026-10-24 2화 S05)
      katex.renderToString(String(src).replace(/·/g, "‧"), { displayMode: true, throwOnError: true, strict: "ignore" });
    } catch (e) {
      out.push({ i, error: String(e.message || e).replace(/^KaTeX parse error:\s*/, "").slice(0, 200) });
    }
    if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(String(src))) out.push({ i, error: "보이지 않는 제어 문자가 섞여 있습니다(역슬래시가 깨진 흔적)" });
  });
  process.stdout.write(JSON.stringify(out));
});
