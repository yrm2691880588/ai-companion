/** 语音：录音、上传、播放的纯逻辑封装（不依赖 React，便于测试）。 */

export const MAX_RECORD_MS = 60_000;

export interface RecorderOptions {
  onLevel?: (level: number) => void;
  maxMs?: number;
  onTimeout?: () => void;
}

export interface Recorder {
  stop: () => Promise<Blob>;
  cancel: () => void;
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

export async function startRecording(options: RecorderOptions = {}): Promise<Recorder> {
  if (!isRecordingSupported()) {
    throw new Error("这个浏览器不支持录音，请换 Chrome 或 Edge");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = pickMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: Blob[] = [];
  const startedAt = Date.now();
  let timer: number | undefined;
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
    if (timer !== undefined) window.clearInterval(timer);
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
  timer = window.setInterval(() => {
    if (Date.now() - startedAt >= maxMs) {
      options.onTimeout?.();
    }
  }, 500);

  return {
    elapsedMs: () => Date.now() - startedAt,
    cancel: () => {
      try {
        if (recorder.state !== "inactive") recorder.stop();
      } catch {
        // 已停止
      }
      stopAll();
    },
    stop: () =>
      new Promise<Blob>((resolve, reject) => {
        const finish = () => {
          stopAll();
          const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
          if (blob.size === 0) {
            reject(new Error("没有录到声音，请再试一次"));
            return;
          }
          resolve(blob);
        };
        if (recorder.state === "inactive") {
          finish();
          return;
        }
        recorder.onstop = finish;
        try {
          recorder.stop();
        } catch (error) {
          stopAll();
          reject(error instanceof Error ? error : new Error("录音结束失败"));
        }
      }),
  };
}

/** 播放一段音频；返回停止函数，便于“打断/重播”。 */
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
