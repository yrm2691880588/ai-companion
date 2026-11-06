/** 测试公共工具：动态取伴侣 id，避免硬编码导致数据一变就全线失败。 */

export const BASE = "http://127.0.0.1:8000";

/**
 * 确保页面已在同源上下文里，否则 page.evaluate 里的 fetch 无法发同源请求。
 * 调用方可能还没导航，这里兜底打开首页。
 */
async function ensureSameOrigin(page) {
  const url = page.url();
  if (!url.startsWith(BASE)) {
    await page.goto(BASE, { waitUntil: "domcontentloaded" });
  }
}

/**
 * 取一个有音色的伴侣 id（按名字优先「苏小糖·测试版」）。
 *
 * 为什么不用固定 id：批量删除功能上线后，测试伴侣可能被删掉，
 * 硬编码 `companions/19` 会让一整套语音验收假失败。
 */
export async function pickCompanionWithVoice(page) {
  await ensureSameOrigin(page);
  // 不经过页面，直接用接口取，避免依赖 DOM 渲染时序
  return await page.evaluate(async () => {
    const response = await fetch("/v1/companions", { credentials: "same-origin" });
    if (!response.ok) return null;
    const list = await response.json();
    const withVoice = list.filter((c) => c.voice_id);
    if (withVoice.length === 0) return null;
    // 优先测试伴侣，其次任意有音色的
    const preferred = withVoice.find((c) => c.name.includes("测试"));
    return (preferred ?? withVoice[0]).id;
  });
}

/** 取任意一个伴侣 id（不需要音色）。 */
export async function pickAnyCompanion(page) {
  await ensureSameOrigin(page);
  return await page.evaluate(async () => {
    const response = await fetch("/v1/companions", { credentials: "same-origin" });
    if (!response.ok) return null;
    const list = await response.json();
    return list.length > 0 ? list[0].id : null;
  });
}

/** 取一个没有音色的伴侣 id，用于验证「没音色时的引导」。 */
export async function pickCompanionWithoutVoice(page) {
  await ensureSameOrigin(page);
  return await page.evaluate(async () => {
    const response = await fetch("/v1/companions", { credentials: "same-origin" });
    if (!response.ok) return null;
    const list = await response.json();
    const target = list.find((c) => !c.voice_id);
    return target ? target.id : null;
  });
}
