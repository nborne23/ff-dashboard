// The Game Log tab's shading rules, kept pure so the thresholds are pinned by tests.
//
// A week is shaded against the player's OWN season average, the way Yahoo's game log
// does it ("Compared to Player's Average"): within a quarter of his average either way is
// typical, beyond that it's above or below. The 25% band reproduces every cell of Yahoo's
// own card that the feature was modeled on.

import type { GameLogColumn, SeasonLogWeek } from "../../types/api";

export type Tone = "above" | "typical" | "below";

const BAND = 0.25;

export function toneFor(value: number, average: number, lowerIsBetter = false): Tone {
  if (value === average) return "typical";
  const band = Math.abs(average) * BAND;
  let tone: Tone = "typical";
  if (value >= average + band) tone = "above";
  else if (value <= average - band) tone = "below";
  if (lowerIsBetter && tone !== "typical") return tone === "above" ? "below" : "above";
  return tone;
}

export interface Averages {
  fantasy_points: number | null;
  stats: Record<string, number>;
}

/** Averages over FINAL weeks only — a live week, a bye, or a DNP would drag them down. */
export function averagesFor(weeks: SeasonLogWeek[], columns: GameLogColumn[]): Averages {
  const played = weeks.filter((w) => w.state === "final");
  const points = played
    .map((w) => w.fantasy_points)
    .filter((v): v is number => v !== null && v !== undefined);
  const stats: Record<string, number> = {};
  for (const column of columns) {
    const values = played
      .map((w) => w.stats?.[column.key])
      .filter((v): v is number => v !== undefined && v !== null);
    if (values.length > 0) stats[column.key] = values.reduce((a, b) => a + b, 0) / values.length;
  }
  return {
    fantasy_points: points.length > 0 ? points.reduce((a, b) => a + b, 0) / points.length : null,
    stats,
  };
}

export type MatchupTier = "easy" | "hard" | "neutral";

/** Opponent rank -> tier, by thirds: of 32 teams, 1st-10th easy, 23rd-32nd hard. */
export function matchupTier(rank: number, rankedTeams: number): MatchupTier {
  const third = Math.round((rankedTeams * 10) / 32);
  if (rank <= third) return "easy";
  if (rank > rankedTeams - third) return "hard";
  return "neutral";
}

export function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}
