import { useEffect, useState } from "react";
import { api } from "../api";
import type { AdminSettingsResponse, ModelDefaults } from "../types";

export default function AdminSettingsCard() {
  const [admin, setAdmin] = useState<AdminSettingsResponse | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .adminSettings()
      .then(setAdmin)
      .catch((event) => setError((event as Error).message));
  }, []);

  function patchTask(task: string, patch: Partial<ModelDefaults>) {
    setAdmin((prev) => {
      if (!prev) return prev;
      const current = prev.settings.model_defaults[task];
      return {
        ...prev,
        settings: {
          ...prev.settings,
          model_defaults: {
            ...prev.settings.model_defaults,
            [task]: { ...current, ...patch },
          },
        },
      };
    });
  }

  async function save() {
    if (!admin) return;
    setError("");
    try {
      setAdmin(await api.adminUpdate(admin.settings));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  if (!admin) {
    return <p className="muted">{error || "加载管理员设置…"}</p>;
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <h2>管理员设置</h2>
      <p className="muted">统一控制额度开关与默认模型参数；普通用户看不到这一块。</p>
      {error && <div className="alert">{error}</div>}
      <label className="muted">
        <input
          type="checkbox"
          checked={admin.settings.quota.enforced}
          onChange={(event) =>
            setAdmin({
              ...admin,
              settings: {
                ...admin.settings,
                quota: { ...admin.settings.quota, enforced: event.target.checked },
              },
            })
          }
        />{" "}
        启用每日额度（关闭时仍记录轮次）
      </label>
      <div className="composer" style={{ marginTop: 8 }}>
        <label className="muted" style={{ alignSelf: "center" }}>
          每日上限
        </label>
        <input
          type="number"
          min={1}
          max={10000}
          value={admin.settings.quota.daily_limit}
          onChange={(event) =>
            setAdmin({
              ...admin,
              settings: {
                ...admin.settings,
                quota: {
                  ...admin.settings.quota,
                  daily_limit: Number(event.target.value),
                },
              },
            })
          }
        />
      </div>

      {(["chat_main", "persona_generate"] as const).map((task) => {
        const item = admin.settings.model_defaults[task];
        const label = task === "chat_main" ? "日常对话" : "人设生成";
        return (
          <div key={task} style={{ marginTop: 14 }}>
            <h3>{label}</h3>
            <div className="composer">
              <select
                value={item.model}
                onChange={(event) => patchTask(task, { model: event.target.value })}
              >
                <option value="">跟随系统路由</option>
                {admin.models.map((model) => (
                  <option key={model.key} value={model.key}>
                    {model.display_name}
                  </option>
                ))}
              </select>
              <input
                type="number"
                step="0.1"
                min={0}
                max={2}
                value={item.temperature}
                onChange={(event) =>
                  patchTask(task, { temperature: Number(event.target.value) })
                }
              />
              <input
                type="number"
                min={32}
                max={4096}
                value={item.max_tokens}
                onChange={(event) => patchTask(task, { max_tokens: Number(event.target.value) })}
              />
              <input
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={item.top_p ?? 0.95}
                onChange={(event) => patchTask(task, { top_p: Number(event.target.value) })}
              />
              <label className="muted" style={{ alignSelf: "center" }}>
                <input
                  type="checkbox"
                  checked={item.thinking}
                  onChange={(event) => patchTask(task, { thinking: event.target.checked })}
                />{" "}
                思考模式
              </label>
            </div>
            <p className="muted">
              温度 {item.temperature} · top_p {item.top_p ?? 0.95} · 最大输出 {item.max_tokens}{" "}
              tokens
            </p>
          </div>
        );
      })}

      <div className="toolbar">
        <button className="primary" onClick={() => void save()}>
          保存管理员设置
        </button>
        {saved && <span className="muted">已保存</span>}
      </div>
    </div>
  );
}
