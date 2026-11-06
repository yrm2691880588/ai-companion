import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import { formatDuration, isRecordingSupported, startVadRecording } from "../lib/voice";
import { getSelectedMic } from "../lib/mic";
import type { Recorder } from "../lib/voice";
import { explainErrorText } from "../lib/errors";

interface Props {
  /** 识别出文字后交给对话页去发送 */
  onTranscribed: (text: string) => void;
  /** 语音供应商是否已配置；未配置时按钮置灰 */
  available: boolean;
  providerKey?: string;
}

type Phase = "idle" | "listening" | "uploading";

export default function VoiceBar({ onTranscribed, available, providerKey = "volcengine" }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const recorderRef = useRef<Recorder | null>(null);
  const tickerRef = useRef<number | undefined>(undefined);
  // 防止重复点「说话」起两个 VAD 实例
  const startingRef = useRef(false);
  // 每次录音/识别递增；回调与请求返回时比对，过期的一律丢弃
  const sessionRef = useRef(0);
  // finish() 的兜底定时器，成功送出后要清掉，避免误报「没听清」
  const fallbackTimerRef = useRef<number | undefined>(undefined);
  // 记录哪个会话已经交回音频，用于区分「没录到声音」与「识别慢」
  const audioReceivedRef = useRef(0);
  // 组件卸载后不再 setState，避免内存泄漏与 React 警告
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      recorderRef.current?.cancel();
      recorderRef.current = null;
      if (tickerRef.current !== undefined) window.clearInterval(tickerRef.current);
    };
  }, []);

  if (!isRecordingSupported()) return null;

  function clearTicker() {
    if (tickerRef.current !== undefined) {
      window.clearInterval(tickerRef.current);
      tickerRef.current = undefined;
    }
  }

  function resetToIdle(message?: string) {
    clearTicker();
    recorderRef.current = null;
    startingRef.current = false;
    if (!mountedRef.current) return;
    setPhase("idle");
    setLevel(0);
    setElapsed(0);
    if (message) {
      setError(message);
      window.setTimeout(() => {
        if (mountedRef.current) setError("");
      }, 3000);
    }
  }

  async function begin() {
    if (startingRef.current || phase !== "idle") return;
    if (!available) {
      setError("请先在「模型与用量 → 语音」配置 AppID 与 Token");
      return;
    }
    startingRef.current = true;
    sessionRef.current += 1;
    const session = sessionRef.current;
    setError("");
    setPhase("listening");
    setLevel(0);
    setElapsed(0);
    try {
      const recorder = await startVadRecording({
        // 使用设置里选定的输入设备；未指定则跟随系统默认
        deviceId: getSelectedMic(),
        onLevel: (value) => {
          if (mountedRef.current) setLevel(value);
        },
        onSpeechStart: () => {
          if (mountedRef.current) setPhase("listening");
        },
        onSpeechEnd: (audio) => {
          // 用户已取消或已开始下一次录音：丢弃这段音频
          if (session !== sessionRef.current) return;
          void sendAudio(audio, session);
        },
        onDeviceFallback: () => {
          // 用户选的设备不可用，已改用系统默认——必须说出来，否则他会以为在用自己选的
          toast.warning("选的麦克风不可用，已临时改用系统默认设备", { id: "mic-fallback" });
        },
        onEmpty: () => {
          // 一个字节都没录到：多半是麦克风被别的程序占用，或权限异常
          resetToIdle("麦克风没有录到声音，检查系统输入设备或被其他程序占用");
        },
        onTimeout: () => {
          resetToIdle("已到 60 秒上限，自动结束");
        },
      });
      if (!mountedRef.current) {
        recorder.cancel();
        return;
      }
      recorderRef.current = recorder;
      tickerRef.current = window.setInterval(() => {
        if (mountedRef.current) setElapsed(recorder.elapsedMs());
      }, 200);
    } catch (event) {
      resetToIdle((event as Error).message || "麦克风启动失败");
    }
  }

  /** 用户主动点「说完了」：交出已录音频去识别。 */
  function finish() {
    const recorder = recorderRef.current;
    if (!recorder) {
      resetToIdle();
      return;
    }
    clearTicker();
    recorderRef.current = null;
    startingRef.current = false;
    if (mountedRef.current) {
      setPhase("uploading");
      setLevel(0);
    }
    // stop() 会通过 onSpeechEnd 回调把音频送到 sendAudio
    recorder.stop();
    // 兜底只覆盖「音频根本没交回来」（例如全程静音、VAD 没判定出语音）。
    // 不能覆盖「正在识别」——识别实测要 3 秒以上，用 2 秒会误报没听清。
    const session = sessionRef.current;
    window.clearTimeout(fallbackTimerRef.current);
    fallbackTimerRef.current = window.setTimeout(() => {
      if (!mountedRef.current || session !== sessionRef.current) return;
      // 音频已经交回来了，说明只是识别慢，继续等，不要打断
      if (audioReceivedRef.current === session) return;
      setPhase((current) => (current === "uploading" ? "idle" : current));
      setError("没听清，请靠近麦克风再说一次");
    }, 1500);
  }

  async function sendAudio(audio: Blob, session: number) {
    recorderRef.current = null;
    startingRef.current = false;
    clearTicker();
    if (!mountedRef.current || session !== sessionRef.current) return;
    // 音频已交回：兜底定时器据此判断「不是没录到声音，只是识别慢」
    audioReceivedRef.current = session;
    window.clearTimeout(fallbackTimerRef.current);
    setPhase("uploading");
    setLevel(0);
    try {
      const result = await api.transcribe(audio, providerKey);
      // 请求返回时用户可能已经取消：此时不能把结果发出去
      if (!mountedRef.current || session !== sessionRef.current) return;
      setPhase("idle");
      setElapsed(0);
      if (result.text.trim()) onTranscribed(result.text.trim());
      else setError("没有听清，请再说一次");
    } catch (event) {
      if (!mountedRef.current || session !== sessionRef.current) return;
      setError(explainErrorText(event));
      setPhase("idle");
      setElapsed(0);
    }
  }

  /** 取消：丢弃录音与在途识别，不发送。 */
  function cancel() {
    // 递增会话号，让任何在途回调与请求结果失效
    sessionRef.current += 1;
    recorderRef.current?.cancel();
    resetToIdle();
  }

  if (phase === "listening") {
    return (
      <div className="voice-bar">
        <span className="voice-dot" />
        <span className="voice-timer">{formatDuration(elapsed)}</span>
        <div className="voice-meter">
          <div className="voice-meter-fill" style={{ width: `${Math.round(level * 100)}%` }} />
        </div>
        <span className="muted" style={{ fontSize: 12 }}>
          停顿 1.3 秒自动发送，也可以点右边
        </span>
        <button className="btn primary" onClick={finish}>
          说完了，发送
        </button>
        <button className="btn ghost" onClick={cancel}>
          取消
        </button>
      </div>
    );
  }

  return (
    <div className="voice-bar">
      <button
        className="btn ghost voice-mic"
        disabled={phase === "uploading"}
        title={available ? "点一下开始说话，说完自动发送，也可手动点发送" : "先配置语音供应商"}
        onClick={() => void begin()}
      >
        {phase === "uploading" ? "识别中…" : "🎤 说话"}
      </button>
      {phase === "uploading" && (
        <button className="btn ghost" onClick={cancel}>
          取消
        </button>
      )}
      {!available && <span className="muted">语音未配置</span>}
      {error && <span className="voice-error">{error}</span>}
    </div>
  );
}
