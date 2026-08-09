import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope } from "../types/api";
import type { TeamsListData } from "./teams";
import { useTeams } from "./teams";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function envelope(teams: TeamsListData["teams"]): Envelope<TeamsListData> {
  return {
    data: { teams },
    meta: {
      live_state: "live",
      as_of: "2026-07-12T12:00:00Z",
      next_refresh_at: "2026-07-12T12:00:30Z",
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useTeams", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("parses the envelope and requests the given week", async () => {
    const body = envelope([
      {
        id: "yahoo:nfl.l.1.t.1",
        league_id: "yahoo:nfl.l.1",
        name: "Highland Bombers",
        manager_name: "Nick",
        record: { w: 8, l: 3, t: 0 },
        rank: { current: 2, total: 12 },
        points_for: 1000,
        points_against: 900,
        is_user_team: true,
        current_score: 87.4,
        current_opp_score: 71.2,
        current_opponent_name: "The Touchdown Club",
        is_live: true,
        spark_last_6: [78, 92, 64, 88, 94, 87],
        accent_color: "#FF2D55",
      },
    ]);

    const fetchMock = vi.fn(async () => jsonResponse(200, body));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTeams(14), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(fetchMock).toHaveBeenCalledWith("/api/teams?week=14", expect.anything());
    expect(result.current.data?.data.teams).toHaveLength(1);
    expect(result.current.data?.data.teams[0].name).toBe("Highland Bombers");
    expect(result.current.data?.meta.live_state).toBe("live");
    expect(result.current.data?.meta.platforms.yahoo.ok).toBe(true);
  });
});
