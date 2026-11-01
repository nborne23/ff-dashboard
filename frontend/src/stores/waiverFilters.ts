import { create } from "zustand";

import { DEFAULT_WAIVER_FILTERS, type WaiverFilters } from "../screens/Waivers/filters";

/**
 * The Waivers screen's filters, remembered per team for the session: switch to another
 * team's waivers and back, and the list is still filtered the way it was left.
 *
 * Its own store rather than a slice of `stores/ui.ts`, and deliberately NOT wrapped in
 * `persist`: a "Waivers Only" left on from Tuesday's claims would otherwise greet the
 * user on Saturday as an unexplained short list. A reload starts from the defaults.
 */
interface WaiverFiltersState {
  byTeam: Record<string, WaiverFilters>;
  setFilters: (teamId: string, filters: WaiverFilters) => void;
}

export const useWaiverFiltersStore = create<WaiverFiltersState>()((set) => ({
  byTeam: {},
  setFilters: (teamId, filters) =>
    set((state) => ({ byTeam: { ...state.byTeam, [teamId]: filters } })),
}));

/** This team's filters and a setter that merges a partial change into them. */
export function useWaiverFilters(
  teamId: string,
): [WaiverFilters, (change: Partial<WaiverFilters>) => void] {
  const filters = useWaiverFiltersStore((s) => s.byTeam[teamId]) ?? DEFAULT_WAIVER_FILTERS;
  const setFilters = useWaiverFiltersStore((s) => s.setFilters);
  return [filters, (change) => setFilters(teamId, { ...filters, ...change })];
}
