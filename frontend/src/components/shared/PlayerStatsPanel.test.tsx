import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, Player, PlayerStatsData, SeasonLog, SeasonLogWeek } from "../../types/api";
import { PlayerAvatarButton, PlayerName } from "./PlayerName";
import { resetPlayerCardTab } from "./playerCardTab";

const PLAYER: Player = {
  id: "espn:p-4431452",
  name: "Drake Maye",
  position: "QB",
  nfl_team: "NE",
  nfl_opponent: "CHI",
  nfl_game_id: null,
  headshot_url: "",
  bye_week: 14,
  injury_status: "ACTIVE",
};

const QB_COLUMNS = [
  { key: "pass_yd", label: "Pass Yds", agg: "sum" as const },
  { key: "pass_td", label: "Pass TD", agg: "sum" as const },
  { key: "rush_td", label: "Rush TD", agg: "sum" as const },
];

function logWeek(week: number, overrides: Partial<SeasonLogWeek> = {}): SeasonLogWeek {
  return {
    week,
    state: "upcoming",
    opponent: null,
    home: null,
    opponent_rank: null,
    proj_points: null,
    fantasy_points: null,
    stats: null,
    ...overrides,
  };
}

const SEASON_LOG: SeasonLog = {
  season: 2026,
  columns: [
    { key: "pass_yd", label: "Pass Yds", agg: "sum", lower_is_better: false },
    { key: "pass_td", label: "Pass TD", agg: "sum", lower_is_better: false },
    { key: "pass_int", label: "Int", agg: "sum", lower_is_better: true },
  ],
  weeks: [
    logWeek(1, {
      state: "final",
      opponent: "LAC",
      home: false,
      opponent_rank: 26,
      proj_points: 13.65,
      fantasy_points: 16.48,
      stats: { pass_yd: 277, pass_td: 1, pass_int: 0 },
    }),
    logWeek(2, {
      state: "final",
      opponent: "SEA",
      home: true,
      opponent_rank: 31,
      proj_points: 13.97,
      fantasy_points: 6.5,
      stats: { pass_yd: 95, pass_td: 1, pass_int: 2 },
    }),
    logWeek(3, {
      state: "final",
      opponent: "SF",
      home: false,
      opponent_rank: 22,
      proj_points: 15.87,
      fantasy_points: 25.6,
      stats: { pass_yd: 280, pass_td: 2, pass_int: 0 },
    }),
    logWeek(4, { state: "bye" }),
    logWeek(5, { state: "dnp", opponent: "DET", home: true, opponent_rank: 1 }),
    logWeek(6, {
      state: "live",
      opponent: "NYJ",
      home: false,
      opponent_rank: 8,
      proj_points: 19.5,
      fantasy_points: 2.1,
      stats: { pass_yd: 40, pass_td: 0, pass_int: 1 },
    }),
    logWeek(7, { opponent: "DAL", home: false, opponent_rank: 6, proj_points: 18.75 }),
  ],
  fantasy_points: 50.68,
  position_rank: 16,
  bye_week: 4,
  ranked_teams: 32,
  ranks_through_week: 5,
};

function stats(overrides: Partial<PlayerStatsData> = {}): PlayerStatsData {
  return {
    player_id: PLAYER.id,
    sleeper_id: "11564",
    position_group: "QB",
    points_format: "half_ppr",
    points_format_fallback: false,
    columns: QB_COLUMNS,
    this_week: {
      season: 2026,
      week: 7,
      final: false,
      opponent: "CHI",
      is_live: true,
      status_text: "Q3 4:12",
      league_points: 10.32,
      league_proj: 20.59,
      stats: { pass_yd: 103, rush_td: 1 },
      stats_source: "espn",
      breakdown: [
        { label: "Rushing TD", stat_value: 1, points: 6 },
        { label: "Passing yards", stat_value: 103, points: 4.12 },
        { label: "Interceptions thrown", stat_value: 1, points: -2 },
        { label: "Rushing yards", stat_value: 22, points: 2.2 },
      ],
      breakdown_source: "league",
      breakdown_total: 10.32,
    },
    seasons: [
      {
        season: 2026,
        team: "NE",
        games: 2,
        fantasy_points: 41.8,
        ppg: 20.9,
        stats: { pass_yd: 419, pass_td: 2 },
      },
      {
        season: 2025,
        team: "NE",
        games: 1,
        fantasy_points: 16.8,
        ppg: 16.8,
        stats: { pass_yd: 287, pass_td: 1 },
      },
    ],
    game_log: [
      {
        season: 2026,
        week: 6,
        date: "2026-10-11",
        team: "NE",
        opponent: "NYJ",
        fantasy_points: 23.8,
        stats: { pass_yd: 250, pass_td: 2 },
      },
      {
        season: 2026,
        week: 7,
        date: "2026-10-18",
        team: "NE",
        opponent: "CHI",
        fantasy_points: 18,
        stats: { pass_yd: 169 },
      },
      {
        season: 2025,
        week: 1,
        date: "2025-09-07",
        team: "NE",
        opponent: "LV",
        fantasy_points: 16.8,
        stats: { pass_yd: 287, pass_td: 1 },
      },
    ],
    season_log: SEASON_LOG,
    jersey_number: "10",
    ...overrides,
  };
}

function envelope(data: PlayerStatsData): Envelope<PlayerStatsData> {
  return {
    data,
    meta: {
      live_state: "live",
      as_of: "2026-10-18T20:00:00Z",
      next_refresh_at: "2026-10-18T20:00:30Z",
      current_week: 7,
      platforms: { yahoo: { ok: true }, espn: { ok: true } },
    },
  };
}

function stubFetch(data: PlayerStatsData) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(envelope(data)),
  }));
  vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
  return fetchMock;
}

function renderName(node: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/team/espn:l-1-t-1/myteam"]}>
        <Routes>
          <Route path="/team/:teamId/myteam" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openPanel() {
  fireEvent.click(screen.getByRole("button", { name: "Drake Maye" }));
  const dialog = await screen.findByRole("dialog", { name: "Drake Maye stats" });
  await within(dialog).findByTestId("points-breakdown");
  return dialog;
}

describe("PlayerName + PlayerStatsPanel", () => {
  afterEach(() => {
    resetPlayerCardTab();
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("asks for the route's team and the given week", async () => {
    const fetchMock = stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    await openPanel();
    const url = String((fetchMock.mock.calls[0] as unknown[])[0]);
    expect(url).toContain("/api/players/espn%3Ap-4431452/stats?");
    expect(url).toContain("week=7");
    expect(url).toContain("team_id=espn%3Al-1-t-1");
  });

  it("shows the live week: league points, status, stat line, and breakdown", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();

    expect(dialog.querySelector(".pstats-score")?.textContent).toBe("10.3");
    expect(within(dialog).getByText("of 20.6 proj", { exact: false })).toBeTruthy();
    expect(within(dialog).getByText("Q3 4:12")).toBeTruthy();
    expect(within(dialog).getByText("Week 7 · vs CHI")).toBeTruthy();

    const breakdown = within(dialog).getByTestId("points-breakdown");
    const rows = within(breakdown).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      "Rushing TD1+6",
      "Passing yards103+4.12",
      "Interceptions thrown1-2",
      "Rushing yards22+2.2",
      "Total10.3",
    ]);
    expect(within(breakdown).getByText(/league's own scoring/)).toBeTruthy();
  });

  it("labels an estimated breakdown as estimated", async () => {
    const data = stats();
    data.this_week = { ...data.this_week, stats_source: "sleeper", breakdown_source: "estimated" };
    stubFetch(data);
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();
    expect(within(dialog).getByText(/Estimated from the latest stat line/)).toBeTruthy();
    expect(within(dialog).getByText("Estimated total")).toBeTruthy();
  });

  it("switches the box scores between seasons and shows career rows", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();
    fireEvent.click(within(dialog).getByRole("tab", { name: "Stats" }));

    const log = within(dialog).getByRole("region", { name: "Box scores" });
    expect(within(log).getByText("NYJ")).toBeTruthy();
    expect(within(log).queryByText("LV")).toBeNull();
    expect(within(log).getByText("2 games")).toBeTruthy();

    fireEvent.click(within(log).getByRole("tab", { name: "2025" }));
    expect(within(log).getByText("LV")).toBeTruthy();
    expect(within(log).queryByText("NYJ")).toBeNull();
    expect(within(log).getByText("1 games")).toBeTruthy();

    const career = within(dialog).getByRole("region", { name: "Career" });
    expect(within(career).getAllByRole("row")).toHaveLength(3); // header + 2 seasons
    expect(within(career).getByText("20.9")).toBeTruthy();
  });

  it("says so when there's no history to show", async () => {
    stubFetch(
      stats({
        sleeper_id: null,
        seasons: [],
        game_log: [],
        this_week: {
          ...stats().this_week,
          stats: null,
          stats_source: null,
          breakdown: [],
          breakdown_source: null,
          breakdown_total: null,
          is_live: false,
          status_text: null,
        },
      }),
    );
    renderName(<PlayerName player={PLAYER} week={7} />);
    fireEvent.click(screen.getByRole("button", { name: "Drake Maye" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("No stats yet this week.");
    expect(dialog.querySelector(".pstats-score")?.textContent).toBe("—");
    fireEvent.click(within(dialog).getByRole("tab", { name: "Stats" }));
    expect(within(dialog).getByText("No stat history available for this player.")).toBeTruthy();
  });

  it("opens on Overview, with the season strip and the player's details above the tabs", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();

    const tabs = within(dialog)
      .getAllByRole("tab")
      .filter((t) => t.closest(".pgl-tabs"));
    expect(tabs.map((t) => t.textContent)).toEqual(["Overview", "Game Log", "Stats"]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");

    expect(within(dialog).getByText("QB #10 · New England Patriots · Bye 4")).toBeTruthy();
    const strip = dialog.querySelector(".pgl-headline")!;
    const items = Array.from(strip.querySelectorAll("div")).map((d) => [
      d.querySelector("dd")?.textContent,
      d.querySelector("dt")?.textContent,
    ]);
    // No start or roster percentages: neither platform publishes them to us.
    expect(items).toEqual([
      ["50.68", "Fan Pts"],
      ["QB 16", "Pos Rank"],
      ["20.90", "Pts / Game"],
    ]);
  });

  it("shows the season week by week in the Game Log tab", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();
    fireEvent.click(within(dialog).getByRole("tab", { name: "Game Log" }));

    const log = within(dialog).getByRole("region", { name: "Week-by-week game log" });
    const headers = within(log)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "Wk",
      "Opp (vs QBs)",
      "Proj Pts",
      "Fan Pts",
      "Pass Yds",
      "Pass TD",
      "Int",
    ]);

    const rows = within(log).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-state"))).toEqual([
      "final",
      "final",
      "final",
      "bye",
      "dnp",
      "live",
      "upcoming",
    ]);

    const [w1, w2, w3, bye, dnp, live, upcoming] = rows;
    const cells = (row: HTMLElement) => within(row).getAllByRole("cell");

    // Opponent, with its rank vs QBs and the easy/hard tint.
    expect(cells(w1)[0].textContent).toBe("@LAC (26th)");
    expect(cells(w1)[0].querySelector("[data-tier]")?.getAttribute("data-tier")).toBe("hard");
    expect(cells(w3)[0].querySelector("[data-tier]")?.getAttribute("data-tier")).toBe("neutral");
    expect(cells(dnp)[0].querySelector("[data-tier]")?.getAttribute("data-tier")).toBe("easy");
    expect(cells(w2)[0].textContent).toBe("SEA (31st)");

    // Each cell against his average over the three final weeks only (16.19 Fan Pts,
    // 217 yds, 1.33 TD, 0.67 Int) — the live, bye and DNP weeks stay out of it.
    const tones = (row: HTMLElement) =>
      cells(row).map((c) => c.querySelector("[data-tone]")?.getAttribute("data-tone") ?? null);
    expect(tones(w1)).toEqual([null, null, "typical", "above", "below", "above"]);
    // Two picks against an average of 0.67 is a bad week — the Int column's shading flips.
    expect(tones(w2)).toEqual([null, null, "below", "below", "below", "below"]);
    expect(tones(w3)).toEqual([null, null, "above", "above", "above", "above"]);

    expect(cells(w1)[1].textContent).toBe("13.65");
    expect(cells(w1)[2].textContent).toContain("16.48");

    expect(cells(bye)[0].textContent).toBe("BYE");
    expect(cells(dnp)[2].textContent).toBe("DNP");

    // The live week shows its running numbers, unshaded.
    expect(tones(live).every((t) => t === null)).toBe(true);
    expect(cells(live)[2].textContent).toBe("2.10");
    expect(within(live).getByRole("img", { name: "in progress" })).toBeTruthy();

    // A week ahead: opponent and projection, dashes for everything else.
    expect(cells(upcoming)[0].textContent).toBe("@DAL (6th)");
    expect(cells(upcoming)[1].textContent).toBe("18.75");
    expect(
      cells(upcoming)
        .slice(2)
        .map((c) => c.textContent),
    ).toEqual(["—", "—", "—", "—"]);

    const legend = within(dialog).getByTestId("game-log-legend");
    expect(legend.textContent).toContain("Compared to Player’s Average");
    expect(legend.textContent).toContain("Above");
    expect(legend.textContent).toContain("Typical");
    expect(legend.textContent).toContain("Below");
    expect(within(log).getByText(/through week 5/)).toBeTruthy();
  });

  it("says so when there is no season log", async () => {
    stubFetch(stats({ season_log: null, jersey_number: null }));
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();
    expect(dialog.querySelector(".pgl-headline")).toBeNull();
    // Falls back to the platform's bye week.
    expect(within(dialog).getByText("QB · New England Patriots · Bye 14")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("tab", { name: "Game Log" }));
    expect(within(dialog).getByText("No game log for this season yet.")).toBeTruthy();
  });

  it("reopens on the last tab chosen", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    let dialog = await openPanel();
    fireEvent.click(within(dialog).getByRole("tab", { name: "Game Log" }));
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Drake Maye" }));
    dialog = await screen.findByRole("dialog", { name: "Drake Maye stats" });
    await within(dialog).findByRole("region", { name: "Week-by-week game log" });
    expect(
      within(dialog).getByRole("tab", { name: "Game Log" }).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("opens the same card from the headshot", async () => {
    stubFetch(stats());
    renderName(
      <PlayerAvatarButton player={PLAYER} week={7}>
        <div className="headshot">DM</div>
      </PlayerAvatarButton>,
    );
    fireEvent.click(screen.getByTestId("player-avatar-button"));
    const dialog = await screen.findByRole("dialog", { name: "Drake Maye stats" });
    await within(dialog).findByTestId("points-breakdown");
  });

  it("closes on Escape and returns focus to the name", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    await openPanel();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement?.textContent).toBe("Drake Maye");
  });
});
