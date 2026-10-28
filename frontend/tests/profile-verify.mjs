import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";

async function loginCookie() {
  const codeResp = await fetch(`${BASE}/v1/auth/sms-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: "TEST_PHONE_REDACTED" }),
  });
  const { debug_code } = await codeResp.json();
  const loginResp = await fetch(`${BASE}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: "TEST_PHONE_REDACTED", code: debug_code }),
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

await page.goto(`${BASE}/companions/19/persona`, { waitUntil: "networkidle" });
const personaBody = await page.locator("body").innerText();
console.log("人设页有“和她聊时的我”:", personaBody.includes("和她聊时的我"));
console.log("回填专属身份:", await page.locator("#up-identity-19").inputValue());
await page.screenshot({ path: "tmp/verify-profile-companion.png", fullPage: true });
console.log("JS 错误:", errors.length);

await browser.close();

