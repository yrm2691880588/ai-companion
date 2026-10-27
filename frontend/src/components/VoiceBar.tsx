import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatDuration, isRecordingSupported, startRecording } from "../voice";
import type { Recorder } from "../voice";

interface Props {
  /** 识别出文字后交给对话页去发送 */
  onTranscribed: (text: string) => void;
  /** 语音供应商是否已配置；未配置时按钮置灰 */
  available: boolean;
  providerKey?: string;
}

type Phase = "idle" | "recording" | "uploading";

export default function VoiceBar({ onTranscribed, available, providerKey = "volcengine" }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const recorderRef = useRef<Recorder | null>(null);
  const autoStopRef = useRef(false);

  useEffect(() => {
    return () => {
      recorderRef.current?.cancel();
    };
  }, []);

  if (!isRecordingSupported()) return null;

  async function begin() {
    if (!available) {
      setError("请先在「模型与用量 → 语音」配置 AppID 与 Token");
      return;
    }
    setError("");
    autoStopRef.current = false;
    try {
      const recorder = await startRecording({
        onLevel: setLevel,
        onTimeout: () => {
          autoStopRef.current = true;
          void finish();
        },
      });
      recorderRef.current = recorder;
      setPhase("recording");
      setElapsed(0);
      const ticker = window.setInterval(() => {
        setElapsed(recorder.elapsedMs());
      }, 200);
      window.setTimeout(() => window.clearInterval(ticker), 65_000);
    } catch (event) {
      setError((event as Error).message);
      setPhase("idle");
    }
  }

  async function finish() {
    const recorder = recorderRef.current;
    if (!recorder) return;
    setPhase("uploading");
    try {
      const blob = await recorder.stop();
      recorderRef.current = null;
      const result = await api.transcribe(blob, providerKey);
      setPhase("idle");
      setLevel(0);
      setElapsed(0);
      if (autoStopRef.current) {
        setError("已到 60 秒上限，自动结束录音");
        window.setTimeout(() => setError(""), 2500);
      }
      if (result.text.trim()) onTranscribed(result.text.trim());
    } catch (event) {
      setError((event as Error).message);
      setPhase("idle");
      setLevel(0);
      recorderRef.current = null;
    }
  }

  function cancel() {
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setPhase("idle");
    setLevel(0);
    setElapsed(0);
  }

  if (phase === "recording") {
    return (
      <div className="voice-bar">
        <span className="voice-dot" />
        <span className="voice-timer">{formatDuration(elapsed)}</span>
        <div className="voice-meter">
          <div className="voice-meter-fill" style={{ width: `${Math.round(level * 100)}%` }} />
        </div>
        <button className="btn primary" onClick={() => void finish()}>
          说完了
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
        title={available ? "点一下开始说话" : "先配置语音供应商"}
        onClick={() => void begin()}
      >
        {phase === "uploading" ? "识别中…" : "🎤 语音"}
      </button>
      {!available && <span className="muted">语音未配置</span>}
      {error && <span className="voice-error">{error}</span>}
    </div>
  );
}
