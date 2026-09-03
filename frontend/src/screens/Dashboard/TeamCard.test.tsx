import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type { Team } from "../../types/api";
import { ordinal } from "./ordinal";
import { TeamCard } from "./TeamCard";

function makeTeam(overrides: Partial<Team> = {}): Team {
  return {
    id: "yahoo:nfl.l.1.t.4",
    league_id: "yahoo:nfl.l.1",
    name: "Highland Bombers",
    manager_name: "Nick",
    record: { w: 8, l: 3, t: 0 },
    rank: { current: 2, total: 12 },
    points_for: 1000,
    points_against: 900,
    is_user_team: true,
    current_score: 87.4,
    current_opp_score: 71.2,
    current_opponent_name: "The Touchdown Club",
    is_live: true,
    spark_last_6: [78, 92, 64, 88, 94, 87],
    accent_color: "#FF2D55",
  logo_url: null,
    ...overrides,
  };
}

function renderCard(team: Team) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<TeamCard team={team} />} />
        <Route path="/team/:teamId" element={<div data-testid="team-screen" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TeamCard", () => {
  afterEach(cleanup);

  it("colors the winner white and the loser secondary", () => {
    renderCard(makeTeam({ current_score: 87.4, current_opp_score: 71.2 }));

    expect(screen.getByText("87.4").style.color).toBe("var(--text)");
    expect(screen.getByText("71.2").style.color).toBe("var(--text-secondary)");
  });

  it("flips the colors when the team is losing", () => {
    renderCard(makeTeam({ current_score: 64.9, current_opp_score: 78.4 }));

    expect(screen.getByText("64.9").style.color).toBe("var(--text-secondary)");
    expect(screen.getByText("78.4").style.color).toBe("var(--text)");
  });

  it("renders opponent, record, rank, team logo, and live dot", () => {
    const { container } = renderCard(makeTeam());

    expect(screen.getByText("vs The Touchdown Club")).toBeTruthy();
    expect(screen.getByText("8–3")).toBeTruthy();
    expect(screen.getByText("2nd / 12")).toBeTruthy();
    // The logo replaced the platform pill in this row: at ~127px the two could not
    // coexist with the team name, and the logo identifies the team rather than
    // repeating a platform the sidebar already conveys.
    expect(container.querySelector(".team-logo")).toBeTruthy();
    expect(screen.queryByText("YAHOO")).toBeNull();
    expect(container.querySelector(".live-dot")).toBeTruthy();
  });

  it("keeps the logo out of the name row", () => {
    // The name row is ~95px on desktop and the team names need 83-149px, so anything
    // sharing that row comes straight out of the name. The logo lives in the right
    // column with the sparkline instead. A leading avatar column would NOT fix this —
    // it takes from the same fixed content box (95px -> 75px).
    const { container } = renderCard(makeTeam());

    expect(container.querySelector(".top-row .team-logo")).toBeNull();
    expect(container.querySelector(".spark .team-logo")).toBeTruthy();
  });

  it("rings the logo in neutral white, the same on every platform", () => {
    // The ring used to encode the platform (red ESPN / purple Yahoo). It no longer
    // does: both platforms are pinned here so a reintroduced per-platform colour
    // fails loudly rather than quietly returning a cue the design dropped.
    const { container: yahoo } = renderCard(makeTeam({ id: "yahoo:nfl.l.1.t.4" }));
    expect((yahoo.querySelector(".team-logo") as HTMLElement).style.boxShadow).toContain(
      "var(--text)",
    );

    cleanup();

    const { container: espn } = renderCard(makeTeam({ id: "espn:l-9-t-2" }));
    expect((espn.querySelector(".team-logo") as HTMLElement).style.boxShadow).toContain(
      "var(--text)",
    );
  });

  it("navigates to /team/:id on click", () => {
    renderCard(makeTeam({ id: "espn:l-9-t-2" }));

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByTestId("team-screen")).toBeTruthy();
  });
});

describe("ordinal", () => {
  it("handles st/nd/rd/th including the 11-13 exceptions", () => {
    expect(ordinal(1)).toBe("1st");
    expect(ordinal(2)).toBe("2nd");
    expect(ordinal(3)).toBe("3rd");
    expect(ordinal(4)).toBe("4th");
    expect(ordinal(11)).toBe("11th");
    expect(ordinal(12)).toBe("12th");
    expect(ordinal(13)).toBe("13th");
    expect(ordinal(21)).toBe("21st");
    expect(ordinal(22)).toBe("22nd");
    expect(ordinal(23)).toBe("23rd");
  });
});
