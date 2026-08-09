// "Appearance" settings-group — matches design/screen-settings.jsx's Appearance group.
// Decorative for v1 (task 7.5): the theme/accent selection is persisted in the zustand
// ui store's persisted partition, but nothing actually reads it to re-theme the app —
// there's no theme engine yet.

import type { Theme } from "../../stores/ui";
import { useUiStore } from "../../stores/ui";
import { SettingsRow } from "./SettingsRow";

const THEMES: Array<{ value: Theme; label: string }> = [
  { value: "dark", label: "Dark" },
  { value: "light", label: "Light" },
  { value: "auto", label: "Auto" },
];

// Ported straight from design/screen-settings.jsx's accent swatch list.
const ACCENT_COLORS = ["#FF2D55", "#30D158", "#64D2FF", "#FF9F0A", "#BF5AF2"];

export function AppearanceCard() {
  const theme = useUiStore((s) => s.appearance.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const accentColor = useUiStore((s) => s.appearance.accentColor);
  const setAccentColor = useUiStore((s) => s.setAccentColor);

  return (
    <div className="settings-group">
      <h3>Appearance</h3>
      <SettingsRow
        label="Theme"
        right={
          <div className="segmented">
            {THEMES.map((t) => (
              <button
                key={t.value}
                type="button"
                className={t.value === theme ? "active" : ""}
                onClick={() => setTheme(t.value)}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
      />
      <SettingsRow
        label="Accent color"
        right={
          <div style={{ display: "flex", gap: 8 }}>
            {ACCENT_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={`Accent color ${color}`}
                aria-pressed={color === accentColor}
                onClick={() => setAccentColor(color)}
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  background: color,
                  border: color === accentColor ? "2px solid #fff" : "2px solid transparent",
                  cursor: "pointer",
                  padding: 0,
                  appearance: "none",
                }}
              />
            ))}
          </div>
        }
      />
    </div>
  );
}
