import { chromium } from "playwright";

/** 验证方案 A 的分工：我的/设置各管什么、设置页三个标签能否正常切换。 */

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox"],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

// --- 导航 ---
await page.goto(BASE, { waitUntil: "networkidle" });
const navText = await page.locator("nav").innerText();
check("导航有 4 项", navText.split("\n").filter(Boolean).length === 4, navText.replace(/\n/g, "/"));
check("导航有「设置」入口", navText.includes("设置"));

// --- 我的页：只放个人相关 ---
await page.goto(`${BASE}/me`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
const meBody = await page.locator("body").innerText();
check("我的页有我的身份", meBody.includes("我的身份"));
check("我的页有外观", meBody.includes("外观"));
check("我的页有数据导出", meBody.includes("导出我的数据"));
check("我的页有关于", meBody.includes("关于"));
check("我的页不再有模型参数区块", !meBody.includes("调整温度"));
check("我的页不再有供应商列表", !meBody.includes("可用供应商"));
check("我的页不再有用量统计", !meBody.includes("最近 7 天用量"));

// --- 设置页：三个标签 ---
await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const tabNames = await page.locator(".tab").allInnerTexts();
check("设置页有 3 个标签", tabNames.length === 3, tabNames.join("/"));
check("标签名正确", tabNames.join("/") === "模型与用量/语音与设备/供应商", tabNames.join("/"));

// 默认在模型标签
let body = await page.locator("body").innerText();
check("默认显示模型参数", body.includes("日常对话"));
check("默认显示用量", body.includes("最近 7 天用量"));
check("模型标签不显示语音配置", !body.includes("Access Token"));

// 切到语音
await page.locator(".tab").nth(1).click();
await page.waitForTimeout(800);
body = await page.locator("body").innerText();
check("语音标签显示火山配置", body.includes("Access Token"));
check("语音标签显示麦克风", body.includes("输入设备"));
check("语音标签不显示模型参数", !body.includes("日常对话"));

// 切到供应商
await page.locator(".tab").nth(2).click();
await page.waitForTimeout(800);
body = await page.locator("body").innerText();
check("供应商标签显示供应商卡片", body.includes("DeepSeek"));
check("供应商标签不显示麦克风", !body.includes("输入设备"));

// 标签可访问性
const selected = await page.locator('.tab[aria-selected="true"]').innerText();
check("选中标签有 aria-selected", selected === "供应商", selected);

// --- 页面高度（拆分后的收益）---
await page.locator(".tab").nth(0).click();
await page.waitForTimeout(500);
const modelHeight = await page.evaluate(() => document.body.scrollHeight);
await page.screenshot({ path: "tmp/ui-audit/settings-tab-model.png", fullPage: true });
await page.locator(".tab").nth(1).click();
await page.waitForTimeout(500);
const voiceHeight = await page.evaluate(() => document.body.scrollHeight);
await page.screenshot({ path: "tmp/ui-audit/settings-tab-voice.png", fullPage: true });
check("模型标签页面变短（原约 2300px）", modelHeight < 1600, `${modelHeight}px`);
check("语音标签页面变短", voiceHeight < 1600, `${voiceHeight}px`);

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await browser.close();
process.exit(failed === 0 ? 0 : 1);
