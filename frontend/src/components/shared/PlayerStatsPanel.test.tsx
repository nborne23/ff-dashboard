import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Envelope, Player, PlayerStatsData } from "../../types/api";
import { PlayerAvatarButton, PlayerName } from "./PlayerName";

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

  it("switches the game log between seasons and shows career rows", async () => {
    stubFetch(stats());
    renderName(<PlayerName player={PLAYER} week={7} />);
    const dialog = await openPanel();

    const log = within(dialog).getByRole("region", { name: "Game log" });
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
    await within(dialog).findByText("No stat history available for this player.");
    expect(within(dialog).getByText("No stats yet this week.")).toBeTruthy();
    expect(dialog.querySelector(".pstats-score")?.textContent).toBe("—");
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
