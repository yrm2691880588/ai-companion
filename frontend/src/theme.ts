export interface ThemePreset {
  key: string;
  name: string;
  accent: string;
}

export interface ThemeState {
  preset: string;
  custom: string;
}

const STORAGE_KEY = "ui.theme";

export const PRESETS: ThemePreset[] = [
  { key: "rose", name: "玫瑰恋爱", accent: "#C63B69" },
  { key: "peach", name: "蜜桃日落", accent: "#D9603B" },
  { key: "sakura", name: "樱花紫", accent: "#B84A8C" },
  { key: "latte", name: "奶咖拿铁", accent: "#A56A4A" },
  { key: "mint", name: "薄荷初雪", accent: "#2F8F7A" },
  { key: "dusk", name: "暮色蓝", accent: "#5B6FB5" },
];

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((item) => item + item)
          .join("")
      : value;
  const rgb = [0, 2, 4].map((index) => {
    const channel = parseInt(full.slice(index, index + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
}

export function contrastRatio(a: string, b: string): number {
  const light = Math.max(luminance(a), luminance(b));
  const dark = Math.min(luminance(a), luminance(b));
  return (light + 0.05) / (dark + 0.05);
}

export function onAccent(hex: string): string {
  const white = contrastRatio(hex, "#FFFFFF");
  const dark = contrastRatio(hex, "#2C2430");
  return white >= dark ? "#FFFFFF" : "#2C2430";
}

export function loadTheme(): ThemeState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { preset: "rose", custom: "" };
    const parsed = JSON.parse(raw) as Partial<ThemeState>;
    return {
      preset: typeof parsed.preset === "string" ? parsed.preset : "rose",
      custom: typeof parsed.custom === "string" ? parsed.custom : "",
    };
  } catch {
    return { preset: "rose", custom: "" };
  }
}

export function applyTheme(state: ThemeState): void {
  const root = document.documentElement;
  const preset = PRESETS.find((item) => item.key === state.preset) ?? PRESETS[0];
  root.dataset.theme = preset.key;

  const accent = state.custom;
  if (accent) {
    root.dataset.theme = "custom";
    root.style.setProperty("--accent", accent);
    root.style.setProperty("--accent-2", accent);
    root.style.setProperty("--accent-soft", `color-mix(in srgb, ${accent} 13%, white)`);
    root.style.setProperty("--on-accent", onAccent(accent));
  } else {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-2");
    root.style.removeProperty("--accent-soft");
    root.style.removeProperty("--on-accent");
  }
}

export function saveTheme(state: ThemeState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // 隐私模式禁用 localStorage 时只应用不持久化
  }
  applyTheme(state);
}
