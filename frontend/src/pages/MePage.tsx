import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { Link } from "react-router-dom";
import AppearanceCard from "../components/AppearanceCard";
import UserProfileForm from "../components/UserProfileForm";

export default function MePage() {
  const providerQuery = useQuery(queries.providers());
  const usageQuery = useQuery(queries.usage());
  const providers = providerQuery.data ?? [];
  const usage = usageQuery.data;
  const error = providerQuery.error?.message || usageQuery.error?.message;

  return (
    <div>
      <h1>我的</h1>
      <p className="muted">身份、外观、模型与数据都在这台机器上，不需要登录。</p>

      {error && <div className="alert">{error}</div>}

      <div style={{ marginTop: 12 }}>
        <UserProfileForm
          title="我的身份"
          description="她默认会知道这些信息：怎么称呼你、你做什么、多大、在哪。不同伴侣可以单独覆盖。"
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <AppearanceCard />
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h2>模型</h2>
        <p className="muted">
          默认使用 DeepSeek V4.1 Flash；可以在这里调整温度、top_p、思考模式等参数。
        </p>
        <div className="toolbar">
          <Link className="btn" to="/settings">
            模型与用量
          </Link>
          <a className="btn ghost" href="/v1/me/export" target="_blank" rel="noreferrer">
            导出我的数据（JSON）
          </a>
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h2>可用供应商</h2>
        <p className="muted">共 {providers.length} 家；未配置 Key 的供应商不会出现在对话路由里。</p>
        <div>
          {providers.slice(0, 6).map((provider) => (
            <span className="tag" key={provider.key}>
              {provider.name}
            </span>
          ))}
        </div>
      </div>

      {usage && (
        <div className="card" style={{ marginTop: 12 }}>
          <h2>最近 7 天用量</h2>
          <p className="muted">
            调用 {usage.totals.calls} 次 · 成本 ¥{usage.totals.cost_cny.toFixed(4)} · 缓存命中{" "}
            {Math.round(usage.totals.hit_ratio * 100)}%
          </p>
        </div>
      )}

      <div className="card" style={{ marginTop: 12 }}>
        <h2>关于</h2>
        <p className="muted">AI 伴侣系统 v0.1.0 · 本地开源版，数据只存在本机。</p>
        <p className="muted">遇到危机时，请拨打全国心理援助热线 12356，紧急情况拨打 120。</p>
      </div>
    </div>
  );
}

