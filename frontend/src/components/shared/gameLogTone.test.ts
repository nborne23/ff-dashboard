import { describe, expect, it } from "vitest";

import type { GameLogColumn, SeasonLogWeek } from "../../types/api";
import { averagesFor, matchupTier, ordinal, toneFor } from "./gameLogTone";

// Jacoby Brissett's 2026 weeks 1-7 from the Yahoo card this tab was modeled on, with the
// shading Yahoo gave each cell. The thresholds must reproduce every one of them.
const FAN_PTS: [number, string][] = [
  [16.48, "typical"],
  [6.5, "below"],
  [25.6, "above"],
  [10.44, "below"],
  [24.78, "above"],
  [6.92, "below"],
  [16.48, "typical"],
];
const PASS_YDS: [number, string][] = [
  [277, "typical"],
  [95, "below"],
  [280, "typical"],
  [166, "below"],
  [292, "above"],
  [218, "typical"],
  [272, "typical"],
];
const PASS_TD: [number, string][] = [
  [1, "below"],
  [1, "below"],
  [2, "above"],
  [2, "above"],
  [3, "above"],
  [0, "below"],
  [1, "below"],
];

const mean = (rows: [number, string][]) => rows.reduce((a, [v]) => a + v, 0) / rows.length;

describe("toneFor", () => {
  it.each([
    ["Fan Pts", FAN_PTS],
    ["Pass Yds", PASS_YDS],
    ["Pass TD", PASS_TD],
  ])("matches Yahoo's shading for %s", (_label, rows) => {
    const average = mean(rows);
    expect(rows.map(([value]) => toneFor(value, average))).toEqual(rows.map(([, tone]) => tone));
  });

  it("flips for stats where lower is better", () => {
    expect(toneFor(3, 1, true)).toBe("below");
    expect(toneFor(0, 1, true)).toBe("above");
    expect(toneFor(1, 1, true)).toBe("typical");
  });

  it("treats any production over a zero average as above, and zero as typical", () => {
    expect(toneFor(1, 0)).toBe("above");
    expect(toneFor(0, 0)).toBe("typical");
    // An interception from a QB who never throws them is a bad week.
    expect(toneFor(1, 0, true)).toBe("below");
  });

  it("handles a negative average (a D/ST that keeps getting shelled)", () => {
    expect(toneFor(-2, -2)).toBe("typical");
    expect(toneFor(4, -2)).toBe("above");
    expect(toneFor(-6, -2)).toBe("below");
  });
});

describe("matchupTier", () => {
  // Yahoo's opponent colors from the same card: rank vs QBs -> green / white / red.
  it.each([
    [26, "hard"],
    [31, "hard"],
    [22, "neutral"],
    [8, "easy"],
    [1, "easy"],
    [15, "neutral"],
    [23, "hard"],
    [6, "easy"],
    [30, "hard"],
    [3, "easy"],
    [9, "easy"],
    [10, "easy"],
    [11, "neutral"],
  ])("rank %i of 32 is %s", (rank, tier) => {
    expect(matchupTier(rank, 32)).toBe(tier);
  });
});

describe("ordinal", () => {
  it.each([
    [1, "1st"],
    [2, "2nd"],
    [3, "3rd"],
    [4, "4th"],
    [11, "11th"],
    [12, "12th"],
    [13, "13th"],
    [21, "21st"],
    [22, "22nd"],
    [23, "23rd"],
    [31, "31st"],
  ])("%i -> %s", (n, text) => {
    expect(ordinal(n)).toBe(text);
  });
});

describe("averagesFor", () => {
  const columns: GameLogColumn[] = [
    { key: "pass_yd", label: "Pass Yds", agg: "sum", lower_is_better: false },
    { key: "pass_td", label: "Pass TD", agg: "sum", lower_is_better: false },
  ];
  const week = (w: number, state: SeasonLogWeek["state"], pts: number | null, yd?: number) =>
    ({
      week: w,
      state,
      opponent: "LAC",
      home: true,
      opponent_rank: null,
      proj_points: null,
      fantasy_points: pts,
      stats: yd === undefined ? null : { pass_yd: yd, pass_td: 1 },
    }) satisfies SeasonLogWeek;

  it("averages final weeks only", () => {
    const averages = averagesFor(
      [
        week(1, "final", 20, 300),
        week(2, "final", 10, 100),
        week(3, "bye", null),
        week(4, "dnp", null),
        week(5, "live", 2, 20),
        week(6, "upcoming", null),
      ],
      columns,
    );
    expect(averages.fantasy_points).toBe(15);
    expect(averages.stats).toEqual({ pass_yd: 200, pass_td: 1 });
  });

  it("has no average before a game is final", () => {
    const averages = averagesFor([week(1, "live", 5, 50)], columns);
    expect(averages.fantasy_points).toBeNull();
    expect(averages.stats).toEqual({});
  });
});
