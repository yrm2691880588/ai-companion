import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
const body = await page.locator("body").innerText();
console.log("有配置按钮:", body.includes("配置 Key"));
console.log("有未配置标记:", body.includes("未配置"));
console.log("配置按钮数:", await page.getByRole("button", { name: /配置 Key|修改配置/ }).count());

await page.getByRole("button", { name: /配置 Key|修改配置/ }).first().click();
await page.waitForTimeout(500);
const modal = await page.locator(".modal").innerText();
console.log("弹窗有 API Key:", modal.includes("API Key"));
console.log("弹窗有 Base URL:", modal.includes("Base URL"));
console.log("弹窗有启用开关:", modal.includes("启用这个供应商"));
await page.screenshot({ path: "tmp/verify-provider-config.png", fullPage: true });
await page.getByRole("button", { name: "取消" }).click();
console.log("JS 错误:", errors.length);
await browser.close();
