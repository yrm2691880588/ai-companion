import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getUserId, setUserId } from "../api";
import type { Account, Provider, UsageSummary } from "../types";

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [user, setUser] = useState(getUserId());
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const [list, summary, me] = await Promise.all([
          api.providers(),
          api.usage(7),
          api.me().catch(() => null),
        ]);
        setProviders(list);
        setUsage(summary);
        setAccount(me);
      } catch (event) {
        setError((event as Error).message);
      }
    })();
  }, []);

  async function logout() {
    try {
      await api.logout();
      setAccount(null);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <div>
      <h1>模型与服务</h1>
      <p className="muted">
        默认 DeepSeek 官方，也可接多家预设与本地模型；这里展示当前可用供应商与最近 7 天用量。
      </p>

      {error && <div className="alert">{error}</div>}

      <div className="card">
        <h2>登录状态</h2>
        {account?.phone_masked ? (
          <p>
            已登录：{account.phone_masked}
            <button className="ghost" style={{ marginLeft: 10 }} onClick={() => void logout()}>
              退出登录
            </button>
          </p>
        ) : (
          <p className="muted">未登录。开发模式下可以继续用下面的「开发用户」浏览数据。</p>
        )}
        <Link className="btn" to="/login">
          去登录
        </Link>
        <a className="btn ghost" style={{ marginLeft: 8 }} href="/v1/me/export" target="_blank" rel="noreferrer">
          导出我的数据（JSON）
        </a>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h2>开发用户</h2>
        <p className="muted">
          开发模式用 X-User-Id 模拟登录（生产必须关闭 AI_COMPANION_DEBUG_AUTH）。改这里可以切换数据归属。
        </p>
        <div className="composer">
          <input value={user} onChange={(event) => setUser(event.target.value)} />
          <button
            className="primary"
            onClick={() => {
              setUserId(user);
              setSaved(true);
              window.setTimeout(() => setSaved(false), 1500);
            }}
          >
            保存
          </button>
        </div>
        {saved && <div className="notice">已保存，刷新页面生效。</div>}
      </div>

      <h2 style={{ marginTop: 18 }}>可用供应商</h2>
      <div className="grid">
        {providers.map((provider) => (
          <div className="card" key={provider.key}>
            <h3>{provider.name}</h3>
            <p className="muted">{provider.base_url}</p>
            <p className="muted">
              协议 {provider.kind} · 模型 {provider.models.length} 个 ·{" "}
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
              {item.model_key}：{item.totals.calls} 次 · ¥{item.totals.cost_cny.toFixed(4)} ·
              首字均值 {item.avg_first_token_ms ?? "-"} ms
            </p>
          ))}
        </div>
      ) : (
        <p className="muted">加载中…</p>
      )}
    </div>
  );
}
