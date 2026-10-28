/** 前端错误上报：把崩溃与未捕获异常送到后端日志，便于用户导出后排查。

隐私边界（与后端约定一致）：
- 只发错误消息、堆栈、来源组件与页面路径；
- **不发聊天内容、不发用户身份相关字段**；
- 同一错误短时间内只报一次，避免刷屏。
*/

import { apiUrl, authHeaders } from "./client";

const recent = new Map<string, number>();
const DEDUPE_MS = 30_000;

function shouldSend(key: string): boolean {
  const now = Date.now();
  const last = recent.get(key);
  if (last !== undefined && now - last < DEDUPE_MS) return false;
  recent.set(key, now);
  if (recent.size > 50) {
    // 简单的容量保护：只保留最近 50 条键
    const cutoff = now - DEDUPE_MS;
    for (const [item, at] of recent) {
      if (at < cutoff) recent.delete(item);
    }
  }
  return true;
}

export interface ClientErrorPayload {
  message: string;
  stack?: string;
  component?: string;
}

export function reportClientError(payload: ClientErrorPayload): void {
  const message = (payload.message || "未知错误").slice(0, 500);
  if (!shouldSend(message + (payload.component ?? ""))) return;

  void fetch(apiUrl("/v1/system/client-error"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      message,
      stack: (payload.stack ?? "").slice(0, 4000),
      component: (payload.component ?? "").slice(0, 200),
      // 只发路径，不发查询串，避免把参数带进去
      url: window.location.pathname.slice(0, 300),
    }),
    keepalive: true,
  }).catch(() => {
    // 上报失败不能影响用户，静默丢弃
  });
}

/** 安装全局兜底：未捕获异常与未处理的 Promise 拒绝。 */
export function installGlobalErrorReporting(): void {
  window.addEventListener("error", (event) => {
    reportClientError({
      message: event.message,
      stack: event.error instanceof Error ? event.error.stack : undefined,
      component: "window.onerror",
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    reportClientError({
      message: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
      component: "unhandledrejection",
    });
  });
}
