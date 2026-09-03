// Query hook for /api/players/* — see backend/gridiron/api/players.py.

import { useQuery } from "@tanstack/react-query";

import type { Envelope, PlayerInjuryData } from "../types/api";
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
