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

// 1) 删除确认弹窗：焦点陷阱 + Esc 关闭
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "更多" }).first().click();
await page.waitForTimeout(300);
await page.getByRole("button", { name: "删除" }).first().click();
await page.waitForTimeout(500);

const dialog = page.getByRole("dialog");
check("弹窗有 dialog 语义", (await dialog.count()) > 0);
check("弹窗有标题语义", (await page.getByRole("heading", { name: /删除「/ }).count()) > 0);

// 焦点是否在弹窗内
const focusInDialog = await page.evaluate(() => {
  const node = document.querySelector('[role="dialog"]');
  return Boolean(node && node.contains(document.activeElement));
});
check("打开后焦点进入弹窗", focusInDialog);

// Tab 多次后焦点仍应在弹窗内
let stayed = true;
for (let i = 0; i < 8; i++) {
  await page.keyboard.press("Tab");
  const inside = await page.evaluate(() => {
    const node = document.querySelector('[role="dialog"]');
    return Boolean(node && node.contains(document.activeElement));
  });
  if (!inside) {
    stayed = false;
    break;
  }
}
check("Tab 焦点被锁在弹窗内", stayed);

// Esc 关闭
await page.keyboard.press("Escape");
await page.waitForTimeout(500);
check("Esc 可关闭弹窗", (await page.locator('[role="dialog"]').count()) === 0);

// 2) 语音配置弹窗仍然可用
await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: /配置 Key|修改配置/ }).first().click();
await page.waitForTimeout(500);
check("供应商弹窗可打开", (await page.locator('[role="dialog"]').count()) > 0);
const modalText = await page.locator('[role="dialog"]').innerText();
check("供应商弹窗内容完整", modalText.includes("API Key") && modalText.includes("Base URL"));
await page.screenshot({ path: "tmp/verify-modal-radix.png", fullPage: true });
await page.keyboard.press("Escape");
await page.waitForTimeout(400);
check("供应商弹窗可关闭", (await page.locator('[role="dialog"]').count()) === 0);

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));
await browser.close();

const failed = results.filter((item) => !item.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
if (failed > 0) process.exit(1);
