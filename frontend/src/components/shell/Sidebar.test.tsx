// The sidebar's scoreboard column: each team carries its current margin, colored by
// valence, and a live marker while any of its players are playing.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";

function team(id: string, name: string, score: number, opp: number, isLive = false) {
  return { id, name, current_score: score, current_opp_score: opp, is_live: isLive };
}

function renderWith(teams: ReturnType<typeof team>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          data: { teams },
          meta: {
            live_state: "live",
            as_of: new Date().toISOString(),
            next_refresh_at: new Date().toISOString(),
            current_week: 1,
            platforms: {},
          },
        }),
    })) as unknown as typeof fetch,
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Sidebar scoreboard", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows each team's margin with its valence", async () => {
    const { container } = renderWith([
      team("espn:a", "Winning Team", 30, 20),
      team("espn:b", "Losing Team", 10, 25.5),
    ]);

    await waitFor(() => expect(screen.getByText("+10.0")).toBeTruthy());
    expect(screen.getByText("+10.0").getAttribute("data-sign")).toBe("pos");
    expect(screen.getByText("−15.5").getAttribute("data-sign")).toBe("neg");
    expect(container.querySelectorAll(".team-item-margin")).toHaveLength(2);
  });

  it("shows no margin before kickoff, when both sides are at zero", async () => {
    const { container } = renderWith([team("espn:a", "Not Started", 0, 0)]);
    await waitFor(() => expect(screen.getByText("Not Started")).toBeTruthy());
    expect(container.querySelector(".team-item-margin")).toBeNull();
  });

  it("marks a team live while its players are playing", async () => {
    renderWith([team("espn:a", "Live Team", 5, 3, true), team("espn:b", "Idle Team", 5, 3)]);
    await waitFor(() => expect(screen.getByText("Live Team")).toBeTruthy());
    expect(screen.getAllByLabelText("Live")).toHaveLength(1);
  });
});
