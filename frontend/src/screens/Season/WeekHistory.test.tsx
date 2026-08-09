import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { SeasonWeek } from "../../types/api";
import { WeekHistory } from "./WeekHistory";

function makeWeek(overrides: Partial<SeasonWeek> = {}): SeasonWeek {
  return {
    team_id: "yahoo:nfl.l.1.t.4",
    week: 1,
    score: 102.4,
    opp_score: 88.1,
    opp_team_name: "Beard Mode",
    is_win: true,
    is_current: false,
    ...overrides,
  };
}

describe("WeekHistory", () => {
  afterEach(cleanup);

  it("renders weeks in reverse chronological order with 'vs {opp}' and the score pair", () => {
    const { container } = render(
      <WeekHistory
        weeks={[
          makeWeek({ week: 1, opp_team_name: "Beard Mode" }),
          makeWeek({
            week: 2,
            opp_team_name: "Gronk Stars",
            is_win: false,
            score: 78.0,
            opp_score: 95.4,
          }),
        ]}
      />,
    );

    const labels = screen.getAllByText(/^W\d+$/).map((el) => el.textContent);
    expect(labels).toEqual(["W2", "W1"]);
    expect(screen.getByText("Gronk Stars")).toBeTruthy();
    // Score pair is split across text nodes inside .num — assert on the
    // normalized textContent of the first (most recent) row's score cell.
    const scoreCells = Array.from(container.querySelectorAll(".num")).map((el) =>
      el.textContent?.replace(/\s+/g, " ").trim(),
    );
    expect(scoreCells[0]).toBe("78.0 – 95.4");
    expect(scoreCells[1]).toBe("102.4 – 88.1");
  });

  it("tints the current-week row and only that row", () => {
    render(
      <WeekHistory
        weeks={[
          makeWeek({ week: 13 }),
          makeWeek({ week: 14, is_current: true, opp_team_name: "Touchdown Club" }),
        ]}
      />,
    );

    const current = screen.getByTestId("week-history-current-row");
    expect(current.style.background).toBe("rgba(255, 45, 85, 0.06)");
    expect(screen.getAllByTestId("week-history-current-row")).toHaveLength(1);
  });

  it("colors the dot cyan for a win and pink for a loss", () => {
    const { container } = render(
      <WeekHistory
        weeks={[
          makeWeek({ week: 1, is_win: true }),
          makeWeek({ week: 2, is_win: false, opp_team_name: "Gronk Stars" }),
        ]}
      />,
    );

    const dots = Array.from(container.querySelectorAll(".row-list > div > div:nth-child(2)")).map(
      (el) => (el as HTMLElement).style.background,
    );
    // Reverse chronological: week 2 (loss, pink) first, then week 1 (win, cyan).
    expect(dots).toEqual(["var(--move)", "var(--stand)"]);
  });

  it("shows an empty state when there are no weeks", () => {
    render(<WeekHistory weeks={[]} />);

    expect(screen.getByText("No weeks yet")).toBeTruthy();
  });
});
