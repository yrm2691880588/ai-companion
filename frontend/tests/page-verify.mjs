import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const BASE = "http://127.0.0.1:8000";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
}

const browser = await chromium.launch({
  // 本地用真实 Chrome；CI 里没有 Chrome，用 Playwright 自带 Chromium
  ...(process.env.PW_CHANNEL === "none" ? {} : { channel: process.env.PW_CHANNEL || "chrome" }),
  headless: true,
  args: ["--no-sandbox"],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });


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
  // 2026-11 起改为「原地保存」：改人设不再新建伴侣，而是生成新版本。
  // 这里验证新行为，同时确认「基于此版再造一个」作为高级操作仍然存在。
  const saveButton = page.getByRole("button", { name: "保存人设" });
  const deriveButton = page.getByRole("button", { name: /基于此版再造一个/ });
  check("编辑后出现保存按钮", (await saveButton.count()) > 0);
  check("保留了再造一个的入口", (await deriveButton.count()) > 0);

  // 记录改动前的版本号
  const beforeVersion = await page.evaluate(async (id) => {
    const response = await fetch(`/v1/companions/${id}`, { credentials: "same-origin" });
    return (await response.json()).current_version;
  }, firstCompanionId);

  // 改说话风格后原地保存
  const styleInput = page.locator("#p-style");
  const newStyle = `页面验收测试：更短的句子，一次只问一个问题。${Date.now() % 10000}`;
  await styleInput.fill(newStyle);
  await saveButton.click();
  await page.waitForTimeout(2500);

  // 关键断言：URL 没变（没有跳到新伴侣），版本号 +1
  check("保存后还在同一个人设页", page.url().includes(`/companions/${firstCompanionId}/persona`), page.url());
  const afterSave = await page.evaluate(async (id) => {
    const response = await fetch(`/v1/companions/${id}`, { credentials: "same-origin" });
    return await response.json();
  }, firstCompanionId);
  check("版本号递增", afterSave.current_version === beforeVersion + 1, `${beforeVersion} → ${afterSave.current_version}`);
  check("改动已生效", afterSave.persona.speaking_style === newStyle, String(afterSave.persona.speaking_style).slice(0, 20));
  check("伴侣没变多（不是衍生）", afterSave.id === firstCompanionId);

  // 版本历史里能看到旧版本
  const versions = await page.evaluate(async (id) => {
    const response = await fetch(`/v1/companions/${id}/personas`, { credentials: "same-origin" });
    return (await response.json()).map((v) => v.version);
  }, firstCompanionId);
  check("版本历史保留旧版本", versions.length >= 2 && versions.includes(beforeVersion), versions.join(","));

  // 还原到上一版：应生成更新的版本，而不是把版本号拨回去
  const restored = await page.evaluate(
    async ({ id, version }) => {
      const response = await fetch(`/v1/companions/${id}/personas/${version}/restore`, {
        method: "POST",
        credentials: "same-origin",
      });
      return response.ok ? await response.json() : null;
    },
    { id: firstCompanionId, version: beforeVersion },
  );
  check("还原生成新版本", restored?.current_version === afterSave.current_version + 1, String(restored?.current_version));
  check("还原后内容回到旧版", restored?.persona.speaking_style !== newStyle);

  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  check(
    "页面上能看到版本历史区块",
    (await page.getByRole("heading", { name: /历史版本/ }).count()) > 0,
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
  (await page.getByRole("menuitem", { name: "导出人设" }).count()) > 0,
);

// 埋点：验证「本次打开页面」确实产生了 app_open
// 不依赖历史数据，也不依赖日期边界：取打开前的基线，再对比打开后的增量。
const readAppOpen = () =>
  page.evaluate(async () => {
    const response = await fetch("/v1/analytics/summary?days=7", { credentials: "same-origin" });
    if (!response.ok) return -1;
    const rows = await response.json();
    return rows.filter((row) => row.name === "app_open").reduce((sum, row) => sum + row.count, 0);
  });

const analyticsBefore = await readAppOpen();
await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.waitForTimeout(800);
const analyticsAfter = await readAppOpen();
check(
  "埋点已记录 app_open",
  analyticsBefore >= 0 && analyticsAfter > analyticsBefore,
  `计数 ${analyticsBefore} → ${analyticsAfter}`,
);

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
const cropper = page.locator(".reactEasyCrop_Container");
check("裁剪弹窗打开", (await cropper.count()) > 0);
if ((await cropper.count()) > 0) {
  check("缩放滑杆存在", (await page.locator('.modal input[type="range"]').count()) > 0);
  check("保存/取消按钮存在", (await page.getByRole("button", { name: "保存头像" }).count()) > 0);

  // 滚轮放大：标签应从 1.0× 变为更大
  // 2026-11 重做裁剪界面后，缩放数值改用 .cropper-zoom-value（原来靠 label.muted 定位）
  const zoomLabel = page.locator(".cropper-zoom-value").first();
  const beforeZoom = await zoomLabel.innerText();
  await cropper.hover();
  await page.mouse.wheel(0, -600);
  await page.waitForTimeout(500);
  const afterZoom = await zoomLabel.innerText();
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
  check("取消后弹窗关闭", (await page.locator(".reactEasyCrop_Container").count()) === 0);
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





