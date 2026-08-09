// "Preferences" settings-group — matches design/screen-settings.jsx's Preferences
// group. Polling frequency is server state (GET/POST /api/settings*); the three
// notification toggles below it are client-only (stores/ui.ts) and functionally inert
// — there's no push-notification delivery mechanism yet (Phase 8).

import { useSetLiveTier, useSettings } from "../../api/settings";
import type { LiveTier } from "../../api/settings";
import { useUiStore } from "../../stores/ui";
import { SettingsRow } from "./SettingsRow";
import { Switch } from "./Switch";

const TIERS: LiveTier[] = ["10s", "30s", "1m"];

export function PreferencesCard() {
  const settingsQuery = useSettings();
  const setLiveTier = useSetLiveTier();
  const notifications = useUiStore((s) => s.notifications);
  const setNotification = useUiStore((s) => s.setNotification);

  const activeTier = settingsQuery.data?.live_tier ?? "30s";

  return (
    <div className="settings-group">
      <h3>Preferences</h3>
      <SettingsRow
        label="Polling frequency"
        sub="How often to refresh during live games"
        right={
          <div className="segmented">
            {TIERS.map((tier) => (
              <button
                key={tier}
                type="button"
                className={tier === activeTier ? "active" : ""}
                disabled={setLiveTier.isPending}
                onClick={() => setLiveTier.mutate(tier)}
              >
                {tier}
              </button>
            ))}
          </div>
        }
      />
      <SettingsRow
        label="Notify on score change"
        sub="Push when a starter scores 6+ pts"
        right={
          <Switch
            on={notifications.scoreChange}
            onChange={(next) => setNotification("scoreChange", next)}
            label="Notify on score change"
          />
        }
      />
      <SettingsRow
        label="Red zone alerts"
        sub="When my players enter the red zone"
        right={
          <Switch
            on={notifications.redzone}
            onChange={(next) => setNotification("redzone", next)}
            label="Red zone alerts"
          />
        }
      />
      <SettingsRow
        label="Final score recap"
        right={
          <Switch
            on={notifications.finalScore}
            onChange={(next) => setNotification("finalScore", next)}
            label="Final score recap"
          />
        }
      />
    </div>
  );
}
