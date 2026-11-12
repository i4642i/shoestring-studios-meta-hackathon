// KaTeX 가 아는 명령 이름 목록을 뽑아 app/runs/katex_commands.json 으로 쓴다(2026-10-17).
// 플랫폼이 직원 결과(JSON) 속 LaTeX 가 깨진 것을 되살릴 때 쓴다 — 사람이 목록을 관리하지 않게, KaTeX 를 올리면 다시 돌린다.
//   node katex_commands.js
const fs = require("fs");
const src = fs.readFileSync(require.resolve("katex/dist/katex.js"), "utf8");
const set = new Set();
const re = /"\\\\([a-zA-Z]+)"/g;   // 소스 안의 "\\frac" 같은 글
let m;
while ((m = re.exec(src))) set.add(m[1]);
const arr = [...set].sort();
fs.writeFileSync(__dirname + "/../app/runs/katex_commands.json", JSON.stringify(arr));
console.log(arr.length, "개 —", arr.filter((x) => /^[bfnrt]/.test(x)).length, "개가 b·f·n·r·t 로 시작");
