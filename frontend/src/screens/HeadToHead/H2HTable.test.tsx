import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MatchupSlot, Player } from "../../types/api";
import { H2HTable } from "./H2HTable";

function makePlayer(overrides: Partial<Player> = {}): Player {
  return {
    id: "p1",
    name: "P. Mahomes",
    position: "QB",
    nfl_team: "KC",
    nfl_opponent: "DEN",
    nfl_game_id: null,
    headshot_url: "/api/headshots/yahoo/1.png",
    bye_week: null,
    injury_status: null,
    ...overrides,
  };
}

function makeSlot(overrides: Partial<MatchupSlot> = {}): MatchupSlot {
  return {
    matchup_id: "m1",
    slot: "QB",
    home_player: makePlayer({ id: "home", name: "Home Guy" }),
    away_player: makePlayer({ id: "away", name: "Away Guy" }),
    home_pts: 20,
    away_pts: 10,
    // Per-side live state (add-game-day-view). The endpoint always sends these, so
    // they're required on the type rather than optional — a component reading
    // `undefined` here would be reading a case that cannot happen in production.
    home_state: "post",
    away_state: "post",
    home_is_live: false,
    away_is_live: false,
    ...overrides,
  };
}

describe("H2HTable diff-chip orientation", () => {
  afterEach(cleanup);

  it("when the route's team is the home team and leading, shows a positive (pink) chip", () => {
    render(
      <H2HTable
        slots={[makeSlot({ home_pts: 20, away_pts: 10 })]}
        iAmHome
        myTeamName="Highland Bombers"
        oppTeamName="Touchdown Club"
      />,
    );

    const chip = document.querySelector(".diff-chip");
    expect(chip?.className).toBe("diff-chip pos");
    expect(chip?.textContent).toBe("+10.0");
    // "me" column shows the home player when iAmHome is true.
    expect(screen.getByText("Home Guy")).toBeTruthy();
  });

  it("when the route's team is the away team and trailing, shows a negative (cyan) chip", () => {
    render(
      <H2HTable
        slots={[makeSlot({ home_pts: 20, away_pts: 10 })]}
        iAmHome={false}
        myTeamName="Touchdown Club"
        oppTeamName="Highland Bombers"
      />,
    );

    const chip = document.querySelector(".diff-chip");
    expect(chip?.className).toBe("diff-chip neg");
    expect(chip?.textContent).toBe("-10.0");
    // "me" column shows the away player when iAmHome is false — the case
    // the design prototype (which hardcodes me=home) never exercises.
    expect(screen.getByText("Away Guy")).toBeTruthy();
  });

  it("shows a tie chip when both sides score the same", () => {
    render(
      <H2HTable
        slots={[makeSlot({ home_pts: 15, away_pts: 15 })]}
        iAmHome
        myTeamName="Me"
        oppTeamName="Them"
      />,
    );

    const chip = document.querySelector(".diff-chip");
    expect(chip?.className).toBe("diff-chip tie");
    expect(chip?.textContent).toBe("TIE");
  });
});

describe("H2HTable injury badges", () => {
  afterEach(cleanup);

  it("badges both sides independently", () => {
    // The matchup path persists player-id FKs (`matchup_slots.home_player_id`) and the
    // read joins `players`, so these carry the same `injury_status` the roster does.
    render(
      <H2HTable
        slots={[
          makeSlot({
            home_player: makePlayer({ id: "home", name: "Home Guy", injury_status: "Q" }),
            away_player: makePlayer({ id: "away", name: "Away Guy", injury_status: null }),
          }),
        ]}
        iAmHome
        myTeamName="Mine"
        oppTeamName="Theirs"
      />,
    );

    const badges = screen.getAllByTestId("injury-badge");
    expect(badges).toHaveLength(1);
    expect(badges[0].textContent).toBe("Q");
  });
});
