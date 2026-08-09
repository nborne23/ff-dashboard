// Query/mutation hooks for /api/settings — Settings' "Preferences" card (task 7.4).
// Only the live-refresh polling tier is server state today; the notification toggles
// next to it are client-only (stores/ui.ts), since they're functionally inert until
// Phase 8 wires up push notifications.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "./client";

export type LiveTier = "10s" | "30s" | "1m";

export interface SettingsResponse {
  live_tier: LiveTier;
}

export const SETTINGS_QUERY_KEY = ["settings"] as const;

export function useSettings() {
  return useQuery({
    queryKey: SETTINGS_QUERY_KEY,
    queryFn: () => apiClient.get<SettingsResponse>("/api/settings"),
  });
}

export function useSetLiveTier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (liveTier: LiveTier) =>
      apiClient.post<SettingsResponse>("/api/settings/live-tier", { live_tier: liveTier }),
    onSuccess: (data) => {
      queryClient.setQueryData(SETTINGS_QUERY_KEY, data);
    },
  });
}
