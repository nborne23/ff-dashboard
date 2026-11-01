// The Scores screen's own state.
//
// `leagueId` is persisted, so the Fantasy tab comes back in the league the user last
// scored it in — the way Sleeper remembers it.
//
// `pickedWeek` is not: every load opens on the NFL's current week, which the server
// knows and the shared week (`stores/ui.ts`) may not — on a database with no leagues,
// that one defaults to week 1. Once the user picks a week here (or opens a game, or uses
// the Topbar's arrows on this screen), the screen stays on it for the session.

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ScoresState {
  /** null until the user picks one; the backend then defaults to the first league. */
  leagueId: string | null;
  setLeagueId: (leagueId: string) => void;
  /** null until the user picks a week; the backend then serves the current one. */
  pickedWeek: number | null;
  setPickedWeek: (week: number | null) => void;
}

export const useScoresStore = create<ScoresState>()(
  persist(
    (set) => ({
      leagueId: null,
      setLeagueId: (leagueId) => set({ leagueId }),
      pickedWeek: null,
      setPickedWeek: (pickedWeek) => set({ pickedWeek }),
    }),
    { name: "gridiron.scores", partialize: (state) => ({ leagueId: state.leagueId }) },
  ),
);
