/** 语音录制：自己管麦克风流，VAD 只负责判断「说完了」。

为什么不用 VAD 交出来的音频（@ricky0123/vad-web 的 onSpeechEnd 参数）：
库内部的 endSegment 只有在 Silero 模型判定「这一段是语音」（speaking=true）时
才会把音频交出来。用户的麦克风音量偏低、离得远、环境嘈杂时，模型可能整段都不
判定为语音，此时点「发送」拿不到任何音频，只能提示「没听清」——这是本模块
存在的根本原因。

现在的分工：
- MediaRecorder 全程录音，**一定有音频**，与模型判断无关；
- VAD 只提供「检测到说话」与「判定说完了」两个信号，用于自动结束；
- 用户点「发送」时，直接把 MediaRecorder 录到的整段交出去。
*/

import { MicVAD } from "@ricky0123/vad-web";

export const MAX_RECORD_MS = 60_000;

export interface RecorderOptions {
  /** 音量（0~1），用于界面音量条 */
  onLevel?: (level: number) => void;
  /** 检测到开始说话 */
  onSpeechStart?: () => void;
  /** VAD 自动判定说完，或用户手动点发送，都会回调 */
  onSpeechEnd?: (audio: Blob, durationMs: number) => void;
  /** 录音时长到达上限 */
  onTimeout?: () => void;
  maxMs?: number;
}

export interface Recorder {
  /** 用户点「说完了」：交出已录音频去识别。 */
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

/** 选一个浏览器支持的录音格式；拿不到就用默认。 */
function pickMimeType(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"];
  if (typeof MediaRecorder === "undefined") return "";
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported?.(type)) return type;
  }
  return "";
}

/**
 * 把 Float32Array（-1~1）编码成 16kHz 单声道 WAV。
 * 服务端对 WAV 兼容性最好，且体积可控。
 */
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
 * 开始录音：MediaRecorder 负责音频，VAD 负责「说完了」的自动判断。
 *
 * 麦克风跟随系统默认输入设备（不指定 deviceId），并开启回声消除、
 * 自动增益与降噪——音量偏小的用户靠自动增益也能录清楚。
 */
export async function startVadRecording(options: RecorderOptions = {}): Promise<Recorder> {
  if (!isRecordingSupported()) {
    throw new Error("这个浏览器不支持录音，请换 Chrome 或 Edge");
  }
  const startedAt = Date.now();
  let settled = false;
  let cancelled = false;
  let vad: MicVAD | null = null;
  let audioContext: AudioContext | null = null;
  const ticker: { id?: number } = {};
  const guard: { id?: number } = {};

  // 自己拿麦克风流：显式请求增益与降噪，降低「录不到」的概率
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      autoGainControl: true,
      noiseSuppression: true,
    },
  });

  const mimeType = pickMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  // 每 200ms 切一块，保证停止时能拿到较完整的数据
  recorder.start(200);

  const stopTracks = () => {
    stream.getTracks().forEach((track) => track.stop());
    if (audioContext) {
      void audioContext.close().catch(() => undefined);
      audioContext = null;
    }
  };

  const destroyVad = () => {
    if (!vad) return;
    const current = vad;
    vad = null;
    // destroy 内部会 pause，而 pauseStream 会 stop 轨道；
    // 轨道我们已经在 stopTracks 里处理，这里只需释放模型与音频线程
    void current.destroy().catch(() => undefined);
  };

  /** 把已录到的数据收尾并回调；audio 一定非空（除非完全没数据）。 */
  const finalize = () => {
    if (settled) return;
    settled = true;
    if (guard.id !== undefined) window.clearInterval(guard.id);
    if (ticker.id !== undefined) window.clearInterval(ticker.id);
    const durationMs = Date.now() - startedAt;
    const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
    const emit = () => {
      destroyVad();
      stopTracks();
      if (!cancelled && blob.size > 0) {
        options.onSpeechEnd?.(blob, durationMs);
      }
    };
    if (recorder.state !== "inactive") {
      // 等最后一次 dataavailable 落进 chunks 再收尾
      recorder.onstop = emit;
      try {
        recorder.stop();
      } catch {
        emit();
      }
    } else {
      emit();
    }
  };

  // VAD 只用来判断「说完了」和驱动音量条，不依赖它交音频
  try {
    vad = await MicVAD.new({
      baseAssetPath: "/vad/",
      onnxWASMBasePath: "/vad/",
      model: "v5",
      startOnLoad: true,
      // 复用同一个麦克风流，避免两次 getUserMedia 抢占设备
      getStream: async () => stream,
      pauseStream: async () => {
        // 不要在这里 stop 轨道：音频由 MediaRecorder 继续录
      },
      resumeStream: async () => stream,
      positiveSpeechThreshold: 0.3,
      negativeSpeechThreshold: 0.2,
      redemptionMs: 1200,
      minSpeechMs: 300,
      preSpeechPadMs: 800,
      onSpeechStart: () => options.onSpeechStart?.(),
      onFrameProcessed: (probabilities) => {
        options.onLevel?.(probabilities.isSpeech);
      },
      onSpeechEnd: () => {
        // VAD 判定说完：把整段录音交出去（含 VAD 没识别的部分）
        finalize();
      },
      onVADMisfire: () => {
        // 判为误触：不结束，继续录，用户可以继续说或手动点发送
        options.onLevel?.(0);
      },
    });
  } catch {
    // VAD 起不来不致命：MediaRecorder 已经在录，用户可以手动点发送
    vad = null;
  }

  // 音量条兜底：VAD 不可用时用波形振幅驱动
  if (!vad) {
    audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const buffer = new Uint8Array(analyser.frequencyBinCount);
    ticker.id = window.setInterval(() => {
      analyser.getByteFrequencyData(buffer);
      let sum = 0;
      for (const value of buffer) sum += value;
      options.onLevel?.(Math.min(1, sum / buffer.length / 80));
    }, 100);
  }

  const maxMs = options.maxMs ?? MAX_RECORD_MS;
  guard.id = window.setInterval(() => {
    if (Date.now() - startedAt >= maxMs && !settled) {
      options.onTimeout?.();
      finalize();
    }
  }, 500);

  return {
    elapsedMs: () => Date.now() - startedAt,
    stop: () => {
      finalize();
    },
    cancel: () => {
      cancelled = true;
      if (settled) return;
      settled = true;
      if (guard.id !== undefined) window.clearInterval(guard.id);
      if (ticker.id !== undefined) window.clearInterval(ticker.id);
      try {
        if (recorder.state !== "inactive") recorder.stop();
      } catch {
        // 已停止
      }
      destroyVad();
      stopTracks();
    },
  };
}

/** 播放一段音频；返回停止函数，便于打断。 */
export function playAudio(url: string, onEnded?: () => void): () => void {
  const audio = new Audio(url);
  let settled = false;
  const finish = () => {
    if (settled) return;
    settled = true;
    onEnded?.();
  };
  audio.onended = finish;
  audio.onerror = finish;
  void audio.play().catch(finish);
  return () => {
    audio.pause();
    audio.currentTime = 0;
    finish();
  };
}

/**
 * 分段播放队列：把流式合成返回的多段音频按顺序无缝播完。
 *
 * 为什么需要它：流式合成边生成边返回音频块，如果每块都 new Audio 会互相打断；
 * 必须排队，且要支持随时中断（用户关掉语音、切会话、点停止）。
 */
export interface SpeechPlayer {
  enqueue: (url: string) => void;
  onIdle: (handler: () => void) => void;
  stop: () => void;
  pending: () => number;
}

export function createSpeechPlayer(): SpeechPlayer {
  const queue: string[] = [];
  let current: HTMLAudioElement | null = null;
  let idleHandler: (() => void) | undefined;
  let stopped = false;
  let idleTimer: number | undefined;

  function scheduleIdle() {
    if (idleTimer !== undefined) window.clearTimeout(idleTimer);
    idleTimer = window.setTimeout(() => {
      if (stopped) return;
      if (current || queue.length > 0) return;
      idleHandler?.();
    }, 400);
  }

  function playNext() {
    if (stopped) return;
    const url = queue.shift();
    if (!url) {
      scheduleIdle();
      return;
    }
    const audio = new Audio(url);
    current = audio;
    const advance = () => {
      if (current === audio) current = null;
      audio.onended = null;
      audio.onerror = null;
      playNext();
    };
    audio.onended = advance;
    audio.onerror = advance;
    void audio.play().catch(advance);
  }

  return {
    enqueue: (url) => {
      if (stopped) return;
      if (idleTimer !== undefined) window.clearTimeout(idleTimer);
      queue.push(url);
      if (!current) playNext();
    },
    onIdle: (handler) => {
      idleHandler = handler;
    },
    stop: () => {
      stopped = true;
      if (idleTimer !== undefined) window.clearTimeout(idleTimer);
      queue.length = 0;
      if (current) {
        current.pause();
        current.currentTime = 0;
        current.onended = null;
        current.onerror = null;
        current = null;
      }
    },
    pending: () => queue.length + (current ? 1 : 0),
  };
}

/** 把毫秒格式化成 0:05 这样的时长。 */
export function formatDuration(ms: number): string {
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
