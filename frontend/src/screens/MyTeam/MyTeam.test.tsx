import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, League, RosterSlot, SeasonWeek, Team } from "../../types/api";
import type { TeamDetailData } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import MyTeam from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
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
    ...overrides,
  };
}

function makeLeague(overrides: Partial<League> = {}): League {
  return {
    id: "yahoo:nfl.l.1",
    platform: "yahoo",
    platform_id: "nfl.l.1",
    name: "Highland Bros Dynasty",
    season: 2025,
    team_count: 12,
    scoring_type: "ppr",
    current_week: 14,
    ...overrides,
  };
}

function makeStarter(overrides: Partial<RosterSlot> = {}): RosterSlot {
  return {
    team_id: "yahoo:nfl.l.1.t.4",
    week: 14,
    slot: "QB",
    player: {
      id: "p1",
      name: "Patrick Mahomes",
      position: "QB",
      nfl_team: "KC",
      nfl_opponent: "DEN",
      nfl_game_id: null,
      headshot_url: "/api/headshots/yahoo/1.png",
      bye_week: null,
      injury_status: null,
    },
    proj_points: 22.4,
    actual_points: 19.8,
    is_live: true,
    game_state: "in",
    status_text: "LIVE Q3 7:42",
    ...overrides,
  };
}

function envelope(data: TeamDetailData): Envelope<TeamDetailData> {
  return {
    data,
    meta: {
      live_state: "game_day",
      as_of: "2026-07-12T12:00:00Z",
      next_refresh_at: "2026-07-12T12:30:00Z",
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

const recordHistory: SeasonWeek[] = [
  {
    team_id: "t4",
    week: 13,
    score: 99.5,
    opp_score: 76.2,
    opp_team_name: "Stallion 6",
    is_win: true,
    is_current: false,
  },
  {
    team_id: "t4",
    week: 14,
    score: 87.4,
    opp_score: 71.2,
    opp_team_name: "Touchdown Club",
    is_win: true,
    is_current: true,
  },
];

function renderMyTeam(teamId = "yahoo:nfl.l.1.t.4") {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async () =>
    jsonResponse(
      200,
      envelope({
        team: makeTeam({ id: teamId }),
        league: makeLeague(),
        starters: [makeStarter()],
        bench: [],
        record_history: recordHistory,
      }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/team/${teamId}`]}>
        <Routes>
          <Route path="/team/:teamId" element={<MyTeam />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("MyTeam", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
  });

  it("renders the team header and roster once loaded", async () => {
    renderMyTeam();

    expect(await screen.findByText("Highland Bombers")).toBeTruthy();
    expect(screen.getByText(/Highland Bros Dynasty/)).toBeTruthy();
    expect(screen.getByText("Patrick Mahomes")).toBeTruthy();
  });

  it("refetches with the new week param when a segmented control button is clicked", async () => {
    useUiStore.setState({ week: 1 });
    const fetchMock = renderMyTeam();

    await screen.findByText("Highland Bombers");

    const initialUrl = String(fetchMock.mock.calls[0][0]);
    expect(initialUrl).toContain("week=1");

    fireEvent.click(screen.getByRole("button", { name: "W2" }));

    await screen.findByText((_, el) => el?.textContent === "W2" && el.tagName === "BUTTON");

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(String(lastCall[0])).toContain("week=2");
    expect(useUiStore.getState().week).toBe(2);
  });
});
