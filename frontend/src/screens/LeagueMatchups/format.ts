// Pure helpers shared by the All Matchups list, its cards, and the read-only detail.

import { encodeMatchupId } from "../../api/leagueMatchups";
import { teamRoutePath } from "../../hooks/teamRoute";

/** Nested under the League tab, so `parseTeamRoute` keeps that tab selected. */
export function matchupsPath(teamId: string): string {
  return `${teamRoutePath(teamId, "league")}/matchups`;
}

export function matchupDetailPath(teamId: string, matchupId: string): string {
  return `${matchupsPath(teamId)}/${encodeMatchupId(matchupId)}`;
}

/** Always W-L-T, as a scoreboard reads — unlike Standings, which drops a zero T. */
export function recordText(record: { w: number; l: number; t: number }): string {
  return `${record.w}-${record.l}-${record.t}`;
}

/** `1` when home leads, `-1` when away does, `0` for a tie (within display precision). */
export function leader(home: number, away: number): 1 | -1 | 0 {
  const diff = home - away;
  if (Math.abs(diff) < 0.05) return 0;
  return diff > 0 ? 1 : -1;
}
