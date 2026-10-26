import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });

// 打开 DeepSeek 的配置弹窗（已配置 Key）
await page.getByRole("button", { name: "修改配置" }).first().click();
await page.waitForTimeout(400);
console.log("弹窗有搜索按钮:", await page.getByRole("button", { name: /搜索该供应商/ }).count());
await page.getByRole("button", { name: /搜索该供应商/ }).click();
await page.waitForTimeout(4000);
const body = await page.locator(".modal").innerText();
console.log("显示找到模型:", body.includes("找到"));
console.log("包含 deepseek-flash:", body.includes("deepseek-flash"));
await page.screenshot({ path: "tmp/verify-model-discovery.png", fullPage: true });
await page.getByRole("button", { name: "取消" }).click();

// 无 Key 的供应商应提示先配置
await page.getByRole("button", { name: "配置 Key" }).first().click();
await page.waitForTimeout(400);
await page.getByRole("button", { name: /搜索该供应商/ }).click();
await page.waitForTimeout(2500);
const noKeyBody = await page.locator(".modal").innerText();
console.log("无 Key 提示:", noKeyBody.includes("请先配置 API Key"));
await page.getByRole("button", { name: "取消" }).click();
console.log("JS 错误:", errors.length);
await browser.close();
