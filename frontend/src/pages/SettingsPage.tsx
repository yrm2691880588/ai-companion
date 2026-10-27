import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import AdminSettingsCard from "../components/AdminSettingsCard";
import ProviderSettingsList from "../components/ProviderSettingsList";
import VoiceSettingsCard from "../components/VoiceSettingsCard";
import type { Provider, UsageSummary } from "../types";

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState("");

  async function reload() {
    try {
      const [list, summary] = await Promise.all([api.providers(), api.usage(7)]);
      setProviders(list);
      setUsage(summary);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const [list, summary] = await Promise.all([api.providers(), api.usage(7)]);
        setProviders(list);
        setUsage(summary);
      } catch (event) {
        setError((event as Error).message);
      }
    })();
  }, []);

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>模型与用量</h1>
          <p className="muted">本地版没有管理员，这些参数由你自己调整。</p>
        </div>
        <Link className="btn ghost" to="/me">
          回到我的
        </Link>
      </div>

      {error && <div className="alert">{error}</div>}

      <AdminSettingsCard />

      <VoiceSettingsCard />

      <h2 style={{ marginTop: 18 }}>供应商</h2>
      <ProviderSettingsList providers={providers} onChanged={() => void reload()} />
      <h2 style={{ marginTop: 18 }}>最近 7 天用量</h2>
      {usage ? (
        <div className="card">
          <p>
            调用 {usage.totals.calls} 次 · 输入 {usage.totals.input_tokens} tokens · 输出{" "}
            {usage.totals.output_tokens} tokens · 缓存命中{" "}
            {Math.round(usage.totals.hit_ratio * 100)}% · 成本 ¥
            {usage.totals.cost_cny.toFixed(4)}
          </p>
          {usage.by_model.map((item) => (
            <p className="muted" key={item.model_key}>
              {item.model_key}：{item.totals.calls} 次 · ¥{item.totals.cost_cny.toFixed(4)}
            </p>
          ))}
        </div>
      ) : (
        <p className="muted">加载中…</p>
      )}
    </div>
  );
}


