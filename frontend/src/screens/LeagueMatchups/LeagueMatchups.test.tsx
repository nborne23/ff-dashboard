import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import {
  createMemoryRouter,
  MemoryRouter,
  Outlet,
  Route,
  RouterProvider,
  Routes,
} from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LeagueMatchupsData } from "../../api/leagueMatchups";
import { parseTeamRoute } from "../../hooks/teamRoute";
import { routeChildren } from "../../routes";
import { useUiStore } from "../../stores/ui";
import type { Envelope, Meta } from "../../types/api";
import { MATCHUPS_FIXTURE, OTHER_ENTRY, USER_TEAM } from "./fixtures";
import LeagueMatchups from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

const meta: Meta = {
  live_state: "live",
  as_of: "2026-10-25T18:00:00Z",
  next_refresh_at: "2026-10-25T18:00:30Z",
  current_week: 8,
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

function stubFetch(data: LeagueMatchupsData = MATCHUPS_FIXTURE, status = 200) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (status >= 400) return jsonResponse(status, { detail: "boom" });
    const week = Number(new URL(url, "http://x").searchParams.get("week") ?? data.week);
    return jsonResponse(200, {
      data: { ...data, week },
      meta,
    } satisfies Envelope<LeagueMatchupsData>);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderScreen(data?: LeagueMatchupsData, status?: number) {
  const fetchMock = stubFetch(data, status);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/team/${USER_TEAM.id}/league/matchups`]}>
        <Routes>
          <Route path="/team/:teamId/league/matchups" element={<LeagueMatchups />} />
          <Route path="/team/:teamId/league/matchups/:matchupId" element={<div>detail</div>} />
          <Route path="/team/:teamId/h2h" element={<div>own h2h</div>} />
          <Route path="/team/:teamId/league" element={<div>standings</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("LeagueMatchups", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
  });

  it("renders the league, the week, and one card per matchup in endpoint order", async () => {
    useUiStore.setState({ week: 8 });
    renderScreen();

    expect(await screen.findByRole("heading", { name: "All Matchups" })).toBeTruthy();
    expect(
      await screen.findByText("GAI IT Battle Royale", { selector: ".large-subtitle" }),
    ).toBeTruthy();
    expect(screen.getByText("Week 8")).toBeTruthy();

    const cards = screen.getAllByRole("link", { name: /\d+\.\d\d, / });
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByText("Scranton Stranglers")).toBeTruthy();
    expect(within(cards[1]).getByText("HellFire Club")).toBeTruthy();
  });

  it("shows each team's position, manager, and W-L-T record", async () => {
    useUiStore.setState({ week: 8 });
    renderScreen();
    const card = (await screen.findAllByRole("link", { name: /HellFire Club/ }))[0];

    const rows = card.querySelectorAll(".lm-row");
    expect(rows[0].querySelector(".lm-rank")?.textContent).toBe("7");
    expect(within(card).getByText("Tony · 3-4-0")).toBeTruthy();
    expect(within(card).getByText("Matt · 6-1-0")).toBeTruthy();
  });

  it("marks the user's matchup and the leader of each", async () => {
    useUiStore.setState({ week: 8 });
    renderScreen();
    const [own, other] = await screen.findAllByRole("link", { name: /\d+\.\d\d, / });

    expect(own.getAttribute("data-own")).not.toBeNull();
    expect(within(own).getByText("Your matchup")).toBeTruthy();
    expect(other.getAttribute("data-own")).toBeNull();

    // Away leads in both fixtures, so only the second row is emphasized.
    for (const card of [own, other]) {
      const rows = card.querySelectorAll(".lm-row");
      expect(rows[0].hasAttribute("data-leading")).toBe(false);
      expect(rows[1].hasAttribute("data-leading")).toBe(true);
    }
  });

  it("labels a live matchup LIVE and a settled one Final, with projections only while open", async () => {
    useUiStore.setState({ week: 8 });
    renderScreen();
    const [own, other] = await screen.findAllByRole("link", { name: /\d+\.\d\d, / });

    expect(within(own).getByText("LIVE")).toBeTruthy();
    expect(within(own).getByText("proj 94.7")).toBeTruthy();
    expect(within(other).getByText("Final")).toBeTruthy();
    expect(within(other).queryByText(/^proj/)).toBeNull();
  });

  it("sends your matchup to the Matchup tab and anyone else's to the read-only detail", async () => {
    useUiStore.setState({ week: 8 });
    renderScreen();
    const [own, other] = await screen.findAllByRole("link", { name: /\d+\.\d\d, / });

    expect(own.getAttribute("href")).toBe(`/team/${USER_TEAM.id}/h2h`);
    expect(other.getAttribute("href")).toBe(
      `/team/${USER_TEAM.id}/league/matchups/${encodeURIComponent(OTHER_ENTRY.matchup.id)}`,
    );

    fireEvent.click(other);
    expect(await screen.findByText("detail")).toBeTruthy();
  });

  it("steps the shared week and refetches, stopping at the league's current week", async () => {
    useUiStore.setState({ week: 8 });
    const fetchMock = renderScreen();
    await screen.findByText("Scranton Stranglers");

    const next = screen.getByRole("button", { name: "Next week" }) as HTMLButtonElement;
    expect(next.disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
    expect(useUiStore.getState().week).toBe(7);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("week=7"))).toBe(true),
    );
    expect(await screen.findByText("Week 7")).toBeTruthy();
  });

  it("disables the back arrow on week 1", async () => {
    renderScreen();
    await screen.findByText("Week 1");

    expect(
      (screen.getByRole("button", { name: "Previous week" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("explains an empty week rather than showing nothing", async () => {
    useUiStore.setState({ week: 8 });
    renderScreen({ ...MATCHUPS_FIXTURE, matchups: [] });

    expect(await screen.findByText("No matchups synced for week 8 yet.")).toBeTruthy();
  });

  it("shows a retryable error card when the request fails", async () => {
    renderScreen(undefined, 500);

    expect(await screen.findByTestId("league-matchups-error")).toBeTruthy();
    expect(screen.getByRole("link", { name: /League/ }).getAttribute("href")).toBe(
      `/team/${USER_TEAM.id}/league`,
    );
  });
});

describe("All Matchups routing", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useUiStore.setState({ week: 1 });
  });

  it("keeps the League tab selected", () => {
    expect(parseTeamRoute(`/team/${USER_TEAM.id}/league/matchups`)).toEqual({
      teamId: USER_TEAM.id,
      section: "league",
    });
    expect(parseTeamRoute(`/team/${USER_TEAM.id}/league/matchups/x`)?.section).toBe("league");
  });

  it("resolves /league/matchups to All Matchups, not another team's roster", async () => {
    useUiStore.setState({ week: 8 });
    stubFetch();
    const router = createMemoryRouter(
      [{ path: "/", element: <Outlet />, children: routeChildren }],
      {
        initialEntries: [`/team/${USER_TEAM.id}/league/matchups`],
      },
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "All Matchups" })).toBeTruthy();
    expect(screen.queryByTestId("league-team-loading")).toBeNull();
  });
});
