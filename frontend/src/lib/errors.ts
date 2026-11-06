/** 把浏览器抛出的原始错误翻译成用户能看懂、知道怎么办的中文提示。

为什么需要：浏览器的 MediaDevices 错误是英文枚举值（NotAllowedError 等），
直接展示给用户只会看到 "Permission denied"，既看不懂也不知道下一步做什么。
*/

export interface FriendlyError {
  /** 给用户看的一句话 */
  message: string;
  /** 建议怎么做；没有建议时为空 */
  hint?: string;
}

/**
 * 把任意错误转成中文说明。
 * 认得出来的按类型给具体建议，认不出来的退回兜底文案 + 原始信息。
 */
export function explainError(error: unknown, fallback = "操作失败"): FriendlyError {
  const name = error instanceof Error ? error.name : "";
  const raw = error instanceof Error ? error.message : String(error ?? "");

  // 麦克风 / 摄像头权限与设备类错误
  if (name === "NotAllowedError" || /permission denied/i.test(raw)) {
    return {
      message: "浏览器没有麦克风权限",
      hint: "点地址栏左边的锁图标，把「麦克风」改成允许，然后刷新页面",
    };
  }
  if (name === "NotFoundError" || /requested device not found/i.test(raw)) {
    return {
      message: "找不到麦克风设备",
      hint: "检查麦克风是否插好，或在系统设置里确认输入设备存在",
    };
  }
  if (name === "NotReadableError" || /could not start/i.test(raw)) {
    return {
      message: "麦克风被其他程序占用",
      hint: "关掉正在用麦克风的软件（会议、录音、直播工具），再试一次",
    };
  }
  if (name === "OverconstrainedError") {
    return {
      message: "这个麦克风不支持当前的录音参数",
      hint: "换一个输入设备试试",
    };
  }
  if (name === "AbortError") {
    return { message: "操作被中断", hint: "重试一次" };
  }

  // 网络类
  if (name === "TypeError" && /fetch|network/i.test(raw)) {
    return {
      message: "连不上服务",
      hint: "检查后端是否在运行，以及网络是否正常",
    };
  }

  // 认不出来：保留原始信息，但加上兜底说明，避免只有一个英文词
  return {
    message: fallback,
    hint: raw ? `原始信息：${raw.slice(0, 120)}` : undefined,
  };
}

/** 只要一句话时用这个：把 message 与 hint 合成一行。 */
export function explainErrorText(error: unknown, fallback = "操作失败"): string {
  const { message, hint } = explainError(error, fallback);
  return hint ? `${message}（${hint}）` : message;
}
