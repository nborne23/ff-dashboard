// `useFreshness` (task 8.8) — turns an envelope's `meta.as_of` into a ticking
// "Last updated Xs/Xm ago" caption, going stale after 90s (the point at which even the
// slowest tier — off-day, 30 min — plus SSE lag would still look "fresh" if we didn't
// cap it, so 90s is a deliberately tight, always-meaningful staleness signal rather than
// one keyed to the current cadence).

import { useEffect, useState } from "react";

const STALE_THRESHOLD_MS = 90_000;
const TICK_MS = 1000;

export interface FreshnessResult {
  label: string;
  stale: boolean;
}

function formatLabel(deltaMs: number): string {
  const seconds = Math.max(0, Math.floor(deltaMs / 1000));
  if (seconds < 60) return `Last updated ${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  return `Last updated ${minutes}m ago`;
}

export function useFreshness(asOf: string | null | undefined): FreshnessResult {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(interval);
  }, []);

  if (!asOf) {
    return { label: "Last updated —", stale: false };
  }

  const asOfMs = new Date(asOf).getTime();
  if (Number.isNaN(asOfMs)) {
    return { label: "Last updated —", stale: false };
  }

  const delta = now - asOfMs;
  return {
    label: formatLabel(delta),
    stale: delta >= STALE_THRESHOLD_MS,
  };
}
