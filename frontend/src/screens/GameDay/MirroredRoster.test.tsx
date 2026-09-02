import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MatchupSlot, Player } from "../../types/api";
import { MirroredRoster } from "./MirroredRoster";

function makePlayer(name: string, nflTeam: string): Player {
  return {
    id: name,
    name,
    position: "QB",
    nfl_team: nflTeam,
    nfl_opponent: null,
    nfl_game_id: null,
    headshot_url: "",
    bye_week: null,
    injury_status: null,
  };
}

function makeSlot(overrides: Partial<MatchupSlot> = {}): MatchupSlot {
  return {
    matchup_id: "m1",
    slot: "QB",
    home_player: makePlayer("Home Guy", "KC"),
    away_player: makePlayer("Away Guy", "BUF"),
    home_pts: 20,
    away_pts: 10,
    home_state: "post",
    away_state: "post",
    home_is_live: false,
    away_is_live: false,
    ...overrides,
  };
}

function sides(): { mine: HTMLElement; theirs: HTMLElement } {
  const row = screen.getByTestId("gd-roster").querySelector(".gd-row") as HTMLElement;
  return {
    mine: row.querySelector("[data-side='mine']") as HTMLElement,
    theirs: row.querySelector("[data-side='theirs']") as HTMLElement,
  };
}

describe("MirroredRoster orientation", () => {
  afterEach(cleanup);

  it("puts the home player on the user's side when the user is home", () => {
    render(<MirroredRoster slots={[makeSlot()]} iAmHome />);
    const { mine, theirs } = sides();

    expect(within(mine).getByText("Home Guy")).toBeTruthy();
    expect(within(mine).getByText("20.0")).toBeTruthy();
    expect(within(theirs).getByText("Away Guy")).toBeTruthy();
    expect(within(theirs).getByText("10.0")).toBeTruthy();
  });

  it("puts the AWAY player on the user's side when the user is away", () => {
    render(<MirroredRoster slots={[makeSlot()]} iAmHome={false} />);
    const { mine, theirs } = sides();

    // The user's players stay on the left of every row regardless of which side of the
    // matchup they occupy — the whole point of routing through orientSlot().
    expect(within(mine).getByText("Away Guy")).toBeTruthy();
    expect(within(mine).getByText("10.0")).toBeTruthy();
    expect(within(theirs).getByText("Home Guy")).toBeTruthy();
  });

  it("orients the per-slot differential from the user's perspective", () => {
    const { unmount } = render(<MirroredRoster slots={[makeSlot()]} iAmHome />);
    expect(screen.getByText("+10.0")).toBeTruthy();
    unmount();

    render(<MirroredRoster slots={[makeSlot()]} iAmHome={false} />);
    expect(screen.getByText("-10.0")).toBeTruthy();
  });

  it("shows a neutral em-dash when the two players are within the tie threshold", () => {
    render(<MirroredRoster slots={[makeSlot({ home_pts: 12, away_pts: 12.02 })]} iAmHome />);
    const diff = document.querySelector(".gd-slot-diff") as HTMLElement;

    expect(diff.textContent).toBe("—");
    expect(diff.getAttribute("data-sign")).toBe("tied");
  });

  it("marks a `pre` side dimmed rather than rendering it as a real zero", () => {
    render(
      <MirroredRoster
        slots={[makeSlot({ home_pts: 0, home_state: "pre", away_pts: 0, away_state: "post" })]}
        iAmHome
      />,
    );
    const { mine, theirs } = sides();

    // Both read 0.0; only the one that hasn't kicked off is marked as unplayed.
    expect(mine.getAttribute("data-state")).toBe("pre");
    expect(theirs.getAttribute("data-state")).toBe("post");
  });

  it("carries a null state as `unknown`, not as a fabricated post", () => {
    render(<MirroredRoster slots={[makeSlot({ home_state: null })]} iAmHome />);
    expect(sides().mine.getAttribute("data-state")).toBe("unknown");
  });

  it("renders a live dot only on the side that is live", () => {
    render(<MirroredRoster slots={[makeSlot({ home_is_live: true })]} iAmHome />);
    const { mine, theirs } = sides();

    expect(mine.querySelector(".gd-live-dot")).toBeTruthy();
    expect(theirs.querySelector(".gd-live-dot")).toBeNull();
  });

  it("renders one row per slot, in the order given", () => {
    render(
      <MirroredRoster
        slots={[makeSlot({ slot: "QB" }), makeSlot({ slot: "RB1" }), makeSlot({ slot: "K" })]}
        iAmHome
      />,
    );
    const labels = Array.from(document.querySelectorAll(".gd-slot-label")).map(
      (el) => el.textContent,
    );
    expect(labels).toEqual(["QB", "RB1", "K"]);
  });
});

describe("MirroredRoster injury badges", () => {
  afterEach(cleanup);

  it("badges the injured side and leaves the healthy one alone", () => {
    render(
      <MirroredRoster
        slots={[
          makeSlot({
            home_player: { ...makePlayer("Home Guy", "KC"), injury_status: "IR" },
            away_player: makePlayer("Away Guy", "BUF"),
          }),
        ]}
        iAmHome
      />,
    );

    const { mine, theirs } = sides();
    expect(within(mine).getByTestId("injury-badge").textContent).toBe("IR");
    expect(within(theirs).queryByTestId("injury-badge")).toBeNull();
  });

  it("renders the badge as a static span — Game Day opens no dialogs", () => {
    render(
      <MirroredRoster
        slots={[makeSlot({ home_player: { ...makePlayer("Home Guy", "KC"), injury_status: "O" } })]}
        iAmHome
      />,
    );
    expect(screen.getByTestId("injury-badge").tagName).toBe("SPAN");
  });
});
