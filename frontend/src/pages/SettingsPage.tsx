import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Account, Provider, UsageSummary } from "../types";
import AdminSettingsCard from "../components/AdminSettingsCard";

export default function SettingsPage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const me = await api.me();
        setAccount(me);
        if (me.role !== "admin") return;
        const [list, summary] = await Promise.all([api.providers(), api.usage(7)]);
        setProviders(list);
        setUsage(summary);
      } catch (event) {
        setError((event as Error).message);
      }
    })();
  }, []);

  if (account && account.role !== "admin") {
    return (
      <div>
        <h1>模型与用量</h1>
        <div className="card">
          <p>这里只有管理员可以查看。模型参数由管理员统一配置，普通用户不需要理解这些概念。</p>
          <Link className="btn" to="/me">
            回到我的
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1>模型与用量</h1>
      <p className="muted">管理员专用：统一模型参数、供应商状态与最近用量。</p>

      {error && <div className="alert">{error}</div>}

      {account?.role === "admin" && <AdminSettingsCard />}

      <h2 style={{ marginTop: 18 }}>可用供应商</h2>
      <div className="grid">
        {providers.map((provider) => (
          <div className="card" key={provider.key}>
            <h3>{provider.name}</h3>
            <p className="muted">
              {provider.models.length} 个模型 ·{" "}
              {provider.has_key ? `Key ${provider.masked_key}` : "未配置 Key"}
            </p>
            <div>
              {provider.models.slice(0, 3).map((model) => (
                <span className="tag" key={model.key}>
                  {model.model_name}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

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
