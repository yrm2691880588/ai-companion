import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Cpu, KeyRound, Mic2, Wallet } from "lucide-react";
import { queries } from "../lib/queries";
import AdminSettingsCard from "../components/AdminSettingsCard";
import ProviderSettingsList from "../components/ProviderSettingsList";
import VoiceSettingsCard from "../components/VoiceSettingsCard";
import MicSettingsCard from "../components/MicSettingsCard";
import UsageCard from "../components/UsageCard";
import PageHeader from "../components/PageHeader";
import ErrorAlert from "../components/ErrorAlert";

/**
 * 设置页：只放「系统怎么运转」的配置。
 *
 * 分四个标签，按「谁需要改」而不是「功能属于哪个模块」来分：
 * - 模型：日常要看的模型参数（管理员改，普通用户只读）
 * - 用量：花了多少钱、花在哪（纯展示，和配置分开）
 * - 语音：配一次就不动，含麦克风（本机设备）
 * - 供应商：配一次就不动的密钥
 *
 * 之前「用量」和「模型参数」挤在同一个标签里：
 * 用户来调模型参数，却先撞上一段挤成小字的成本报表。
 *
 * 「我是谁 / 外观 / 关于」不在这里，属于「我的」页。
 *
 * 当前标签记在 URL 的 ?tab= 上：刷新后不会跳回第一个标签，
 * 也方便从别处直接链到某一类配置。
 */
type TabKey = "model" | "usage" | "voice" | "provider";

const TABS: { key: TabKey; label: string; icon: typeof Cpu; hint: string }[] = [
  { key: "model", label: "模型", icon: Cpu, hint: "日常对话与人设生成用哪个模型、温度多少" },
  { key: "usage", label: "用量", icon: Wallet, hint: "花了多少钱、花在哪个模型上" },
  { key: "voice", label: "语音与设备", icon: Mic2, hint: "她怎么说话、用哪个麦克风" },
  { key: "provider", label: "供应商", icon: KeyRound, hint: "API Key 与地址，加密存在本机" },
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
  const providers = providerQuery.data ?? [];
  const active = TABS.find((item) => item.key === tab);

  return (
    <div>
      <PageHeader
        title="设置"
        description="这里只放系统运行需要的配置；你的身份和外观在「我的」。"
      />

      <div className="tabs" role="tablist" aria-label="设置分类">
        {TABS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              role="tab"
              aria-selected={tab === item.key}
              className={tab === item.key ? "tab active" : "tab"}
              onClick={() => selectTab(item.key)}
            >
              <Icon size={15} aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </div>

      {/* 当前标签一句话说明，避免用户点进来不知道这页在配什么 */}
      {active && <p className="tab-hint">{active.hint}</p>}

      <ErrorAlert
        message={providerQuery.error?.message}
        onRetry={providerQuery.isError ? () => void providerQuery.refetch() : undefined}
      />

      {tab === "model" && <AdminSettingsCard />}

      {tab === "usage" && <UsageCard />}

      {tab === "voice" && (
        <>
          <VoiceSettingsCard />
          <MicSettingsCard />
        </>
      )}

      {tab === "provider" && <ProviderSettingsList providers={providers} />}
    </div>
  );
}
