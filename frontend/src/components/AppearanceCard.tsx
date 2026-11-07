import { useState } from "react";
import { Check } from "lucide-react";
import { PRESETS, loadTheme, saveTheme, type ThemeState } from "../lib/theme";

/**
 * 外观设置。
 *
 * 主题按钮原来是六个只有名字的胶囊，用户点之前不知道那是什么颜色，
 * 得逐个试。改成色块 + 名字：每个主题用自身主色画一个圆点，
 * 一眼能看出差别，也不用点开才知道效果。
 */
export default function AppearanceCard() {
  const [theme, setTheme] = useState<ThemeState>(() => loadTheme());
  const [echo, setEcho] = useState(() => localStorage.getItem("ai-companion-echo") !== "off");

  return (
    <div className="card">
      <h2>外观</h2>
      <p className="muted">换主色不影响内容；按钮文字会自动选黑/白保证可读。</p>

      <div className="theme-grid" role="group" aria-label="主题">
        {PRESETS.map((preset) => {
          const active = theme.preset === preset.key && !theme.custom;
          return (
            <button
              key={preset.key}
              className={`theme-swatch${active ? " active" : ""}`}
              aria-pressed={active}
              onClick={() => {
                const next: ThemeState = { preset: preset.key, custom: "" };
                setTheme(next);
                saveTheme(next);
              }}
            >
              <span
                className="theme-swatch-dot"
                style={{ background: preset.accent }}
                aria-hidden="true"
              >
                {active && <Check size={12} strokeWidth={3} />}
              </span>
              <span className="theme-swatch-name">{preset.name}</span>
            </button>
          );
        })}
      </div>

      <div className="appearance-row">
        <label htmlFor="custom-accent">自定义主色</label>
        <input
          id="custom-accent"
          type="color"
          value={theme.custom || "#C63B69"}
          onChange={(event) => {
            const next: ThemeState = { preset: theme.preset, custom: event.target.value };
            setTheme(next);
            saveTheme(next);
          }}
        />
        {theme.custom && (
          <button
            className="ghost"
            onClick={() => {
              const next: ThemeState = { preset: "rose", custom: "" };
              setTheme(next);
              saveTheme(next);
            }}
          >
            恢复默认
          </button>
        )}
      </div>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={echo}
          onChange={(event) => {
            const next = event.target.checked;
            setEcho(next);
            localStorage.setItem("ai-companion-echo", next ? "on" : "off");
          }}
        />
        在回复下方显示「她想起了…」
      </label>
    </div>
  );
}
