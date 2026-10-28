import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: [
    "--no-sandbox",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
  ],
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 950 },
  permissions: ["microphone"],
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

await page.goto(`${BASE}/companions/19/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

// 开语音模式
const toggle = page.getByRole("button", { name: /语音模式/ });
const hasToggle = (await toggle.count()) > 0;
console.log("语音模式开关:", hasToggle);
if (hasToggle) {
  await toggle.first().click();
  await page.waitForTimeout(800);
  const micButton = page.getByRole("button", { name: /🎤 说话/ });
  console.log("有说话按钮:", (await micButton.count()) > 0);
  if ((await micButton.count()) > 0) {
    await micButton.first().click();
    // VAD 初始化需要下载 2.3MB 模型 + wasm，给足时间
    await page.waitForTimeout(15000);
    const body = await page.locator("body").innerText();
    const listening = body.includes("说完自动发送");
    const meter = (await page.locator(".voice-meter").count()) > 0;
    console.log("VAD 进入监听态:", listening);
    console.log("音量条出现:", meter);
    // 检查是否有错误提示
    const errText = await page.locator(".voice-error").count();
    if (errText > 0) {
      console.log("错误提示:", await page.locator(".voice-error").first().innerText());
    }
  }
}
console.log("JS 错误:", errors.length, errors.slice(0, 2).join(" | "));
await page.screenshot({ path: "tmp/verify-vad.png" });
await browser.close();
