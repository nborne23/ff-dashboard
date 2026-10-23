// Query hook for /api/players/* — see backend/gridiron/api/players.py.

import { useQuery } from "@tanstack/react-query";

import type { Envelope, PlayerInjuryData, PlayerStatsData } from "../types/api";
import { apiClient } from "./client";

// Longer than the 15s the team reads use: the backing `refresh_injuries` job runs every
// 30 minutes, so a shorter window would just re-fetch bytes that cannot have changed.
const STALE_TIME_MS = 60_000;

export function usePlayerInjury(playerId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["player-injury", playerId],
    queryFn: () => apiClient.get<Envelope<PlayerInjuryData>>(`/api/players/${playerId}/injury`),
    staleTime: STALE_TIME_MS,
    enabled: enabled && Boolean(playerId),
  });
}

// The team reads' window. History never moves, but `this_week` does during games.
const STATS_STALE_TIME_MS = 15_000;
// While a game is on, poll at the live tier's slowest setting so an open panel keeps
// ticking without the user closing and reopening it.
const LIVE_REFETCH_MS = 30_000;

/** `teamId` picks the league's points format and roster slot; `week` the "this week" row. */
export function usePlayerStats(playerId: string, teamId: string | undefined, week: number) {
  const params = new URLSearchParams({ week: String(week) });
  if (teamId) params.set("team_id", teamId);
  return useQuery({
    queryKey: ["player-stats", playerId, teamId ?? null, week],
    queryFn: () =>
      apiClient.get<Envelope<PlayerStatsData>>(
        `/api/players/${encodeURIComponent(playerId)}/stats?${params}`,
      ),
    staleTime: STATS_STALE_TIME_MS,
    refetchInterval: (query) =>
      query.state.data?.data.this_week.is_live ? LIVE_REFETCH_MS : false,
    enabled: Boolean(playerId) && week >= 1,
  });
}
