// The health designation, rendered wherever a player is listed (add-player-health D5).
//
// Two deliberate choices:
//
//  1. The badge carries a LETTER CODE as well as a color. Color alone fails for the
//     ~8% of men with a red/green deficiency, and these rows are exactly the ones the
//     user makes start/sit decisions from.
//  2. It renders NOTHING for ACTIVE and for null. A green "healthy" pill on 12 of 14
//     roster rows is noise that makes the two rows that matter harder to find, and null
//     means "we don't know" — which must not be drawn as an assertion either way.

import type { InjuryStatus } from "../../types/api";
import { INJURY_LABELS, isNoteworthy } from "./injuryLabels";

export interface InjuryBadgeProps {
  status: InjuryStatus | null | undefined;
  /** Omit for a static badge (Game Day, which is a glanceable view with no dialogs). */
  onClick?: () => void;
}

export function InjuryBadge({ status, onClick }: InjuryBadgeProps) {
  if (!isNoteworthy(status)) return null;
  const code = status as Exclude<InjuryStatus, "ACTIVE">;
  const label = INJURY_LABELS[code] ?? code;
  const className = `pill inj inj-${code.toLowerCase()}`;

  if (!onClick) {
    return (
      <span className={className} title={label} aria-label={label} data-testid="injury-badge">
        {code}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={`${className} inj-button`}
      title={`${label} — tap for detail`}
      aria-label={`${label}. Show health detail.`}
      data-testid="injury-badge"
      onClick={(event) => {
        // Roster rows are nested inside other click targets on some screens; the badge
        // opens its own dialog and must not also trigger the row's navigation.
        event.stopPropagation();
        onClick();
      }}
    >
      {code}
    </button>
  );
}
