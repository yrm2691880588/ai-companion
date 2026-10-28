import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { Link } from "react-router-dom";
import AdminSettingsCard from "../components/AdminSettingsCard";
import ProviderSettingsList from "../components/ProviderSettingsList";
import VoiceSettingsCard from "../components/VoiceSettingsCard";

export default function SettingsPage() {
  const providerQuery = useQuery(queries.providers());
  const usageQuery = useQuery(queries.usage());
  const providers = providerQuery.data ?? [];
  const usage = usageQuery.data;
  const error = providerQuery.error?.message || usageQuery.error?.message;

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
      <ProviderSettingsList providers={providers} />
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



