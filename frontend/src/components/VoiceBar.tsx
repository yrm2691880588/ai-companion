import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatDuration, isRecordingSupported, startVadRecording } from "../lib/voice";
import type { Recorder } from "../lib/voice";

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

  useEffect(() => {
    return () => {
      recorderRef.current?.stop();
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

  async function begin() {
    if (!available) {
      setError("请先在「模型与用量 → 语音」配置 AppID 与 Token");
      return;
    }
    setError("");
    setPhase("listening");
    setLevel(0);
    setElapsed(0);
    try {
      // VAD 自动检测说完，用户不需要点任何按钮
      const recorder = await startVadRecording({
        onLevel: setLevel,
        onSpeechStart: () => setPhase("listening"),
        onSpeechEnd: (audio) => {
          clearTicker();
          void sendAudio(audio);
        },
        onTooShort: () => {
          clearTicker();
          setError("没听清，请靠近麦克风再说一次");
          window.setTimeout(() => setError(""), 3000);
          setPhase("idle");
          setLevel(0);
          setElapsed(0);
        },
        onTimeout: () => {
          clearTicker();
          setError("已到 60 秒上限，自动结束");
          window.setTimeout(() => setError(""), 2500);
          setPhase("idle");
        },
      });
      recorderRef.current = recorder;
      tickerRef.current = window.setInterval(() => {
        setElapsed(recorderRef.current?.elapsedMs() ?? 0);
      }, 200);
    } catch (event) {
      setError((event as Error).message);
      setPhase("idle");
    }
  }

  async function sendAudio(audio: Blob) {
    recorderRef.current = null;
    setPhase("uploading");
    setLevel(0);
    try {
      const result = await api.transcribe(audio, providerKey);
      setPhase("idle");
      setElapsed(0);
      if (result.text.trim()) onTranscribed(result.text.trim());
      else setError("没有听清，请再说一次");
    } catch (event) {
      setError((event as Error).message);
      setPhase("idle");
      setElapsed(0);
    }
  }

  function cancel() {
    recorderRef.current?.stop();
    recorderRef.current = null;
    clearTicker();
    setPhase("idle");
    setLevel(0);
    setElapsed(0);
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
          说完自动发送，不用点
        </span>
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
        title={available ? "点一下开始说话，说完自动发送" : "先配置语音供应商"}
        onClick={() => void begin()}
      >
        {phase === "uploading" ? "识别中…" : "🎤 说话"}
      </button>
      {!available && <span className="muted">语音未配置</span>}
      {error && <span className="voice-error">{error}</span>}
    </div>
  );
}
