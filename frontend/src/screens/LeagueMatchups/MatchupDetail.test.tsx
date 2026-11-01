import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LeagueMatchupDetailData } from "../../api/leagueMatchups";
import type { Envelope, Meta } from "../../types/api";
import { DETAIL_FIXTURE, USER_TEAM } from "./fixtures";
import MatchupDetail from "./MatchupDetail";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

const meta: Meta = {
  live_state: "off_day",
  as_of: "2026-10-27T12:00:00Z",
  next_refresh_at: "2026-10-27T12:30:00Z",
  current_week: 8,
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

function renderDetail(data: LeagueMatchupDetailData = DETAIL_FIXTURE, status = 200) {
  const fetchMock = vi.fn(async () =>
    status >= 400
      ? jsonResponse(status, { detail: "boom" })
      : jsonResponse(200, { data, meta } satisfies Envelope<LeagueMatchupDetailData>),
  );
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const path = `/team/${USER_TEAM.id}/league/matchups/${encodeURIComponent(data.matchup.id)}`;
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/team/:teamId/league/matchups/:matchupId" element={<MatchupDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("MatchupDetail", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches the matchup by its encoded id under the viewing team", async () => {
    const fetchMock = renderDetail();
    await screen.findByRole("heading", { name: "Matchup" });

    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe(
      `/api/teams/${USER_TEAM.id}/league/matchups/${encodeURIComponent(DETAIL_FIXTURE.matchup.id)}`,
    );
  });

  it("shows both teams, their scores, and who leads by how much", async () => {
    renderDetail();
    await screen.findByRole("heading", { name: "Matchup" });

    expect(screen.getByText("GAI IT Battle Royale · Week 8 · Final")).toBeTruthy();
    expect(screen.getByText("HELLFIRE CLUB")).toBeTruthy();
    expect(screen.getByText("TRASH PANDAS")).toBeTruthy();
    expect(screen.getByText("103.3", { selector: ".me .score-big" })).toBeTruthy();
    expect(screen.getByText("114.8", { selector: ".opp .score-big" })).toBeTruthy();
    expect(screen.getByText("Leads by")).toBeTruthy();
    expect(screen.getByText("11.5")).toBeTruthy();
    expect(screen.getByText("Trash Pandas", { selector: ".lm-ring-leader" })).toBeTruthy();
  });

  it("pairs the starters slot by slot", async () => {
    renderDetail();
    const table = (await screen.findByRole("table")) as HTMLElement;

    expect(within(table).getByText("Drake Maye")).toBeTruthy();
    expect(within(table).getByText("Caleb Williams")).toBeTruthy();
    expect(within(table).getByText("+6.3")).toBeTruthy();
  });

  it("says so when no lineups were synced for that week", async () => {
    renderDetail({ ...DETAIL_FIXTURE, slots: [] });

    expect(await screen.findByText("Lineups weren't synced for week 8.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("calls a level game tied", async () => {
    renderDetail({
      ...DETAIL_FIXTURE,
      matchup: { ...DETAIL_FIXTURE.matchup, home_score: 90, away_score: 90 },
    });

    expect(await screen.findByText("Tied")).toBeTruthy();
  });

  it("links back to All Matchups", async () => {
    renderDetail();
    const back = await screen.findByRole("link", { name: /All Matchups/ });

    expect(back.getAttribute("href")).toBe(`/team/${USER_TEAM.id}/league/matchups`);
  });

  it("shows a retryable error card when the request fails", async () => {
    renderDetail(DETAIL_FIXTURE, 404);

    expect(await screen.findByTestId("league-matchup-error")).toBeTruthy();
  });
});
