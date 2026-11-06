import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox", "--use-fake-ui-for-media-stream"],
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 1000 },
  permissions: ["microphone"],
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

await page.goto(`${BASE}/settings`, { waitUntil: "networkidle" });
await page.waitForTimeout(3000);

const body = await page.locator("body").innerText();
check("设置页有「麦克风」区块", body.includes("麦克风"));
check("有输入设备下拉框", (await page.locator("#mic-device").count()) > 0);

// 下拉框默认应是「跟随系统默认」
const defaultValue = await page.locator("#mic-device").inputValue().catch(() => "(无)");
check("默认值是跟随系统", defaultValue === "", `实际值: "${defaultValue}"`);

// 选项应包含「跟随系统默认」且列出设备
const options = await page.locator("#mic-device option").allInnerTexts();
check("有「跟随系统默认」选项", options.some((o) => o.includes("跟随系统")), options.join(" / "));
check("列出了实际设备", options.length > 1, `共 ${options.length} 项`);

// 试音按钮
check("有试音按钮", (await page.getByRole("button", { name: /试音/ }).count()) > 0);
check("有刷新设备按钮", (await page.getByRole("button", { name: /刷新设备/ }).count()) > 0);

// 点击试音，应出现电平条与提示
await page.getByRole("button", { name: /试音/ }).first().click();
await page.waitForTimeout(2500);
const afterTest = await page.locator("body").innerText();
check("试音后出现电平提示", afterTest.includes("峰值"), "");
check("试音后给出可用性判断", /几乎没声音|声音很弱|能录到声音/.test(afterTest));

// 选择设备后应写入 localStorage
const firstDevice = options.length > 1 ? await page.locator("#mic-device option").nth(1).getAttribute("value") : null;
if (firstDevice) {
  await page.locator("#mic-device").selectOption(firstDevice);
  await page.waitForTimeout(500);
  const saved = await page.evaluate(() => localStorage.getItem("ai-companion-mic-device"));
  check("选择后写入 localStorage", saved === firstDevice, `保存值: ${saved?.slice(0, 10)}`);

  // 刷新页面后应保持选择
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  const afterReload = await page.locator("#mic-device").inputValue();
  check("刷新后仍保持选择", afterReload === firstDevice);

  // 选回跟随系统
  await page.locator("#mic-device").selectOption("");
  await page.waitForTimeout(400);
  const cleared = await page.evaluate(() => localStorage.getItem("ai-companion-mic-device"));
  check("选回跟随后清除保存值", cleared === null);
}

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await page.screenshot({ path: "tmp/mic-settings.png", fullPage: true });
await browser.close();
process.exit(failed === 0 ? 0 : 1);
