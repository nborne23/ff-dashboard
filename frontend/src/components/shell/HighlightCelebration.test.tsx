import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PlayerHighlight } from "../../api/highlights";
import { useHighlightStore } from "../../stores/highlights";
import { CELEBRATION_MS, HighlightCelebration } from "./HighlightCelebration";

function highlight(id: number, kind: PlayerHighlight["kind"] = "touchdown"): PlayerHighlight {
  return {
    id,
    kind,
    stat_key: kind === "touchdown" ? "rec_td" : "rec_40p",
    yards: 34,
    stat_line: "6 rec · 112 yds · 2 TD",
    player_id: "yahoo:p1",
    player_name: `Player ${id}`,
    position: "WR",
    nfl_team: "CIN",
    headshot_url: "",
    created_at: "2026-10-25T18:00:00",
  };
}

function renderCelebration() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <HighlightCelebration />
    </QueryClientProvider>,
  );
}

describe("HighlightCelebration", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useHighlightStore.setState({ queue: [], overflow: 0 });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () => JSON.stringify({ data: { highlights: [], latest_id: null }, meta: {} }),
      })),
    );
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders nothing with an empty queue", () => {
    renderCelebration();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("plays the queue one at a time", () => {
    renderCelebration();
    act(() => useHighlightStore.getState().enqueue([highlight(1), highlight(2, "big_play")]));

    expect(screen.getByText("Player 1")).toBeTruthy();
    expect(screen.getByText("Touchdown")).toBeTruthy();
    expect(screen.getByText("34-yd receiving TD · WR · CIN")).toBeTruthy();

    act(() => vi.advanceTimersByTime(CELEBRATION_MS));
    expect(screen.getByText("Player 2")).toBeTruthy();
    expect(screen.getByText("Big Play")).toBeTruthy();

    act(() => vi.advanceTimersByTime(CELEBRATION_MS));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("a tap skips to the next one", () => {
    renderCelebration();
    act(() => useHighlightStore.getState().enqueue([highlight(1), highlight(2)]));

    fireEvent.click(screen.getByRole("status"));

    expect(screen.getByText("Player 2")).toBeTruthy();
  });

  it("shows the overflow on the last card", () => {
    renderCelebration();
    act(() => useHighlightStore.getState().enqueue([1, 2, 3, 4].map((id) => highlight(id))));

    expect(screen.queryByText("and 1 more")).toBeNull();
    // One act per card: the next card's timer only exists once React has committed it.
    act(() => vi.advanceTimersByTime(CELEBRATION_MS));
    act(() => vi.advanceTimersByTime(CELEBRATION_MS));
    expect(screen.getByText("Player 3")).toBeTruthy();
    expect(screen.getByText("and 1 more")).toBeTruthy();
  });

  it("falls back to initials with no headshot", () => {
    renderCelebration();
    act(() => useHighlightStore.getState().enqueue([highlight(1)]));

    expect(screen.getByText("P1")).toBeTruthy();
  });
});
