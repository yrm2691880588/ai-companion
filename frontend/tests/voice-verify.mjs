import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
}

const browser = await chromium.launch({
  ...(process.env.PW_CHANNEL === "none" ? {} : { channel: process.env.PW_CHANNEL || "chrome" }),
  headless: true,
  args: ["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 1100 },
  permissions: ["microphone"],
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

// 1) 语音设置卡片
await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
const settingsBody = await page.locator("body").innerText();
check("设置页有语音分区", settingsBody.includes("语音"));
check("有 AppID 输入", (await page.locator("#voice-appid").count()) > 0);
check("有 Token 输入", (await page.locator("#voice-token").count()) > 0);
check("有测试连接按钮", (await page.getByRole("button", { name: "测试连接" }).count()) > 0);

// 2) 教程
await page.getByRole("button", { name: /怎么拿到 AppID/ }).click();
await page.waitForTimeout(400);
const guide = await page.locator("body").innerText();
check("教程可展开", guide.includes("登录火山引擎控制台"));
check("教程写明要勾选的两项能力", guide.includes("豆包语音合成模型 2.0") && guide.includes("录音文件识别模型 2.0"));
check("教程给出 AppID 示例", guide.includes("4982965749"));
check("教程有控制台链接", (await page.getByRole("link", { name: "打开火山控制台" }).count()) > 0);
await page.screenshot({ path: "tmp/verify-voice-settings.png", fullPage: true });

// 3) 对话页语音按钮
await page.goto(`${BASE}/companions/19/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
const chatBody = await page.locator("body").innerText();
check("对话页有语音模式开关", chatBody.includes("语音模式"));
check("未配置时标注", chatBody.includes("语音未配置") || chatBody.includes("语音模式：关"));

// 4) 人设页音色：按当前是否已配置语音，断言对应状态
await page.goto(`${BASE}/companions/19/persona`, { waitUntil: "networkidle" });
const personaBody = await page.locator("body").innerText();
check("人设页有她的声音", personaBody.includes("她的声音"));
const voiceConfigured = await page.evaluate(async () => {
  const response = await fetch("/v1/voice/providers", { credentials: "same-origin" });
  if (!response.ok) return false;
  const list = await response.json();
  return list.some((item) => item.configured);
});
if (voiceConfigured) {
  check("已配置时显示音色选择", personaBody.includes("选一个音色"));
} else {
  check("未配置时提示去配置", personaBody.includes("还没有配置语音供应商"));
}
await page.screenshot({ path: "tmp/verify-voice-persona.png", fullPage: true });

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));
await browser.close();

const failed = results.filter((item) => !item.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
if (failed > 0) process.exit(1);

