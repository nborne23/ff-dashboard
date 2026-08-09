// Query/mutation hooks for /api/leagues — Settings' "ESPN Leagues" card (task 7.3).
// GET returns a plain list across both platforms (no envelope — this is Settings
// config data, not a Dashboard read); EspnLeaguesCard filters to platform === "espn".

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Platform, ScoringType } from "../types/api";
import { apiClient } from "./client";

export interface LeagueSetting {
  id: string;
  platform: Platform;
  platform_id: string;
  name: string;
  season: number;
  team_count: number;
  scoring_type: ScoringType;
  current_week: number;
  is_enabled: boolean;
}

export const LEAGUES_QUERY_KEY = ["leagues"] as const;

export function useLeagues() {
  return useQuery({
    queryKey: LEAGUES_QUERY_KEY,
    queryFn: () => apiClient.get<LeagueSetting[]>("/api/leagues"),
  });
}

export function useUpdateLeague() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leagueId, isEnabled }: { leagueId: string; isEnabled: boolean }) =>
      apiClient.patch<LeagueSetting>(`/api/leagues/${leagueId}`, { is_enabled: isEnabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LEAGUES_QUERY_KEY });
      // A disabled league's teams drop out of GET /api/teams (backend/gridiron/
      // services/fantasy_service.py:list_teams) — keep the Dashboard in sync.
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  });
}
