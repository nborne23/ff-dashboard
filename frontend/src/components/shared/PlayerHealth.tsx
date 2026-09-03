// Badge + its dialog, as one drop-in. The badge owns its open state so the four tables
// that use it don't each have to thread a `selectedPlayer` through their own props —
// four copies of the same three lines was the alternative.

import { useState } from "react";

import type { InjuryStatus } from "../../types/api";
import { InjuryBadge } from "./InjuryBadge";
import { isNoteworthy } from "./injuryLabels";
import { PlayerHealthPanel } from "./PlayerHealthPanel";

export interface PlayerHealthProps {
  playerId: string;
  playerName: string;
  status: InjuryStatus | null | undefined;
}

export function PlayerHealth({ playerId, playerName, status }: PlayerHealthProps) {
  const [open, setOpen] = useState(false);
  if (!isNoteworthy(status)) return null;
  return (
    <>
      <InjuryBadge status={status} onClick={() => setOpen(true)} />
      {open && (
        <PlayerHealthPanel
          playerId={playerId}
          playerName={playerName}
          status={status}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
