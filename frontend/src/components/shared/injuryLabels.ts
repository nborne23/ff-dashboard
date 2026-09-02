// Split out of InjuryBadge.tsx so that file exports components only — the
// react-refresh/only-export-components rule (eslint.config.js) fails a mixed module.

import type { InjuryStatus } from "../../types/api";

/** Long form, for a badge's `title`/`aria-label` and the detail panel's header. The pill
 *  itself shows the short code. */
export const INJURY_LABELS: Record<Exclude<InjuryStatus, "ACTIVE">, string> = {
  Q: "Questionable",
  D: "Doubtful",
  O: "Out",
  IR: "Injured Reserve",
  PUP: "Physically Unable to Perform",
  DTD: "Day-to-Day",
  SUSP: "Suspended",
  NFI: "Non-Football Injury",
};

/** Is this a designation worth drawing? False for ACTIVE and for unknown (null).
 *
 *  A green "healthy" pill on 12 of 14 roster rows is noise that makes the two rows that
 *  matter harder to find, and `null` means "we don't know" — which must not be drawn as
 *  an assertion in either direction. */
export function isNoteworthy(status: InjuryStatus | null | undefined): boolean {
  return Boolean(status) && status !== "ACTIVE";
}
