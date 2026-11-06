/** 麦克风设备选择：默认跟随系统，可手动指定某个输入设备。

为什么需要：用户机器上常装有 Voicemeeter、NVIDIA Broadcast、Steam Streaming
这类虚拟音频设备，浏览器默认可能选中它们，录到的是静音，表现为「没有识别到
内容」。允许手动指定物理麦克风可以直接规避。

选择存在 localStorage，仅本机生效，不参与跨端同步。
*/

const STORAGE_KEY = "ai-companion-mic-device";
/** 空字符串代表跟随系统默认设备。 */
export const FOLLOW_SYSTEM = "";

export interface MicDevice {
  deviceId: string;
  label: string;
}

export function getSelectedMic(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? FOLLOW_SYSTEM;
  } catch {
    return FOLLOW_SYSTEM;
  }
}

export function setSelectedMic(deviceId: string): void {
  try {
    if (deviceId) localStorage.setItem(STORAGE_KEY, deviceId);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage 不可用（隐私模式等）：退化为跟随系统
  }
}

export function isMicSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.enumerateDevices)
  );
}

/**
 * 列出所有音频输入设备。
 *
 * 注意：未授权麦克风前，浏览器会把 label 返回为空字符串，
 * 所以调用前应先 getUserMedia 取得权限，否则用户看不到设备名。
 */
export async function listMicDevices(): Promise<MicDevice[]> {
  if (!isMicSupported()) return [];
  const list = await navigator.mediaDevices.enumerateDevices();
  return list
    .filter((item) => item.kind === "audioinput")
    .map((item, index) => ({
      deviceId: item.deviceId,
      label: item.label || `麦克风 ${index + 1}（未授权，显示不出名字）`,
    }));
}

/** 把保存的设备转换成 getUserMedia 的 audio 约束。 */
export function micConstraints(deviceId: string): MediaStreamConstraints {
  const base = {
    channelCount: 1,
    echoCancellation: true,
    autoGainControl: true,
    noiseSuppression: true,
  };
  if (deviceId) {
    return { audio: { ...base, deviceId: { exact: deviceId } } };
  }
  return { audio: base };
}

/**
 * 打开麦克风。
 *
 * 指定设备不可用时**抛错而不是静默退回系统默认**。
 * 原因：试音区块要判断「这个设备到底能不能录到」，如果偷偷换成系统默认，
 * 用户会看到电平条有反应、以为选中的设备可用，恰好破坏了这个功能的意义。
 * 录音时若确实需要兜底，由调用方显式决定（见 startVadRecording）。
 */
export async function openMic(deviceId: string): Promise<MediaStream> {
  return await navigator.mediaDevices.getUserMedia(micConstraints(deviceId));
}

/**
 * 打开麦克风并允许兜底：指定设备失败时退回系统默认。
 * 返回实际使用的设备标识，便于界面提示「已切换」。
 *
 * 仅录音链路使用——那里宁可换设备也不能让整段录音失败；
 * 试音场景请用 openMic，让用户看到真实结果。
 */
export async function openMicWithFallback(
  deviceId: string,
): Promise<{ stream: MediaStream; fallback: boolean }> {
  try {
    return { stream: await openMic(deviceId), fallback: false };
  } catch (error) {
    if (!deviceId) throw error;
    // 设备被拔掉或被别的程序占用：退回系统默认，让调用方告知用户
    return { stream: await openMic(FOLLOW_SYSTEM), fallback: true };
  }
}
