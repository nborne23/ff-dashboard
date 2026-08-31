import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, PlatformStatus, Team } from "../../types/api";
import type { TeamsListData } from "../../api/teams";
import Dashboard from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

function envelope(
  teams: Team[],
  platforms: Record<"yahoo" | "espn", PlatformStatus> = { yahoo: { ok: true }, espn: { ok: true } },
): Envelope<TeamsListData> {
  return {
    data: { teams },
    meta: {
      live_state: "off_day",
      as_of: "2026-07-12T12:00:00Z",
      next_refresh_at: "2026-07-12T12:30:00Z",
      platforms,
    },
  };
}

function makeTeam(overrides: Partial<Team> = {}): Team {
  return {
    id: "yahoo:nfl.l.1.t.4",
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
  logo_url: null,
    ...overrides,
  };
}

function renderDashboard(body: Envelope<TeamsListData>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse(200, body)),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Dashboard", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the connect-required empty state when teams=[] and both platforms are down", async () => {
    renderDashboard(
      envelope([], {
        yahoo: { ok: false, error: "auth_required" },
        espn: { ok: false, error: "auth_required" },
      }),
    );

    expect(await screen.findByTestId("connect-required")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to Settings" }).getAttribute("href")).toBe(
      "/settings",
    );
  });

  it("shows the connect-required empty state when the teams list is empty", async () => {
    renderDashboard(envelope([]));

    expect(await screen.findByTestId("connect-required")).toBeTruthy();
  });

  it("renders team cards and the live-count meta line from real data", async () => {
    renderDashboard(
      envelope([
        makeTeam(),
        makeTeam({ id: "espn:l-9-t-2", name: "Eleven Thunder", is_live: false }),
      ]),
    );

    // "Highland Bombers" appears twice: as a team card and as the
    // InsightTopPerformer fallback headline (it's the top scorer).
    expect(await screen.findAllByText("Highland Bombers")).toHaveLength(2);
    expect(screen.getByText("Eleven Thunder")).toBeTruthy();
    expect(screen.getByText("2 teams · 1 live")).toBeTruthy();
    expect(screen.getByText("Insights")).toBeTruthy();
  });
});
