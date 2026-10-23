// The mirrored roster (design D2) — one row per starter slot carrying BOTH teams,
// reading outward from a dashed center rule.
//
// Head-to-Head's three-column table needs ~900px before names start truncating. A
// 3-across or 4-column Game Day panel gets 340–520px, so the width has to be spent on
// text rather than on a third structural column: mirroring puts the slot label and the
// per-slot differential in a narrow center cell and gives both names the rest.
//
// Orientation is `orientSlot()` from Head-to-Head, unchanged. Game Day must not
// re-derive the home/away ternary — one source of truth for "which side is mine".

import { InjuryBadge } from "../../components/shared/InjuryBadge";
import { PlayerName } from "../../components/shared/PlayerName";
import { useChangedValuePulse } from "../../hooks/useChangedValuePulse";
import type { GameState, MatchupSlot, Player } from "../../types/api";
import { orientSlot } from "../HeadToHead/orientation";
import { displaySlot } from "../../components/shared/slotLabel";
import type { BigPlay } from "./useBigPlay";
import { TIE_EPSILON } from "./useLeadFlip";

export interface MirroredRosterProps {
  slots: MatchupSlot[];
  iAmHome: boolean;
  /**
   * The user's team in this panel. Game Day has no `:teamId` route, so the stats card a
   * name opens needs it passed explicitly to pick the league's scoring and slot.
   */
  teamId?: string;
  /**
   * Lets the panel read this element's computed `display` when toggling disclosure.
   * A plainly-named prop rather than `ref`: this project is on React 18, where `ref`
   * on a function component is not forwarded automatically and would be silently
   * dropped — leaving the toggle unable to tell open from shut.
   */
  rosterRef?: React.Ref<HTMLDivElement>;
  /** Big plays firing right now, keyed by slot label. Detected by the panel. */
  bigPlays?: Record<string, BigPlay>;
}

interface SideProps {
  player: Player;
  teamId?: string;
  points: number;
  state: GameState | null;
  isLive: boolean;
  side: "mine" | "theirs";
}

/**
 * One team's half of a row. `pre` renders dimmed via `data-state`, which is the whole
 * point of carrying per-side state: a dimmed 0.0 reads as "hasn't played", a full-
 * brightness 0.0 reads as "was shut out". Without the distinction every pre-kickoff
 * panel would look like a blowout.
 */
function Side({ player, teamId, points, state, isLive, side }: SideProps) {
  return (
    <div className="gd-side" data-side={side} data-state={state ?? "unknown"}>
      {isLive && <span className="gd-live-dot" aria-hidden="true" />}
      {/* The name opens the stats card (add-player-stats) — on a wall display nobody
          clicks it, and at a desk it is the fastest way to a live stat line. */}
      <PlayerName player={player} teamId={teamId} className="gd-player-name" />
      {/* The injury badge stays static: the health detail is one screen away on MyTeam,
          and a second dialog trigger per side would crowd a 340px panel. */}
      <InjuryBadge status={player.injury_status} />
      <span className="gd-nfl-team">{player.nfl_team}</span>
      <span className="gd-pts">{points.toFixed(1)}</span>
    </div>
  );
}

interface RowProps {
  slot: MatchupSlot;
  iAmHome: boolean;
  teamId?: string;
  bigPlay?: BigPlay;
}

function MirroredRow({ slot, iAmHome, teamId, bigPlay }: RowProps) {
  const { myPlayer, oppPlayer, myPts, oppPts } = orientSlot(slot, iAmHome);
  const myState = iAmHome ? slot.home_state : slot.away_state;
  const oppState = iAmHome ? slot.away_state : slot.home_state;
  const myIsLive = iAmHome ? slot.home_is_live : slot.away_is_live;
  const oppIsLive = iAmHome ? slot.away_is_live : slot.home_is_live;

  // The row flashes when *either* side's points move — a scoring play on the opponent's
  // roster is as much a change to this row as one on the user's.
  const pulse = useChangedValuePulse(`${myPts}:${oppPts}`);

  const diff = myPts - oppPts;
  const tied = Math.abs(diff) < TIE_EPSILON;

  return (
    <div
      className="gd-row"
      data-just-changed={pulse["data-just-changed"]}
      data-big-play={bigPlay?.side}
      // `animationend` bubbles, so the burst chip's own animation would otherwise reach
      // this handler and clear the row's flash early. Only the row's animation counts.
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget) pulse.onAnimationEnd();
      }}
    >
      {bigPlay && (
        // Keyed by firing id so a second big play on a row whose chip is still up
        // remounts the chip and replays the animation from the start.
        <span key={bigPlay.id} className="gd-big-play" data-side={bigPlay.side}>
          <span aria-hidden="true">⚡</span> +{bigPlay.delta.toFixed(1)} {bigPlay.player}
        </span>
      )}
      <Side
        player={myPlayer}
        teamId={teamId}
        points={myPts}
        state={myState}
        isLive={myIsLive}
        side="mine"
      />
      <div className="gd-center">
        <span className="gd-slot-label">{displaySlot(slot.slot)}</span>
        <span
          className="gd-slot-diff"
          data-sign={tied ? "tied" : diff > 0 ? "pos" : "neg"}
          // The em-dash for a tie is decorative; the label carries the meaning.
          aria-label={tied ? "even" : `${diff > 0 ? "+" : ""}${diff.toFixed(1)}`}
        >
          {tied ? "—" : `${diff > 0 ? "+" : ""}${diff.toFixed(1)}`}
        </span>
      </div>
      <Side
        player={oppPlayer}
        teamId={teamId}
        points={oppPts}
        state={oppState}
        isLive={oppIsLive}
        side="theirs"
      />
    </div>
  );
}

export function MirroredRoster({
  slots,
  iAmHome,
  teamId,
  rosterRef,
  bigPlays,
}: MirroredRosterProps) {
  return (
    <div className="gd-roster" data-testid="gd-roster" ref={rosterRef}>
      {slots.map((slot) => (
        <MirroredRow
          key={slot.slot}
          slot={slot}
          iAmHome={iAmHome}
          teamId={teamId}
          bigPlay={bigPlays?.[slot.slot]}
        />
      ))}
    </div>
  );
}
