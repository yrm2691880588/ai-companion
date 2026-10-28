import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const audioFile = process.argv[2];
// 没传语音文件时，假麦克风是静音，识别必然为空：此时只验证 UI 与「不卡死」，
// 不验证「消息真的发出」（那需要真实语音输入，见 package.json 的 test:voice）
const hasAudio = Boolean(audioFile);

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: [
    "--no-sandbox",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    ...(audioFile ? [`--use-file-for-fake-audio-capture=${audioFile}`] : []),
  ],
});
const context = await browser.newContext({ permissions: ["microphone"] });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

await page.goto(`${BASE}/companions/19/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByRole("button", { name: /语音模式/ }).first().click();
await page.waitForTimeout(500);

// 场景 1：进入录音态必须同时有「发送」和「取消」
await page.getByRole("button", { name: /🎤 说话/ }).first().click();
await page.waitForTimeout(2000);
const sendCount = await page.getByRole("button", { name: /说完了，发送/ }).count();
const cancelCount = await page.getByRole("button", { name: "取消" }).count();
check("录音态有「说完了，发送」按钮", sendCount > 0);
check("录音态有「取消」按钮", cancelCount > 0);

// 场景 2：点「说完了，发送」必须真的发出去，且退出录音态
const beforeCount = await page.locator(".bubble").count();
if (sendCount > 0) {
  await page.getByRole("button", { name: /说完了，发送/ }).first().click();
  await page.waitForTimeout(18000);
}
const afterCount = await page.locator(".bubble").count();
const barText = await page.evaluate(
  () => document.querySelector(".voice-bar")?.innerText.replace(/\n/g, " | ") ?? "(无)",
);
check("点发送后气泡增加（消息真的发出）", !hasAudio || afterCount > beforeCount, `${beforeCount} → ${afterCount}`);
check("点发送后不再卡在录音态", !barText.includes("说完了，发送"), barText.slice(0, 60));
check("点发送后不再卡在识别中", !barText.includes("识别中"), barText.slice(0, 60));
// 成功送出后不应同时出现「没听清」，否则是矛盾提示
check(
  "送出成功后没有「没听清」矛盾提示",
  !(afterCount > beforeCount && barText.includes("没听清")),
  barText.slice(0, 60),
);

// 场景 3：取消通路不发送
await page.getByRole("button", { name: /🎤 说话/ }).first().click();
await page.waitForTimeout(2000);
const beforeCancel = await page.locator(".bubble").count();
await page.getByRole("button", { name: "取消" }).first().click();
await page.waitForTimeout(3000);
const afterCancel = await page.locator(".bubble").count();
check("取消后气泡不增加", afterCancel === beforeCancel, `${beforeCancel} → ${afterCancel}`);
check("取消后回到待机", (await page.getByRole("button", { name: /🎤 说话/ }).count()) > 0);

// 场景 4：录音时「说话」按钮消失（真正验证不可重入）
await page.getByRole("button", { name: /🎤 说话/ }).first().click();
await page.waitForTimeout(1500);
const sendWhileRecording = await page.getByRole("button", { name: /说完了，发送/ }).count();
const micWhileRecording = await page.getByRole("button", { name: /🎤 说话/ }).count();
check("录音时存在「说完了，发送」", sendWhileRecording > 0);
check("录音时「说话」按钮不存在（真正不可重入）", micWhileRecording === 0);

// 场景 5：识别耗时超过兜底阈值时，不能误报「没听清」
// （后端 ASR 轮询实测 3 秒以上，兜底是 1.5 秒，这里验证不会误报）
// 只有真实语音输入才谈得上「识别中」；静音输入本来就该提示没听清。
if (hasAudio) {
  const beforeSlow = await page.locator(".bubble").count();
  if (sendWhileRecording > 0) {
    await page.getByRole("button", { name: /说完了，发送/ }).first().click();
    // 在识别可能仍在进行的时刻取样，检查没有误报
    await page.waitForTimeout(2200);
    const midBar = await page.evaluate(
      () => document.querySelector(".voice-bar")?.innerText.replace(/\n/g, " | ") ?? "",
    );
    check("识别中不误报「没听清」", !midBar.includes("没听清"), midBar.slice(0, 60));
    await page.waitForTimeout(16000);
  }
  const afterSlow = await page.locator(".bubble").count();
  check("慢识别最终仍成功发出", afterSlow > beforeSlow, `${beforeSlow} → ${afterSlow}`);
} else {
  console.log("SKIP 识别相关断言（未提供真实语音文件，静音输入不适用）");
}

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await page.screenshot({ path: "tmp/voice-deadlock.png" });
await browser.close();
process.exit(failed === 0 ? 0 : 1);
