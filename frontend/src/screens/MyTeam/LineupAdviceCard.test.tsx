import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { LineupAdvice, LineupMove, Player } from "../../types/api";
import { LineupAdviceCard } from "./LineupAdviceCard";

function player(id: string, name: string): Player {
  return {
    id,
    name,
    position: "RB",
    nfl_team: "KC",
    nfl_opponent: "DEN",
    nfl_game_id: null,
    headshot_url: "",
    bye_week: null,
    injury_status: null,
  };
}

function move(overrides: Partial<LineupMove> = {}): LineupMove {
  return {
    slot: "RB1",
    out_player: player("p1", "Bench Him"),
    in_player: player("p2", "Start Him"),
    out_points: 8.0,
    in_points: 14.0,
    delta: 6.0,
    reason: "higher_projection",
    consensus: false,
    ...overrides,
  };
}

function advice(overrides: Partial<LineupAdvice> = {}): LineupAdvice {
  return {
    team_id: "espn:l-1-t-1",
    week: 1,
    source: "rotowire",
    current_points: 120,
    optimal_points: 126,
    gain: 6,
    moves: [move()],
    sources_agree: false,
    comparison_available: true,
    advice_available: true,
    unevaluated: [],
    ...overrides,
  };
}

describe("LineupAdviceCard", () => {
  afterEach(cleanup);

  it("shows the gain and the swap", () => {
    render(<LineupAdviceCard advice={advice()} />);
    // Twice: once as the headline total, once on the single move that produces it.
    // With one move those numbers must match — the backend guarantees `gain` equals the
    // sum of the moves shown, and this is where that becomes visible.
    expect(screen.getAllByText("+6.0")).toHaveLength(2);
    expect(screen.getByText("Bench Him")).toBeTruthy();
    expect(screen.getByText("Start Him")).toBeTruthy();
  });

  it("says the lineup is optimal rather than showing an empty list", () => {
    render(<LineupAdviceCard advice={advice({ moves: [], gain: 0 })} />);
    expect(screen.getByTestId("lineup-optimal").textContent).toBe("Your lineup is optimal.");
  });

  it("distinguishes 'cannot evaluate' from 'already optimal'", () => {
    // The failure this guards: rendering "your lineup is optimal" when we simply have
    // no data is a confident lie the user would act on.
    render(<LineupAdviceCard advice={advice({ advice_available: false, moves: [] })} />);
    expect(screen.queryByTestId("lineup-optimal")).toBeNull();
    expect(screen.getByText(/No projections to work from yet/)).toBeTruthy();
  });

  it("marks a move both sources agree on", () => {
    render(<LineupAdviceCard advice={advice({ moves: [move({ consensus: true })] })} />);
    expect(screen.getByText("✓ both sources")).toBeTruthy();
  });

  it("flags an unstartable starter differently from a mere upgrade", () => {
    render(
      <LineupAdviceCard advice={advice({ moves: [move({ reason: "unstartable", delta: 0 })] })} />,
    );
    expect(screen.getByText("OUT")).toBeTruthy();
    expect(
      screen.getByTestId("lineup-advice").querySelector('[data-reason="unstartable"]'),
    ).toBeTruthy();
  });

  it("names the players it could not evaluate", () => {
    render(
      <LineupAdviceCard
        advice={advice({ moves: [], gain: 0, unevaluated: [player("p9", "New Signing")] })}
      />,
    );
    expect(screen.getByText(/New Signing/)).toBeTruthy();
  });

  it("notes when both sources agree the lineup is already right", () => {
    render(<LineupAdviceCard advice={advice({ moves: [], gain: 0, sources_agree: true })} />);
    expect(screen.getByText("Both projection sources agree.")).toBeTruthy();
  });
});
