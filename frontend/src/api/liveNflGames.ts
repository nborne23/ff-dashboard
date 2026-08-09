// TODO(Phase 8): GET /api/nfl/scoreboard does not exist yet — it lands with
// the SSE/live-updates work (specs/live-updates/spec.md, "Scoreboard
// refresh"). Until then this hook is a typed stub so InsightLiveGames can be
// built against the real LiveNflGame shape now and wired to the real
// endpoint later without changing its call site.

import type { LiveNflGame } from "../types/api";

export interface UseLiveNflGamesResult {
  games: LiveNflGame[];
  isLoading: boolean;
}

export function useLiveNflGames(): UseLiveNflGamesResult {
  return { games: [], isLoading: false };
}
