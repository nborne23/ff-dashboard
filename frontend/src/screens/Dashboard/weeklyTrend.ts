// Pure helpers for InsightWeeklyTrend.tsx — split into their own module so
// the component file only exports a component (react-refresh lint rule).

import type { Team } from "../../types/api";

export const WEEKS_SHOWN = 6;

/** Per-week average of every team's `spark_last_6` (each entry already
 * represents "last 6 weeks ending at the current week", per Team's D12
 * shape). */
export function computeWeeklyAverages(teams: Team[]): number[] {
  const averages: number[] = [];
  for (let i = 0; i < WEEKS_SHOWN; i++) {
    const values = teams
      .map((t) => t.spark_last_6[i])
      .filter((v): v is number => typeof v === "number");
    averages.push(values.length === 0 ? 0 : values.reduce((sum, v) => sum + v, 0) / values.length);
  }
  return averages;
}

export function computeWeekLabels(currentWeek: number, count: number): string[] {
  return Array.from({ length: count }, (_, i) => {
    const wk = currentWeek - (count - 1) + i;
    return `W${wk}`;
  });
}
