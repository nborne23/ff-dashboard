import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Visual tweaks matching design/app.jsx's TWEAK_DEFAULTS. Persisted to
 * localStorage so layout/visual experiments survive a reload; `week` (below)
 * is intentionally left out of persistence.
 */
export interface Tweaks {
  sidebarWidth: number;
  teamCols: number;
  rowHeight: number;
  showInsights: boolean;
  sparkThickness: number;
  auroraIntensity: number;
}

export const TWEAK_DEFAULTS: Tweaks = {
  sidebarWidth: 240,
  teamCols: 2,
  rowHeight: 56,
  showInsights: true,
  sparkThickness: 1.5,
  auroraIntensity: 0.18,
};

/**
 * Settings' Preferences card notification toggles (task 7.4). Persisted so the choice
 * survives a reload, but functionally inert — there's no push-notification delivery
 * mechanism yet (Phase 8).
 */
export interface Notifications {
  scoreChange: boolean;
  redzone: boolean;
  finalScore: boolean;
}

export const NOTIFICATION_DEFAULTS: Notifications = {
  scoreChange: true,
  redzone: true,
  finalScore: true,
};

export type Theme = "dark" | "light" | "auto";

/**
 * Settings' Appearance card (task 7.5). Decorative for v1: the selection is persisted
 * but nothing reads it to actually change the rendered theme/accent yet.
 */
export interface Appearance {
  theme: Theme;
  accentColor: string;
}

export const APPEARANCE_DEFAULTS: Appearance = {
  theme: "dark",
  accentColor: "#FF2D55",
};

interface UiState {
  week: number;
  setWeek: (week: number) => void;
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(key: K, value: Tweaks[K]) => void;
  notifications: Notifications;
  setNotification: <K extends keyof Notifications>(key: K, value: Notifications[K]) => void;
  appearance: Appearance;
  setTheme: (theme: Theme) => void;
  setAccentColor: (accentColor: string) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      week: 1,
      setWeek: (week) => set({ week }),
      tweaks: TWEAK_DEFAULTS,
      setTweak: (key, value) => set((state) => ({ tweaks: { ...state.tweaks, [key]: value } })),
      notifications: NOTIFICATION_DEFAULTS,
      setNotification: (key, value) =>
        set((state) => ({ notifications: { ...state.notifications, [key]: value } })),
      appearance: APPEARANCE_DEFAULTS,
      setTheme: (theme) => set((state) => ({ appearance: { ...state.appearance, theme } })),
      setAccentColor: (accentColor) =>
        set((state) => ({ appearance: { ...state.appearance, accentColor } })),
    }),
    {
      name: "gridiron-ui-tweaks",
      partialize: (state) => ({
        tweaks: state.tweaks,
        notifications: state.notifications,
        appearance: state.appearance,
      }),
    },
  ),
);
