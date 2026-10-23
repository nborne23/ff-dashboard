import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TeamDetailData } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import type { Envelope, Meta, RosterSlot } from "../../types/api";
import { LEAGUE_FIXTURE, STANDINGS_FIXTURE } from "./fixtures";
import LeagueTeam from "./LeagueTeam";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

const meta: Meta = {
  live_state: "off_day",
  as_of: "2026-08-31T12:00:00Z",
  next_refresh_at: "2026-08-31T12:30:00Z",
  current_week: 1,
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

const own = STANDINGS_FIXTURE.rows.find((r) => r.team.is_user_team)!.team;
const other = STANDINGS_FIXTURE.rows.find((r) => r.team.name === "Fresh Meat")!.team;

const starter: RosterSlot = {
  team_id: other.id,
  week: 1,
  slot: "QB",
  player: {
    id: "p1",
    name: "Patrick Mahomes",
    position: "QB",
    nfl_team: "KC",
    nfl_opponent: "DEN",
    nfl_game_id: null,
    headshot_url: "",
    bye_week: null,
    injury_status: null,
  },
  proj_points: 22.4,
  actual_points: 0,
  is_live: false,
  game_state: "pre",
  status_text: "Sun 1:00 PM",
  ext_proj_points: null,
};

function renderLeagueTeam(detail: Partial<TeamDetailData> = {}, status = 200) {
  const data: TeamDetailData = {
    team: other,
    league: LEAGUE_FIXTURE,
    starters: [starter],
    bench: [],
    record_history: [],
    ...detail,
  };
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async () =>
    status >= 400
      ? jsonResponse(status, { detail: { code: "team_not_found", message: "No such team" } })
      : jsonResponse(200, { data, meta } satisfies Envelope<TeamDetailData>),
  );
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/team/${own.id}/league/${other.id}`]}>
        <Routes>
          <Route path="/team/:teamId/league/:rosterTeamId" element={<LeagueTeam />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("LeagueTeam", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
  });

  it("fetches and renders the other team's roster", async () => {
    const fetchMock = renderLeagueTeam();

    expect(await screen.findByRole("heading", { name: "Fresh Meat" })).toBeTruthy();
    expect(screen.getByText(/Dana · 3-0/)).toBeTruthy();
    expect(screen.getByText("Patrick Mahomes")).toBeTruthy();
    expect(String(fetchMock.mock.calls[0][0])).toContain(`/api/teams/${other.id}?week=1`);
  });

  it("links back to the viewing team's standings", async () => {
    renderLeagueTeam();

    const back = await screen.findByRole("link", { name: /THE LEAGUE/ });
    expect(back.getAttribute("href")).toBe(`/team/${own.id}/league`);
  });

  it("says so when no roster is synced for the week", async () => {
    renderLeagueTeam({ starters: [], bench: [] });

    expect(await screen.findByText("No roster synced for week 1.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("renders the error card with a way back when the team can't be loaded", async () => {
    renderLeagueTeam({}, 404);

    expect(await screen.findByTestId("league-team-error")).toBeTruthy();
    expect(screen.getByRole("link", { name: /League/ })).toBeTruthy();
  });
});
