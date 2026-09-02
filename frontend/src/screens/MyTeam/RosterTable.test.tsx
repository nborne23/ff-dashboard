import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Player, RosterSlot } from "../../types/api";
import { RosterTable } from "./RosterTable";

function makePlayer(overrides: Partial<Player> = {}): Player {
  return {
    id: "p1",
    name: "Patrick Mahomes",
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

function makeSlot(overrides: Partial<RosterSlot> = {}): RosterSlot {
  return {
    team_id: "yahoo:1.t.1",
    week: 14,
    slot: "QB",
    player: makePlayer(),
    proj_points: 22.4,
    actual_points: 19.8,
    is_live: false,
    game_state: "post",
    status_text: "FINAL",
    ...overrides,
  };
}

describe("RosterTable", () => {
  afterEach(cleanup);

  it("renders Starters and Bench section rows", () => {
    render(
      <RosterTable
        starters={[makeSlot()]}
        bench={[makeSlot({ slot: "BN", player: makePlayer({ id: "p2", name: "Russell Wilson" }) })]}
      />,
    );

    expect(screen.getByText("Starters")).toBeTruthy();
    expect(screen.getByText("Bench")).toBeTruthy();
    expect(screen.getByText("Patrick Mahomes")).toBeTruthy();
    expect(screen.getByText("Russell Wilson")).toBeTruthy();
  });

  it("marks a live starter row with tr.live-row and an orange status dot", () => {
    const { container } = render(
      <RosterTable
        starters={[
          makeSlot({
            is_live: true,
            game_state: "in",
            status_text: "LIVE Q3 7:42",
          }),
        ]}
        bench={[]}
      />,
    );

    const row = container.querySelector("tr.live-row");
    expect(row).toBeTruthy();
    expect(screen.getByText("LIVE Q3 7:42")).toBeTruthy();
  });

  it("marks a bench row with tr.bench-row", () => {
    const { container } = render(
      <RosterTable
        starters={[]}
        bench={[makeSlot({ slot: "BN", player: makePlayer({ id: "p3", name: "Tank Dell" }) })]}
      />,
    );

    expect(container.querySelector("tr.bench-row")).toBeTruthy();
  });

  it("shows a red OUT badge for an injured (O) player instead of the muted status text", () => {
    render(
      <RosterTable
        starters={[]}
        bench={[
          makeSlot({
            slot: "IR",
            player: makePlayer({ id: "p4", name: "Aaron Jones", injury_status: "O" }),
            status_text: "OUT",
            proj_points: 0,
            actual_points: 0,
            game_state: null,
          }),
        ]}
      />,
    );

    const out = screen.getByText("OUT");
    expect(out.style.color).toBe("var(--espn)");
  });

  it("colors a positive delta cyan (pos) and a negative delta pink (neg)", () => {
    render(
      <RosterTable
        starters={[
          makeSlot({
            player: makePlayer({ id: "p5", name: "Bijan Robinson" }),
            proj_points: 18.6,
            actual_points: 24.1,
          }),
          makeSlot({
            slot: "WR1",
            player: makePlayer({ id: "p6", name: "Justin Jefferson" }),
            proj_points: 19.4,
            actual_points: 5.0,
          }),
        ]}
        bench={[]}
      />,
    );

    const posDelta = screen.getByText("+5.5");
    expect(posDelta.className).toBe("delta pos");
    const negDelta = screen.getByText("-14.4");
    expect(negDelta.className).toBe("delta neg");
  });

  it("shows a muted dash for players who haven't scored yet", () => {
    render(
      <RosterTable
        starters={[
          makeSlot({
            player: makePlayer({ id: "p7", name: "Sam LaPorta" }),
            proj_points: 10.8,
            actual_points: 0,
            status_text: "Mon 8:15",
            game_state: "pre",
          }),
        ]}
        bench={[]}
      />,
    );

    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("RosterTable injury badges", () => {
  afterEach(cleanup);

  it("badges a questionable starter WITHOUT losing its kickoff time", () => {
    // The regression this guards: the Status column is an `is_live ? … : isOut ? … :
    // status_text` chain. Extending that chain to Q/D/IR would have replaced the
    // kickoff time on exactly the rows a start/sit decision turns on.
    render(
      <RosterTable
        starters={[
          makeSlot({
            player: makePlayer({ id: "p9", name: "Tyrone Tracy Jr.", injury_status: "Q" }),
            status_text: "Sun 1:00",
            actual_points: 0,
          }),
        ]}
        bench={[]}
      />,
    );

    expect(screen.getByTestId("injury-badge").textContent).toBe("Q");
    expect(screen.getByText("Sun 1:00")).toBeTruthy();
  });

  it("renders no badge for a healthy or unknown player", () => {
    render(
      <RosterTable
        starters={[
          makeSlot({ player: makePlayer({ id: "a", injury_status: "ACTIVE" }) }),
          makeSlot({ player: makePlayer({ id: "b", injury_status: null }) }),
        ]}
        bench={[]}
      />,
    );
    expect(screen.queryByTestId("injury-badge")).toBeNull();
  });
});
