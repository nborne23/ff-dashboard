import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GameDetail, ScoresWeek } from "../../api/scores";
import { useScoresStore } from "../../stores/scores";
import type { Envelope, Meta } from "../../types/api";
import { DETAIL_FIXTURE, FINAL_GAME, LIVE_GAME, MAYE, WEEK_FIXTURE } from "./fixtures";
import GameDetailScreen from "./GameDetail";

const meta: Meta = {
  live_state: "off_day",
  as_of: "2026-10-23T04:00:00Z",
  next_refresh_at: "2026-10-23T04:30:00Z",
  current_week: 8,
  platforms: { yahoo: { ok: true }, espn: { ok: true } },
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response;
}

function renderDetail(detail: Partial<GameDetail> = {}, status = 200) {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
    const url = new URL(String(input), "http://test");
    if (url.pathname.startsWith("/api/scores/games/")) {
      if (status >= 400) return jsonResponse(status, { detail: "no cached game" });
      const leagueId = url.searchParams.get("league_id") ?? DETAIL_FIXTURE.league_id;
      const data = { ...DETAIL_FIXTURE, league_id: leagueId, ...detail };
      return jsonResponse(200, { data, meta } satisfies Envelope<GameDetail>);
    }
    if (url.pathname === "/api/scores") {
      return jsonResponse(200, { data: WEEK_FIXTURE, meta } satisfies Envelope<ScoresWeek>);
    }
    return jsonResponse(404, {});
  });
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/scores/game/${FINAL_GAME.game_id}?week=7`]}>
        <Routes>
          <Route path="/scores/game/:gameId" element={<GameDetailScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

beforeEach(() => {
  useScoresStore.setState({ leagueId: null });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("GameDetail", () => {
  it("asks for the game in the URL's week", async () => {
    const fetchMock = renderDetail();
    await screen.findByTestId("game-detail");

    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `/api/scores/games/${FINAL_GAME.game_id}?week=7`,
    );
  });

  it("strips the week's games across the top with this one selected", async () => {
    renderDetail();
    const strip = await screen.findByLabelText("This week's games");

    const current = within(strip).getByRole("link", { current: "page" });
    expect(current.getAttribute("href")).toBe(`/scores/game/${FINAL_GAME.game_id}?week=7`);
    const live = within(strip)
      .getAllByRole("link")
      .find((a) => a.getAttribute("href")?.includes(LIVE_GAME.game_id));
    expect(live?.textContent).toContain("Q3 4:12");
    expect(within(strip).getByRole("link", { name: "All scores" }).getAttribute("href")).toBe(
      "/scores",
    );
  });

  it("draws the linescore with every quarter and the total", async () => {
    renderDetail();
    const table = await screen.findByTestId("linescore");

    const rows = within(table).getAllByRole("row");
    expect(rows[0].textContent).toBe("TeamQ1Q2Q3Q4TOT");
    expect(rows[1].textContent).toContain("NE0147324");
    expect(rows[2].textContent).toContain("CHI10107330");
  });

  it("opens on the Fantasy tab with players mirrored by position", async () => {
    renderDetail();
    const tab = await screen.findByTestId("fantasy-tab");

    expect(screen.getByRole("tab", { name: "Fantasy" }).getAttribute("aria-selected")).toBe("true");
    const qb = within(tab).getByRole("region", { name: "QB" });
    const maye = within(qb).getByTestId("fp-11564");
    const williams = within(qb).getByTestId("fp-12345");
    expect(maye.className).toContain("sc-fp-away");
    expect(williams.className).toContain("sc-fp-home");
    expect(qb.textContent).toContain("28.44");
    expect(qb.textContent).toContain("21.70");
    expect(qb.textContent).toContain("22.12");
    expect(maye.textContent).toContain("24/31 CMP");
  });

  it("marks the user's own players and names the owner of the rest", async () => {
    renderDetail();
    const maye = await screen.findByTestId("fp-11564");
    const stevenson = screen.getByTestId("fp-7611");

    expect(maye.className).toContain("mine");
    expect(maye.textContent).toContain("Your team");
    expect(stevenson.textContent).toContain("Da Bears");
  });

  it("makes a player we know a button for his stats card; a stranger is plain text", async () => {
    renderDetail();
    await screen.findByTestId("fantasy-tab");

    expect(screen.getByRole("button", { name: "Drake Maye" }).textContent).toBe("D. Maye");
    expect(screen.queryByRole("button", { name: "Caleb Williams" })).toBeNull();
    expect(screen.getByText("C. Williams")).toBeTruthy();
  });

  it("switching league remembers the choice and rescores", async () => {
    const fetchMock = renderDetail();
    const picker = (await screen.findByTestId("league-picker")) as HTMLSelectElement;
    expect(picker.value).toBe("espn:1");

    fireEvent.change(picker, { target: { value: "yahoo:2" } });

    expect(useScoresStore.getState().leagueId).toBe("yahoo:2");
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes("league_id=yahoo%3A2")),
      ).toBe(true),
    );
  });

  it("says when a custom league is estimated in PPR", async () => {
    renderDetail({ points_format_fallback: true });

    expect((await screen.findByTestId("fantasy-tab")).textContent).toContain("custom scoring");
  });

  it("a team tab shows that team's box score", async () => {
    renderDetail();
    await screen.findByTestId("fantasy-tab");

    fireEvent.click(screen.getByRole("tab", { name: /Patriots/ }));

    const box = screen.getByTestId("box-away");
    const tables = within(box).getAllByRole("table");
    expect(tables.map((t) => within(t).getAllByRole("columnheader")[0].textContent)).toEqual([
      "Passing",
      "Rushing",
      "Receiving",
    ]);
    expect(within(tables[0]).getByRole("row", { name: /D. Maye/ }).textContent).toBe(
      "D. Maye24/3132121",
    );
  });

  it("a team with no stat lines says so", async () => {
    renderDetail({ groups: [{ position: "QB", away: [MAYE], home: [] }] });
    await screen.findByTestId("fantasy-tab");

    fireEvent.click(screen.getByRole("tab", { name: /Bears/ }));

    expect(screen.getByTestId("box-empty").textContent).toBe("No stats yet for Bears.");
  });

  it("says when a pre-game has no projections yet", async () => {
    renderDetail({ groups: [], game: { ...FINAL_GAME, state: "pre" } });

    expect((await screen.findByTestId("fantasy-empty")).textContent).toContain("Projections");
  });

  it("shows the error card when the game isn't cached", async () => {
    renderDetail({}, 404);

    expect(await screen.findByTestId("game-error")).toBeTruthy();
  });
});
