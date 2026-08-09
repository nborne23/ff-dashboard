import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DISCONNECT_LONG_MS,
  DISCONNECTED_REFETCH_INTERVAL_MS,
  queryKeyForScope,
  useLiveEvents,
} from "./events";
import { useLiveConnectionStore } from "../stores/live";

type Listener = (event: { data: string }) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, cb: Listener): void {
    const existing = this.listeners.get(type) ?? [];
    existing.push(cb);
    this.listeners.set(type, existing);
  }

  close(): void {
    this.closed = true;
  }

  emitOpen(): void {
    this.onopen?.();
  }

  emitError(): void {
    this.onerror?.();
  }

  emit(type: string, data: unknown): void {
    const event = { data: JSON.stringify(data) };
    for (const cb of this.listeners.get(type) ?? []) cb(event);
  }
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

function renderWithClient(queryClient: QueryClient) {
  return renderHook(() => useLiveEvents(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("queryKeyForScope", () => {
  it("maps the aggregate teams scope", () => {
    expect(queryKeyForScope("teams")).toEqual(["teams"]);
  });

  it("maps a team scope to the team prefix (also invalidates h2h/season by prefix match)", () => {
    expect(queryKeyForScope("team:yahoo:l1.t1")).toEqual(["team", "yahoo:l1.t1"]);
  });

  it("maps an h2h scope", () => {
    expect(queryKeyForScope("h2h:yahoo:l1.t1")).toEqual(["team", "yahoo:l1.t1", "h2h"]);
  });

  it("maps a season scope", () => {
    expect(queryKeyForScope("season:yahoo:l1.t1")).toEqual(["team", "yahoo:l1.t1", "season"]);
  });

  it("maps the live_nfl_games scope", () => {
    expect(queryKeyForScope("live_nfl_games")).toEqual(["live_nfl_games"]);
  });

  it("returns null for an unrecognized scope", () => {
    expect(queryKeyForScope("something_else")).toBeNull();
  });

  it("returns null for a scope with an empty id", () => {
    expect(queryKeyForScope("team:")).toBeNull();
  });
});

describe("useLiveEvents", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    resetStore();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    resetStore();
  });

  it("opens a connection to /api/events on mount", () => {
    renderWithClient(new QueryClient());
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe("/api/events");
  });

  it("reports connected once the EventSource opens", async () => {
    const { result } = renderWithClient(new QueryClient());
    expect(result.current.connected).toBe(false);

    act(() => FakeEventSource.instances[0].emitOpen());

    await waitFor(() => expect(result.current.connected).toBe(true));
  });

  it("invalidates the mapped query keys for a data.changed event's scopes", async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    renderWithClient(queryClient);

    act(() => {
      FakeEventSource.instances[0].emit("data.changed", {
        type: "data.changed",
        scopes: ["teams", "team:yahoo:l1.t1"],
        as_of: "2025-12-07T18:00:00",
      });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["teams"] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["team", "yahoo:l1.t1"] });
    });
  });

  it("invalidates EXACTLY the query keys named in the scopes list — no over-invalidation", async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    renderWithClient(queryClient);

    act(() => {
      FakeEventSource.instances[0].emit("data.changed", {
        type: "data.changed",
        scopes: ["h2h:yahoo:l1.t1", "season:yahoo:l1.t1"],
        as_of: "2025-12-07T18:00:00",
      });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());

    // Exactly two calls, one per scope, each with exactly the mapped key — not
    // "teams", not a third catch-all invalidateQueries() with no args, nothing else.
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy.mock.calls).toEqual([
      [{ queryKey: ["team", "yahoo:l1.t1", "h2h"] }],
      [{ queryKey: ["team", "yahoo:l1.t1", "season"] }],
    ]);
  });

  it("also invalidates day-rings when the teams scope changes (task 10.6)", async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    renderWithClient(queryClient);

    act(() => {
      FakeEventSource.instances[0].emit("data.changed", {
        type: "data.changed",
        scopes: ["teams"],
        as_of: "2025-12-07T18:00:00",
      });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());

    expect(invalidateSpy.mock.calls).toEqual([
      [{ queryKey: ["teams"] }],
      [{ queryKey: ["day-rings"] }],
    ]);
  });

  it("skips an unrecognized scope without invalidating anything for it", async () => {
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    renderWithClient(queryClient);

    act(() => {
      FakeEventSource.instances[0].emit("data.changed", {
        type: "data.changed",
        scopes: ["teams", "something_else"],
        as_of: "2025-12-07T18:00:00",
      });
    });

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalled());

    // "teams" resolves (+ its day-rings side-effect, task 10.6); "something_else" maps
    // to nothing and is silently skipped rather than invalidating anything for it.
    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["teams"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["day-rings"] });
  });

  it("updates liveState from a live_state.changed event", async () => {
    const { result } = renderWithClient(new QueryClient());

    act(() => {
      FakeEventSource.instances[0].emit("live_state.changed", {
        type: "live_state.changed",
        live_state: "live",
      });
    });

    await waitFor(() => expect(result.current.liveState).toBe("live"));
  });

  it("updates the liveTierSeconds store field from a tier.change event", async () => {
    renderWithClient(new QueryClient());

    act(() => {
      FakeEventSource.instances[0].emit("tier.change", {
        type: "tier.change",
        live_tier_seconds: 10,
      });
    });

    await waitFor(() => {
      expect(useLiveConnectionStore.getState().liveTierSeconds).toBe(10);
    });
  });

  it("records lastEventAt on a heartbeat", async () => {
    const { result } = renderWithClient(new QueryClient());
    expect(result.current.lastEventAt).toBeNull();

    act(() => {
      FakeEventSource.instances[0].emit("heartbeat", { type: "heartbeat", at: "now" });
    });

    await waitFor(() => expect(result.current.lastEventAt).not.toBeNull());
  });

  it("marks disconnected and reconnects with backoff after an error", async () => {
    vi.useFakeTimers();
    const { result } = renderWithClient(new QueryClient());
    act(() => FakeEventSource.instances[0].emitOpen());
    expect(result.current.connected).toBe(true);

    act(() => FakeEventSource.instances[0].emitError());
    expect(result.current.connected).toBe(false);
    expect(FakeEventSource.instances[0].closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1); // no reconnect attempt yet

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000); // first backoff: 1s
    });
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it("doubles the reconnect delay on each consecutive failure, capped at 30s", async () => {
    vi.useFakeTimers();
    renderWithClient(new QueryClient());

    // 1st failure -> reconnect after 1s
    act(() => FakeEventSource.instances[0].emitError());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(999);
    });
    expect(FakeEventSource.instances).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(FakeEventSource.instances).toHaveLength(2);

    // 2nd failure -> reconnect after 2s
    act(() => FakeEventSource.instances[1].emitError());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1999);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it("a successful reconnect resets the backoff attempt counter", async () => {
    vi.useFakeTimers();
    renderWithClient(new QueryClient());

    act(() => FakeEventSource.instances[0].emitError());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(FakeEventSource.instances).toHaveLength(2);

    act(() => FakeEventSource.instances[1].emitOpen()); // reconnected -> attempt resets to 0
    act(() => FakeEventSource.instances[1].emitError());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(999);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(FakeEventSource.instances).toHaveLength(3); // 1s again, not 2s
  });

  it("sets connectionLostLong after being disconnected for >30s", async () => {
    vi.useFakeTimers();
    renderWithClient(new QueryClient());

    act(() => FakeEventSource.instances[0].emitError());
    expect(useLiveConnectionStore.getState().connectionLostLong).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCONNECT_LONG_MS + 1000);
    });

    expect(useLiveConnectionStore.getState().connectionLostLong).toBe(true);
  });

  it("sets a 5-minute refetchInterval default once connectionLostLong flips true", async () => {
    vi.useFakeTimers();
    const queryClient = new QueryClient();
    renderWithClient(queryClient);

    act(() => FakeEventSource.instances[0].emitError());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISCONNECT_LONG_MS + 1000);
    });

    expect(queryClient.getDefaultOptions().queries?.refetchInterval).toBe(
      DISCONNECTED_REFETCH_INTERVAL_MS,
    );
  });

  it("refetches and reconnects immediately when the tab becomes visible again", async () => {
    vi.useFakeTimers();
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    renderWithClient(queryClient);

    act(() => FakeEventSource.instances[0].emitError());
    expect(FakeEventSource.instances).toHaveLength(1);

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    act(() => document.dispatchEvent(new Event("visibilitychange")));

    expect(invalidateSpy).toHaveBeenCalledWith();
    expect(FakeEventSource.instances).toHaveLength(2); // reconnected immediately, not after backoff
  });
});
