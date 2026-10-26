import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
}

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });

const options = await page.locator(".admin-field select").first().locator("option").count();
check("模型下拉框有选项", options >= 2, `${options} 个选项`);

const providerCards = await page.locator(".grid .card").count();
check("供应商卡片渲染", providerCards >= 8, `${providerCards} 张`);

const missingCount = await page.getByText("未配置", { exact: true }).count();
check("供应商标注是否已配置", missingCount > 0, `${missingCount} 处未配置`);

// 切换模型并保存
const select = page.locator(".admin-field select").first();
await select.selectOption({ label: "DeepSeek V4 Pro" });
await page.getByRole("button", { name: "保存管理员设置" }).click();
await page.waitForTimeout(1200);
const saved = await page.evaluate(async () => {
  const response = await fetch("/v1/admin/settings", { credentials: "same-origin" });
  const data = await response.json();
  return data.settings.model_defaults.chat_main.model;
});
check("界面切换模型已保存", saved === "deepseek:deepseek-v4-pro", String(saved));

// 改回 Flash
await select.selectOption({ label: "DeepSeek V4.1 Flash" });
await page.getByRole("button", { name: "保存管理员设置" }).click();
await page.waitForTimeout(1200);
const restored = await page.evaluate(async () => {
  const response = await fetch("/v1/admin/settings", { credentials: "same-origin" });
  const data = await response.json();
  return data.settings.model_defaults.chat_main.model;
});
check("恢复默认模型", restored === "deepseek:deepseek-flash", String(restored));

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));
await page.screenshot({ path: "tmp/verify-model-switch.png", fullPage: true });
await browser.close();

const failed = results.filter((item) => !item.ok);
console.log(`\n共 ${results.length} 项，失败 ${failed.length} 项`);
if (failed.length > 0) process.exit(1);

