import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { Coins, MessageSquare, Timer, Zap } from "lucide-react";
import ErrorAlert from "./ErrorAlert";

/**
 * 用量与花费。
 *
 * 原来这块是设置页底部一段挤在一起的灰字：
 * 「调用 90 次 · 输入 52138 tokens · 输出 3842 tokens · 缓存命中 25% · 成本 ¥0.1069」
 * 用户既看不出趋势，也不知道哪个模型在花钱。
 *
 * 现在拆成：四个关键数字 + 按天趋势 + 按模型明细。
 * 只做展示，不发任何写请求。
 */
function money(value: number): string {
  if (value === 0) return "¥0";
  if (value < 0.01) return `¥${value.toFixed(4)}`;
  return `¥${value.toFixed(2)}`;
}

function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export default function UsageCard() {
  const usageQuery = useQuery(queries.usage());
  const usage = usageQuery.data;

  if (usageQuery.isPending) {
    return (
      <div className="card">
        <p className="muted">加载用量…</p>
      </div>
    );
  }

  if (usageQuery.isError) {
    return (
      <div className="card">
        <ErrorAlert message={`用量读取失败：${usageQuery.error.message}`} variant="inline" />
      </div>
    );
  }

  if (!usage) return null;

  const { totals, by_model, daily } = usage;
  const peak = Math.max(...daily.map((item) => item.cost_cny), 0.0001);

  /**
   * 后端只返回「有调用的那天」。
   * 直接渲染会出现：连着两周没聊，图里只有两根柱子挤在角落，
   * 看起来像坏了。这里补全整段日期，没数据的那天高度为 0。
   */
  const filled = (() => {
    const map = new Map(daily.map((item) => [item.day, item]));
    const key = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const out: { day: string; calls: number; cost_cny: number }[] = [];
    for (let i = usage.days - 1; i >= 0; i -= 1) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const k = key(d);
      out.push(map.get(k) ?? { day: k, calls: 0, cost_cny: 0 });
    }
    return out;
  })();

  return (
    <>
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-icon" aria-hidden="true">
            <MessageSquare size={15} />
          </span>
          <span className="stat-value">{totals.calls}</span>
          <span className="stat-label">最近 {usage.days} 天调用</span>
        </div>
        <div className="stat-card">
          <span className="stat-icon" aria-hidden="true">
            <Coins size={15} />
          </span>
          <span className="stat-value">{money(totals.cost_cny)}</span>
          <span className="stat-label">总花费</span>
        </div>
        <div className="stat-card">
          <span className="stat-icon" aria-hidden="true">
            <Zap size={15} />
          </span>
          <span className="stat-value">{Math.round(totals.hit_ratio * 100)}%</span>
          <span className="stat-label">缓存命中</span>
        </div>
        <div className="stat-card">
          <span className="stat-icon" aria-hidden="true">
            <Timer size={15} />
          </span>
          <span className="stat-value">
            {compact(totals.input_tokens + totals.output_tokens)}
          </span>
          <span className="stat-label">字词量（输入+输出）</span>
        </div>
      </div>

      {filled.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>每天花费</h2>
          <p className="muted">柱子高度按当天成本比例，鼠标悬停可看具体数值。</p>
          <div className="usage-bars">
            {filled.map((item) => (
              <div className="usage-bar-col" key={item.day}>
                <div
                  className={`usage-bar${item.cost_cny === 0 ? " empty" : ""}`}
                  style={{ height: `${Math.max(2, (item.cost_cny / peak) * 100)}%` }}
                  title={
                    item.cost_cny === 0
                      ? `${item.day}：没有调用`
                      : `${item.day}：${item.calls} 次，${money(item.cost_cny)}`
                  }
                />
                <span className="usage-bar-label">
                  {new Date(item.day).getMonth() + 1}/{new Date(item.day).getDate()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {by_model.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>按模型</h2>
          <table className="usage-table">
            <thead>
              <tr>
                <th>模型</th>
                <th>调用</th>
                <th>花费</th>
                <th>首字延迟</th>
              </tr>
            </thead>
            <tbody>
              {by_model.map((item) => (
                <tr key={item.model_key}>
                  <td className="usage-model">{item.model_key}</td>
                  <td>{item.totals.calls}</td>
                  <td>{money(item.totals.cost_cny)}</td>
                  <td>{item.avg_first_token_ms ? `${item.avg_first_token_ms} ms` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totals.calls === 0 && (
        <p className="muted" style={{ marginTop: 12 }}>
          还没有调用记录。聊几句之后这里就会有数据。
        </p>
      )}
    </>
  );
}
