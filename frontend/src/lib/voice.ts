/** 语音：录音、上传、播放。

VAD（语音活动检测）交给 @ricky0123/vad-web：它用 Silero 模型判断「说完了没有」，
停顿足够久就自动结束并交回音频；用户也可以随时点「说完了，发送」手动结束，
两条路径都走 submitUserSpeechOnPause 把已录片段交出来。
资源文件由 scripts/sync_vad_assets.py 复制到 public/vad。
*/

import { MicVAD } from "@ricky0123/vad-web";

export const MAX_RECORD_MS = 60_000;

export interface RecorderOptions {
  onLevel?: (level: number) => void;
  /** 检测到开始说话 */
  onSpeechStart?: () => void;
  /** 自动检测到说完，回调 wav 音频与时长 */
  onSpeechEnd?: (audio: Blob, durationMs: number) => void;
  /** 说话太短或没听清（VAD 判为误触），用于提示用户，不送识别 */
  onTooShort?: () => void;
  maxMs?: number;
  onTimeout?: () => void;
}

export interface Recorder {
  /** 用户点「说完了」：把已录到的音频交出来去识别。 */
  stop: () => void;
  /** 用户点「取消」：丢弃已录音频，不发送。 */
  cancel: () => void;
  elapsedMs: () => number;
}

export function isRecordingSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== "undefined"
  );
}

/** 把 VAD 给的 Float32Array（16kHz 单声道）编码成 WAV，服务端识别兼容性最好。 */
export function encodeWav(samples: Float32Array, sampleRate = 16000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeText = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * 启动 VAD 自动录音：检测到说话开始，说完自动结束并回调音频。
 *
 * 返回的 Recorder 有两个结束方式，语义不同：
 * - `stop()`：**提交**。把已录片段通过 onSpeechEnd 交出去识别；
 * - `cancel()`：**取消**。丢弃已录片段，不发送。
 */
export async function startVadRecording(options: RecorderOptions = {}): Promise<Recorder> {
  if (!isRecordingSupported()) {
    throw new Error("这个浏览器不支持录音，请换 Chrome 或 Edge");
  }
  const startedAt = Date.now();
  let finished = false;
  let cancelled = false;
  // 计时器只赋值一次，用对象包一层是为了能在闭包里安全引用
  const ticker: { id?: number } = {};

  // 统一销毁：VAD 可能已被销毁，重复调用不应抛错
  const destroyVad = (): void => {
    void vad.destroy().catch(() => undefined);
  };

  const vad = await MicVAD.new({
    baseAssetPath: "/vad/",
    onnxWASMBasePath: "/vad/",
    model: "v5",
    startOnLoad: true,
    // 阈值贴近库默认值：0.6 太严，小声说话不触发，导致截到的是静音
    positiveSpeechThreshold: 0.35,
    negativeSpeechThreshold: 0.25,
    // 停顿 1.3 秒才判定说完，给「想一下再继续说」留余地
    redemptionMs: 1300,
    // 少于 500ms 的当误触（咳嗽、敲键盘），不送识别
    minSpeechMs: 500,
    // 保留开口前 800ms，避免吞掉第一个字
    preSpeechPadMs: 800,
    // 关键：手动 pause 时把已录片段交出来，否则「点按钮结束」拿不到音频
    submitUserSpeechOnPause: true,
    onSpeechStart: () => options.onSpeechStart?.(),
    onFrameProcessed: (probabilities) => {
      options.onLevel?.(probabilities.isSpeech);
    },
    onSpeechEnd: (audio) => {
      if (finished) return;
      finished = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      const durationMs = Math.round((audio.length / 16000) * 1000);
      // 太短的片段不送识别，直接提示重说，避免"没有识别到内容"的困惑
      if (durationMs < 400) {
        options.onLevel?.(0);
        options.onTooShort?.();
        destroyVad();
        return;
      }
      options.onSpeechEnd?.(encodeWav(audio), durationMs);
      destroyVad();
    },
    onVADMisfire: () => {
      options.onLevel?.(0);
      // 手动点「说完了」但录到的有效语音不足时也会走到这里。
      // 必须销毁 VAD 释放麦克风流，否则组件已丢弃引用，卸载也收不回来。
      if (finished || cancelled) return;
      finished = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      options.onTooShort?.();
      destroyVad();
    },
  });

  const maxMs = options.maxMs ?? MAX_RECORD_MS;
  ticker.id = window.setInterval(() => {
    if (Date.now() - startedAt >= maxMs && !finished) {
      finished = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      options.onTimeout?.();
      destroyVad();
    }
  }, 500);

  return {
    elapsedMs: () => Date.now() - startedAt,
    // 用户点「说完了」：pause 会把已录片段交出来（见 submitUserSpeechOnPause）
    stop: () => {
      if (finished || cancelled) return;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      // 不置 finished，让 pause 触发的 onSpeechEnd 能正常送达音频
      void vad
        .pause()
        .catch(() => undefined)
        .then(destroyVad);
    },
    // 用户点「取消」：丢弃录音，不发送
    cancel: () => {
      if (finished) return;
      cancelled = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      destroyVad();
    },
  };
}

/** 播放一段音频；返回停止函数，便于打断。 */
export function playAudio(url: string, onEnded?: () => void): () => void {
  const audio = new Audio(url);
  audio.onended = () => onEnded?.();
  void audio.play().catch(() => {
    onEnded?.();
  });
  return () => {
    audio.pause();
    audio.currentTime = 0;
  };
}

/** 把毫秒格式化成 0:05 这样的时长。 */
export function formatDuration(ms: number): string {
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
