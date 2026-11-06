import { chromium } from "playwright";
import { pickCompanionWithVoice } from "./lib/fixtures.mjs";

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

await page.goto(`${BASE}/`, { waitUntil: "networkidle" });

// 1) 伴侣卡片菜单：可打开、含全部条目
const moreButton = page.getByRole("button", { name: /更多操作|更多/ }).first();
await moreButton.click();
await page.waitForTimeout(400);
const menu = page.getByRole("menu");
check("菜单可打开", (await menu.count()) > 0);
const menuText = await menu.innerText().catch(() => "");
check("菜单含人设", menuText.includes("人设"));
check("菜单含导出人设", menuText.includes("导出人设"));
check("菜单含记忆", menuText.includes("记忆"));
check("菜单含演练", menuText.includes("演练"));
check("菜单含删除", menuText.includes("删除"));

// 2) 键盘可用：方向键高亮，Esc 关闭
await page.keyboard.press("ArrowDown");
await page.waitForTimeout(200);
const highlighted = await page.locator('[data-highlighted]').count();
check("方向键可高亮菜单项", highlighted > 0);

await page.keyboard.press("Escape");
await page.waitForTimeout(400);
check("Esc 可关闭菜单", (await page.getByRole("menu").count()) === 0);

// 3) 聊天页头部菜单
const companionId = await pickCompanionWithVoice(page);
if (!companionId) {
  console.log("SKIP 没有可用的测试伴侣（先跑 scripts/seed_test_companion.py）");
  await browser.close();
  process.exit(0);
}
await page.goto(`${BASE}/companions/${companionId}/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByRole("button", { name: "更多操作" }).first().click();
await page.waitForTimeout(400);
const headerMenu = page.getByRole("menu");
check("聊天页菜单可打开", (await headerMenu.count()) > 0);
const headerText = await headerMenu.innerText().catch(() => "");
check("聊天页菜单含她记得的事", headerText.includes("她记得的事"));
check("聊天页菜单含场景演练", headerText.includes("场景演练"));
await page.screenshot({ path: "tmp/verify-menu-radix.png" });

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));
await browser.close();

const failed = results.filter((item) => !item.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
if (failed > 0) process.exit(1);

