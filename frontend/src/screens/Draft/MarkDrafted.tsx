// Task 3.9 — one-tap pick recording, distinguishing a pick BY the user ("Mine") from a
// pick by another team ("Theirs"). `UndoLastPickButton` lives in this same file (the
// task pairs "MarkDrafted + undo control") and is rendered in the screen header
// (Draft/index.tsx) so it's visible without scrolling -- mis-taps happen constantly
// during a live draft and the fix has to be one tap away, not a scroll away.

import { useState } from "react";

import type { BoardPlayerOut } from "../../api/draft";
import { useMarkDrafted, useUndoLastPick } from "../../api/draft";
import { getApiErrorMessage } from "../../api/client";

export interface MarkDraftedProps {
  player: BoardPlayerOut;
}

export function MarkDrafted({ player }: MarkDraftedProps) {
  const markDrafted = useMarkDrafted();
  const [error, setError] = useState<string | null>(null);

  function mark(isMine: boolean) {
    setError(null);
    markDrafted.mutate(
      {
        board_player_id: player.id,
        player_name: player.name,
        is_my_pick: isMine,
        drafted_by_team: isMine ? undefined : "Another team",
      },
      { onError: (err) => setError(getApiErrorMessage(err, "Couldn't record that pick.")) },
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="button"
          className="btn primary"
          style={{ padding: "8px 12px", fontSize: 13 }}
          onClick={() => mark(true)}
          disabled={markDrafted.isPending}
          aria-label={`Mark ${player.name} drafted by me`}
        >
          Mine
        </button>
        <button
          type="button"
          className="btn"
          style={{ padding: "8px 12px", fontSize: 13 }}
          onClick={() => mark(false)}
          disabled={markDrafted.isPending}
          aria-label={`Mark ${player.name} drafted by another team`}
        >
          Theirs
        </button>
      </div>
      {error && (
        <span style={{ color: "var(--espn)", fontSize: 11 }} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export function UndoLastPickButton() {
  const undoLastPick = useUndoLastPick();
  const [error, setError] = useState<string | null>(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
      <button
        type="button"
        className="btn danger"
        onClick={() =>
          undoLastPick.mutate(undefined, {
            onError: (err) => setError(getApiErrorMessage(err, "Couldn't undo the last pick.")),
            onSuccess: () => setError(null),
          })
        }
        disabled={undoLastPick.isPending}
        data-testid="undo-last-pick"
      >
        Undo last pick
      </button>
      {error && (
        <span style={{ color: "var(--espn)", fontSize: 11 }} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
