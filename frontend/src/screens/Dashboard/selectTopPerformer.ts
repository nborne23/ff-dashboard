// TODO(Phase 4 backend follow-up): see InsightTopPerformer.tsx's header
// comment — this is a client-side stand-in until a real per-player
// top-performer endpoint exists.

import type { Team } from "../../types/api";

export interface TopPerformerFallback {
  /** Stand-in for the player name — the leading team's name, since we have
   * no per-player scoring yet. */
  headline: string;
  subline: string;
  initials: string;
  points: number;
}

export function selectTopPerformerFallback(teams: Team[]): TopPerformerFallback | null {
  if (teams.length === 0) return null;
  const top = teams.reduce(
    (best, t) => (t.current_score > best.current_score ? t : best),
    teams[0],
  );
  const initials = top.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  return {
    headline: top.name,
    subline: "Top scorer this week",
    initials: initials || "?",
    points: top.current_score,
  };
}

export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}
