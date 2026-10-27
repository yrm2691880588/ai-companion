/** 轻量埋点：只上报事件名与可选上下文，绝不上报消息正文。 */

export type AnalyticsEvent =
  | "app_open"
  | "create_start"
  | "create_success"
  | "first_message"
  | "first_reply"
  | "message_action"
  | "persona_save"
  | "error";

export function track(
  name: AnalyticsEvent,
  extra: { session_id?: number; duration_ms?: number; error_code?: string } = {},
): void {
  try {
    void fetch("/v1/analytics", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": localStorage.getItem("ai-companion-user-id") || "dev-user",
      },
      body: JSON.stringify({ name, ...extra }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // 埋点失败不能影响主流程
  }
}
