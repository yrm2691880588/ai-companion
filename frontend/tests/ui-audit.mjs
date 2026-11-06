import { chromium } from "playwright";

/** 逐页截图，用于界面体检。同时收集 JS 错误与横向溢出。 */

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox"],
});

const pages = [
  { path: "/", name: "01-companions" },
  { path: "/create", name: "02-create" },
  { path: "/me", name: "03-me" },
  { path: "/settings", name: "04-settings" },
];

// 动态取一个伴侣，用于详情页
const probe = await browser.newPage();
await probe.goto(BASE, { waitUntil: "domcontentloaded" });
const companionId = await probe.evaluate(async () => {
  const response = await fetch("/v1/companions");
  const list = await response.json();
  const withVoice = list.find((c) => c.voice_id);
  return (withVoice ?? list[0])?.id ?? null;
});
await probe.close();

if (companionId) {
  pages.push(
    { path: `/companions/${companionId}/chat`, name: "05-chat" },
    { path: `/companions/${companionId}/persona`, name: "06-persona" },
    { path: `/companions/${companionId}/memories`, name: "07-memories" },
    { path: `/companions/${companionId}/roleplay`, name: "08-roleplay" },
  );
}

const report = [];

for (const width of [1280, 390]) {
  const context = await browser.newContext({
    viewport: { width, height: width === 390 ? 844 : 900 },
    isMobile: width === 390,
    hasTouch: width === 390,
  });
  for (const item of pages) {
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message.slice(0, 100)));
    await page.goto(BASE + item.path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);

    const metrics = await page.evaluate(() => {
      const doc = document.documentElement;
      return {
        // 横向溢出：移动端最常见的布局问题
        overflowX: doc.scrollWidth > doc.clientWidth + 1,
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        // 触控目标尺寸：小于 44px 在手机上很难点
        smallTargets: [...document.querySelectorAll("button, a.btn, input, select")]
          .filter((el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && (r.height < 32 || r.width < 32);
          })
          .map((el) => `${el.tagName}:${(el.textContent || "").trim().slice(0, 12)}`)
          .slice(0, 5),
        title: document.querySelector("h1")?.textContent?.trim() ?? "",
        bodyLength: document.body.innerText.length,
      };
    });

    await page.screenshot({
      path: `tmp/ui-audit/${item.name}-${width}.png`,
      fullPage: true,
    });

    report.push({
      page: item.name,
      width,
      ...metrics,
      errors: errors.length,
    });
    await page.close();
  }
  await context.close();
}

console.log("页面 | 宽 | 横向溢出 | 过小目标 | 标题 | JS错误");
console.log("---");
for (const r of report) {
  console.log(
    `${r.page} | ${r.width} | ${r.overflowX ? "❌溢出" : "ok"} | ${
      r.smallTargets.length ? r.smallTargets.join(",") : "-"
    } | ${r.title || "-"} | ${r.errors}`,
  );
}

const problems = report.filter((r) => r.overflowX || r.smallTargets.length > 0 || r.errors > 0);
console.log(`\n有问题的页面组合: ${problems.length} / ${report.length}`);
await browser.close();
