import { useEffect, useState } from "react";
import { api } from "../api";
import type { VoiceProvider } from "../types";

const GUIDE_STEPS = [
  {
    title: "1. 登录火山引擎控制台",
    detail: "打开 console.volcengine.com，用手机号或账号登录。",
  },
  {
    title: "2. 开通语音技术",
    detail: "在控制台搜索「语音技术」或「豆包语音」，进入后按提示开通（有免费额度试）。",
  },
  {
    title: "3. 创建应用",
    detail: "在语音技术控制台里创建一个应用，勾选「语音合成」与「语音识别」两个能力。",
  },
  {
    title: "4. 复制 AppID 与 Access Token",
    detail: "应用详情里能看到 AppID 和一串 Access Token，两个都要复制下来。",
  },
  {
    title: "5. 回到这里粘贴保存",
    detail: "把 AppID 与 Token 填进下面的输入框，点保存，再点「测试连接」确认通了。",
  },
];

export default function VoiceSettingsCard() {
  const [providers, setProviders] = useState<VoiceProvider[]>([]);
  const [appId, setAppId] = useState("");
  const [token, setToken] = useState("");
  const [cluster, setCluster] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showGuide, setShowGuide] = useState(false);

  async function reload() {
    try {
      const list = await api.voiceProviders();
      setProviders(list);
      const volc = list.find((item) => item.key === "volcengine");
      if (volc?.app_id) setAppId(volc.app_id);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await api.saveVoiceProvider("volcengine", {
        app_id: appId.trim(),
        token: token.trim() || undefined,
        cluster: cluster.trim() || undefined,
      });
      await reload();
      setToken("");
      setMessage("已保存，可以点「测试连接」验证");
      window.setTimeout(() => setMessage(""), 2500);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function probe() {
    setBusy(true);
    setError("");
    try {
      const result = await api.probeVoiceProvider("volcengine");
      setMessage(
        result.ok ? `连接成功，拿到 ${result.voice_count ?? 0} 个音色` : "连接失败，检查 AppID 与 Token",
      );
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const volc = providers.find((item) => item.key === "volcengine");

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h2>语音</h2>
      <p className="muted">
        语音对话需要单独的供应商：你说话它识别成文字，她回复时合成语音。Key 只存在本机，加密保存。
      </p>

      {error && <div className="alert">{error}</div>}
      {message && <div className="notice">{message}</div>}

      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h3>火山引擎（豆包语音）</h3>
        <span className="chip">{volc?.configured ? "已配置" : "未配置"}</span>
      </div>

      <div className="field-grid">
        <div>
          <label htmlFor="voice-appid">AppID</label>
          <input
            id="voice-appid"
            value={appId}
            placeholder="控制台里的 AppID"
            onChange={(event) => setAppId(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="voice-token">Access Token</label>
          <input
            id="voice-token"
            type="password"
            value={token}
            placeholder={volc?.configured ? "留空则不修改" : "控制台里的 Access Token"}
            onChange={(event) => setToken(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="voice-cluster">Cluster（可选）</label>
          <input
            id="voice-cluster"
            value={cluster}
            placeholder="例如 volcano_tts"
            onChange={(event) => setCluster(event.target.value)}
          />
        </div>
      </div>

      <div className="toolbar">
        <button className="primary" disabled={busy} onClick={() => void save()}>
          {busy ? "保存中…" : "保存"}
        </button>
        <button className="ghost" disabled={busy || !volc?.configured} onClick={() => void probe()}>
          测试连接
        </button>
        <button className="ghost" onClick={() => setShowGuide(!showGuide)}>
          {showGuide ? "收起教程" : "怎么拿到 AppID 和 Token？"}
        </button>
        <a
          className="btn ghost"
          href="https://console.volcengine.com/speech/app"
          target="_blank"
          rel="noreferrer"
        >
          打开火山控制台
        </a>
      </div>

      {showGuide && (
        <div className="notice" style={{ marginTop: 10 }}>
          <ol style={{ paddingLeft: 20 }}>
            {GUIDE_STEPS.map((step) => (
              <li key={step.title} style={{ marginBottom: 8 }}>
                <strong>{step.title}</strong>
                <div className="muted">{step.detail}</div>
              </li>
            ))}
          </ol>
          <p className="muted">
            提示：开通语音服务可能产生费用，按你的实际用量由火山计费；本产品不代收、不加价。
          </p>
        </div>
      )}
    </div>
  );
}
