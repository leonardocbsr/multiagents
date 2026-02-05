export type ThemeMode = "dark" | "light" | "system";
export type ThemeAccent = "cyan" | "emerald" | "amber";
export type ThemeDensity = "compact" | "cozy";

export interface ThemeConfig {
  mode: ThemeMode;
  accent: ThemeAccent;
  density: ThemeDensity;
}

const FALLBACK: ThemeConfig = {
  mode: "dark",
  accent: "cyan",
  density: "cozy",
};

export function normalizeThemeConfig(raw?: Partial<ThemeConfig>): ThemeConfig {
  const mode = raw?.mode === "light" || raw?.mode === "system" || raw?.mode === "dark" ? raw.mode : FALLBACK.mode;
  const accent = raw?.accent === "emerald" || raw?.accent === "amber" || raw?.accent === "cyan" ? raw.accent : FALLBACK.accent;
  const density = raw?.density === "compact" || raw?.density === "cozy" ? raw.density : FALLBACK.density;
  return { mode, accent, density };
}

export function resolveThemeMode(mode: ThemeMode): "dark" | "light" {
  if (mode !== "system") return mode;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyThemeAttributes(config: ThemeConfig) {
  const root = document.documentElement;
  root.setAttribute("data-theme", resolveThemeMode(config.mode));
  root.setAttribute("data-accent", config.accent);
  root.setAttribute("data-density", config.density);
}
