// Task 6.6 — a PERSISTENT banner naming each field where ESPN and the static
// `league_config.json` disagree, and each field that could not be read from ESPN at
// all. Source: `resolve_league_shape` (backend/gridiron/services/draft_state.py),
// surfaced as `DraftStateData.settings_conflicts` -- every static field is reported
// here even when ESPN agrees or is silent, precisely so this screen never has to guess
// which numbers are confirmed. The static values (12 teams, half-PPR, 1QB/2RB/2WR/1TE/
// 2FLEX/1DST, no kicker, slot 1) are UNCONFIRMED until this banner says otherwise --
// it renders unconditionally whenever anything is unconfirmed, not tucked behind a
// dismiss/collapse control, so the screen can't silently imply the config is settled.

import type { SettingsConflictOut } from "../../api/draft";

const CONNECTIVITY_FIELD = "_espn_connectivity";

function valuesDisagree(conflict: SettingsConflictOut): boolean {
  if (conflict.espn_value === null || conflict.espn_value === undefined) return false;
  return JSON.stringify(conflict.espn_value) !== JSON.stringify(conflict.static_value);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export interface SettingsConflictBannerProps {
  conflicts: SettingsConflictOut[];
}

export function SettingsConflictBanner({ conflicts }: SettingsConflictBannerProps) {
  const connectivity = conflicts.find((c) => c.field === CONNECTIVITY_FIELD);
  const fields = conflicts.filter((c) => c.field !== CONNECTIVITY_FIELD);

  const disagreements = fields.filter(valuesDisagree);
  const unreadable = fields.filter((c) => !c.confirmed_by_espn && !valuesDisagree(c));

  // Nothing unconfirmed and ESPN is reachable -- no banner needed. (Not reachable
  // today with zero ESPN roster-settings support, but this keeps the banner honest if
  // that ever changes rather than hardcoding "always show it".)
  if (disagreements.length === 0 && unreadable.length === 0 && connectivity?.confirmed_by_espn) {
    return null;
  }

  return (
    <div className="settings-conflict-banner" data-testid="settings-conflict-banner">
      <div className="settings-conflict-title">League settings are not fully confirmed by ESPN</div>

      {connectivity && !connectivity.confirmed_by_espn && (
        <p style={{ margin: 0 }} data-testid="settings-conflict-connectivity">
          No ESPN league settings are available right now — every field below is your entered config
          (<code>league_config.json</code>), not confirmed against the live league.
        </p>
      )}

      {disagreements.length > 0 && (
        <>
          <div className="settings-conflict-group-label">ESPN disagrees</div>
          <ul>
            {disagreements.map((c) => (
              <li key={c.field} data-testid="settings-conflict-disagreement">
                <strong>{c.field}</strong>: entered {formatValue(c.static_value)}, ESPN says{" "}
                {formatValue(c.espn_value)} — using {formatValue(c.resolved_value)}.
              </li>
            ))}
          </ul>
        </>
      )}

      {unreadable.length > 0 && (
        <>
          <div className="settings-conflict-group-label">Could not be read from ESPN</div>
          <ul>
            {unreadable.map((c) => (
              <li key={c.field} data-testid="settings-conflict-unread">
                <strong>{c.field}</strong>: using entered value {formatValue(c.static_value)}
                {c.note ? ` — ${c.note}` : ""}.
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
