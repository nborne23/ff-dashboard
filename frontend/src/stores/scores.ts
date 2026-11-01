// The Scores screen's league picker. Persisted, so the Fantasy tab comes back in the
// league the user last scored it in — the way Sleeper remembers it.

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ScoresState {
  /** null until the user picks one; the backend then defaults to the first league. */
  leagueId: string | null;
  setLeagueId: (leagueId: string) => void;
}

export const useScoresStore = create<ScoresState>()(
  persist(
    (set) => ({
      leagueId: null,
      setLeagueId: (leagueId) => set({ leagueId }),
    }),
    { name: "gridiron.scores" },
  ),
);
