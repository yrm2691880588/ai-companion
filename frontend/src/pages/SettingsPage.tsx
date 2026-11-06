import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { queries } from "../lib/queries";
import AdminSettingsCard from "../components/AdminSettingsCard";
import ProviderSettingsList from "../components/ProviderSettingsList";
import VoiceSettingsCard from "../components/VoiceSettingsCard";
import MicSettingsCard from "../components/MicSettingsCard";

/**
 * 设置页：只放「系统怎么运转」的配置。
 * 按使用频率与心智归类分成三个标签，避免一页堆到 2300px。
 *
 * - 模型与用量：日常要看的模型参数与花费
 * - 语音与设备：配一次就不动，含麦克风（本机设备）
 * - 供应商：配一次就不动的密钥
 *
 * 「我是谁 / 外观 / 关于」不在这里，属于「我的」页。
 *
 * 当前标签记在 URL 的 ?tab= 上：刷新后不会跳回第一个标签，
 * 也方便从别处直接链到某一类配置。
 */
type TabKey = "model" | "voice" | "provider";

const TABS: { key: TabKey; label: string }[] = [
  { key: "model", label: "模型与用量" },
  { key: "voice", label: "语音与设备" },
  { key: "provider", label: "供应商" },
];

const VALID_TABS = new Set<string>(TABS.map((item) => item.key));

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab") ?? "model";
  const tab: TabKey = VALID_TABS.has(requested) ? (requested as TabKey) : "model";

  function selectTab(next: TabKey) {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  }

  const providerQuery = useQuery(queries.providers());
  const usageQuery = useQuery(queries.usage());
  const providers = providerQuery.data ?? [];
  const usage = usageQuery.data;
  const error = providerQuery.error?.message || usageQuery.error?.message;

  return (
    <div>
      <h1>设置</h1>
      <p className="muted">这里只放系统运行需要的配置；你的身份和外观在「我的」。</p>

      {error && <div className="alert">{error}</div>}

      <div className="tabs" role="tablist" aria-label="设置分类">
        {TABS.map((item) => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            className={tab === item.key ? "tab active" : "tab"}
            onClick={() => selectTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "model" && (
        <>
          <AdminSettingsCard />
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
        </>
      )}

      {tab === "voice" && (
        <>
          <VoiceSettingsCard />
          <MicSettingsCard />
        </>
      )}

      {tab === "provider" && (
        <>
          <p className="muted" style={{ marginTop: 12 }}>
            点击供应商卡片配置 API Key 与地址。Key 只存在本机，加密保存，不会显示明文。
          </p>
          <ProviderSettingsList providers={providers} />
        </>
      )}
    </div>
  );
}
