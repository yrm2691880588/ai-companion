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
import { getSelectedMic, openMicWithFallback } from "./mic";
import { MAX_RECORD_MS, formatDuration } from "./recording";

export { MAX_RECORD_MS, formatDuration };

export interface RecorderOptions {
  /** 指定输入设备；留空则跟随系统默认 */
  deviceId?: string;
  /** 音量（0~1），用于界面音量条 */
  onLevel?: (level: number) => void;
  /** 检测到开始说话 */
  onSpeechStart?: () => void;
  /** VAD 自动判定说完，或用户手动点发送，都会回调 */
  onSpeechEnd?: (audio: Blob, durationMs: number) => void;
  /** 录音结束但一个字节都没录到（麦克风被占用或权限异常） */
  onEmpty?: () => void;
  /** 指定的设备不可用，已自动改用系统默认设备 */
  onDeviceFallback?: () => void;
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

  // 自己拿麦克风流：显式请求增益与降噪，降低「录不到」的概率。
  // 指定设备不可用时退回系统默认——录音宁可换设备也不能整段失败；
  // 但会通过 onDeviceFallback 告知界面，避免用户以为在用自己选的设备。
  const opened = await openMicWithFallback(options.deviceId ?? getSelectedMic());
  const stream = opened.stream;
  if (opened.fallback) options.onDeviceFallback?.();

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

  /** 把已录到的数据收尾并回调。 */
  const finalize = () => {
    if (settled) return;
    settled = true;
    if (guard.id !== undefined) window.clearInterval(guard.id);
    if (ticker.id !== undefined) window.clearInterval(ticker.id);
    const durationMs = Date.now() - startedAt;
    // 注意：blob 必须在 recorder.stop() 触发的 onstop 里创建。
    // MediaRecorder 是异步把数据通过 ondataavailable 交出来的，
    // 在 stop() 之前读 chunks 会拿到空数组，导致上传 0 字节、
    // 后端回「没有识别到内容」——这是真实用户报的「语音输入不进去」。
    const emit = () => {
      destroyVad();
      stopTracks();
      if (cancelled) return;
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      if (blob.size > 0) {
        options.onSpeechEnd?.(blob, durationMs);
      } else {
        options.onEmpty?.();
      }
    };
    if (recorder.state !== "inactive") {
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
  /** 某一段播放失败时回调；不中断整个队列。 */
  onError: (handler: (message: string) => void) => void;
  stop: () => void;
  pending: () => number;
}

export function createSpeechPlayer(): SpeechPlayer {
  const queue: string[] = [];
  let current: HTMLAudioElement | null = null;
  let idleHandler: (() => void) | undefined;
  let errorHandler: ((message: string) => void) | undefined;
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
    audio.onerror = () => {
      // 加载失败（地址失效等）：报错并继续播下一段
      errorHandler?.("这段语音没能播放，可能是音频地址已过期");
      advance();
    };
    void audio.play().catch((error: unknown) => {
      // 自动播放被浏览器拦截或解码失败：必须让用户知道，否则表现为「没声音」
      errorHandler?.(
        `语音播放被浏览器拦住了：${(error as Error).message || "未知原因"}，点一下页面再试`,
      );
      advance();
    });
  }

  return {
    enqueue: (url) => {
      if (stopped) return;
      if (idleTimer !== undefined) window.clearTimeout(idleTimer);
      queue.push(url);
      if (!current) playNext();
    },
    onError: (handler) => {
      errorHandler = handler;
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

