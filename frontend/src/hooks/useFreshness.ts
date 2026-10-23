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

// Each unit takes over once the one below it stops being readable at a glance:
// "46292m ago" is technically correct and tells a person nothing.
function formatLabel(deltaMs: number): string {
  const seconds = Math.max(0, Math.floor(deltaMs / 1000));
  if (seconds < 10) return "Updated just now";
  if (seconds < 60) return `Updated ${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Updated ${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Updated ${hours}h ago`;
  return `Updated ${Math.floor(hours / 24)}d ago`;
}

export function useFreshness(asOf: string | null | undefined): FreshnessResult {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(interval);
  }, []);

  if (!asOf) {
    return { label: "Not updated yet", stale: false };
  }

  const asOfMs = new Date(asOf).getTime();
  if (Number.isNaN(asOfMs)) {
    return { label: "Not updated yet", stale: false };
  }

  const delta = now - asOfMs;
  return {
    label: formatLabel(delta),
    stale: delta >= STALE_THRESHOLD_MS,
  };
}
