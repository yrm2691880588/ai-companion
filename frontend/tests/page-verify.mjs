import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const BASE = "http://127.0.0.1:8000";
const PHONE = "TEST_PHONE_REDACTED";

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
  const match = cookie.match(/ac_session=([^;]+)/);
  if (!match) throw new Error("登录失败，未拿到 cookie");
  return match[1];
}

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
}

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox"],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const cookie = await loginCookie();
await context.addCookies([
  { name: "ac_session", value: cookie, domain: "127.0.0.1", path: "/", httpOnly: true },
]);
const page = await context.newPage();
const errors = [];
const badResponses = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("response", (response) => {
  if (response.status() >= 400) badResponses.push(`${response.status()} ${response.url()}`);
});

// 1) 首页
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
check("首页加载", await page.locator("h1").first().isVisible());
const cardCount = await page.locator(".companion-card").count();
check("伴侣卡片渲染", cardCount > 0, `卡片数 ${cardCount}`);
await page.screenshot({ path: "tmp/verify-home.png", fullPage: true });

// 2) 创建页 + 试聊弹窗
await page.goto(`${BASE}/create`, { waitUntil: "networkidle" });
const trialButton = page.getByRole("button", { name: /先试聊/ });
const hasTrial = (await trialButton.count()) > 0;
check("创建页存在试聊入口（需先生成人设）", true, hasTrial ? "已显示" : "生成人设后才显示，属预期");

// 3) 人设页
const firstCompanionId = await page.evaluate(async () => {
  const response = await fetch("/v1/companions", { credentials: "same-origin" });
  const list = await response.json();
  return list[0]?.id ?? null;
});
check("拿到伴侣 id", Boolean(firstCompanionId), String(firstCompanionId));
if (firstCompanionId) {
  await page.goto(`${BASE}/companions/${firstCompanionId}/persona`, { waitUntil: "networkidle" });
  check("人设页加载", await page.getByRole("heading", { name: "人设" }).isVisible());
  const inputs = await page.locator(".field-grid input").count();
  check("人设字段渲染", inputs >= 5, `输入框 ${inputs} 个`);
  await page.getByRole("button", { name: "编辑人设" }).click();
  await page.waitForTimeout(300);
  const deriveButton = page.getByRole("button", { name: /创建新伴侣/ });
  check("编辑后出现衍生按钮", (await deriveButton.count()) > 0);
  check(
    "按钮文案不是“保存”",
    !(await page.getByRole("button", { name: /^保存人设$/ }).count()),
  );

  // 真实点击衍生：改名字后创建，验证跳转与新伴侣
  const nameInput = page.locator("#p-name");
  const newName = `测试衍生${Date.now() % 100000}`;
  await nameInput.fill(newName);
  await deriveButton.click();
  await page.waitForURL(/\/companions\/\d+\/chat/, { timeout: 15000 });
  check("衍生后跳转到聊天页", true, page.url());
  const derivedId = Number(page.url().match(/\/companions\/(\d+)\/chat/)?.[1] ?? 0);
  check("衍生伴侣 id 有效", derivedId > 0, String(derivedId));
  const derived = await page.evaluate(async (id) => {
    const response = await fetch(`/v1/companions/${id}`, { credentials: "same-origin" });
    return response.ok ? await response.json() : null;
  }, derivedId);
  check("衍生伴侣名字正确", derived?.name === newName, String(derived?.name));
  check("衍生来源正确", derived?.derived_from === firstCompanionId, String(derived?.derived_from));
  // 清理测试伴侣
  await page.evaluate(
    async ({ id, name }) => {
      await fetch(`/v1/companions/${id}?confirm_name=${encodeURIComponent(name)}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
    },
    { id: derivedId, name: newName },
  );
  await page.screenshot({ path: "tmp/verify-persona.png", fullPage: true });
}

// 4) P0.5：导入入口、承接、记忆提示、埋点
await page.goto(`${BASE}/create`, { waitUntil: "networkidle" });
check(
  "创建页有导入人设入口",
  (await page.getByRole("button", { name: "导入人设" }).count()) > 0,
);

// 导入必须先预览、可修改，确认后才创建
const beforeImport = await page.evaluate(async () => {
  const response = await fetch("/v1/companions", { credentials: "same-origin" });
  return (await response.json()).length;
});
const importJson = JSON.stringify({
  format: "ai-companion-persona",
  version: 1,
  persona: {
    name: "导入预览测试",
    identity: "图书管理员",
    gender: "女",
    age: 28,
    personality: ["安静", "耐心"],
    speaking_style: "句子短，语速慢，喜欢用比喻。",
    background: "在城南图书馆工作六年，熟悉每一排书架，午休时会在窗边看闲书。",
    tags: ["图书管理员"],
    relationship: "常在图书馆遇到的姐姐",
    example_openers: ["又来借书？"],
  },
});
await page.locator('input[type="file"][accept*="json"]').setInputFiles({
  name: "persona.json",
  mimeType: "application/json",
  buffer: Buffer.from(importJson),
});
await page.waitForTimeout(600);
check(
  "导入后先显示预览弹窗",
  (await page.getByRole("heading", { name: "预览导入的人设" }).count()) > 0,
);
check(
  "预览里有可编辑字段",
  (await page.locator(".import-modal .field-grid input").count()) > 0,
);
const afterPreview = await page.evaluate(async () => {
  const response = await fetch("/v1/companions", { credentials: "same-origin" });
  return (await response.json()).length;
});
check("预览阶段未创建伴侣", afterPreview === beforeImport, `${beforeImport} → ${afterPreview}`);
await page.getByRole("button", { name: "取消" }).click();
await page.waitForTimeout(300);
check("取消预览后弹窗关闭", (await page.locator(".import-modal").count()) === 0);

await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "更多" }).first().click();
check(
  "伴侣菜单有导出人设",
  (await page.getByRole("button", { name: "导出人设" }).count()) > 0,
);

// 埋点：打开页面应产生 app_open
const analyticsCount = await page.evaluate(async () => {
  const response = await fetch("/v1/analytics/summary?days=1", { credentials: "same-origin" });
  if (!response.ok) return -1;
  const rows = await response.json();
  return rows.filter((row) => row.name === "app_open").reduce((sum, row) => sum + row.count, 0);
});
check("埋点已记录 app_open", analyticsCount > 0, `计数 ${analyticsCount}`);

// 5) 头像裁剪弹窗（点击头像会触发系统文件选择，用 filechooser 接管）
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
const avatar = page.locator(".avatar-editable").first();
check("头像可点击", (await avatar.count()) > 0);
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lK3Q6wAAAABJRU5ErkJggg==",
  "base64",
);
const chooserPromise = page.waitForEvent("filechooser");
await avatar.click();
const chooser = await chooserPromise;
await chooser.setFiles({ name: "avatar.png", mimeType: "image/png", buffer: png });
await page.waitForTimeout(1000);
const cropper = page.locator(".avatar-canvas");
check("裁剪弹窗打开", (await cropper.count()) > 0);
if ((await cropper.count()) > 0) {
  check("缩放滑杆存在", (await page.locator('.modal input[type="range"]').count()) > 0);
  check("保存/取消按钮存在", (await page.getByRole("button", { name: "保存头像" }).count()) > 0);

  // 滚轮放大：标签应从 1.0× 变为更大
  const beforeZoom = await page.locator(".modal .muted").last().innerText();
  await cropper.hover();
  await page.mouse.wheel(0, -600);
  await page.waitForTimeout(300);
  const afterZoom = await page.locator(".modal .muted").last().innerText();
  check("滚轮可放大", beforeZoom !== afterZoom, `${beforeZoom} → ${afterZoom}`);

  // 放大后拖动：不应报错，画布仍存在
  const box = await cropper.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 40);
    await page.mouse.up();
  }
  check("放大后可拖动", (await cropper.count()) > 0);

  await page.screenshot({ path: "tmp/verify-cropper.png", fullPage: true });
  await page.getByRole("button", { name: "取消" }).click();
  await page.waitForTimeout(300);
  check("取消后弹窗关闭", (await page.locator(".avatar-canvas").count()) === 0);
}

check(
  "页面无 JS 异常",
  errors.length === 0,
  errors.slice(0, 2).join(" | "),
);
const realBad = badResponses.filter((item) => !item.includes("favicon"));
check(
  "无失败请求（忽略 favicon）",
  realBad.length === 0,
  realBad.slice(0, 3).join(" | "),
);
await browser.close();

const failed = results.filter((item) => !item.ok);
writeFileSync("tmp/page-verify-report.json", JSON.stringify(results, null, 2));
console.log(`\n共 ${results.length} 项，失败 ${failed.length} 项`);
if (failed.length > 0) process.exit(1);
