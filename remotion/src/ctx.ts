import { createContext, useContext } from "react";
import { continueRender, delayRender, staticFile } from "remotion";
import { THEMES, Theme } from "./theme";

// 화면 틀이 함께 쓰는 것: 초→프레임, 테마, 글꼴
export const FPS = 30;
export const f = (s: number) => Math.round(s * FPS);
export const T = createContext<Theme>(THEMES.finance);
export const useT = () => useContext(T);

// 인쇄 모드(2026-10-22 심사용 슬라이드): 등장·퇴장 효과를 끄고 배치가 끝난 상태로 그린다. Page 가 props.print 로 정한다.
let printMode = false;
export const setPrint = (v: boolean) => { printMode = v; };
export const isPrint = () => printMode;

// Pretendard(SIL OFL — 상업 사용 가능)를 public/fonts 에서 읽는다. 없으면 Noto Sans KR·맑은 고딕으로 넘어간다.
const WEIGHTS: [string, string][] = [["Medium", "500"], ["SemiBold", "600"], ["Bold", "700"], ["ExtraBold", "800"], ["Black", "900"]];
if (typeof document !== "undefined" && typeof FontFace !== "undefined") {
  const h = delayRender("load fonts");
  Promise.all(WEIGHTS.map(([n, w]) => new FontFace("Pretendard", `url(${staticFile(`fonts/Pretendard-${n}.woff2`)}) format('woff2')`, { weight: w })
    .load().then((ff) => { (document as any).fonts.add(ff); }).catch(() => undefined)))
    .finally(() => continueRender(h));
}
