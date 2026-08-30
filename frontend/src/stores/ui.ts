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

/** The four Game Day arrangements (design D8). */
export type GameDayMode = "g2" | "g3" | "c4" | "spot";

/** Auto-sort modes. `"manual"` and an auto mode are mutually exclusive states. */
export type GameDaySortMode = "manual" | "margin" | "live";

export interface GameDaySpan {
  cols: 1 | 2;
  rows: 1 | 2;
}

/**
 * The Game Day stage layout, persisted so a wall display restored by the LaunchAgent
 * comes back arranged the way it was left (design D8).
 *
 * `openIds` is a `string[]`, never a `Set` — a `Set` does not survive the JSON
 * round-trip this store's `persist` middleware does, and would rehydrate as `{}`.
 * `order` holds team ids and is reconciled against the live envelope on every read
 * (see screens/GameDay/arrangement.ts) rather than trusted as-is.
 */
export interface GameDayLayout {
  mode: GameDayMode;
  order: string[];
  spans: Record<string, GameDaySpan>;
  /** Panels the user explicitly opened, overriding the container query. */
  openIds: string[];
  /**
   * Panels the user explicitly shut. A second list rather than a flag on `openIds`
   * because the override is genuinely three-valued: open, shut, and "no preference —
   * let the container query decide", which is the default and cannot be represented by
   * a single list's absence-means-closed. Without it the spec's "overrides the
   * container query in both directions" is unreachable: a panel wide enough for the
   * query to open could never be closed again.
   */
  shutIds: string[];
  sortMode: GameDaySortMode;
}

export const GAME_DAY_DEFAULTS: GameDayLayout = {
  mode: "g3",
  order: [],
  spans: {},
  openIds: [],
  shutIds: [],
  sortMode: "manual",
};

/**
 * Width of the sidebar when collapsed to icons only — the same 56px the <1024px
 * responsive rule in global.css already uses, so the manual collapse and the automatic
 * one land on identical geometry instead of two near-identical widths.
 */
export const COLLAPSED_SIDEBAR_W = 56;

interface UiState {
  week: number;
  setWeek: (week: number) => void;
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(key: K, value: Tweaks[K]) => void;
  /**
   * Icon-only sidebar. Persisted deliberately: the iMac wall display is set up once and
   * restarted by a LaunchAgent, so a collapse that reset on every restart would have to
   * be redone every time the machine came back.
   */
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  /**
   * Off-canvas nav drawer, phone only. Deliberately NOT persisted (absent from
   * `partialize`): a drawer that reopens itself on every load would cover the screen
   * the app exists to show. `sidebarCollapsed` above is the opposite case — that one
   * is a deliberate setup choice and does persist.
   */
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
  notifications: Notifications;
  setNotification: <K extends keyof Notifications>(key: K, value: Notifications[K]) => void;
  appearance: Appearance;
  setTheme: (theme: Theme) => void;
  setAccentColor: (accentColor: string) => void;
  gameDay: GameDayLayout;
  setGameDayMode: (mode: GameDayMode) => void;
  setGameDayOrder: (order: string[]) => void;
  setGameDaySpan: (id: string, span: GameDaySpan) => void;
  setGameDayOpenIds: (openIds: string[]) => void;
  setGameDayShutIds: (shutIds: string[]) => void;
  /** Record one panel's explicit disclosure choice, or clear it back to the query. */
  setGameDayRosterOverride: (id: string, override: "open" | "shut" | undefined) => void;
  setGameDaySortMode: (sortMode: GameDaySortMode) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      week: 1,
      setWeek: (week) => set({ week }),
      tweaks: TWEAK_DEFAULTS,
      setTweak: (key, value) => set((state) => ({ tweaks: { ...state.tweaks, [key]: value } })),
      sidebarCollapsed: false,
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      mobileNavOpen: false,
      setMobileNavOpen: (mobileNavOpen) => set({ mobileNavOpen }),
      notifications: NOTIFICATION_DEFAULTS,
      setNotification: (key, value) =>
        set((state) => ({ notifications: { ...state.notifications, [key]: value } })),
      appearance: APPEARANCE_DEFAULTS,
      setTheme: (theme) => set((state) => ({ appearance: { ...state.appearance, theme } })),
      setAccentColor: (accentColor) =>
        set((state) => ({ appearance: { ...state.appearance, accentColor } })),
      gameDay: GAME_DAY_DEFAULTS,
      setGameDayMode: (mode) => set((state) => ({ gameDay: { ...state.gameDay, mode } })),
      setGameDayOrder: (order) => set((state) => ({ gameDay: { ...state.gameDay, order } })),
      setGameDaySpan: (id, span) =>
        set((state) => ({
          gameDay: { ...state.gameDay, spans: { ...state.gameDay.spans, [id]: span } },
        })),
      setGameDayOpenIds: (openIds) => set((state) => ({ gameDay: { ...state.gameDay, openIds } })),
      setGameDayShutIds: (shutIds) => set((state) => ({ gameDay: { ...state.gameDay, shutIds } })),
      setGameDayRosterOverride: (id, override) =>
        set((state) => {
          const openIds = state.gameDay.openIds.filter((x) => x !== id);
          const shutIds = state.gameDay.shutIds.filter((x) => x !== id);
          if (override === "open") openIds.push(id);
          if (override === "shut") shutIds.push(id);
          return { gameDay: { ...state.gameDay, openIds, shutIds } };
        }),
      setGameDaySortMode: (sortMode) =>
        set((state) => ({ gameDay: { ...state.gameDay, sortMode } })),
    }),
    {
      name: "gridiron-ui-tweaks",
      partialize: (state) => ({
        tweaks: state.tweaks,
        sidebarCollapsed: state.sidebarCollapsed,
        notifications: state.notifications,
        appearance: state.appearance,
        gameDay: state.gameDay,
      }),
    },
  ),
);
