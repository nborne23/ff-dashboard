// `useChangedValuePulse` (task 8.7) — flashes a value for one animation cycle whenever
// it changes (e.g. a score number ticking up after a `data.changed` SSE-driven refetch).
// Spread the returned props onto the element carrying the value; global.css's
// `[data-just-changed]` rule (the `value-flash` keyframe) does the actual animating.

import { useEffect, useRef, useState } from "react";

// Mirrors global.css's `value-flash` animation-duration — the fallback timer in case
// `animationend` never fires (prefers-reduced-motion, or the element unmounts mid-cycle).
export const PULSE_ANIMATION_MS = 900;

export interface ChangedValuePulseProps {
  "data-just-changed": "true" | undefined;
  onAnimationEnd: () => void;
}

export function useChangedValuePulse<T>(value: T): ChangedValuePulseProps {
  const previous = useRef(value);
  const [justChanged, setJustChanged] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (previous.current === value) return;
    previous.current = value;
    setJustChanged(true);

    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setJustChanged(false), PULSE_ANIMATION_MS);
  }, [value]);

  // Unmount-only cleanup — separate from the value-driven effect above so it doesn't
  // fire (and potentially race the next triggering effect's own clear) on every change.
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return {
    "data-just-changed": justChanged ? "true" : undefined,
    onAnimationEnd: () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      setJustChanged(false);
    },
  };
}
