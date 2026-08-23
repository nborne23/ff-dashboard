// `useLiveEvents()` — the SSE client for `GET /api/events` (task 8.6).
//
// Design principle (see backend/gridiron/api/events.py): SSE is the signal, REST is the
// data. Every event we receive here either carries no payload we act on directly
// (heartbeat) or just enough to know *what* changed — `data.changed`'s `scopes` map to
// TanStack Query keys we invalidate so the normal query machinery refetches; we never
// read entity data off the event itself.
//
// Reconnection: on any error the EventSource is closed (to stop the browser's own
// built-in retry, which we don't control the backoff of) and a new connection is
// scheduled with capped exponential backoff. `stores/live.ts` tracks `connected` +
// `connectionLostLong` (>30s continuously down, task 8.9) for any component to read.

import { useEffect } from "react";
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";

import { useLiveConnectionStore } from "../stores/live";
import type { LiveState as LiveStateValue } from "../types/api";

const EVENTS_URL = "/api/events";
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30_000;
export const DISCONNECT_LONG_MS = 30_000;
export const DISCONNECTED_REFETCH_INTERVAL_MS = 5 * 60 * 1000;

interface DataChangedPayload {
  type: "data.changed";
  scopes: string[];
  as_of: string;
}

interface LiveStateChangedPayload {
  type: "live_state.changed";
  live_state: LiveStateValue;
}

interface TierChangePayload {
  type: "tier.change";
  live_tier_seconds: number;
}

/**
 * Map one `data.changed` scope string to the TanStack Query key(s) it should
 * invalidate. Keys use `invalidateQueries`' default prefix-match semantics, so
 * `["team", id]` also catches that team's `h2h`/`season` sub-queries — harmless
 * over-invalidation, not a correctness issue — while the more specific `h2h:{id}` /
 * `season:{id}` scopes exist so the differ can signal *just* that slice changed.
 *
 * Query key shapes are read straight from api/teams.ts / api/liveNflGames.ts:
 *   useTeams(week)      -> ["teams", week]
 *   useTeam(id, week)   -> ["team", id, week]
 *   useTeamH2H(id, week)-> ["team", id, "h2h", week]
 *   useTeamSeason(id)   -> ["team", id, "season"]
 */
export function queryKeyForScope(scope: string): QueryKey | null {
  if (scope === "teams") return ["teams"];
  if (scope === "live_nfl_games") return ["live_nfl_games"];
  // Draft Assistant (task 3.6): one bare "draft" scope covers picks, current-pick, and
  // session status all at once (services/differ.py's draft_fingerprints), so a single
  // prefix key here invalidates every api/draft.ts query (board/pool/state/
  // recommendations all key off ["draft", ...]) via invalidateQueries' prefix match.
  if (scope === "draft") return ["draft"];

  const separatorIndex = scope.indexOf(":");
  if (separatorIndex === -1) return null;
  const prefix = scope.slice(0, separatorIndex);
  const id = scope.slice(separatorIndex + 1);
  if (!id) return null;

  if (prefix === "team") return ["team", id];
  if (prefix === "h2h") return ["team", id, "h2h"];
  if (prefix === "season") return ["team", id, "season"];
  return null;
}

function invalidateScopes(queryClient: QueryClient, scopes: string[]): void {
  for (const scope of scopes) {
    const queryKey = queryKeyForScope(scope);
    if (queryKey) void queryClient.invalidateQueries({ queryKey });

    // Task 10.6: the Topbar's day rings (api/dayRings.ts, ["day-rings", week]) are
    // sourced from the same current-week roster/matchup rows the "teams" scope already
    // covers — there's no separate differ fingerprint for them, so the "teams" scope's
    // own invalidation is deliberately widened to include them too, rather than adding
    // a whole new backend scope for one small extra query.
    if (scope === "teams") void queryClient.invalidateQueries({ queryKey: ["day-rings"] });
  }
}

export interface UseLiveEventsResult {
  connected: boolean;
  liveState: LiveStateValue;
  lastEventAt: number | null;
}

export function useLiveEvents(): UseLiveEventsResult {
  const queryClient = useQueryClient();
  const connected = useLiveConnectionStore((s) => s.connected);
  const liveState = useLiveConnectionStore((s) => s.liveState);
  const lastEventAt = useLiveConnectionStore((s) => s.lastEventAt);

  useEffect(() => {
    const store = useLiveConnectionStore.getState();
    let source: EventSource | null = null;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let longDisconnectTimer: ReturnType<typeof setInterval> | null = null;
    let disconnectedSince: number | null = null;
    let cancelled = false;

    function clearReconnectTimer(): void {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function clearLongDisconnectTimer(): void {
      if (longDisconnectTimer !== null) {
        clearInterval(longDisconnectTimer);
        longDisconnectTimer = null;
      }
    }

    function markConnected(): void {
      attempt = 0;
      disconnectedSince = null;
      clearLongDisconnectTimer();
      store.setConnected(true);
      store.setConnectionLostLong(false);
    }

    function markDisconnected(): void {
      store.setConnected(false);
      if (disconnectedSince === null) disconnectedSince = Date.now();
      if (longDisconnectTimer === null) {
        longDisconnectTimer = setInterval(() => {
          if (disconnectedSince !== null && Date.now() - disconnectedSince >= DISCONNECT_LONG_MS) {
            useLiveConnectionStore.getState().setConnectionLostLong(true);
          }
        }, 1000);
      }
    }

    function recordEvent(): void {
      useLiveConnectionStore.getState().setLastEventAt(Date.now());
    }

    function scheduleReconnect(): void {
      if (cancelled) return;
      clearReconnectTimer();
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
      attempt += 1;
      reconnectTimer = setTimeout(connect, delay);
    }

    function connect(): void {
      if (cancelled) return;
      if (typeof EventSource === "undefined") {
        // No SSE support in this environment (jsdom under test, a very old browser, an
        // SSR pass, ...) — stay disconnected without retrying; nothing a retry loop
        // would fix here. Real deployments (Safari/Chrome/Firefox) all support
        // EventSource natively.
        markDisconnected();
        return;
      }
      const es = new EventSource(EVENTS_URL);
      source = es;

      es.onopen = () => markConnected();
      es.onerror = () => {
        es.close();
        markDisconnected();
        scheduleReconnect();
      };

      es.addEventListener("data.changed", (event) => {
        recordEvent();
        const payload = JSON.parse((event as MessageEvent).data) as DataChangedPayload;
        invalidateScopes(queryClient, payload.scopes);
      });

      es.addEventListener("live_state.changed", (event) => {
        recordEvent();
        const payload = JSON.parse((event as MessageEvent).data) as LiveStateChangedPayload;
        useLiveConnectionStore.getState().setLiveState(payload.live_state);
      });

      es.addEventListener("tier.change", (event) => {
        recordEvent();
        const payload = JSON.parse((event as MessageEvent).data) as TierChangePayload;
        useLiveConnectionStore.getState().setLiveTierSeconds(payload.live_tier_seconds);
      });

      es.addEventListener("heartbeat", () => {
        // No payload we act on — receiving it at all is the signal (the connection is
        // still alive), so just record it via `recordEvent()`.
        recordEvent();
      });
    }

    function onVisibilityChange(): void {
      if (document.visibilityState !== "visible") return;
      // Coming back to the tab: refetch everything immediately (don't wait for the next
      // scheduled refetch/SSE event) and, if we'd drifted disconnected, reconnect now
      // instead of waiting out the remaining backoff delay.
      void queryClient.invalidateQueries();
      if (!useLiveConnectionStore.getState().connected) {
        clearReconnectTimer();
        attempt = 0;
        source?.close();
        connect();
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    connect();

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      clearReconnectTimer();
      clearLongDisconnectTimer();
      source?.close();
    };
    // Mount-only: `queryClient` is the one stable instance from main.tsx's single
    // QueryClientProvider for the app's whole lifetime, so it's safe to close over here
    // without re-running this effect (which would tear down and reopen the connection).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Drive the 5-minute fallback poll (task 8.9) from connectionLostLong, as a QueryClient
  // default — main.tsx sets no other query defaults, and per-query `staleTime` (api/teams.ts)
  // is independent of `refetchInterval`, so this can't clobber anything.
  useEffect(() => {
    return useLiveConnectionStore.subscribe((state, previous) => {
      if (state.connectionLostLong === previous.connectionLostLong) return;
      queryClient.setDefaultOptions({
        queries: {
          refetchInterval: state.connectionLostLong ? DISCONNECTED_REFETCH_INTERVAL_MS : undefined,
        },
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connected, liveState, lastEventAt };
}
