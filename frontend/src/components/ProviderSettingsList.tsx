import { useEffect, useState } from "react";
import { api } from "../api";
import type { DiscoveredModel, Provider, ProviderSetting } from "../types";

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
  const [discovered, setDiscovered] = useState<DiscoveredModel[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState("");
  const [probeResult, setProbeResult] = useState("");

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
    setDiscovered([]);
    setDiscoverError("");
    setProbeResult("");
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

  async function probe() {
    if (!editing) return;
    setProbeResult("测试中…");
    try {
      const result = await api.probeProvider(editing);
      setProbeResult(result.ok ? `连接成功，可用模型 ${result.model_count} 个` : "连接失败");
    } catch (event) {
      setProbeResult((event as Error).message);
    }
  }

  async function importAll() {
    if (!editing || discovered.length === 0) return;
    setDiscovering(true);
    try {
      await api.importModels(
        editing,
        discovered.map((model) => model.id),
      );
      setSaved("已加入模型列表，可在上方下拉中选择");
      window.setTimeout(() => setSaved(""), 2500);
    } catch (event) {
      setDiscoverError((event as Error).message);
    } finally {
      setDiscovering(false);
    }
  }

  async function discover() {
    if (!editing) return;
    setDiscovering(true);
    setDiscoverError("");
    try {
      setDiscovered(await api.discoverModels(editing));
    } catch (event) {
      setDiscoverError((event as Error).message);
      setDiscovered([]);
    } finally {
      setDiscovering(false);
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
            <div className="toolbar" style={{ marginTop: 8 }}>
              <button className="ghost" disabled={discovering} onClick={() => void discover()}>
                {discovering ? "搜索中…" : "搜索该供应商的可用模型"}
              </button>
              <button className="ghost" onClick={() => void probe()}>
                测试连接
              </button>
            </div>
            {probeResult && <div className="notice">{probeResult}</div>}
            {discoverError && <div className="alert">{discoverError}</div>}
            {discovered.length > 0 && (
              <div className="discovered">
                <p className="muted">
                  找到 {discovered.length} 个模型（点击下方按钮加入本机模型列表）：
                </p>
                <div>
                  {discovered.map((model) => (
                    <span className="tag" key={model.id} title={model.owned_by}>
                      {model.id}
                    </span>
                  ))}
                </div>
                <div className="toolbar">
                  <button className="primary" disabled={discovering} onClick={() => void importAll()}>
                    全部加入模型列表
                  </button>
                </div>
              </div>
            )}

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



