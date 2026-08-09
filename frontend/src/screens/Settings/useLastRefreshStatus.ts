// "Last refresh: Xs ago · ok" status line for DataManagementCard (task 11.2). Ticks
// every second like hooks/useFreshness.ts, but reports the most recent scheduler run
// (GET /api/admin/refresh-runs) rather than the data's own `as_of` — this is about
// scheduler health ("did the last run succeed"), not data staleness.

import { useEffect, useState } from "react";

import { useRefreshRuns } from "../../api/admin";

const TICK_MS = 1000;
const MAX_ERROR_LENGTH = 60;

export interface LastRefreshStatus {
  label: string;
  isError: boolean;
}

function formatElapsed(deltaMs: number): string {
  const seconds = Math.max(0, Math.floor(deltaMs / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function shorten(error: string): string {
  return error.length > MAX_ERROR_LENGTH ? `${error.slice(0, MAX_ERROR_LENGTH - 3)}...` : error;
}

/** `null` while there's no run to report yet (never refreshed, or the query hasn't
 * resolved) — callers should render nothing in that case rather than a misleading
 * "0s ago". */
export function useLastRefreshStatus(): LastRefreshStatus | null {
  const runsQuery = useRefreshRuns(1);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(interval);
  }, []);

  const run = runsQuery.data?.[0];
  if (!run) return null;

  const elapsed = formatElapsed(now - new Date(run.run_at).getTime());
  if (run.ok) {
    return { label: `Last refresh: ${elapsed} · ok`, isError: false };
  }
  const errorLabel = run.error ? shorten(run.error) : "unknown error";
  return { label: `Last refresh: ${elapsed} · failed: ${errorLabel}`, isError: true };
}
