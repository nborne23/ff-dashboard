import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatchupSlot, Player, Slot } from "../../types/api";
import { BIG_PLAY_ANIMATION_MS, BIG_PLAY_POINTS, useBigPlays } from "./useBigPlay";

function player(name: string): Player {
  return {
    id: name,
    name,
    position: "RB",
    nfl_team: "KC",
    nfl_opponent: null,
    nfl_game_id: null,
    headshot_url: "",
    bye_week: null,
    injury_status: null,
  };
}

function slot(label: Slot, homePts: number, awayPts: number, matchupId = "m-w-1"): MatchupSlot {
  return {
    matchup_id: matchupId,
    slot: label,
    home_player: player(`${label} home`),
    away_player: player(`${label} away`),
    home_pts: homePts,
    away_pts: awayPts,
    home_state: "in",
    away_state: "in",
    home_is_live: true,
    away_is_live: true,
  };
}

function Probe({ slots, iAmHome = true }: { slots: MatchupSlot[]; iAmHome?: boolean }) {
  const { panelSide, bySlot } = useBigPlays(slots, iAmHome);
  return (
    <div data-testid="panel" data-big-play={panelSide}>
      {Object.entries(bySlot).map(([key, play]) => (
        <span key={key} data-testid={`play-${key}`} data-side={play.side} data-play-id={play.id}>
          {play.delta.toFixed(1)}|{play.player}
        </span>
      ))}
    </div>
  );
}

const panelSide = (c: HTMLElement) =>
  c.querySelector("[data-testid='panel']")?.getAttribute("data-big-play") ?? null;
const play = (c: HTMLElement, key: string) => c.querySelector(`[data-testid='play-${key}']`);

describe("useBigPlays", () => {
  afterEach(cleanup);

  it("does not fire on first render, however large the points already are", () => {
    // The whole reason the map is seeded rather than assumed empty: on a Sunday
    // afternoon reload every starter already has a full score, and treating that as a
    // jump from zero would light up every row at once.
    const { container } = render(<Probe slots={[slot("RB1", 24.6, 31.2)]} />);
    expect(panelSide(container)).toBeNull();
  });

  it("fires for my side when a starter gains a touchdown's worth of points", () => {
    const { container, rerender } = render(<Probe slots={[slot("RB1", 4, 9)]} />);
    act(() => rerender(<Probe slots={[slot("RB1", 4 + BIG_PLAY_POINTS, 9)]} />));

    expect(panelSide(container)).toBe("mine");
    expect(play(container, "RB1")?.getAttribute("data-side")).toBe("mine");
    expect(play(container, "RB1")?.textContent).toBe("6.0|RB1 home");
  });

  it("fires for the opponent's side, and names their player", () => {
    const { container, rerender } = render(<Probe slots={[slot("WR1", 3, 3)]} />);
    act(() => rerender(<Probe slots={[slot("WR1", 3, 17.4)]} />));

    expect(panelSide(container)).toBe("theirs");
    expect(play(container, "WR1")?.getAttribute("data-side")).toBe("theirs");
    expect(play(container, "WR1")?.textContent).toBe("14.4|WR1 away");
  });

  it("follows orientation — the away user's own player is still 'mine'", () => {
    const { container, rerender } = render(<Probe slots={[slot("QB", 0, 2)]} iAmHome={false} />);
    act(() => rerender(<Probe slots={[slot("QB", 0, 12)]} iAmHome={false} />));

    expect(panelSide(container)).toBe("mine");
    expect(play(container, "QB")?.textContent).toBe("10.0|QB away");
  });

  it("ignores ordinary scoring below the threshold", () => {
    const { container, rerender } = render(<Probe slots={[slot("TE", 2, 2)]} />);
    // A reception, a short catch, a field goal — each real, none worth the loudest cue
    // on the screen.
    act(() => rerender(<Probe slots={[slot("TE", 3, 5)]} />));
    expect(panelSide(container)).toBeNull();
    expect(play(container, "TE")).toBeNull();
  });

  it("never fires on a points DROP, however large", () => {
    // Stat corrections take points away. A negative delta must not pass the threshold
    // by magnitude.
    const { container, rerender } = render(<Probe slots={[slot("RB1", 22, 22)]} />);
    act(() => rerender(<Probe slots={[slot("RB1", 2, 2)]} />));
    expect(panelSide(container)).toBeNull();
  });

  it("reports 'both' when the two sides score big in the same refresh", () => {
    const { container, rerender } = render(
      <Probe slots={[slot("RB1", 0, 0), slot("WR1", 0, 0)]} />,
    );
    act(() => rerender(<Probe slots={[slot("RB1", 9, 0), slot("WR1", 0, 9)]} />));

    expect(panelSide(container)).toBe("both");
    expect(play(container, "RB1")?.getAttribute("data-side")).toBe("mine");
    expect(play(container, "WR1")?.getAttribute("data-side")).toBe("theirs");
  });

  it("gives one row a single cue — the larger jump wins", () => {
    const { container, rerender } = render(<Probe slots={[slot("FLEX", 0, 0)]} />);
    act(() => rerender(<Probe slots={[slot("FLEX", 7, 19)]} />));

    expect(panelSide(container)).toBe("theirs");
    expect(play(container, "FLEX")?.textContent).toBe("19.0|FLEX away");
  });

  it("stays silent for a slot label it has never seen", () => {
    // A lineup edit, or the conditional numbering that turns K into K1/K2 when a league
    // starts two kickers: the renamed slot arrives carrying a full score, which must
    // seed rather than read as that player scoring it all at once.
    const { container, rerender } = render(<Probe slots={[slot("K", 8, 8)]} />);
    act(() => rerender(<Probe slots={[slot("K1", 8, 8), slot("K2", 9, 9)]} />));
    expect(panelSide(container)).toBeNull();

    // ...and it is now tracking them, so the NEXT jump does fire.
    act(() => rerender(<Probe slots={[slot("K1", 8, 8), slot("K2", 19, 9)]} />));
    expect(panelSide(container)).toBe("mine");
  });

  it("stays silent when the whole matchup changes — stepping to another week", () => {
    // The panel is keyed by team id on the stage, so it does NOT remount when the week
    // changes, and a week served from cache has no loading state to reseed through.
    // Both platforms put the week in the matchup id, which is why the snapshot is keyed
    // by it: without that, week 1 -> week 2 -> week 1 would compare one week's points
    // against another's and flare every row on the board at once.
    const { container, rerender } = render(<Probe slots={[slot("RB1", 2, 2, "m-w-1")]} />);
    act(() => rerender(<Probe slots={[slot("RB1", 21, 24, "m-w-2")]} />));
    expect(panelSide(container)).toBeNull();

    act(() => rerender(<Probe slots={[slot("RB1", 2, 2, "m-w-1")]} />));
    expect(panelSide(container)).toBeNull();
  });

  it("clears itself after the animation duration", () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(<Probe slots={[slot("RB1", 0, 0)]} />);
      act(() => rerender(<Probe slots={[slot("RB1", 12, 0)]} />));
      expect(panelSide(container)).toBe("mine");

      act(() => vi.advanceTimersByTime(BIG_PLAY_ANIMATION_MS + 10));
      expect(panelSide(container)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("gives each firing a distinct id, so a repeat play replays the animation", () => {
    const { container, rerender } = render(<Probe slots={[slot("RB1", 0, 0)]} />);
    act(() => rerender(<Probe slots={[slot("RB1", 12, 0)]} />));
    const firstId = play(container, "RB1")?.getAttribute("data-play-id");
    act(() => rerender(<Probe slots={[slot("RB1", 24, 0)]} />));

    // Same row, same delta, same text — only the id distinguishes the two firings, and
    // it is what the chip's React key is built from.
    expect(play(container, "RB1")?.textContent).toBe("12.0|RB1 home");
    expect(play(container, "RB1")?.getAttribute("data-play-id")).not.toBe(firstId);
  });
});
