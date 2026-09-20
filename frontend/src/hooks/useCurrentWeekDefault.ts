// Lands the app on the live NFL week instead of week 1.
//
// `stores/ui.ts` has to initialize `week` to *some* number — every screen reads it
// synchronously — and the real answer only exists on the server. So 1 is a placeholder,
// and this hook replaces it with `meta.current_week` (the week a request omitting
// `?week=` resolves to) as soon as the first envelope lands.
//
// It defers to anything that already chose a week: the URL's `?week=`, or the Topbar's
// arrows. Both go through `setWeek`, which pins, and a pinned week is never overwritten
// — so this fires at most once per load, and a deep link to week 2 stays on week 2.
//
// Mounted once in the shell (App.tsx), beside `useWeekParam`. It reuses the `teams`
// query the Topbar already issues, so it costs no request of its own.

import { useEffect } from "react";

import { useTeams } from "../api/teams";
import { useUiStore } from "../stores/ui";

export function useCurrentWeekDefault(): void {
  const week = useUiStore((s) => s.week);
  const weekPinned = useUiStore((s) => s.weekPinned);
  const setWeek = useUiStore((s) => s.setWeek);

  // Same query key the Topbar mounts, so this shares its cache entry rather than
  // firing a second request. The one wasted fetch on a cold load is the placeholder
  // week's — unavoidable without blocking the whole shell on a request, which is the
  // wrong trade for a display that is supposed to come back up on its own.
  const teamsQuery = useTeams(week);
  // Read off `data`, never `data?.meta?.current_week ?? 1`: a failed fetch must leave
  // the week unpinned so the retry can still seed it, and a fabricated 1 would pin it
  // for the rest of the session.
  const currentWeek = teamsQuery.data?.meta?.current_week;

  useEffect(() => {
    if (weekPinned || currentWeek === undefined) return;
    setWeek(currentWeek);
  }, [weekPinned, currentWeek, setWeek]);
}
