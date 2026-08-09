// Live SSE connection state (task 8.6/8.9) — a small zustand slice `api/events.ts`'s
// useLiveEvents() writes to and any component (Topbar, Sidebar) can read from without
// prop-drilling. Deliberately not persisted: connection state is meaningless across a
// reload (a fresh mount always starts disconnected until the first `EventSource` "open").

import { create } from "zustand";

import type { LiveState as LiveStateValue } from "../types/api";

interface LiveConnectionState {
  /** Is the `/api/events` EventSource currently open. */
  connected: boolean;
  /** Most recent `live_state.changed` value (replayed on every connect — see
   * api/events.py's `event_stream` — so this is accurate even before the first
   * `refresh_nfl_state` tick after a fresh page load). */
  liveState: LiveStateValue;
  /** epoch ms of the last event received of *any* type (including heartbeats) — a
   * heartbeat still proves the connection is alive even with no `data.changed` to show. */
  lastEventAt: number | null;
  /** True once the connection has been down continuously for >30s (task 8.9). */
  connectionLostLong: boolean;
  /** Current live-tier interval in seconds, from the last `tier.change` event. */
  liveTierSeconds: number | null;
  setConnected: (connected: boolean) => void;
  setLiveState: (liveState: LiveStateValue) => void;
  setLastEventAt: (lastEventAt: number) => void;
  setConnectionLostLong: (connectionLostLong: boolean) => void;
  setLiveTierSeconds: (liveTierSeconds: number) => void;
}

export const useLiveConnectionStore = create<LiveConnectionState>()((set) => ({
  connected: false,
  liveState: "off_day",
  lastEventAt: null,
  connectionLostLong: false,
  liveTierSeconds: null,
  setConnected: (connected) => set({ connected }),
  setLiveState: (liveState) => set({ liveState }),
  setLastEventAt: (lastEventAt) => set({ lastEventAt }),
  setConnectionLostLong: (connectionLostLong) => set({ connectionLostLong }),
  setLiveTierSeconds: (liveTierSeconds) => set({ liveTierSeconds }),
}));
