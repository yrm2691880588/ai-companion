import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { api } from "../api";
import { playAudio } from "../lib/voice";
import type { VoiceOption } from "../lib/types";
import { explainErrorText } from "../lib/errors";
import ErrorAlert from "./ErrorAlert";
import Loading from "./Loading";

interface Props {
  companionId: number;
  value: string | null;
  onChange: (voiceId: string | null) => void;
}

export default function VoicePicker({ companionId, value, onChange }: Props) {
  const providersQuery = useQuery(queries.voiceProviders());
  const configured = providersQuery.data?.some(item => item.configured && item.enabled) ?? false;
  const voicesQuery = useQuery({ ...queries.voices("volcengine"), enabled: configured });
  const voices = voicesQuery.data ?? [];
  const loading = providersQuery.isPending || (configured && voicesQuery.isPending);
  const loadError = providersQuery.error?.message || voicesQuery.error?.message;
  const [error, setError] = useState("");
  const [previewing, setPreviewing] = useState<string | null>(null);
  async function preview(voice: VoiceOption) {
    setPreviewing(voice.voice_id);
    try {
      const speech = await api.synthesize(
        `你好，我是${voice.display_name}，很高兴认识你。`,
        voice.voice_id,
      );
      playAudio(speech.audio_url, () => setPreviewing(null));
    } catch (event) {
      setError(explainErrorText(event));
      setPreviewing(null);
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>她的声音</h2>
        <Loading lines={2} label="加载音色" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="card">
        <h2>她的声音</h2>
        <ErrorAlert message={loadError} variant="inline" onRetry={() => void providersQuery.refetch()} />
      </div>
    );
  }

  if (!configured) {
    return (
      <div className="card">
        <h2>她的声音</h2>
        <p className="muted">
          还没有配置语音供应商。先去「模型与用量 → 语音」填写共火山引擎的 AppID 与 Token，
          然后就能在这里挑音色了。
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>她的声音</h2>
      <p className="muted">选一个音色，以后语音回复就用这个声音。</p>
      {error && <ErrorAlert message={error} variant="inline" />}
      {loading ? (
        <Loading lines={1} label="加载音色列表" />
      ) : (
        <>
          <select
            id={`voice-${companionId}`}
            value={value ?? ""}
            onChange={(event) => onChange(event.target.value || null)}
          >
            <option value="">不启用语音</option>
            {voices.map((voice) => (
              <option key={voice.voice_id} value={voice.voice_id}>
                {voice.display_name}
                {voice.gender ? `（${voice.gender}）` : ""}
              </option>
            ))}
          </select>
          <div className="toolbar">
            {voices.slice(0, 4).map((voice) => (
              <button
                key={voice.voice_id}
                className="btn ghost"
                disabled={previewing !== null}
                onClick={() => void preview(voice)}
              >
                {previewing === voice.voice_id ? "试听中…" : `试听 ${voice.display_name}`}
              </button>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            音色克隆后续支持；语速、音调等参数在供应商支持时可调。
          </p>
        </>
      )}
    </div>
  );
}

