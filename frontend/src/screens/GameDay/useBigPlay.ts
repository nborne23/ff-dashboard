// `useBigPlays` — the loudest cue on the screen: a player just did something big.
//
// The third member of the Game Day cue family, after `useChangedValuePulse` (any value
// moved) and `useLeadFlip` (the margin crossed zero). Its structure — a ref seeded on
// the first run, state, and a timeout that owns the clear — is deliberately copied from
// those two so all three behave identically; only the trigger and the volume differ.
//
// Why it is lifted to the panel rather than living in the row: the panel-level flare
// must be caused by the same event as the row flash. Deriving it from the matchup's
// total instead would be wrong in both directions — two players gaining 4 apiece would
// trip a 6-point threshold with nobody having done anything, and a 14-point touchdown
// offset by a fumble elsewhere would trip nothing at all. Both are ordinary Sundays.

import { useEffect, useRef, useState } from "react";

import type { MatchupSlot } from "../../types/api";
import { orientSlot } from "../HeadToHead/orientation";

/**
 * Points gained in a single refresh that count as a big play. Six is a touchdown: the
 * smallest event a fan would look up for. PPR receptions (1), a long catch (a few), and
 * a field goal (3) all stay below it, which is the point — a cue that fires on every
 * checkdown is one the eye stops seeing by noon.
 */
export const BIG_PLAY_POINTS = 6;

/** Mirrors styles/gameday.css's `gd-big-play` / `gd-big-play-flare` durations. */
export const BIG_PLAY_ANIMATION_MS = 2400;

export type BigPlaySide = "mine" | "theirs";

export interface BigPlay {
  side: BigPlaySide;
  /** Points gained in the one refresh that fired this. */
  delta: number;
  player: string;
  /**
   * Distinct per firing, used as a React `key` on the burst chip so a second big play
   * on a row whose chip is still on screen remounts it and restarts the animation —
   * re-setting an attribute that is already set would not.
   */
  id: number;
}

export interface BigPlays {
  /** `undefined` when nothing is firing; spread onto the panel. */
  panelSide: BigPlaySide | "both" | undefined;
  /** Keyed by slot label, e.g. `"RB1"`. */
  bySlot: Record<string, BigPlay>;
}

/** Points at the last refresh, keyed `"<matchup id>|<slot label>"`. */
type PointsSnapshot = Map<string, { mine: number; theirs: number }>;

/**
 * Compares this refresh's slots against the previous snapshot and returns both the
 * detections and the new snapshot.
 *
 * A free function rather than inline effect code because the detection needs a loop, and
 * a `setState` a loop can reach is what the react-hooks lint rule reads as a cascading
 * render. Hoisted out, the effect body is the same shape as `useChangedValuePulse`'s:
 * compare against a ref, bail if nothing happened, otherwise set state once.
 */
function detectBigPlays(
  seen: PointsSnapshot | null,
  slots: MatchupSlot[],
  iAmHome: boolean,
  nextId: { current: number },
): { fired: Record<string, BigPlay>; snapshot: PointsSnapshot } {
  const snapshot: PointsSnapshot = new Map();
  const fired: Record<string, BigPlay> = {};

  for (const slot of slots) {
    const { myPlayer, oppPlayer, myPts, oppPts } = orientSlot(slot, iAmHome);
    // Keyed by matchup AND slot, never by slot alone. Both platforms encode the week in
    // the matchup id, and a panel is keyed by team id on the stage, so it survives a
    // week change rather than remounting: without the matchup in the key, stepping to
    // week 2 and back to week 1 — served from cache, with no loading state to reseed
    // through — would compare week 1's points against week 2's and flare every row on
    // the board at once.
    const key = `${slot.matchup_id}|${slot.slot}`;
    snapshot.set(key, { mine: myPts, theirs: oppPts });

    const before = seen?.get(key);
    if (!before) continue;

    const mineDelta = myPts - before.mine;
    const theirsDelta = oppPts - before.theirs;
    // One row carries one cue, so the larger jump wins. Both sides scoring big in the
    // same refresh is rare enough not to be worth a split-colored row.
    const [side, delta, player]: [BigPlaySide, number, string] =
      mineDelta >= theirsDelta
        ? ["mine", mineDelta, myPlayer.name]
        : ["theirs", theirsDelta, oppPlayer.name];

    if (delta >= BIG_PLAY_POINTS) {
      // Keyed by slot label alone on the way out — the caller looks these up per row,
      // where the matchup is already implied.
      fired[slot.slot] = { side, delta, player, id: nextId.current++ };
    }
  }

  return { fired, snapshot };
}

/**
 * Detects per-slot point jumps across refreshes of one matchup's slots.
 *
 * Never fires on the first run: the previous-points map starts empty and an entry the
 * map has not seen seeds silently. The same rule covers everything else that makes this
 * refresh's rows incomparable to the last one's — a lineup edit, the conditional
 * numbering that turns `K` into `K1`/`K2` when a league starts two kickers, or a change
 * of week — each of which would otherwise read as a whole roster scoring at once.
 */
export function useBigPlays(slots: MatchupSlot[], iAmHome: boolean): BigPlays {
  const previous = useRef<PointsSnapshot | null>(null);
  const [bySlot, setBySlot] = useState<Record<string, BigPlay>>({});
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextId = useRef(0);

  useEffect(() => {
    const { fired, snapshot } = detectBigPlays(previous.current, slots, iAmHome, nextId);
    previous.current = snapshot;
    if (Object.keys(fired).length === 0) return;

    setBySlot((open) => ({ ...open, ...fired }));
    // One timer for the whole panel, not one per row: a second big play during the
    // window extends the first row's chip by the remainder, which is invisible (the
    // animation has already run to its transparent final keyframe) and keeps the clear
    // to a single scheduled write.
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setBySlot({}), BIG_PLAY_ANIMATION_MS);
  }, [slots, iAmHome]);

  // Unmount-only cleanup, separate from the effect above so it doesn't race that
  // effect's own clear on every refresh.
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  // No `animationend` clear here, unlike the other two cues: `animationend` bubbles, so
  // a panel-level handler would also catch every row and chip animation inside it and
  // end the flare early. The timer is the only owner.
  const sides = new Set(Object.values(bySlot).map((play) => play.side));
  const panelSide = sides.size === 0 ? undefined : sides.size > 1 ? "both" : [...sides][0];

  return { panelSide, bySlot };
}
