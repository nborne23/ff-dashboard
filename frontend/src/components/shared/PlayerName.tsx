// A player's name — and his headshot — as buttons that open his stats card
// (add-player-stats). Each owns its open state, the way PlayerHealth does, so the tables
// that render players don't each thread a `selectedPlayer` through their props.
//
// `teamId` and `week` default to the screen's own — the route's team and the shared
// week selector — which is right everywhere a player appears today. The team picks the
// league's points format; an opponent's player resolves to his slot in the same league.

import { useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";

import { useUiStore } from "../../stores/ui";
import type { Player } from "../../types/api";
import { PlayerStatsPanel } from "./PlayerStatsPanel";

interface StatsTarget {
  player: Player;
  teamId?: string;
  week?: number;
}

function usePlayerStatsDialog({ player, teamId, week }: StatsTarget) {
  const [open, setOpen] = useState(false);
  const params = useParams();
  const storeWeek = useUiStore((s) => s.week);
  const dialog = open ? (
    <PlayerStatsPanel
      player={player}
      teamId={teamId ?? params.teamId}
      week={week ?? storeWeek}
      onClose={() => setOpen(false)}
    />
  ) : null;
  return { open: () => setOpen(true), dialog };
}

export interface PlayerNameProps extends StatsTarget {
  className?: string;
}

export function PlayerName({ className = "player-name", ...target }: PlayerNameProps) {
  const { open, dialog } = usePlayerStatsDialog(target);
  return (
    <>
      <button
        type="button"
        className={`${className} player-name-button`}
        onClick={open}
        aria-haspopup="dialog"
      >
        {target.player.name}
      </button>
      {dialog}
    </>
  );
}

export interface PlayerAvatarButtonProps extends StatsTarget {
  /** The screen's own headshot element, unchanged. */
  children: ReactNode;
}

/**
 * The headshot as a second, larger target for the same card. Hidden from assistive tech
 * and the tab order: the name beside it is the accessible path, and announcing two
 * buttons that do the same thing on every row is noise.
 */
export function PlayerAvatarButton({ children, ...target }: PlayerAvatarButtonProps) {
  const { open, dialog } = usePlayerStatsDialog(target);
  return (
    <>
      <button
        type="button"
        className="player-avatar-button"
        onClick={open}
        tabIndex={-1}
        aria-hidden="true"
        data-testid="player-avatar-button"
      >
        {children}
      </button>
      {dialog}
    </>
  );
}
