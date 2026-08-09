// Query/mutation hooks for /api/connections — see
// backend/gridiron/api/connections.py for the source of truth on response
// shapes. Note GET returns a *list* of ConnectionStatus, not a keyed object;
// useConnections() reshapes it into a Record<Platform, ConnectionStatus> so
// callers can address `data.yahoo` / `data.espn` directly.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "./client";

export type Platform = "yahoo" | "espn";

export interface ConnectionStatus {
  platform: Platform;
  is_connected: boolean;
  display_name: string | null;
  last_verified_at: string | null;
}

export type ConnectionsByPlatform = Record<Platform, ConnectionStatus>;

export interface YahooStartResponse {
  auth_url: string;
}

export interface EspnTestPayload {
  swid: string;
  espn_s2: string;
}

export const CONNECTIONS_QUERY_KEY = ["connections"] as const;

function emptyStatus(platform: Platform): ConnectionStatus {
  return { platform, is_connected: false, display_name: null, last_verified_at: null };
}

export function useConnections() {
  return useQuery({
    queryKey: CONNECTIONS_QUERY_KEY,
    queryFn: async (): Promise<ConnectionsByPlatform> => {
      const list = await apiClient.get<ConnectionStatus[]>("/api/connections");
      const byPlatform: ConnectionsByPlatform = {
        yahoo: emptyStatus("yahoo"),
        espn: emptyStatus("espn"),
      };
      for (const status of list) {
        byPlatform[status.platform] = status;
      }
      return byPlatform;
    },
  });
}

export function useYahooStart() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<YahooStartResponse>("/api/connections/yahoo/start"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
    },
  });
}

export function useEspnTest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EspnTestPayload) =>
      apiClient.post<ConnectionStatus>("/api/connections/espn/test", payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
    },
  });
}

export function useDisconnect(platform: Platform) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.delete<void>(`/api/connections/${platform}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
    },
  });
}
