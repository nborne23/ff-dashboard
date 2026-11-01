// Query hooks for the NFL Scores screen — GET /api/scores and /api/scores/games/{id}
// (backend/gridiron/api/scores.py, services/scores.py).
//
// Both keys live under the `["live_nfl_games"]` prefix on purpose: the backend publishes
// that scope from the same tick that writes the scoreboard these endpoints read, and
// api/events.ts already maps it to that prefix. A score change refetches both screens
// with no new SSE scope.
//
// Fantasy points are the exception: they come from Sleeper's stat feed, which the
// backend re-pulls every two minutes during games but doesn't signal. The game detail
// polls while its game is in progress so the Fantasy tab keeps up between score changes.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type { Envelope, Player } from "../types/api";
import { apiClient } from "./client";

const STALE_TIME_MS = 15_000;
export const LIVE_GAME_POLL_MS = 60_000;

export type ScoreGameState = "pre" | "in" | "post" | "postponed";
export type FantasyPosition = "QB" | "RB" | "WR" | "TE" | "K" | "DEF";
export type PointsFormat = "ppr" | "half_ppr" | "standard";

export interface ScoreTeam {
  abbr: string;
  name: string;
  location: string;
  record: string | null;
  /** null before kickoff. */
  score: number | null;
  logo: string | null;
  /** ESPN hex without the leading `#`. */
  color: string | null;
  linescores: number[];
  winner: boolean;
}

export interface GameLeader {
  category: "passing" | "rushing" | "receiving";
  name: string;
  short_name: string;
  position: string | null;
  team: string;
  headshot_url: string | null;
  stat_line: string;
}

export interface ScoreGame {
  game_id: string;
  kickoff_at: string;
  state: ScoreGameState;
  status_text: string;
  period: number | null;
  clock: string | null;
  broadcast: string | null;
  possession: string | null;
  down_distance: string | null;
  away: ScoreTeam;
  home: ScoreTeam;
  top_performer: GameLeader | null;
}

export interface ScoresWeek {
  season: number | null;
  week: number;
  current_week: number | null;
  weeks: number[];
  byes: string[];
  fetched_at: string | null;
  games: ScoreGame[];
}

export interface StatToken {
  value: string;
  label: string;
}

export interface FantasyPlayer {
  sleeper_id: string;
  name: string;
  short_name: string;
  position: FantasyPosition;
  team: string;
  points: number | null;
  projection: number | null;
  source: "league" | "estimated";
  stats: Record<string, number>;
  stat_line: StatToken[];
  player: Player | null;
  fantasy_team: string | null;
  is_mine: boolean;
}

export interface FantasyGroup {
  position: FantasyPosition;
  away: FantasyPlayer[];
  home: FantasyPlayer[];
}

export interface ScoringLeague {
  league_id: string;
  name: string;
  platform: string;
  scoring_type: string;
  team_id: string | null;
}

export interface GameDetail {
  season: number;
  week: number;
  game: ScoreGame;
  leagues: ScoringLeague[];
  league_id: string | null;
  points_format: PointsFormat;
  points_format_fallback: boolean;
  groups: FantasyGroup[];
  stats_as_of: string | null;
}

export function scoresWeekKey(week: number | null) {
  return ["live_nfl_games", "scores", week] as const;
}

export function useScoresWeek(week: number | null) {
  return useQuery({
    queryKey: scoresWeekKey(week),
    queryFn: () =>
      apiClient.get<Envelope<ScoresWeek>>(week ? `/api/scores?week=${week}` : "/api/scores"),
    staleTime: STALE_TIME_MS,
    // Switching weeks keeps the old week on screen until the new one lands, instead of
    // flashing a skeleton between two full scoreboards.
    placeholderData: keepPreviousData,
  });
}

export function useScoreGame(gameId: string, leagueId: string | null, week: number | null) {
  const params = new URLSearchParams();
  if (leagueId) params.set("league_id", leagueId);
  if (week) params.set("week", String(week));
  const query = params.toString();
  return useQuery({
    queryKey: ["live_nfl_games", "scores", "game", gameId, leagueId],
    queryFn: () =>
      apiClient.get<Envelope<GameDetail>>(
        `/api/scores/games/${encodeURIComponent(gameId)}${query ? `?${query}` : ""}`,
      ),
    staleTime: STALE_TIME_MS,
    enabled: Boolean(gameId),
    // Keep the screen up while only the league changes; never show one game's players
    // under another game's header.
    placeholderData: (previous) => (previous?.data.game.game_id === gameId ? previous : undefined),
    refetchInterval: (q) => (q.state.data?.data.game.state === "in" ? LIVE_GAME_POLL_MS : false),
  });
}
