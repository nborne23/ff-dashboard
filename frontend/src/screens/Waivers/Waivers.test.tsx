import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TeamDetailData, WaiversResponseData } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import type { Envelope, League, Meta, Team } from "../../types/api";
import { WAIVERS_FIXTURE } from "./fixtures";
import Waivers from "./index";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

const meta: Meta = {
  live_state: "off_day",
  as_of: "2026-08-30T12:00:00Z",
  next_refresh_at: "2026-08-30T12:30:00Z",
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

const team: Team = {
  id: "espn:l-705139273-t-4",
  league_id: "espn:705139273",
  name: "Broadcom",
  manager_name: "Nick",
  record: { w: 0, l: 0, t: 0 },
  rank: { current: 1, total: 12 },
  points_for: 0,
  points_against: 0,
  is_user_team: true,
  current_score: 0,
  current_opp_score: 0,
  current_opponent_name: "Bing Bong",
  spark_last_6: [],
  accent_color: "#FF2D55",
  is_live: false,
};

const league: League = {
  id: "espn:705139273",
  platform: "espn",
  platform_id: "705139273",
  name: "THE LEAGUE",
  season: 2026,
  team_count: 12,
  scoring_type: "half_ppr",
  current_week: 1,
};

const teamDetail: TeamDetailData = {
  team,
  league,
  starters: [],
  bench: [],
  record_history: [],
};

function renderWaivers(
  waivers: WaiversResponseData = WAIVERS_FIXTURE,
  options: { waiversStatus?: number; platforms?: Meta["platforms"] } = {},
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/waivers")) {
      if (options.waiversStatus && options.waiversStatus >= 400) {
        return jsonResponse(options.waiversStatus, { detail: "boom" });
      }
      // Echo the position filter back so the filter test can assert it narrows.
      const position = new URL(url, "http://x").searchParams.get("position");
      const candidates = position
        ? waivers.candidates.filter((c) => c.player.position === position)
        : waivers.candidates;
      return jsonResponse(200, {
        data: { ...waivers, candidates },
        meta,
      } satisfies Envelope<WaiversResponseData>);
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
      <MemoryRouter initialEntries={[`/team/${team.id}/waivers`]}>
        <Routes>
          <Route path="/team/:teamId/waivers" element={<Waivers />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function rowFor(name: string): HTMLElement {
  return screen.getByText(name).closest("tr") as HTMLElement;
}

describe("Waivers", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
  });

  it("renders candidates in the order the endpoint returned them", async () => {
    renderWaivers();

    expect(await screen.findByText("Waivers")).toBeTruthy();

    const names = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[1].textContent);
    expect(names[0]).toContain("Tyler Boyd");
    expect(names[names.length - 1]).toContain("Blake Grupe");
  });

  it("renders a genuine 0.0 projection as a number, not an em dash", async () => {
    // Tommy DeVito really does project 0.0 in live data. Collapsing it to "—" would
    // report a player the system HAS judged as one it knows nothing about.
    renderWaivers();
    await screen.findByText("Waivers");

    const row = rowFor("Tommy DeVito");
    expect(within(row).getByText("0.0")).toBeTruthy();
  });

  it("renders a null projection as an em dash, never as 0.0", async () => {
    renderWaivers();
    await screen.findByText("Waivers");

    const row = rowFor("Malik Washington");
    const cells = within(row).getAllByRole("cell");
    // Projection and delta columns are the last two.
    expect(cells[cells.length - 2].textContent).toBe("—");
    expect(cells[cells.length - 1].textContent).toBe("—");
  });

  it("renders a null delta as an em dash even when the projection is present", async () => {
    // Blake Grupe projects 121.5 but the user starts no kicker, so there is nothing
    // for him to displace — "no comparison" is not "no upgrade".
    renderWaivers();
    await screen.findByText("Waivers");

    const row = rowFor("Blake Grupe");
    const cells = within(row).getAllByRole("cell");
    expect(cells[cells.length - 2].textContent).toBe("121.5");
    expect(cells[cells.length - 1].textContent).toBe("—");
  });

  it("shows a negative delta as negative", async () => {
    // The whole point of the season-scoped comparison: a downgrade must read as one.
    renderWaivers();
    await screen.findByText("Waivers");

    const row = rowFor("Jaleel McLaughlin");
    expect(within(row).getByText("-37.5")).toBeTruthy();
  });

  it("narrows to one position when a filter is selected", async () => {
    renderWaivers();
    await screen.findByText("Waivers");
    expect(screen.getByText("Tyler Boyd")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "RB" }));

    await waitFor(() => expect(screen.queryByText("Tyler Boyd")).toBeNull());
    expect(screen.getByText("Rachaad White")).toBeTruthy();
  });

  it("returns to the full list when the filter is cleared", async () => {
    renderWaivers();
    await screen.findByText("Waivers");

    fireEvent.click(screen.getByRole("button", { name: "RB" }));
    await waitFor(() => expect(screen.queryByText("Tyler Boyd")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => expect(screen.getByText("Tyler Boyd")).toBeTruthy());
  });

  it("renders an empty-filter message rather than a bare table", async () => {
    renderWaivers({ ...WAIVERS_FIXTURE, candidates: [] });

    expect(await screen.findByText("No available players match this filter.")).toBeTruthy();
  });

  it("renders the error card when the request fails", async () => {
    renderWaivers(WAIVERS_FIXTURE, { waiversStatus: 500 });

    expect(await screen.findByTestId("waivers-error")).toBeTruthy();
  });

  it("renders the empty state when no platform is connected", async () => {
    renderWaivers(WAIVERS_FIXTURE, {
      platforms: {
        yahoo: { ok: false, error: "not_connected" },
        espn: { ok: false, error: "not_connected" },
      },
    });

    expect(await screen.findByTestId("waivers-empty")).toBeTruthy();
  });
});
