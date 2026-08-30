import { describe, expect, it } from "vitest";

import type { GameDayMatchup } from "../../types/api";
import { absMargin, applySort, liveCount, reconcileOrder, reorder } from "./arrangement";
import { GAME_DAY_FIXTURE } from "./fixtures";

const byId: Record<string, GameDayMatchup> = Object.fromEntries(
  GAME_DAY_FIXTURE.matchups.map((m) => [m.team_id, m]),
);
const allIds = GAME_DAY_FIXTURE.matchups.map((m) => m.team_id);

describe("reconcileOrder", () => {
  it("keeps a persisted order that still matches the envelope", () => {
    const persisted = ["b", "a", "c"];
    expect(reconcileOrder(persisted, ["a", "b", "c"])).toEqual(["b", "a", "c"]);
  });

  it("drops ids that are no longer in the envelope", () => {
    expect(reconcileOrder(["a", "gone", "b"], ["a", "b"])).toEqual(["a", "b"]);
  });

  it("appends ids the persisted order predates", () => {
    // The half a plain `.filter()` misses: a newly connected league must not be
    // invisible because the stored order was written before it existed.
    expect(reconcileOrder(["a", "b"], ["a", "b", "new"])).toEqual(["a", "b", "new"]);
  });

  it("drops and appends in the same pass", () => {
    expect(reconcileOrder(["a", "gone", "b"], ["b", "a", "new"])).toEqual(["a", "b", "new"]);
  });

  it("falls back to the envelope order when nothing persisted survives", () => {
    expect(reconcileOrder(["old1", "old2"], ["x", "y"])).toEqual(["x", "y"]);
  });

  it("returns the envelope order from an empty persisted order", () => {
    expect(reconcileOrder([], allIds)).toEqual(allIds);
  });

  it("returns empty when the envelope is empty", () => {
    expect(reconcileOrder(["a", "b"], [])).toEqual([]);
  });

  it("does not duplicate an id that appears in both", () => {
    expect(reconcileOrder(["a", "a", "b"], ["a", "b"])).toEqual(["a", "b"]);
  });
});

describe("applySort", () => {
  it("leaves a manual order exactly as given", () => {
    const shuffled = [...allIds].reverse();
    expect(applySort(shuffled, byId, "manual")).toEqual(shuffled);
  });

  it("orders by smallest absolute margin first", () => {
    const sorted = applySort(allIds, byId, "margin");
    const margins = sorted.map((id) => absMargin(byId[id]));
    for (let i = 1; i < margins.length; i += 1) {
      expect(margins[i]).toBeGreaterThanOrEqual(margins[i - 1]);
    }
    // The fixture's tied matchup has a zero margin, so it must lead.
    expect(sorted[0]).toBe("espn:t4");
  });

  it("orders by descending live-player count", () => {
    const sorted = applySort(allIds, byId, "live");
    const counts = sorted.map((id) => liveCount(byId[id]));
    for (let i = 1; i < counts.length; i += 1) {
      expect(counts[i]).toBeLessThanOrEqual(counts[i - 1]);
    }
    // Fixture 1 has three live slots on both sides — the most of any panel.
    expect(sorted[0]).toBe("yahoo:t1");
  });

  it("is stable across ties, so a no-op tick does not reshuffle the stage", () => {
    // All four of these have zero live players, so "live" ranks them equally.
    const tied = ["espn:t3", "espn:t4", "espn:t6"];
    expect(applySort(tied, byId, "live")).toEqual(tied);
  });

  it("does not mutate the input array", () => {
    const input = [...allIds];
    applySort(input, byId, "margin");
    expect(input).toEqual(allIds);
  });

  it("tolerates an id with no matching matchup", () => {
    expect(applySort(["ghost", ...allIds], byId, "margin")).toHaveLength(allIds.length + 1);
  });
});

describe("reorder", () => {
  it("moves the dragged id to the target's index", () => {
    expect(reorder(["a", "b", "c", "d"], "d", "b")).toEqual(["a", "d", "b", "c"]);
  });

  it("moves forward as well as backward", () => {
    expect(reorder(["a", "b", "c", "d"], "a", "c")).toEqual(["b", "c", "a", "d"]);
  });

  it("is a no-op when a panel is dropped on itself", () => {
    expect(reorder(["a", "b", "c"], "b", "b")).toEqual(["a", "b", "c"]);
  });

  it("is a no-op when either id is unknown", () => {
    expect(reorder(["a", "b"], "ghost", "a")).toEqual(["a", "b"]);
    expect(reorder(["a", "b"], "a", "ghost")).toEqual(["a", "b"]);
  });

  it("does not mutate the input array", () => {
    const input = ["a", "b", "c"];
    reorder(input, "c", "a");
    expect(input).toEqual(["a", "b", "c"]);
  });
});

describe("liveCount", () => {
  it("counts both sides of every live slot", () => {
    // Fixture 1: three slots live on both sides.
    expect(liveCount(byId["yahoo:t1"])).toBe(6);
  });

  it("is zero when nothing has kicked off", () => {
    expect(liveCount(byId["espn:t6"])).toBe(0);
  });
});
