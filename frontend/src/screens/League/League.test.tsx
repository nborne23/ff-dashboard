import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TeamDetailData } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import type { Envelope, LeagueStandingsData, Meta, Team } from "../../types/api";
import { LEAGUE_FIXTURE, STANDINGS_FIXTURE } from "./fixtures";
import League from "./index";

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
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

const team: Team = STANDINGS_FIXTURE.rows.find((r) => r.team.is_user_team)!.team;

const teamDetail: TeamDetailData = {
  team,
  league: LEAGUE_FIXTURE,
  starters: [],
  bench: [],
  record_history: [],
};

function renderLeague(
  standings: LeagueStandingsData = STANDINGS_FIXTURE,
  options: { status?: number; platforms?: Meta["platforms"] } = {},
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/league")) {
      if (options.status && options.status >= 400) {
        return jsonResponse(options.status, { detail: "boom" });
      }
      return jsonResponse(200, { data: standings, meta } satisfies Envelope<LeagueStandingsData>);
    }
    return jsonResponse(200, {
      data: teamDetail,
      meta: { ...meta, platforms: options.platforms ?? meta.platforms },
    } satisfies Envelope<TeamDetailData>);
  });
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/team/${team.id}/league`]}>
        <Routes>
          <Route path="/team/:teamId/league" element={<League />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("League", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
  });

  it("renders the league header", async () => {
    renderLeague();

    expect(await screen.findByText("THE LEAGUE")).toBeTruthy();
    expect(screen.getByText(/2026 · 6 teams/)).toBeTruthy();
  });

  it("renders rows in the order the endpoint returned them", async () => {
    // Order is the backend's decision — it follows ESPN's seed, then record, then a
    // stable id. The screen must not re-sort and quietly disagree with the API.
    renderLeague();
    await screen.findByText("THE LEAGUE");

    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[1].textContent);

    expect(names[0]).toContain("Fresh Meat");
    expect(names[names.length - 1]).toContain("Scarecrow Boat");
  });

  it("renders positions as given rather than recomputing them", async () => {
    renderLeague();
    await screen.findByText("THE LEAGUE");

    const positions = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[0].textContent);

    expect(positions).toEqual(["1", "2", "3", "4", "5", "6"]);
  });

  it("marks the user's own row", async () => {
    renderLeague();
    await screen.findByText("THE LEAGUE");

    const own = screen.getByText("Hingle McCringleberry").closest("tr")!;
    expect(own.getAttribute("data-own")).toBe("true");

    const other = screen.getByText("Fresh Meat").closest("tr")!;
    expect(other.getAttribute("data-own")).toBeNull();
  });

  it("renders a team with no logo without requesting an image", async () => {
    renderLeague();
    await screen.findByText("THE LEAGUE");

    const row = screen.getByText("Baby Got Dak").closest("tr")!;
    expect(within(row).getByTestId("team-logo-fallback").textContent).toBe("BG");
    expect(within(row).queryByRole("presentation", { hidden: true })).toBeNull();
  });

  it("renders records and points", async () => {
    renderLeague();
    await screen.findByText("THE LEAGUE");

    const row = screen.getByText("Fresh Meat").closest("tr")!;
    expect(within(row).getByText("3-0")).toBeTruthy();
    expect(within(row).getByText("402.5")).toBeTruthy();
  });

  it("keeps tied teams in the order the backend gave them", async () => {
    // Both are 0-0-0 with zero points and zero seed — the case that has no natural
    // order and must therefore come from the backend's stable id tiebreak.
    renderLeague();
    await screen.findByText("THE LEAGUE");

    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[1].textContent ?? "");
    const garbage = names.findIndex((n) => n.includes("Garbage"));
    const scarecrow = names.findIndex((n) => n.includes("Scarecrow Boat"));

    expect(garbage).toBeLessThan(scarecrow);
  });

  it("renders the error card when the request fails", async () => {
    renderLeague(STANDINGS_FIXTURE, { status: 500 });

    expect(await screen.findByTestId("league-error")).toBeTruthy();
  });

  it("renders the empty state when no platform is connected", async () => {
    renderLeague(STANDINGS_FIXTURE, {
      platforms: {
        yahoo: { ok: false, error: "not_connected" },
        espn: { ok: false, error: "not_connected" },
      },
    });

    expect(await screen.findByTestId("league-empty")).toBeTruthy();
  });

  it("renders an empty league without crashing", async () => {
    renderLeague({ ...STANDINGS_FIXTURE, rows: [] });

    expect(await screen.findByText("No teams in this league yet.")).toBeTruthy();
  });
});
