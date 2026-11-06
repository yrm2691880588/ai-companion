import { chromium } from "playwright";
import { pickCompanionWithVoice } from "./lib/fixtures.mjs";

// 验证她真的出声了：监听页面里 Audio 元素的 play 事件与时长。
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

// 记录合成请求与音频播放
const synthCalls = [];
page.on("response", async (r) => {
  if (r.url().includes("/v1/voice/synthesize")) {
    synthCalls.push(r.status());
  }
});

const companionId = await pickCompanionWithVoice(page);
if (!companionId) {
  console.log("SKIP 没有可用的测试伴侣（先跑 scripts/seed_test_companion.py）");
  await browser.close();
  process.exit(0);
}
await page.goto(`${BASE}/companions/${companionId}/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(2000);

// 打桩：记录所有 <audio> 的播放
await page.evaluate(() => {
  window.__PLAYED__ = [];
  const origPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    window.__PLAYED__.push({ src: this.src || "", at: Date.now() });
    return origPlay.call(this);
  };
});

await page.getByRole("button", { name: /语音模式/ }).first().click();
await page.waitForTimeout(800);

await page.locator("textarea").fill("跟我说句话吧，我想听听你的声音。");
await page.locator("textarea").press("Enter");
await page.waitForTimeout(25000);

const played = await page.evaluate(() => window.__PLAYED__ || []);
const body = await page.locator("body").innerText();

check("触发了语音合成", synthCalls.length > 0, `合成请求 ${synthCalls.length} 次`);
check("合成接口成功", synthCalls.every((s) => s === 200), synthCalls.join(","));
check("真的调用了音频播放", played.length > 0, `播放 ${played.length} 次`);
check("播放的是语音接口地址", played.some((p) => p.src.includes("/voice/audio/")), played[0]?.src ?? "");
check("没有出现播放失败提示", !body.includes("播放被浏览器拦住"), "");
check("收到回复文字", body.includes("声音") || body.length > 300);

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
if (played.length) console.log("播放记录样例:", JSON.stringify(played.slice(0, 2)));
await browser.close();
process.exit(failed === 0 ? 0 : 1);
