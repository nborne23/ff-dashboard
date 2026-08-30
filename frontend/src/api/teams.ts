// Query hooks for /api/teams* — see
// backend/gridiron/api/teams.py (once the backend agent lands it) for the
// source of truth on response shapes; the envelope + entity shapes here are
// ported from specs/fantasy-data-model/spec.md's "Read API for the frontend"
// requirement and design.md D12.

import { useQuery } from "@tanstack/react-query";

import type {
  Envelope,
  GameDayData,
  League,
  Matchup,
  MatchupSlot,
  Player,
  RosterSlot,
  SeasonWeek,
  Team,
} from "../types/api";
import { apiClient } from "./client";

// staleTime keeps refetch-on-focus/mount from hammering the backend between
// scheduler ticks; no refetchInterval here — polling/SSE-driven invalidation
// arrives in Phase 8.
const STALE_TIME_MS = 15_000;

export interface TeamsListData {
  teams: Team[];
}

export function useTeams(week: number) {
  return useQuery({
    queryKey: ["teams", week],
    queryFn: () => apiClient.get<Envelope<TeamsListData>>(`/api/teams?week=${week}`),
    staleTime: STALE_TIME_MS,
  });
}

export interface TeamDetailData {
  team: Team;
  league: League;
  starters: RosterSlot[];
  bench: RosterSlot[];
  record_history: SeasonWeek[];
}

export function useTeam(id: string, week: number) {
  return useQuery({
    queryKey: ["team", id, week],
    queryFn: () => apiClient.get<Envelope<TeamDetailData>>(`/api/teams/${id}?week=${week}`),
    staleTime: STALE_TIME_MS,
    enabled: Boolean(id),
  });
}

export interface TeamH2HData {
  matchup: Matchup;
  slots: MatchupSlot[];
  remaining: { mine: number; theirs: number };
}

export function useTeamH2H(id: string, week: number) {
  return useQuery({
    queryKey: ["team", id, "h2h", week],
    queryFn: () => apiClient.get<Envelope<TeamH2HData>>(`/api/teams/${id}/h2h?week=${week}`),
    staleTime: STALE_TIME_MS,
    enabled: Boolean(id),
  });
}

export interface TeamSeasonData {
  weeks: SeasonWeek[];
  highlights: {
    // Nullable: backend/gridiron/services/fantasy_service.py's Highlights model
    // returns `None` for season_high when a team has no persisted weeks yet,
    // and for most_started when it has never started a player (no RosterSlot
    // rows). The frontend types here previously assumed both were always
    // present, which drifted from the source of truth.
    season_high: SeasonWeek | null;
    win_streak: number;
    most_started: { player: Player; starts: number; avg_points: number } | null;
  };
}

export function useTeamSeason(id: string) {
  return useQuery({
    queryKey: ["team", id, "season"],
    queryFn: () => apiClient.get<Envelope<TeamSeasonData>>(`/api/teams/${id}/season`),
    staleTime: STALE_TIME_MS,
    enabled: Boolean(id),
  });
}

/**
 * The Game Day bulk envelope — every matchup involving a user team in one request,
 * replacing what would otherwise be a `/h2h` + `/{id}` pair per team (design D5).
 *
 * The key is `["gameday", week]`, a two-element key so `api/events.ts` can invalidate
 * the whole screen with the `["gameday"]` prefix without enumerating weeks (design D9).
 */
export function useGameDay(week: number) {
  return useQuery({
    queryKey: ["gameday", week],
    queryFn: () => apiClient.get<Envelope<GameDayData>>(`/api/teams/game-day?week=${week}`),
    staleTime: STALE_TIME_MS,
  });
}
