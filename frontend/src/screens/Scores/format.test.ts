import { describe, expect, it } from "vitest";

import { queryKeyForScope } from "../../api/events";
import { scoresWeekKey } from "../../api/scores";
import { FINAL_GAME, LIVE_GAME, PRE_GAME } from "./fixtures";
import { formatPoints, groupByDay, statusLabel, winnerSide } from "./format";

describe("groupByDay", () => {
  it("keeps kickoff order and starts a new group on each local day", () => {
    const days = groupByDay([FINAL_GAME, LIVE_GAME, PRE_GAME]);

    expect(days.map((d) => d.games.map((g) => g.game_id))).toEqual([["401"], ["402", "403"]]);
    expect(days[0].label).toBe(
      new Date(FINAL_GAME.kickoff_at).toLocaleDateString(undefined, {
        weekday: "long",
        month: "short",
        day: "numeric",
      }),
    );
  });

  it("is empty for no games", () => {
    expect(groupByDay([])).toEqual([]);
  });
});

describe("statusLabel", () => {
  it("is the server's text once the game has started", () => {
    expect(statusLabel(FINAL_GAME)).toBe("Final");
    expect(statusLabel(LIVE_GAME)).toBe("Q3 4:12");
  });

  it("is the local kickoff time before it, with the weekday when short", () => {
    const time = new Date(PRE_GAME.kickoff_at).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    expect(statusLabel(PRE_GAME)).toBe(time);
    expect(statusLabel(PRE_GAME, { short: true })).toContain(time);
    expect(statusLabel(PRE_GAME, { short: true }).length).toBeGreaterThan(time.length);
  });
});

describe("formatPoints", () => {
  it("shows two decimals, and a dash for nothing", () => {
    expect(formatPoints(28.4)).toBe("28.40");
    expect(formatPoints(0)).toBe("0.00");
    expect(formatPoints(null)).toBe("—");
  });
});

describe("winnerSide", () => {
  it("only names a winner once the game is final", () => {
    expect(winnerSide(FINAL_GAME)).toBe("home");
    expect(winnerSide(LIVE_GAME)).toBeNull();
    expect(winnerSide({ ...FINAL_GAME, home: { ...FINAL_GAME.home, winner: false } })).toBeNull();
  });
});

describe("live invalidation", () => {
  it("rides the live_nfl_games scope the scoreboard tick already publishes", () => {
    const scopeKey = queryKeyForScope("live_nfl_games");

    expect(scopeKey).toEqual(["live_nfl_games"]);
    expect(scoresWeekKey(8).slice(0, scopeKey!.length)).toEqual(scopeKey);
  });
});
