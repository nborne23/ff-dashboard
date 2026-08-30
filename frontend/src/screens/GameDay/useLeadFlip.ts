// `useLeadFlip` (design D4) — the panel-level counterpart to `useChangedValuePulse`.
//
// Where that hook fires on *any* change to a value, this one fires only when a
// matchup's margin crosses zero: the moment the user went from winning to losing or
// back. That is a different event class from "the score moved", and it earns the
// louder cue (a double-pulse of the whole panel rather than a row flash).
//
// The structure — a `useRef` seeded with the first value, a boolean state, and a
// timeout that races `animationend` — is deliberately copied from
// `hooks/useChangedValuePulse.ts` so the two cues have identical lifecycle behavior.

import { useEffect, useRef, useState } from "react";

/** Mirrors styles/gameday.css's `lead-flip` animation-duration. */
export const LEAD_FLIP_ANIMATION_MS = 1400;

/**
 * Margins below this magnitude are "tied" — the same threshold the margin chip uses,
 * so a panel showing TIED is never also claiming a lead in either direction.
 */
export const TIE_EPSILON = 0.05;

export interface LeadFlipProps {
  "data-lead-flip": "true" | undefined;
  onAnimationEnd: () => void;
}

/** -1, 0, or 1 — with the tie band collapsing to 0 rather than to a tiny signed value. */
function leadSign(margin: number): -1 | 0 | 1 {
  if (Math.abs(margin) < TIE_EPSILON) return 0;
  return margin > 0 ? 1 : -1;
}

/**
 * Fires when `margin` crosses zero. Spread the result onto the panel element;
 * `[data-lead-flip]` in styles/gameday.css runs the animation.
 *
 * Two rules together get the tie band right, and each is wrong without the other:
 *
 *   1. The comparison is `previous * next < 0` — *strictly opposite* signs — not
 *      `sign(previous) !== sign(next)`, which would treat every entry into and exit
 *      from the tie band as its own flip and double-pulse one lead change.
 *   2. The remembered sign only updates when the new one is non-zero. A tie is not a
 *      lead in either direction, so it must not become the baseline: with rule 1 alone,
 *      a margin easing +5 -> 0 -> -5 would compare `0 * -1`, which is not negative, and
 *      the flip would never fire at all.
 *
 * So a flip that pauses at tied fires exactly once, on the tick that actually reverses
 * the lead, and a change of magnitude alone never fires (+3 -> +18 is a product of +54).
 *
 * Never fires on first render: the ref is seeded with the initial margin, so the first
 * effect run sees no transition at all.
 */
export function useLeadFlip(margin: number): LeadFlipProps {
  const previousSign = useRef(leadSign(margin));
  const [flipped, setFlipped] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const next = leadSign(margin);
    const previous = previousSign.current;
    // Only a real lead updates the baseline. Letting a tie overwrite it would erase the
    // side the user was on, and the crossing out the other side would compare against
    // zero and silently never fire.
    if (next !== 0) previousSign.current = next;

    if (previous * next >= 0) return;

    setFlipped(true);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setFlipped(false), LEAD_FLIP_ANIMATION_MS);
  }, [margin]);

  // Unmount-only cleanup, separate from the margin-driven effect above so it doesn't
  // race that effect's own clear on every change.
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return {
    "data-lead-flip": flipped ? "true" : undefined,
    onAnimationEnd: () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      setFlipped(false);
    },
  };
}
