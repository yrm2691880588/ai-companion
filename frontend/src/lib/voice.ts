/** 语音：录音、上传、播放。

VAD（语音活动检测）交给 @ricky0123/vad-web：它用 Silero 模型判断「说完了没有」，
不需要用户手动点「说完了」。资源文件由 scripts/sync_vad_assets.py 复制到 public/vad。
*/

import { MicVAD } from "@ricky0123/vad-web";

export const MAX_RECORD_MS = 60_000;

export interface RecorderOptions {
  onLevel?: (level: number) => void;
  /** 检测到开始说话 */
  onSpeechStart?: () => void;
  /** 自动检测到说完，回调 wav 音频与时长 */
  onSpeechEnd?: (audio: Blob, durationMs: number) => void;
  maxMs?: number;
  onTimeout?: () => void;
}

export interface Recorder {
  stop: () => void;
  elapsedMs: () => number;
}

function pickMimeType(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"];
  if (typeof MediaRecorder === "undefined") return "";
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported?.(type)) return type;
  }
  return "";
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
 * 返回的 stop() 用于用户主动取消。
 */
export async function startVadRecording(options: RecorderOptions = {}): Promise<Recorder> {
  if (!isRecordingSupported()) {
    throw new Error("这个浏览器不支持录音，请换 Chrome 或 Edge");
  }
  const startedAt = Date.now();
  let finished = false;
  // 计时器只赋值一次，用对象包一层是为了能在闭包里安全引用
  const ticker: { id?: number } = {};

  const vad = await MicVAD.new({
    baseAssetPath: "/vad/",
    onnxWASMBasePath: "/vad/",
    model: "v5",
    startOnLoad: true,
    positiveSpeechThreshold: 0.6,
    negativeSpeechThreshold: 0.35,
    // 停顿 700ms 判定说完
    redemptionMs: 700,
    // 少于 300ms 的当误触丢弃
    minSpeechMs: 300,
    preSpeechPadMs: 300,
    onSpeechStart: () => options.onSpeechStart?.(),
    onFrameProcessed: (probabilities) => {
      options.onLevel?.(probabilities.isSpeech);
    },
    onSpeechEnd: (audio) => {
      if (finished) return;
      finished = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      const durationMs = Math.round((audio.length / 16000) * 1000);
      options.onSpeechEnd?.(encodeWav(audio), durationMs);
      void vad.destroy();
    },
    onVADMisfire: () => {
      options.onLevel?.(0);
    },
  });

  const maxMs = options.maxMs ?? MAX_RECORD_MS;
  ticker.id = window.setInterval(() => {
    if (Date.now() - startedAt >= maxMs && !finished) {
      finished = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      options.onTimeout?.();
      void vad.destroy();
    }
  }, 500);

  return {
    elapsedMs: () => Date.now() - startedAt,
    stop: () => {
      if (finished) return;
      finished = true;
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      void vad.destroy();
    },
  };
}

/** 兜底路径：VAD 不可用时手动录音（保留给旧浏览器）。 */
export async function startRecording(options: RecorderOptions = {}): Promise<Recorder> {
  if (!isRecordingSupported()) {
    throw new Error("这个浏览器不支持录音，请换 Chrome 或 Edge");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = pickMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: Blob[] = [];
  const startedAt = Date.now();
  let meter: number | undefined;
  let closed = false;

  const audioContext = new AudioContext();
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 512;
  audioContext.createMediaStreamSource(stream).connect(analyser);
  const buffer = new Uint8Array(analyser.frequencyBinCount);

  const stopAll = () => {
    if (closed) return;
    closed = true;
    if (meter !== undefined) window.clearInterval(meter);
    stream.getTracks().forEach((track) => track.stop());
    void audioContext.close();
  };

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.start(200);

  if (options.onLevel) {
    const onLevel = options.onLevel;
    meter = window.setInterval(() => {
      analyser.getByteFrequencyData(buffer);
      let sum = 0;
      for (const value of buffer) sum += value;
      onLevel(Math.min(1, sum / buffer.length / 80));
    }, 100);
  }

  const maxMs = options.maxMs ?? MAX_RECORD_MS;
  const timer = window.setInterval(() => {
    if (Date.now() - startedAt >= maxMs) options.onTimeout?.();
  }, 500);

  return {
    elapsedMs: () => Date.now() - startedAt,
    stop: () => {
      try {
        if (recorder.state !== "inactive") recorder.stop();
      } catch {
        // 已停止
      }
      window.clearInterval(timer);
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      stopAll();
      if (blob.size > 0) options.onSpeechEnd?.(blob, Date.now() - startedAt);
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
