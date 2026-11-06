import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox"],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 950 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

// 批量删除要验证「勾选多个 → 一次删掉」，至少需要 3 个伴侣。
// 数据不够时用接口补齐，避免测试依赖库里恰好剩多少。
await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const seeded = await page.evaluate(async () => {
  const list = await (await fetch("/v1/companions")).json();
  const need = Math.max(0, 3 - list.length);
  const created = [];
  for (let i = 0; i < need; i += 1) {
    const response = await fetch("/v1/companions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: `批量测试${i}`,
        persona: {
          name: `批量测试${i}`,
          identity: "测试角色",
          gender: "不设定",
          age: 25,
          personality: ["安静", "可靠"],
          speaking_style: "句子短，语气平稳。",
          background: "仅用于自动化测试的临时角色，不涉及真实人物。",
          tags: ["测试"],
          relationship: "测试关系",
        },
      }),
    });
    if (response.ok) created.push((await response.json()).id);
  }
  return created;
});
if (seeded.length) {
  console.log(`补齐 ${seeded.length} 个测试伴侣用于批量验证`);
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
}

const before = await page.locator(".companion-card").count();
console.log("初始伴侣数:", before);
check("有伴侣卡片", before > 0);
check("伴侣数够验证批量删除", before >= 3, `当前 ${before} 个`);

// 进入批量管理
await page.getByRole("button", { name: "批量管理" }).click();
await page.waitForTimeout(600);
check("出现批量操作栏", (await page.locator("body").innerText()).includes("已选 0 个"));
check("每张卡片出现勾选框", (await page.locator(".batch-check input").count()) === before);

// 勾选 2 个
const boxes = page.locator(".batch-check input");
await boxes.nth(0).check();
await boxes.nth(1).check();
await page.waitForTimeout(400);
const after2 = await page.locator("body").innerText();
check("已选数量更新为 2", after2.includes("已选 2 个"), after2.match(/已选 \d+ 个/)?.[0] ?? "");

// 全选
await page.getByRole("button", { name: "全选" }).click();
await page.waitForTimeout(400);
check("全选生效", (await page.locator("body").innerText()).includes(`已选 ${before} 个`));

// 取消全选
await page.getByRole("button", { name: "取消全选" }).click();
await page.waitForTimeout(400);
check("取消全选生效", (await page.locator("body").innerText()).includes("已选 0 个"));

// 勾 2 个用于真实批量删除（验证多选路径，不只删 1 个）
await boxes.nth(0).check();
await boxes.nth(1).check();
await page.waitForTimeout(300);
const willDelete = 2;
await page.getByRole("button", { name: "删除选中" }).click();
await page.waitForTimeout(800);

// 等确认规则从后端加载完（输入框解除禁用）
await page.locator("#batch-confirm").waitFor({ state: "visible" });
await page.waitForFunction(() => {
  const el = document.querySelector("#batch-confirm");
  return el && !el.disabled;
}, { timeout: 10000 });
const modalText = await page.locator("body").innerText();
check("弹出确认框", modalText.includes(`删除 ${willDelete} 个伴侣`), modalText.match(/删除 \d+ 个伴侣/)?.[0] ?? "");
check("确认框列出多个名字", (modalText.match(/、/g) || []).length >= 1);
check("确认框要求输入确认词", /请输入「.+」确认/.test(modalText));
check("确认框提示单批上限", modalText.includes("一次最多"), "");

// 确认按钮在未输入时应禁用
const confirmBtn = page.getByRole("button", { name: /确认删除/ });
check("未输入时确认按钮禁用", await confirmBtn.isDisabled());

// 输错词
await page.locator("#batch-confirm").fill("错的");
await page.waitForTimeout(300);
check("输错词时按钮仍禁用", await confirmBtn.isDisabled());

// 输对词
await page.locator("#batch-confirm").fill("删除");
await page.waitForTimeout(300);
check("输对后按钮可用", await confirmBtn.isEnabled());

await confirmBtn.click();
await page.waitForTimeout(5000);

const after = await page.locator(".companion-card").count();
check("批量删除后卡片数减少 2 个", after === before - willDelete, `${before} → ${after}`);
check("退出批量模式", !(await page.locator("body").innerText()).includes("已选"));

// 接口层面：确认词错误必须被拒
const bad = await page.evaluate(async () => {
  const response = await fetch("/v1/companions/batch-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: [999999], confirm: "错" }),
  });
  return { status: response.status, body: await response.json() };
});
check("接口拒绝错误确认词", bad.status === 422 && bad.body.code === "CONFIRM_MISMATCH", JSON.stringify(bad).slice(0, 80));

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await page.screenshot({ path: "tmp/batch-delete.png", fullPage: true });
await browser.close();
process.exit(failed === 0 ? 0 : 1);
