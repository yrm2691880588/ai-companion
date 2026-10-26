import { useEffect, useState } from "react";
import { api } from "../api";
import type { Provider, ProviderSetting } from "../types";

interface Props {
  providers: Provider[];
  onChanged: () => void;
}

export default function ProviderSettingsList({ providers, onChanged }: Props) {
  const [settings, setSettings] = useState<Record<string, ProviderSetting>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  async function reload() {
    try {
      const list = await api.providerSettings();
      setSettings(Object.fromEntries(list.map((item) => [item.provider_key, item])));
    } catch (event) {
      setError((event as Error).message);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  function startEdit(provider: Provider) {
    const setting = settings[provider.key];
    setEditing(provider.key);
    setApiKey("");
    setBaseUrl(setting?.base_url ?? provider.base_url);
    setEnabled(setting?.enabled ?? true);
    setError("");
    setSaved("");
  }

  async function save() {
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      await api.saveProviderSetting(editing, {
        api_key: apiKey.trim() ? apiKey.trim() : undefined,
        base_url: baseUrl.trim() || null,
        enabled,
      });
      await reload();
      setEditing(null);
      setSaved("已保存，立即生效");
      window.setTimeout(() => setSaved(""), 2000);
      onChanged();
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function clearKey(providerKey: string) {
    setBusy(true);
    try {
      await api.saveProviderSetting(providerKey, { api_key: "" });
      await reload();
      onChanged();
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <div className="alert">{error}</div>}
      {saved && <div className="notice">{saved}</div>}
      <p className="muted">
        点击供应商卡片配置 API Key 与地址。Key 只保存在本机，加密存储，不会显示明文。
      </p>
      <div className="grid">
        {providers.map((provider) => {
          const setting = settings[provider.key];
          const hasKey = setting?.has_key ?? provider.has_key;
          const masked = setting?.masked_key ?? provider.masked_key;
          return (
            <div className="card" key={provider.key}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h3>{provider.name}</h3>
                <span className="chip">{hasKey ? "已配置" : "未配置"}</span>
              </div>
              <p className="muted">{setting?.base_url || provider.base_url}</p>
              <p className="muted">
                {provider.models.length} 个模型
                {hasKey ? ` · Key ${masked}` : " · 需要 API Key"}
              </p>
              <div>
                {provider.models.slice(0, 3).map((model) => (
                  <span className="tag" key={model.key}>
                    {model.model_name}
                  </span>
                ))}
              </div>
              <div className="toolbar">
                <button className="btn" onClick={() => startEdit(provider)}>
                  {hasKey ? "修改配置" : "配置 Key"}
                </button>
                {hasKey && (
                  <button className="btn ghost" disabled={busy} onClick={() => void clearKey(provider.key)}>
                    清除 Key
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={() => !busy && setEditing(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h2>配置供应商</h2>
            <p className="muted">
              只保存在本机；保存后立即生效，不需要重启。
            </p>
            {error && <div className="alert">{error}</div>}
            <label htmlFor="provider-key">API Key</label>
            <input
              id="provider-key"
              value={apiKey}
              placeholder="留空则不修改现有 Key"
              onChange={(event) => setApiKey(event.target.value)}
            />
            <label htmlFor="provider-url">Base URL</label>
            <input
              id="provider-url"
              value={baseUrl}
              placeholder="https://api.example.com/v1"
              onChange={(event) => setBaseUrl(event.target.value)}
            />
            <label className="muted" style={{ display: "block", marginTop: 10 }}>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />{" "}
              启用这个供应商
            </label>
            <div className="toolbar">
              <button className="primary" disabled={busy} onClick={() => void save()}>
                {busy ? "保存中…" : "保存"}
              </button>
              <button className="ghost" disabled={busy} onClick={() => setEditing(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
