// Formatting for the Scores screens. Kickoffs arrive as UTC instants and are shown in the
// viewer's own time zone — a Thursday night game is "Thursday" where the phone is.

import type { ScoreGame } from "../../api/scores";

/** Local calendar day, as a sortable key. */
export function dayKey(iso: string): string {
  const d = new Date(iso);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

/** "Thursday, Oct 22". */
export function dayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

/** "1:00 PM". */
export function kickoffTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** "Sun 1:00 PM" — for the game strip, where there's no day header above. */
export function kickoffShort(iso: string): string {
  const weekday = new Date(iso).toLocaleDateString(undefined, { weekday: "short" });
  return `${weekday} ${kickoffTime(iso)}`;
}

export interface GameDay {
  key: string;
  label: string;
  games: ScoreGame[];
}

/** Games grouped by local day, in kickoff order (the API already sorts them). */
export function groupByDay(games: ScoreGame[]): GameDay[] {
  const days: GameDay[] = [];
  for (const game of games) {
    const key = dayKey(game.kickoff_at);
    const last = days[days.length - 1];
    if (last && last.key === key) {
      last.games.push(game);
    } else {
      days.push({ key, label: dayLabel(game.kickoff_at), games: [game] });
    }
  }
  return days;
}

/** The status line: kickoff time before the game, the server's own text after. */
export function statusLabel(game: ScoreGame, { short = false } = {}): string {
  if (game.state === "pre")
    return short ? kickoffShort(game.kickoff_at) : kickoffTime(game.kickoff_at);
  return game.status_text;
}

export function formatPoints(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

/** Which side won, for the winner marker; null while it isn't decided. */
export function winnerSide(game: ScoreGame): "away" | "home" | null {
  if (game.state !== "post") return null;
  if (game.away.winner) return "away";
  if (game.home.winner) return "home";
  return null;
}
