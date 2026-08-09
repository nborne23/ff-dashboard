// Two-way sync between the zustand `week` store (stores/ui.ts) and the `?week=` URL
// search param (task 9.2), so a hard refresh preserves the selected week. Mounted once
// in the shell (App.tsx) — screens keep reading `useUiStore` directly, unaware this
// exists.
//
// "Two-way" here means: the URL is the source of truth on initial load, and afterwards
// the store drives the URL (the Topbar's back/forward buttons call `setWeek`, which the
// second effect below mirrors out). The two effects run in a specific order every
// commit (React always fires them in the order they're declared), which the
// `skipNextWrite` ref leans on: without it, the *first* commit after a URL like
// `?week=14` loads would call `setWeek(14)` (queuing a re-render) and then, still in
// that same commit, the write-effect would fire using the *current* render's stale
// `week` (1) and clobber the URL back to `?week=1` for a tick. The flag lets the read
// effect tell the write effect "skip yourself once, I've got this."

import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

import { useUiStore } from "../stores/ui";

const WEEK_PARAM = "week";

export function useWeekParam(): void {
  const [searchParams, setSearchParams] = useSearchParams();
  const week = useUiStore((s) => s.week);
  const setWeek = useUiStore((s) => s.setWeek);
  const skipNextWrite = useRef(false);

  // URL -> store, once on mount: restores the week a hard refresh would otherwise reset.
  useEffect(() => {
    const fromUrl = searchParams.get(WEEK_PARAM);
    if (fromUrl === null) return;
    const parsed = Number(fromUrl);
    if (Number.isInteger(parsed) && parsed > 0 && parsed !== week) {
      skipNextWrite.current = true;
      setWeek(parsed);
    }
    // Mount-only: intentionally ignoring `searchParams`/`week` so this never re-runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // store -> URL: keeps ?week= in sync whenever the store changes (e.g. the Topbar's
  // back/forward buttons), skipping the write the mount effect above already accounted for.
  useEffect(() => {
    if (skipNextWrite.current) {
      skipNextWrite.current = false;
      return;
    }
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set(WEEK_PARAM, String(week));
        return next;
      },
      { replace: true },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [week]);
}
