import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TeamDetailData, WaiversResponseData } from "../../api/teams";
import { useUiStore } from "../../stores/ui";
import { useWaiverFiltersStore } from "../../stores/waiverFilters";
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
  current_week: 1,
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
  logo_url: null,
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
      // Echo the position and status filters back so the filter tests can assert they
      // narrow, and answer `game_day` the way the server does: applied only when it is
      // one of the week's remaining game days.
      const params = new URL(url, "http://x").searchParams;
      const position = params.get("position");
      const status = params.get("status");
      const gameDay = params.get("game_day");
      const candidates = waivers.candidates
        .filter((c) => !position || c.player.position === position)
        .filter((c) => status !== "waivers" || c.status === "WAIVERS");
      return jsonResponse(200, {
        data: {
          ...waivers,
          candidates,
          game_day: gameDay && waivers.game_days.includes(gameDay) ? gameDay : null,
        },
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

/** A row's cell under the column with this class.
 *
 * Was positional (`cells[cells.length - 2]`), which broke the moment a column was
 * inserted before the last one — the assertions silently moved to the wrong column
 * rather than failing for the right reason. */
function cellIn(row: HTMLElement, columnClass: string): HTMLElement {
  const cell = row.querySelector(`td.${columnClass}`);
  if (!cell) throw new Error(`no .${columnClass} cell in row`);
  return cell as HTMLElement;
}

/** The two horizons a Proj/Upgrade cell now stacks: `[this week, full season]`. */
function stackedIn(row: HTMLElement, columnClass: string): [string, string] {
  const cell = cellIn(row, columnClass);
  const lines = [...cell.querySelectorAll(".waiver-stack > *")].map((el) =>
    (el.textContent ?? "").trim(),
  );
  if (lines.length !== 2) throw new Error(`expected 2 stacked values, got ${lines.length}`);
  return [lines[0], lines[1]];
}

describe("Waivers", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
    useWaiverFiltersStore.setState({ byTeam: {} });
  });

  it("renders candidates in the order the endpoint returned them", async () => {
    renderWaivers();

    expect(await screen.findByText("Waivers")).toBeTruthy();

    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((r) => within(r).getAllByRole("cell")[1].textContent);
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
    // Both horizons: no projection means no number on either, and never a 0.
    expect(stackedIn(row, "roster-col-proj")).toEqual(["—", "—"]);
    expect(stackedIn(row, "roster-col-actual")).toEqual(["—", "—"]);
  });

  it("renders a null delta as an em dash even when the projection is present", async () => {
    // Blake Grupe projects 121.5 but the user starts no kicker, so there is nothing
    // for him to displace — "no comparison" is not "no upgrade".
    renderWaivers();
    await screen.findByText("Waivers");

    const row = rowFor("Blake Grupe");
    // Season projection present, weekly one absent (no independent weekly number in
    // this fixture) — and no eligible kicker to displace, so both deltas stay dashes.
    expect(stackedIn(row, "roster-col-proj")).toEqual(["—", "121.5"]);
    expect(stackedIn(row, "roster-col-actual")).toEqual(["—", "—"]);
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

describe("Waivers filter sheet", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUiStore.setState({ week: 1 });
    useWaiverFiltersStore.setState({ byTeam: {} });
  });

  function waiverUrls(fetchMock: ReturnType<typeof renderWaivers>): URLSearchParams[] {
    return fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.includes("/waivers"))
      .map((url) => new URL(url, "http://x").searchParams);
  }

  async function applyFromSheet(choose: () => void) {
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    await screen.findByRole("dialog", { name: "Filters" });
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Apply Filters" }));
  }

  it("badges a waiver player with the day he clears, and one without a date plainly", async () => {
    renderWaivers();
    await screen.findByText("Tyler Boyd");

    expect(within(rowFor("Tyler Boyd")).getByText("On waivers (clears 9/9)")).toBeTruthy();
    expect(within(rowFor("Rachaad White")).getByText("On waivers")).toBeTruthy();
    expect(within(rowFor("Blake Grupe")).queryByText(/waivers/i)).toBeNull();
  });

  it("starts unfiltered: no badge on the trigger and no filter params on the request", async () => {
    const fetchMock = renderWaivers();
    await screen.findByText("Tyler Boyd");

    const trigger = screen.getByRole("button", { name: "Filters" });
    expect(trigger.className).not.toContain("active");
    const params = waiverUrls(fetchMock)[0];
    for (const key of ["status", "include_mine", "game_day", "sort"]) {
      expect(params.has(key)).toBe(false);
    }
  });

  it("applies Waivers Only server-side and marks the trigger active", async () => {
    const fetchMock = renderWaivers();
    await screen.findByText("Tyler Boyd");

    await applyFromSheet(() =>
      fireEvent.click(screen.getByRole("radio", { name: "Waivers Only" })),
    );

    await waitFor(() => expect(screen.queryByText("Blake Grupe")).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(waiverUrls(fetchMock).at(-1)?.get("status")).toBe("waivers");
    expect(screen.getByRole("button", { name: "Filters, 1 active" })).toBeTruthy();
    expect(screen.getByText(/Waivers Only/)).toBeTruthy(); // the subtitle says so
  });

  it("sends Show My Team, a game day and a sort together", async () => {
    const fetchMock = renderWaivers();
    await screen.findByText("Tyler Boyd");

    await applyFromSheet(() => {
      fireEvent.click(screen.getByRole("switch", { name: "Show My Team" }));
      fireEvent.click(screen.getByRole("radio", { name: "All Available (Games Thursday - 9/10)" }));
      fireEvent.click(screen.getByRole("radio", { name: /This week/ }));
    });

    await waitFor(() => expect(waiverUrls(fetchMock).at(-1)?.get("game_day")).toBe("2026-09-10"));
    const params = waiverUrls(fetchMock).at(-1)!;
    expect(params.get("include_mine")).toBe("true");
    expect(params.get("sort")).toBe("upgrade_week");
    expect(params.has("status")).toBe(false); // "available" is the default
    expect(await screen.findByRole("button", { name: "Filters, 3 active" })).toBeTruthy();
  });

  it("drops a remembered game day the server no longer applies", async () => {
    // The day was chosen earlier in the session; by now its games are over and the
    // server answers without it. The stored choice must go too, or the sheet and the
    // badge would keep claiming a filter the list isn't under.
    useWaiverFiltersStore.setState({
      byTeam: {
        [team.id]: {
          position: null,
          status: "available",
          gameDay: "2026-09-03",
          showMine: false,
          sort: "upgrade",
        },
      },
    });
    renderWaivers();
    await screen.findByText("Tyler Boyd");

    await waitFor(() =>
      expect(useWaiverFiltersStore.getState().byTeam[team.id]?.gameDay).toBeNull(),
    );
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
  });

  it("remembers the filters per team when the screen remounts", async () => {
    renderWaivers();
    await screen.findByText("Tyler Boyd");
    fireEvent.click(screen.getByRole("button", { name: "RB" }));
    await applyFromSheet(() => fireEvent.click(screen.getByRole("radio", { name: "All Players" })));
    await screen.findByRole("button", { name: "Filters, 1 active" });
    cleanup();

    const fetchMock = renderWaivers();
    await screen.findByText("Rachaad White");

    expect(screen.getByRole("button", { name: "RB" }).getAttribute("aria-pressed")).toBe("true");
    const params = waiverUrls(fetchMock)[0];
    expect(params.get("position")).toBe("RB");
    expect(params.get("status")).toBe("all");
  });

  it("marks my own players and other teams' rostered players, with unknown ownership as a dash", async () => {
    const [first, second] = WAIVERS_FIXTURE.candidates;
    renderWaivers({
      ...WAIVERS_FIXTURE,
      candidates: [
        { ...first, status: "ONTEAM", is_mine: true, rostered_by: "Broadcom" },
        { ...second, status: "ONTEAM", rostered_by: "Bing Bong", percent_owned: null },
      ],
    });
    await screen.findByText("Tyler Boyd");

    expect(within(rowFor("Tyler Boyd")).getByText("My team")).toBeTruthy();
    expect(within(rowFor("Rachaad White")).getByText("Bing Bong")).toBeTruthy();
    expect(cellIn(rowFor("Rachaad White"), "roster-col-status").textContent).toBe("—");
  });
});

describe("WaiverTable resilience", () => {
  afterEach(cleanup);

  it("renders a row whose newer projection fields are absent entirely", async () => {
    // A browser holding a bundle newer than the backend it talks to receives no
    // `week_proj_points` at all. `undefined.toFixed()` threw and took the whole screen
    // to the error boundary — one missing number must cost one dash, not the page.
    const stale = JSON.parse(JSON.stringify(WAIVERS_FIXTURE)) as WaiversResponseData;
    for (const c of stale.candidates) {
      delete (c as Partial<(typeof stale.candidates)[number]>).week_proj_points;
      delete (c as Partial<(typeof stale.candidates)[number]>).delta_vs_worst_starter_week;
      delete (c as Partial<(typeof stale.candidates)[number]>).ext_season_proj_points;
    }

    renderWaivers(stale);
    await screen.findByText("Waivers");
    expect(screen.getByText("Blake Grupe")).toBeTruthy();
    expect(stackedIn(rowFor("Blake Grupe"), "roster-col-proj")).toEqual(["—", "121.5"]);
  });
});
