import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScoresWeek } from "../../api/scores";
import { useUiStore } from "../../stores/ui";
import type { Envelope, Meta } from "../../types/api";
import { FINAL_GAME, LIVE_GAME, PRE_GAME, WEEK_FIXTURE } from "./fixtures";
import Scores from "./index";

const meta: Meta = {
  live_state: "game_day",
  as_of: "2026-10-25T18:00:00Z",
  next_refresh_at: "2026-10-25T18:00:30Z",
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

function renderScores(week: Partial<ScoresWeek> = {}, status = 200) {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
    if (status >= 400) return jsonResponse(status, { detail: "boom" });
    const url = new URL(String(input), "http://test");
    const asked = Number(url.searchParams.get("week")) || WEEK_FIXTURE.week;
    const data = { ...WEEK_FIXTURE, week: asked, ...week };
    return jsonResponse(200, { data, meta } satisfies Envelope<ScoresWeek>);
  });
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/scores"]}>
        <Routes>
          <Route path="/scores" element={<Scores />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

beforeEach(() => {
  useUiStore.setState({ week: 7, weekPinned: false });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Scores", () => {
  it("asks for the server's current week until the user picks one", async () => {
    const fetchMock = renderScores();
    await screen.findByTestId("scores");

    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/scores");
  });

  it("uses the shared week once the user has picked one", async () => {
    useUiStore.setState({ week: 5, weekPinned: true });
    const fetchMock = renderScores();
    await screen.findByTestId("scores");

    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/scores?week=5");
  });

  it("marks the current week and the selected one in the strip", async () => {
    renderScores();
    const strip = await screen.findByRole("tablist", { name: "NFL week" });

    const selected = within(strip).getByRole("tab", { selected: true });
    expect(selected?.textContent).toContain("week 7");
    expect(within(strip).getByText("Current").closest("button")?.textContent).toContain("week 8");
  });

  it("picking a week moves the shared week and refetches", async () => {
    const fetchMock = renderScores();
    const strip = await screen.findByRole("tablist", { name: "NFL week" });

    fireEvent.click(within(strip).getByText("week 9"));

    expect(useUiStore.getState().week).toBe(9);
    expect(useUiStore.getState().weekPinned).toBe(true);
    await screen.findByText("NFL · 2026 · Week 9");
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/scores?week=9")).toBe(true);
  });

  it("groups games by local day", async () => {
    renderScores();
    await screen.findByTestId("scores");

    const days = screen.getAllByRole("region");
    expect(days).toHaveLength(2);
    expect(within(days[0]).getByTestId(`score-game-${FINAL_GAME.game_id}`)).toBeTruthy();
    expect(within(days[1]).getByTestId(`score-game-${LIVE_GAME.game_id}`)).toBeTruthy();
    expect(within(days[1]).getByTestId(`score-game-${PRE_GAME.game_id}`)).toBeTruthy();
  });

  it("draws a final with scores, the winner marker and the top performer", async () => {
    renderScores();
    const row = await screen.findByTestId(`score-game-${FINAL_GAME.game_id}`);

    expect(row.getAttribute("href")).toBe(`/scores/game/${FINAL_GAME.game_id}?week=7`);
    expect(row?.textContent).toContain("Patriots");
    expect(row?.textContent).toContain("Bears");
    expect(within(row).getByLabelText("Winner")?.textContent).toContain("◀");
    expect(row?.textContent).toContain("Final");
    expect(row?.textContent).toContain("D. Maye");
    expect(row?.textContent).toContain("24/31, 321 YDS, 2 TD");
  });

  it("draws a live game's clock and down, and a pre-game's network without scores", async () => {
    renderScores();
    const live = await screen.findByTestId(`score-game-${LIVE_GAME.game_id}`);
    const pre = screen.getByTestId(`score-game-${PRE_GAME.game_id}`);

    expect(live?.textContent).toContain("Q3 4:12");
    expect(live?.textContent).toContain("3rd & 4");
    expect(within(live).getByLabelText("Has the ball")).toBeTruthy();
    expect(pre?.textContent).toContain("FOX");
    expect(within(pre).queryByLabelText("Winner")).toBeNull();
  });

  it("lists the week's byes", async () => {
    renderScores();
    expect(await screen.findByText("On bye: BUF, BAL")).toBeTruthy();
  });

  it("explains a week that hasn't been fetched", async () => {
    renderScores({ games: [], fetched_at: null });

    expect((await screen.findByTestId("scores-empty")).textContent).toContain(
      "hasn't been fetched yet",
    );
  });

  it("shows the error card on failure", async () => {
    renderScores({}, 500);

    expect(await screen.findByTestId("scores-error")).toBeTruthy();
  });
});
