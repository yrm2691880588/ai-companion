import { chromium } from "playwright";
import { pickCompanionWithVoice } from "./lib/fixtures.mjs";

const BASE = "http://127.0.0.1:8000";

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

// 记录合成请求次数与时间点，用于验证「边生成边合成」
const synthTimes = [];
page.on("request", (r) => {
  if (r.url().includes("/v1/voice/synthesize")) synthTimes.push(Date.now());
});

const companionId = await pickCompanionWithVoice(page);
if (!companionId) {
  console.log("SKIP 没有可用的测试伴侣（先跑 scripts/seed_test_companion.py）");
  await browser.close();
  process.exit(0);
}
await page.goto(`${BASE}/companions/${companionId}/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

// 打开语音模式
const voiceBtn = page.getByRole("button", { name: /语音模式/ });
await voiceBtn.first().click();
await page.waitForTimeout(600);
const on = await page.locator("body").innerText();
check("语音模式已开启", on.includes("语音模式：开"));

// 发一句要求长回复的话，确保能被切成多段
const start = Date.now();
await page.locator("textarea").fill("跟我讲讲你今天都做了什么，说得详细一点，多讲几句。");
await page.locator("textarea").press("Enter");
await page.waitForTimeout(26000);

const body = await page.locator("body").innerText();
check("收到回复文字", body.length > 200);
check("合成至少被调用一次", synthTimes.length >= 1, `调用 ${synthTimes.length} 次`);
// 关键指标：第一段合成是否早于回复结束（说明边生成边合成，不是最后一次性）
if (synthTimes.length >= 1) {
  const firstSynth = synthTimes[0] - start;
  check("第一段合成在回复结束前就已发出（流式生效）", firstSynth < 20000, `${firstSynth}ms 时开始合成`);
}
// 播报需要时间（多段串行合成+播放），轮询等待复位而不是固定时长取样
let spokeEnded = false;
for (let waited = 0; waited < 40000; waited += 1000) {
  if (!(await page.locator("body").innerText()).includes("她在说话")) {
    spokeEnded = true;
    break;
  }
  await page.waitForTimeout(1000);
}
check("播报结束后「她在说话」已消失", spokeEnded, spokeEnded ? "speaking 状态已复位" : "40 秒内仍未复位");

// 验证停止按钮/关语音能中断
await page.locator("textarea").fill("再说一句试试");
await page.locator("textarea").press("Enter");
await page.waitForTimeout(3000);
await voiceBtn.first().click();
await page.waitForTimeout(1500);
const afterOff = await page.locator("body").innerText();
check("关语音后不再显示她在说话", !afterOff.includes("她在说话…"));

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await page.screenshot({ path: "tmp/streaming-voice.png" });
await browser.close();
process.exit(failed === 0 ? 0 : 1);
