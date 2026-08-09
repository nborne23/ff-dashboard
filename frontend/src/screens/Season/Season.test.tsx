import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, League, Meta, SeasonWeek, Team } from "../../types/api";
import type { TeamDetailData, TeamSeasonData } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import Season from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

const meta: Meta = {
  live_state: "off_day",
  as_of: "2026-07-12T12:00:00Z",
  next_refresh_at: "2026-07-12T12:30:00Z",
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

const team: Team = {
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
  is_live: false,
  spark_last_6: [78, 92, 64, 88, 94, 87],
  accent_color: "#FF2D55",
};

const league: League = {
  id: "yahoo:nfl.l.1",
  platform: "yahoo",
  platform_id: "nfl.l.1",
  name: "Highland Bros Dynasty",
  season: 2025,
  team_count: 12,
  scoring_type: "ppr",
  current_week: 14,
};

function makeWeek(overrides: Partial<SeasonWeek> = {}): SeasonWeek {
  return {
    team_id: team.id,
    week: 1,
    score: 102.4,
    opp_score: 88.1,
    opp_team_name: "Beard Mode",
    is_win: true,
    is_current: false,
    ...overrides,
  };
}

const weeks: SeasonWeek[] = [
  makeWeek({ week: 1 }),
  makeWeek({ week: 2, score: 78.0, opp_score: 95.4, is_win: false, opp_team_name: "Gronk Stars" }),
  makeWeek({ week: 3, score: 124.6, opp_score: 91.0, opp_team_name: "Mom's Spaghetti" }),
  makeWeek({
    week: 4,
    score: 87.4,
    opp_score: 71.2,
    opp_team_name: "Touchdown Club",
    is_current: true,
  }),
];

const seasonData: TeamSeasonData = {
  weeks,
  highlights: {
    season_high: weeks[2],
    win_streak: 2,
    most_started: {
      player: {
        id: "p1",
        name: "P. Mahomes",
        position: "QB",
        nfl_team: "KC",
        nfl_opponent: null,
        nfl_game_id: null,
        headshot_url: "/api/headshots/yahoo/1.png",
        bye_week: null,
        injury_status: null,
      },
      starts: 14,
      avg_points: 18.4,
    },
  },
};

const teamDetail: TeamDetailData = {
  team,
  league,
  starters: [],
  bench: [],
  record_history: weeks,
};

function renderSeason(season: TeamSeasonData = seasonData) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/season")) {
      return jsonResponse(200, { data: season, meta } satisfies Envelope<TeamSeasonData>);
    }
    return jsonResponse(200, { data: teamDetail, meta } satisfies Envelope<TeamDetailData>);
  });
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/team/${team.id}/season`]}>
        <Routes>
          <Route path="/team/:teamId/season" element={<Season />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("Season", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
  });

  it("renders the header with team name and season year", async () => {
    renderSeason();

    expect(await screen.findByText("Season")).toBeTruthy();
    expect(screen.getByText("Highland Bombers · 2025")).toBeTruthy();
  });

  it("renders the three highlight cards from the mocked payload", async () => {
    renderSeason();

    expect(await screen.findByText("Win Streak")).toBeTruthy();
    expect(screen.getByText("2 weeks")).toBeTruthy();

    expect(screen.getByText("Season High")).toBeTruthy();
    expect(screen.getByText("124.6 pts")).toBeTruthy();
    expect(screen.getByText("Week 3 vs Mom's Spaghetti")).toBeTruthy();

    expect(screen.getByText("Most Started")).toBeTruthy();
    expect(screen.getByText("P. Mahomes")).toBeTruthy();
    expect(screen.getByText("14 starts · 18.4 avg pts")).toBeTruthy();
  });

  it("renders the record donut with W–L and win rate", async () => {
    renderSeason();

    expect(await screen.findByText("3–1")).toBeTruthy();
    expect(screen.getByText("75% win rate")).toBeTruthy();
  });

  it("falls back gracefully when season_high and most_started are null", async () => {
    renderSeason({
      weeks: [],
      highlights: { season_high: null, win_streak: 0, most_started: null },
    });

    expect(await screen.findByText("Win Streak")).toBeTruthy();
    expect(screen.getByText("0 weeks")).toBeTruthy();
    expect(screen.getByText("No games played yet")).toBeTruthy();
    expect(screen.getByText("No data yet")).toBeTruthy();
    expect(screen.getByText("No weeks played yet")).toBeTruthy();
  });
});
