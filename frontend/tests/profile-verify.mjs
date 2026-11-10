import { chromium } from "playwright";
import { pickAnyCompanion } from "./lib/fixtures.mjs";

const BASE = "http://127.0.0.1:8000";

/**
 * 登录用的手机号从环境变量读，不写进代码。
 *
 * 为什么：这会随仓库公开，而真实手机号一旦提交，即使之后删掉，
 * Git 历史里仍然留着。跑这套验收前先设：
 *   $env:AI_COMPANION_TEST_PHONE="你的号码"
 */
const PHONE = process.env.AI_COMPANION_TEST_PHONE ?? "";
if (!PHONE) {
  console.error("缺少 AI_COMPANION_TEST_PHONE 环境变量（用于登录的测试手机号）");
  process.exit(1);
}

async function loginCookie() {
  const codeResp = await fetch(`${BASE}/v1/auth/sms-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: PHONE }),
  });
  const { debug_code } = await codeResp.json();
  const loginResp = await fetch(`${BASE}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: PHONE, code: debug_code }),
  });
  const cookie = loginResp.headers.get("set-cookie") || "";
  return cookie.match(/ac_session=([^;]+)/)[1];
}

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 1100 } });
await ctx.addCookies([{ name: "ac_session", value: await loginCookie(), domain: "127.0.0.1", path: "/", httpOnly: true }]);
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(`${BASE}/me`, { waitUntil: "networkidle" });
const meBody = await page.locator("body").innerText();
console.log("我的页有“我的身份”:", meBody.includes("我的身份"));
console.log("回填昵称:", await page.locator("#up-nick-me").inputValue());
await page.screenshot({ path: "tmp/verify-profile-me.png", fullPage: true });

const anyId = await pickAnyCompanion(page);
if (!anyId) {
  console.log("SKIP 没有伴侣可用");
  await browser.close();
  process.exit(0);
}
await page.goto(`${BASE}/companions/${anyId}/persona`, { waitUntil: "networkidle" });
const personaBody = await page.locator("body").innerText();
console.log("人设页有“和她聊时的我”:", personaBody.includes("和她聊时的我"));
console.log("回填专属身份:", await page.locator("#up-identity-19").inputValue());
await page.screenshot({ path: "tmp/verify-profile-companion.png", fullPage: true });
console.log("JS 错误:", errors.length);

await browser.close();

