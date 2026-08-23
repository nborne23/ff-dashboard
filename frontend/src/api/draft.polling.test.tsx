// Task 6.5 (design D12) — degraded-mode polling on draft queries. While the Draft
// screen is mounted and SSE is disconnected, draft queries must poll every ~5s (the
// app-wide fallback in events.ts is 5 MINUTES -- far too slow mid-draft). This override
// must be scoped to draft queries only (never touch queryClient's default options, so
// it can't fight events.ts for control of the same knob) and needs no explicit teardown
// -- unmounting the last component using a draft query removes its only observer, and
// TanStack Query only schedules `refetchInterval` polls for queries with an observer.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLiveConnectionStore } from "../stores/live";
import { useDraftState } from "./draft";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function envelope() {
  return {
    data: {
      picks: [],
      current_overall_pick: 1,
      current_round: 1,
      picks_until_next: 0,
      my_upcoming_picks: [1],
      roster: { starters: [], bench: [], bye_collisions: [] },
      settings_conflicts: [],
      session_status: "manual",
      league_teams: 12,
      draft_over: false,
    },
    meta: {
      live_state: "off_day",
      as_of: "2026-08-23T12:00:00Z",
      next_refresh_at: "2026-08-23T12:30:00Z",
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

function resetStore(): void {
  useLiveConnectionStore.setState({
    connected: false,
    liveState: "off_day",
    lastEventAt: null,
    connectionLostLong: false,
    liveTierSeconds: null,
  });
}

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("degraded-mode polling on draft queries (task 6.5)", () => {
  beforeEach(() => {
    resetStore();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
    resetStore();
  });

  it("polls at ~5s when SSE is disconnected and the query is mounted", async () => {
    useLiveConnectionStore.setState({ connected: false });
    const fetchMock = vi.fn(async () => jsonResponse(200, envelope()));
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useDraftState(), { wrapper: makeWrapper(queryClient) });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(5_000);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    await vi.advanceTimersByTimeAsync(5_000);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });

  it("does not poll on an interval while SSE is connected", async () => {
    useLiveConnectionStore.setState({ connected: true });
    const fetchMock = vi.fn(async () => jsonResponse(200, envelope()));
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderHook(() => useDraftState(), { wrapper: makeWrapper(queryClient) });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(20_000);
    // No interval polling while connected -- still just the one initial fetch.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("leaves the app-wide query default untouched after the Draft screen unmounts", async () => {
    useLiveConnectionStore.setState({ connected: false });
    const fetchMock = vi.fn(async () => jsonResponse(200, envelope()));
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    function DraftStateProbe() {
      useDraftState();
      return null;
    }

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <DraftStateProbe />
      </QueryClientProvider>,
    );

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    unmount();

    // The per-query refetchInterval used while mounted must never have leaked into the
    // client's shared defaults -- events.ts's own app-wide fallback (a totally separate
    // mechanism, keyed off connectionLostLong) is the only thing allowed to touch this.
    expect(queryClient.getQueryDefaults(["draft"]).refetchInterval).toBeUndefined();
    expect(queryClient.getDefaultOptions().queries?.refetchInterval).toBeUndefined();

    // And polling itself stops once unmounted (no observer left to schedule against).
    const callsAtUnmount = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(15_000);
    expect(fetchMock).toHaveBeenCalledTimes(callsAtUnmount);
  });
});
