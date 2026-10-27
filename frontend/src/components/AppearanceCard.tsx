import { useState } from "react";
import { PRESETS, loadTheme, saveTheme, type ThemeState } from "../lib/theme";

export default function AppearanceCard() {
  const [theme, setTheme] = useState<ThemeState>(() => loadTheme());
  const [echo, setEcho] = useState(() => localStorage.getItem("ai-companion-echo") !== "off");

  return (
    <div className="card">
      <h2>外观</h2>
      <p className="muted">默认粉色恋爱主题，可换主色；按钮文字会自动选黑/白保证可读。</p>
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
      <label className="muted" style={{ display: "block", marginTop: 12 }}>
        <input
          type="checkbox"
          checked={echo}
          onChange={(event) => {
            const next = event.target.checked;
            setEcho(next);
            localStorage.setItem("ai-companion-echo", next ? "on" : "off");
          }}
        />{" "}
        在回复下方显示“她想起了…”
      </label>

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
  );
}


