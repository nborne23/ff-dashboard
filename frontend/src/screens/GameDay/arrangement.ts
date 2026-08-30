// Pure ordering/sorting logic for the Game Day stage (design D8). No React, no store
// access, no DOM — everything here is a plain function of its arguments so the
// reconciliation rules can be tested directly rather than through a rendered screen.

import type { GameDayMatchup } from "../../types/api";
import type { GameDaySortMode } from "../../stores/ui";

/**
 * Reconcile a persisted order against the team ids actually in the envelope.
 *
 * Both directions matter, and only one of them is obvious:
 *
 *   - **Drop departed ids.** A disconnected league's team is still named in the stored
 *     order; keeping it would render an empty panel.
 *   - **Append new ids.** The half that is easy to miss — filtering the persisted order
 *     alone silently omits any team the order predates, so connecting a new league
 *     would produce a panel that never appears until the user cleared their layout.
 *
 * A fully-replaced team set therefore reconciles to the envelope's own order rather
 * than to an empty stage.
 */
export function reconcileOrder(persisted: string[], liveIds: string[]): string[] {
  const live = new Set(liveIds);
  const seen = new Set<string>();
  const kept: string[] = [];
  for (const id of persisted) {
    // De-duplicating as we go, not just filtering: a stored order that somehow carries
    // the same id twice would otherwise render two panels for one team and collide on
    // the React key.
    if (!live.has(id) || seen.has(id)) continue;
    seen.add(id);
    kept.push(id);
  }
  const appended = liveIds.filter((id) => !seen.has(id));
  return [...kept, ...appended];
}

/** Live players on a panel — either side of any slot reporting live (design D4). */
export function liveCount(matchup: GameDayMatchup): number {
  let count = 0;
  for (const slot of matchup.slots) {
    if (slot.home_is_live) count += 1;
    if (slot.away_is_live) count += 1;
  }
  return count;
}

/** Absolute points between the two sides, from either perspective. */
export function absMargin(matchup: GameDayMatchup): number {
  return Math.abs(matchup.score - matchup.opp_score);
}

/**
 * Apply an auto-sort mode to an already-reconciled order.
 *
 * `"manual"` returns the order untouched — a hand-placed order and an auto mode are
 * mutually exclusive states, not layers, so this never re-sorts on top of a drag.
 * `"margin"` puts the closest games first (the ones worth watching); `"live"` puts the
 * panels with the most players still on the field first.
 *
 * Ties fall back to the incoming order's index, so the sort is stable and a tick that
 * changes nothing never reshuffles the stage.
 */
export function applySort(
  ids: string[],
  byId: Record<string, GameDayMatchup>,
  sortMode: GameDaySortMode,
): string[] {
  if (sortMode === "manual") return [...ids];

  const index = new Map(ids.map((id, i) => [id, i]));
  const rank = (id: string): number => {
    const matchup = byId[id];
    if (!matchup) return Number.POSITIVE_INFINITY;
    // Negated for "live" so the descending count sorts ascending by rank.
    return sortMode === "margin" ? absMargin(matchup) : -liveCount(matchup);
  };

  return [...ids].sort((a, b) => {
    const delta = rank(a) - rank(b);
    if (delta !== 0) return delta;
    return (index.get(a) ?? 0) - (index.get(b) ?? 0);
  });
}

/**
 * Move `dragId` to `targetId`'s position, shifting the rest along. Returns the input
 * unchanged when either id is absent or they are the same panel, so a drag that lands
 * on itself is a no-op rather than a reshuffle.
 */
export function reorder(ids: string[], dragId: string, targetId: string): string[] {
  if (dragId === targetId) return [...ids];
  const from = ids.indexOf(dragId);
  const to = ids.indexOf(targetId);
  if (from === -1 || to === -1) return [...ids];

  const next = [...ids];
  next.splice(from, 1);
  next.splice(to, 0, dragId);
  return next;
}
