import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getUserId, setUserId } from "../api";
import { PRESETS, loadTheme, saveTheme, type ThemeState } from "../theme";
import type {
  Account,
  AdminSettingsResponse,
  ModelDefaults,
  Provider,
  UsageSummary,
} from "../types";

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [admin, setAdmin] = useState<AdminSettingsResponse | null>(null);
  const [adminSaved, setAdminSaved] = useState(false);
  const [adminError, setAdminError] = useState("");
  const [theme, setTheme] = useState<ThemeState>(() => loadTheme());
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
        if (me?.role === "admin") {
          setAdmin(await api.adminSettings());
        }
      } catch (event) {
        setError((event as Error).message);
      }
    })();
  }, []);

  async function logout() {
    try {
      await api.logout();
      setAccount(null);
      setAdmin(null);
    } catch (event) {
      setError((event as Error).message);
    }
  }

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

  async function saveAdmin() {
    if (!admin) return;
    setAdminError("");
    try {
      const result = await api.adminUpdate(admin.settings);
      setAdmin(result);
      setAdminSaved(true);
      window.setTimeout(() => setAdminSaved(false), 1500);
    } catch (event) {
      setAdminError((event as Error).message);
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
        <h2>外观</h2>
        <p className="muted">
          默认粉色恋爱主题，可换主色；按钮文字会自动选黑/白保证可读。
        </p>
        <div className="row">
          {PRESETS.map((preset) => (
            <button
              key={preset.key}
              className={theme.preset === preset.key && !theme.custom ? "primary" : ""}
              onClick={() => {
                const next: ThemeState = { preset: preset.key, custom: "" };
                setTheme(next);
                saveTheme(next);
              }}
            >
              {preset.name}
            </button>
          ))}
        </div>
        <div className="composer" style={{ marginTop: 10 }}>
          <label className="muted" style={{ alignSelf: "center" }}>
            自定义主色
          </label>
          <input
            type="color"
            value={theme.custom || "#C63B69"}
            onChange={(event) => {
              const next: ThemeState = { preset: theme.preset, custom: event.target.value };
              setTheme(next);
              saveTheme(next);
            }}
            style={{ width: 64, height: 36, padding: 2, flex: "none" }}
          />
          <button
            className="ghost"
            onClick={() => {
              const next: ThemeState = { preset: "rose", custom: "" };
              setTheme(next);
              saveTheme(next);
            }}
          >
            恢复默认粉色
          </button>
        </div>
      </div>

      {account?.role === "admin" && admin && (
        <div className="card" style={{ marginTop: 12 }}>
          <h2>管理员设置</h2>
          <p className="muted">统一控制额度开关与默认模型参数；普通用户看不到这一块。</p>
          {adminError && <div className="alert">{adminError}</div>}
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
            启用每日额度（关闭时仍记录轮次，供稳定性测试观察）
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
                    onChange={(event) =>
                      patchTask(task, { max_tokens: Number(event.target.value) })
                    }
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
                  温度 {item.temperature} · 最大输出 {item.max_tokens} tokens
                </p>
              </div>
            );
          })}

          <div className="toolbar">
            <button className="primary" onClick={() => void saveAdmin()}>
              保存管理员设置
            </button>
            {adminSaved && <span className="muted">已保存</span>}
          </div>
        </div>
      )}

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
