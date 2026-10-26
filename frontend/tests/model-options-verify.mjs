import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });

const selects = page.locator(".admin-field select");
const count = await selects.count();
console.log("下拉数量:", count);

for (let index = 0; index < count; index++) {
  const options = await selects.nth(index).locator("option").allInnerTexts();
  console.log(`下拉 ${index}:`, options.join(" / "));
}

const body = await page.locator("body").innerText();
const leaked = ["通义千问", "Kimi", "GLM", "OpenAI"].filter((name) => body.includes(name));
console.log("供应商卡片仍展示未配置的:", leaked.length > 0, leaked.join(","));
console.log("JS 错误:", errors.length);

await page.screenshot({ path: "tmp/verify-model-options.png", fullPage: true });
await browser.close();
