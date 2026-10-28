import { chromium } from "playwright";
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const BASE = "http://127.0.0.1:8000";
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
}

// 生成一张测试图片（纯色 PNG）
const pngPath = "tmp/test-avatar.png";
if (!existsSync(pngPath)) {
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFElEQVR42mP8z8Dwn4GBgYERAE4kAP5QDf9eAAAAAElFTkSuQmCC",
    "base64",
  );
  writeFileSync(pngPath, png);
}

const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "更多" }).first().click();
await page.waitForTimeout(400);
await page.getByRole("button", { name: "换头像" }).count().catch(() => 0);

// 通过隐藏的 file input 触发
const fileChooser = page.waitForEvent("filechooser", { timeout: 5000 }).catch(() => null);
const uploadTrigger = page.locator('input[type="file"][accept*="image"]').first();
if ((await uploadTrigger.count()) > 0) {
  await uploadTrigger.setInputFiles(pngPath);
} else {
  const chooser = await fileChooser;
  if (chooser) await chooser.setFiles(pngPath);
}

await page.waitForTimeout(1500);
const modalCount = await page.locator(".modal").count();
check("裁剪弹窗打开", modalCount > 0);
check("使用 react-easy-crop", (await page.locator(".reactEasyCrop_Container").count()) > 0);

if (modalCount > 0) {
  check("裁剪框是圆形", (await page.locator(".reactEasyCrop_CropAreaRound").count()) > 0);

  // 滚轮缩放
  const label = page.locator(".modal label.muted").first();
  const before = await label.innerText();
  const box = await page.locator(".reactEasyCrop_Container").boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -400);
  }
  await page.waitForTimeout(600);
  const after = await label.innerText();
  check("滚轮可缩放", before !== after, `${before} → ${after}`);

  // 拖动
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 50, box.y + box.height / 2 + 30);
    await page.mouse.up();
  }
  await page.waitForTimeout(400);
  check("可拖动且无报错", errors.length === 0, errors.slice(0, 1).join(""));

  await page.screenshot({ path: "tmp/verify-cropper-new.png", fullPage: true });

  // 保存
  await page.getByRole("button", { name: "保存头像" }).click();
  await page.waitForTimeout(2500);
  check("保存后弹窗关闭", (await page.locator(".modal").count()) === 0);
}

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));
await browser.close();

const failed = results.filter((item) => !item.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
if (failed > 0) process.exit(1);

