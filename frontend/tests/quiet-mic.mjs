import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8000";
const audioFile = process.argv[2];
// 没有真实语音输入时（假麦克风是静音），识别必然为空，
// 此时只验证「不卡死、不崩溃」，不验证「识别出文字」。
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
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

// 记录识别请求，看是否真的上传了音频
const transcribeCalls = [];
page.on("response", async (r) => {
  if (r.url().includes("/v1/voice/transcribe")) {
    transcribeCalls.push({
      status: r.status(),
      body: (await r.text().catch(() => "")).slice(0, 120),
    });
  }
});

await page.goto(`${BASE}/companions/19/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.getByRole("button", { name: /语音模式/ }).first().click();
await page.waitForTimeout(500);

// 核心场景：点说话 → 说话 → 发送
// 注意：VAD 可能自动判定说完并发送，也可能等用户手动点，
// 两种路径都要能成功，所以这里两种都覆盖。
await page.getByRole("button", { name: /🎤 说话/ }).first().click();
await page.waitForTimeout(2500);

const before = await page.locator(".bubble").count();
const sendVisible = await page.getByRole("button", { name: /说完了，发送/ }).count();
check("录音已启动（出现录音态或已在识别）", sendVisible > 0 || transcribeCalls.length > 0);
if (sendVisible > 0) {
  // 手动发送路径
  await page.getByRole("button", { name: /说完了，发送/ }).first().click();
}
await page.waitForTimeout(20000);
const after = await page.locator(".bubble").count();
const barText = await page.evaluate(
  () => document.querySelector(".voice-bar")?.innerText.replace(/\n/g, " | ") ?? "",
);

check("确实发起了识别请求", transcribeCalls.length > 0, `调用 ${transcribeCalls.length} 次`);
if (transcribeCalls.length > 0) {
  const call = transcribeCalls[0];
  if (hasAudio) {
    check("识别接口返回 200", call.status === 200, `${call.status} ${call.body}`);
    check("识别出了文字（不再是空结果）", !call.body.includes('"text":""'), call.body);
  } else {
    // 静音输入下后端返回 502 VOICE_ASR_EMPTY「没有识别到内容」是正确行为
    check(
      "静音输入被正确判为无内容",
      call.status === 502 && call.body.includes("VOICE_ASR_EMPTY"),
      `${call.status} ${call.body}`,
    );
  }
}
if (hasAudio) {
  check("没有出现「没听清」提示", !barText.includes("没听清"), barText.slice(0, 80));
  check("消息已发出", after > before, `${before} → ${after}`);
} else {
  console.log("SKIP 文字与发出断言（静音输入不适用）");
}
check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await page.screenshot({ path: "tmp/quiet-mic.png" });
await browser.close();
process.exit(failed === 0 ? 0 : 1);
