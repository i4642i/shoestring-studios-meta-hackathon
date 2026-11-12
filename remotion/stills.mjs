// 심사용 슬라이드(2026-10-22): 브라우저 하나로 여러 프레임의 정지 그림을 그린다(장면마다 CLI 를 따로 부르면 매번 브라우저를 새로 띄워 느렸다).
// 사용: node stills.mjs <build 폴더> <props.json> <jobs.json>   jobs = [{"frame": 정수, "out": "PNG 경로"}, ...]
// props 에 print:true 를 넣어 부르면 등장·퇴장 효과가 꺼진 '배치 완료' 상태로 그려진다(src/ctx.ts isPrint).
import fs from "node:fs";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";

const [, , serveUrl, propsFile, jobsFile] = process.argv;
const inputProps = JSON.parse(fs.readFileSync(propsFile, "utf8"));
const jobs = JSON.parse(fs.readFileSync(jobsFile, "utf8"));
const browser = await openBrowser("chrome");
try {
  const composition = await selectComposition({ serveUrl, id: "Page", inputProps, puppeteerInstance: browser, logLevel: "error" });
  for (const j of jobs) {
    const frame = Math.max(0, Math.min(composition.durationInFrames - 1, j.frame));
    await renderStill({ composition, serveUrl, output: j.out, frame, inputProps, puppeteerInstance: browser, imageFormat: "png", logLevel: "error", overwrite: true });
    console.log("OK", j.out);
  }
} finally {
  await browser.close({ silent: true });
}
