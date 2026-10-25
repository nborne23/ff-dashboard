// The celebration queue (add-play-highlights): `api/highlights.ts` enqueues, the
// shell's `HighlightCelebration` plays the head and shifts it off. One at a time — two
// touchdowns in the same refresh are two moments, not one crowded card.

import { create } from "zustand";

import type { PlayerHighlight } from "../api/highlights";

/**
 * At most this many celebrations wait in line. A burst past it (five starters scoring in
 * one refresh is a very good Sunday, or a long sleep) folds into an "and N more" on the
 * last card rather than a minute of back-to-back confetti.
 */
export const MAX_QUEUED = 3;

interface HighlightState {
  queue: PlayerHighlight[];
  /** Highlights dropped past `MAX_QUEUED`, shown on the last card. */
  overflow: number;
  enqueue: (highlights: PlayerHighlight[]) => void;
  /** Done with the head of the queue (played out, or tapped away). */
  shift: () => void;
}

export const useHighlightStore = create<HighlightState>()((set) => ({
  queue: [],
  overflow: 0,
  enqueue: (highlights) =>
    set((state) => {
      const seen = new Set(state.queue.map((h) => h.id));
      const fresh = highlights.filter((h) => !seen.has(h.id));
      const room = Math.max(0, MAX_QUEUED - state.queue.length);
      return {
        queue: [...state.queue, ...fresh.slice(0, room)],
        overflow: state.overflow + Math.max(0, fresh.length - room),
      };
    }),
  shift: () =>
    set((state) => {
      const queue = state.queue.slice(1);
      return { queue, overflow: queue.length === 0 ? 0 : state.overflow };
    }),
}));
