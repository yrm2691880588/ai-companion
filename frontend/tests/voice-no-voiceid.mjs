import { chromium } from "playwright";
import { pickCompanionWithoutVoice, pickCompanionWithVoice } from "./lib/fixtures.mjs";

// 验证：没设音色的伴侣，点开语音模式时应被明确引导去选音色，
// 而不是静默进入「开了也没声音」的状态。
const BASE = "http://127.0.0.1:8000";

const browser = await chromium.launch({
  channel: "chrome",
  headless: true,
  args: ["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
});
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " - " + detail : ""}`);
};

// 伴侣 18「林夏」没设音色
const noVoiceId = await pickCompanionWithoutVoice(page);
if (!noVoiceId) {
  console.log("SKIP 没有「未设音色」的伴侣可用于验证引导");
  await browser.close();
  process.exit(0);
}
await page.goto(`${BASE}/companions/${noVoiceId}/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(2000);

await page.getByRole("button", { name: /语音模式/ }).first().click();
await page.waitForTimeout(1500);

const body = await page.locator("body").innerText();
check(
  "没设音色时给出提示",
  body.includes("还没选音色") || body.includes("选一个才能听到"),
  body.includes("还没选音色") ? "有提示" : "无提示",
);
check(
  "提示里带「去选音色」动作",
  (await page.getByRole("button", { name: /去选音色/ }).count()) > 0,
);
check("语音模式未被打开（避免开了没声音）", body.includes("语音模式：关"));

// 点「去选音色」应跳到人设页
const action = page.getByRole("button", { name: /去选音色/ });
if ((await action.count()) > 0) {
  await action.first().click();
  await page.waitForTimeout(2000);
  check("跳到人设页", page.url().includes("/persona"), page.url().slice(-30));
  const personaBody = await page.locator("body").innerText();
  check("人设页能看到音色选择", personaBody.includes("她的声音"));
}

// 对照：已设音色的伴侣 19 应能正常打开语音模式
const voiceId2 = await pickCompanionWithVoice(page);
if (!voiceId2) {
  console.log("SKIP 没有已设音色的伴侣");
  await browser.close();
  process.exit(0);
}
await page.goto(`${BASE}/companions/${voiceId2}/chat`, { waitUntil: "networkidle" });
await page.waitForTimeout(2000);
await page.getByRole("button", { name: /语音模式/ }).first().click();
await page.waitForTimeout(1200);
const body19 = await page.locator("body").innerText();
check("已设音色时能打开语音模式", body19.includes("语音模式：开"));

check("页面无 JS 异常", errors.length === 0, errors.slice(0, 2).join(" | "));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n共 ${results.length} 项，失败 ${failed} 项`);
await page.screenshot({ path: "tmp/voice-no-voiceid.png" });
await browser.close();
process.exit(failed === 0 ? 0 : 1);
