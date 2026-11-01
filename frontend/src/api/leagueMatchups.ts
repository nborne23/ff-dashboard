// Query hooks for /api/teams/{id}/league/matchups* — every pairing in a team's league
// (backend/gridiron/api/league_matchups.py, services/league_matchups.py).
//
// Every key starts with "league-matchups" so the SSE `matchups:{league_id}` scope can
// invalidate the list and any open detail with one prefix (api/events.ts). The detail is
// fetched by matchup id rather than through `useTeamH2H`, whose `["team", id, ...]` keys
// only ever see `h2h:{id}` scopes for the USER's teams — another manager's matchup
// would never refresh during a live game.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type { Envelope, League, Matchup, MatchupSlot, Team } from "../types/api";
import { apiClient } from "./client";

const STALE_TIME_MS = 15_000;

export interface LeagueMatchupSide {
  /** League-wide team shape: name, manager, record, logo. Its week-scoped fields
   *  (`current_score`, ...) are zeroed — the matchup carries the week's score. */
  team: Team;
  /** The standings position the League screen shows, not the platform's raw seed. */
  position: number;
  /** Starters whose NFL game isn't final yet. */
  remaining: number;
  /** Any starter's NFL game is in progress right now. */
  is_live: boolean;
}

export interface LeagueMatchupEntry {
  matchup: Matchup;
  home: LeagueMatchupSide;
  away: LeagueMatchupSide;
  is_user_matchup: boolean;
}

export interface LeagueMatchupsData {
  league: League;
  week: number;
  /** The user's own matchup first, then by each pairing's better-placed team. */
  matchups: LeagueMatchupEntry[];
}

export interface LeagueMatchupDetailData extends LeagueMatchupEntry {
  league: League;
  week: number;
  slots: MatchupSlot[];
}

/** Path segment for a matchup id: ids carry `:` and `.` (`espn:l-1-m-2-w-8`). */
export function encodeMatchupId(id: string): string {
  return encodeURIComponent(id);
}

export function useLeagueMatchups(teamId: string, week: number) {
  return useQuery({
    queryKey: ["league-matchups", teamId, week],
    queryFn: () =>
      apiClient.get<Envelope<LeagueMatchupsData>>(
        `/api/teams/${teamId}/league/matchups?week=${week}`,
      ),
    staleTime: STALE_TIME_MS,
    enabled: Boolean(teamId),
    // Stepping weeks swaps the query key; keep the last week's cards up rather than
    // collapsing the whole screen to a skeleton on every arrow tap.
    placeholderData: keepPreviousData,
  });
}

export function useLeagueMatchup(teamId: string, matchupId: string) {
  return useQuery({
    queryKey: ["league-matchups", teamId, "detail", matchupId],
    queryFn: () =>
      apiClient.get<Envelope<LeagueMatchupDetailData>>(
        `/api/teams/${teamId}/league/matchups/${encodeMatchupId(matchupId)}`,
      ),
    staleTime: STALE_TIME_MS,
    enabled: Boolean(teamId && matchupId),
  });
}
