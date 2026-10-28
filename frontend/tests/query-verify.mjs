import { chromium } from "playwright";
import assert from "node:assert/strict";

// 浏览器网络替身仅用于加载、错误和竞态验收，不写入真实用户数据。
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL === "none" ? undefined : "chrome", headless: true });
const base = "http://127.0.0.1:8000";
try {
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, serviceWorkers: "block" });
    let release;
    const held = new Promise(resolve => { release = resolve; });
    let requests = 0;
    await page.route("**/v1/companions", async route => {
      requests++;
      await held;
      await route.fulfill({ json: [] });
    });
    await page.goto(base);
    await page.locator(".skeleton-card").first().waitFor();
    await page.screenshot({ path: `tmp/query-loading-${width}.png`, fullPage: true });
    release();
    await page.getByRole("heading", { name: "还没有伴侣", exact: true }).waitFor();
    assert.equal(requests, 1);
    await page.screenshot({ path: `tmp/query-empty-${width}.png`, fullPage: true });
    await page.unroute("**/v1/companions");
    await page.route("**/v1/companions", async route => {
      requests++;
      await route.fulfill({ status: 503, json: { code: "TEST_UNAVAILABLE", message: "测试：服务不可用" } });
    });
    await page.reload({ waitUntil: "networkidle" });
    await page.getByText("测试：服务不可用", { exact: true }).waitFor();
    assert.equal(await page.getByRole("heading", { name: "还没有伴侣", exact: true }).count(), 0);
    assert.equal(requests, 2);
    await page.screenshot({ path: `tmp/query-error-${width}.png`, fullPage: true });
    await page.close();
    console.log(`PASS ${width}: 加载态、空态、错误态、无自动重试`);
  }
  const page = await browser.newPage({ serviceWorkers: "block" });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  let releaseOld;
  const heldOld = new Promise(resolve => { releaseOld = resolve; });
  let oldRequested;
  const oldStarted = new Promise(resolve => { oldRequested = resolve; });
  const now = new Date().toISOString();
  await page.route("**/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/companions/9101") return route.fulfill({ json: { id: 9101, name: "缓存验收", current_version: 1, persona: { name: "缓存验收", identity: "验收角色" } } });
    if (path.endsWith("/sessions")) return route.fulfill({ json: [9102, 9103].map(id => ({ id, companion_id: 9101, title: `会话${id}`, created_at: now })) });
    if (path === "/v1/sessions/9102/messages") { oldRequested(); await heldOld; }
    if (path.endsWith("/messages")) {
      const id = Number(path.split("/")[3]);
      return route.fulfill({ json: [{ id, session_id: id, seq: 1, role: "assistant", content: `消息${id}`, created_at: now }] });
    }
    if (path.endsWith("/summary")) return route.fulfill({ json: { summary: null } });
    if (path === "/v1/voice/providers") return route.fulfill({ json: [] });
    return route.continue();
  });
  await page.goto(`${base}/companions/9101/chat`);
  await oldStarted;
  const oldCancelled = page.waitForEvent("requestfailed", request => request.url().includes("/9102/messages"));
  await page.getByText("会话9103", { exact: true }).click();
  await page.getByText("消息9103", { exact: true }).waitFor();
  assert.match((await oldCancelled).failure().errorText, /ERR_ABORTED/);
  releaseOld();
  await page.waitForLoadState("networkidle");
  assert.equal(await page.getByText("消息9102", { exact: true }).count(), 0);
  await page.getByText("会话9102", { exact: true }).click();
  await page.getByText("消息9102", { exact: true }).waitFor();
  assert.equal(await page.getByText("消息9103", { exact: true }).count(), 0);
  assert.deepEqual(await page.locator(".alert").allTextContents(), []);
  assert.deepEqual(errors, []);
  console.log("PASS 会话切换：旧请求取消、新消息不被覆盖、缓存按会话隔离、无 JS 异常");
  await page.close();
} finally { await browser.close(); }
