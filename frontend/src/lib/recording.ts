/** 录音相关的纯常量与纯函数：不依赖浏览器 API，可被 Node 直接测试。 */

/** 单次录音上限：60 秒，超过自动结束。 */
export const MAX_RECORD_MS = 60_000;

/** 把毫秒格式化成 0:05 这样的时长。 */
export function formatDuration(ms: number): string {
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
