// POST /api/admin/refresh — triggers an immediate scheduler run (default job
// `refresh_fantasy`). No secret is required (tailnet/localhost-only, see
// specs/live-updates/spec.md). On success we invalidate the `teams` query so
// the dashboard reflects the freshly-cached data on its next render.
//
// GET /api/admin/refresh-runs (task 11.2) — recent scheduler run history, source of
// truth for Settings' "Last refresh: Xs ago · ok/failed" status line.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "./client";

export function useRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<unknown>("/api/admin/refresh"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  });
}

export interface RefreshRunResult {
  id: number;
  job_name: string;
  run_at: string;
  ok: boolean;
  error: string | null;
  duration_ms: number;
}

export function useRefreshRuns(limit = 1) {
  return useQuery({
    queryKey: ["refresh-runs", limit],
    queryFn: () => apiClient.get<RefreshRunResult[]>(`/api/admin/refresh-runs?limit=${limit}`),
    refetchInterval: 15_000,
  });
}
