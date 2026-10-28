import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const BASE = "http://127.0.0.1:8000";
// 用真实语音文件作为假麦克风的输入：Chrome 支持 --use-file-for-fake-audio-capture
// 需要 WAV 格式
const audioFile = process.argv[2] || "tmp/mic.wav";

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: [
    "--no-sandbox",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${audioFile}`,
  ],
});
const context = await browser.newContext({ permissions: ["microphone"] });
const page = await context.newPage();
const logs = [];
page.on("console", (m) => logs.push(m.text().slice(0, 120)));

await page.goto(`${BASE}/companions/19/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByRole("button", { name: /语音模式/ }).first().click();
await page.waitForTimeout(500);

const before = await page.locator(".bubble").count();
await page.getByRole("button", { name: /🎤 说话/ }).first().click();
// 等待 VAD 初始化 + 一句话说完 + 识别 + 发送
await page.waitForTimeout(22000);
const after = await page.locator(".bubble").count();
const body = await page.locator("body").innerText();
const err = await page.locator(".voice-error").count();
console.log("气泡:", before, "→", after);
console.log("有语音错误提示:", err > 0 ? await page.locator(".voice-error").first().innerText() : "无");
console.log("最后一条消息:", (await page.locator(".bubble").last().innerText().catch(() => "")).slice(0, 80).replace(/\n/g, " "));
console.log("VAD 日志:", logs.filter((l) => l.includes("VAD")).slice(-3).join(" | "));
await page.screenshot({ path: "tmp/vad-real-audio.png" });
await browser.close();
