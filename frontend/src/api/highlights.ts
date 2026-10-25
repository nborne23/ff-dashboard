// `useHighlightFeed()` — pulls the user's starters' touchdowns and big plays from
// GET /api/highlights and hands new ones to `stores/highlights.ts` for the celebration.
//
// Same "SSE is the signal, REST is the data" split as everything else: the detector
// (backend/gridiron/services/highlights.py) publishes `data.changed` with the
// `highlights` scope, `api/events.ts` invalidates `["highlights"]`, and this query
// refetches. Coming back to the app (visibilitychange) invalidates every query, so a
// touchdown scored while the phone was asleep still lands when it wakes — the server
// keeps only the last 30 minutes in reach, so it's never a replay of the whole day.
//
// The cursor lives in localStorage so a reload doesn't replay what was already seen. A
// device with no cursor yet adopts the newest id and plays nothing.

import { useQuery } from "@tanstack/react-query";

import { useHighlightStore } from "../stores/highlights";
import type { Envelope } from "../types/api";
import { apiClient } from "./client";

export type HighlightKind = "touchdown" | "big_play";

export interface PlayerHighlight {
  id: number;
  kind: HighlightKind;
  stat_key: string;
  yards: number | null;
  stat_line: string;
  player_id: string;
  player_name: string;
  position: string;
  nfl_team: string;
  headshot_url: string;
  created_at: string;
}

export interface HighlightsData {
  highlights: PlayerHighlight[];
  latest_id: number | null;
}

const CURSOR_KEY = "gridiron.highlights.cursor";

function readCursor(): number | null {
  try {
    const raw = localStorage.getItem(CURSOR_KEY);
    const value = raw === null ? NaN : Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function writeCursor(id: number): void {
  try {
    localStorage.setItem(CURSOR_KEY, String(id));
  } catch {
    // Private mode / blocked storage: the next load just seeds again.
  }
}

/** Fetch since the cursor, queue what's new, and advance the cursor. Exported for tests. */
export async function pullHighlights(): Promise<number | null> {
  const cursor = readCursor();
  const query = cursor === null ? "" : `?after=${cursor}`;
  const { data } = await apiClient.get<Envelope<HighlightsData>>(`/api/highlights${query}`);
  if (cursor !== null) useHighlightStore.getState().enqueue(data.highlights);
  // Straight to `latest_id`, not the last one returned: past the server's page size the
  // rest is a backlog, and a backlog isn't a celebration. An empty table seeds 0, so the
  // very first highlight ever recorded plays instead of becoming the seed.
  const next = data.latest_id ?? 0;
  if (next !== cursor) writeCursor(next);
  return data.latest_id;
}

export function useHighlightFeed(): void {
  useQuery({
    queryKey: ["highlights"],
    queryFn: pullHighlights,
    // Never stale on its own: the SSE signal and the foreground refetch are the only
    // reasons to ask again.
    staleTime: Infinity,
  });
}

/** One line under the headline: "34-yd rushing TD", "57-yd catch". */
export function describePlay(highlight: Pick<PlayerHighlight, "stat_key" | "yards">): string {
  const noun = PLAY_NOUNS[highlight.stat_key] ?? "play";
  if (highlight.yards !== null) return `${highlight.yards}-yd ${noun}`;
  return highlight.stat_key.endsWith("_40p") ? `40+ yd ${noun}` : capitalize(noun);
}

const PLAY_NOUNS: Record<string, string> = {
  pass_td: "passing TD",
  rush_td: "rushing TD",
  rec_td: "receiving TD",
  pass_cmp_40p: "completion",
  rush_40p: "run",
  rec_40p: "catch",
};

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
