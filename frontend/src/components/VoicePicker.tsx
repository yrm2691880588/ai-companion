import { useEffect, useState } from "react";
import { api } from "../api";
import { playAudio } from "../lib/voice";
import type { VoiceOption } from "../lib/types";

interface Props {
  companionId: number;
  value: string | null;
  onChange: (voiceId: string | null) => void;
}

export default function VoicePicker({ companionId, value, onChange }: Props) {
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [configured, setConfigured] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const providers = await api.voiceProviders();
        const ready = providers.some((item) => item.configured && item.enabled);
        setConfigured(ready);
        if (!ready) {
          setLoading(false);
          return;
        }
        setVoices(await api.voiceOptions("volcengine"));
      } catch (event) {
        setError((event as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function preview(voice: VoiceOption) {
    setPreviewing(voice.voice_id);
    try {
      const speech = await api.synthesize(
        `你好，我是${voice.display_name}，很高兴认识你。`,
        voice.voice_id,
      );
      playAudio(speech.audio_url, () => setPreviewing(null));
    } catch (event) {
      setError((event as Error).message);
      setPreviewing(null);
    }
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
      {error && <div className="alert">{error}</div>}
      {loading ? (
        <p className="muted">加载中…</p>
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

