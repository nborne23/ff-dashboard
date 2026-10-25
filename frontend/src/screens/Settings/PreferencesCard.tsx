// "Preferences" settings-group — matches design/screen-settings.jsx's Preferences
// group. Polling frequency is server state (GET/POST /api/settings*). Notifications
// have their own card (NotificationsCard.tsx) now that they actually deliver.

import { useSetLiveTier, useSettings } from "../../api/settings";
import type { LiveTier } from "../../api/settings";
import { SettingsRow } from "./SettingsRow";

const TIERS: LiveTier[] = ["10s", "30s", "1m"];

export function PreferencesCard() {
  const settingsQuery = useSettings();
  const setLiveTier = useSetLiveTier();

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
    </div>
  );
}
