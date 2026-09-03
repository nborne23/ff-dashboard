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
import { useChangedValuePulse } from "../../hooks/useChangedValuePulse";
import type { GameState, InjuryStatus, MatchupSlot } from "../../types/api";
import { orientSlot } from "../HeadToHead/orientation";
import { TIE_EPSILON } from "./useLeadFlip";

export interface MirroredRosterProps {
  slots: MatchupSlot[];
  iAmHome: boolean;
  /**
   * Lets the panel read this element's computed `display` when toggling disclosure.
   * A plainly-named prop rather than `ref`: this project is on React 18, where `ref`
   * on a function component is not forwarded automatically and would be silently
   * dropped — leaving the toggle unable to tell open from shut.
   */
  rosterRef?: React.Ref<HTMLDivElement>;
}

interface SideProps {
  name: string;
  nflTeam: string;
  points: number;
  state: GameState | null;
  isLive: boolean;
  side: "mine" | "theirs";
  injuryStatus: InjuryStatus | null;
}

/**
 * One team's half of a row. `pre` renders dimmed via `data-state`, which is the whole
 * point of carrying per-side state: a dimmed 0.0 reads as "hasn't played", a full-
 * brightness 0.0 reads as "was shut out". Without the distinction every pre-kickoff
 * panel would look like a blowout.
 */
function Side({ name, nflTeam, points, state, isLive, side, injuryStatus }: SideProps) {
  return (
    <div className="gd-side" data-side={side} data-state={state ?? "unknown"}>
      {isLive && <span className="gd-live-dot" aria-hidden="true" />}
      <span className="gd-player-name">{name}</span>
      {/* Static, not clickable: Game Day is a glanceable wall display and opening a
          modal over a live scoreboard is the wrong affordance for it. The full detail
          lives one screen away on MyTeam. */}
      <InjuryBadge status={injuryStatus} />
      <span className="gd-nfl-team">{nflTeam}</span>
      <span className="gd-pts">{points.toFixed(1)}</span>
    </div>
  );
}

interface RowProps {
  slot: MatchupSlot;
  iAmHome: boolean;
}

function MirroredRow({ slot, iAmHome }: RowProps) {
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
    <div className="gd-row" {...pulse}>
      <Side
        name={myPlayer.name}
        nflTeam={myPlayer.nfl_team}
        points={myPts}
        state={myState}
        isLive={myIsLive}
        side="mine"
        injuryStatus={myPlayer.injury_status}
      />
      <div className="gd-center">
        <span className="gd-slot-label">{slot.slot}</span>
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
        name={oppPlayer.name}
        nflTeam={oppPlayer.nfl_team}
        points={oppPts}
        state={oppState}
        isLive={oppIsLive}
        side="theirs"
        injuryStatus={oppPlayer.injury_status}
      />
    </div>
  );
}

export function MirroredRoster({ slots, iAmHome, rosterRef }: MirroredRosterProps) {
  return (
    <div className="gd-roster" data-testid="gd-roster" ref={rosterRef}>
      {slots.map((slot) => (
        <MirroredRow key={slot.slot} slot={slot} iAmHome={iAmHome} />
      ))}
    </div>
  );
}
