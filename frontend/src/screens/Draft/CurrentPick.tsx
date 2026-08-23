// Task 3.9a — always-visible current overall pick / round / picks-until-next-turn, plus
// the direct correction control. Without this the tier-alarm and recommendation math
// silently compute against a stale `picks_until_next` (D13's whole rationale) -- so this
// card renders unconditionally near the top of the screen, not tucked into a settings
// panel. A tap on "Mine"/"Theirs" (MarkDrafted.tsx) already advances the counter by one;
// this form is only for the explicit correction case (catching up after skipping picks,
// fixing a mis-tap that Undo doesn't cover, phase 5's poller not existing yet).

import { type FormEvent, useState } from "react";

import { getApiErrorMessage } from "../../api/client";
import { useDraftState, useSetCurrentPick } from "../../api/draft";

export function CurrentPick() {
  const stateQuery = useDraftState();
  const setCurrentPick = useSetCurrentPick();
  const [draftValue, setDraftValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const data = stateQuery.data?.data;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(draftValue);
    if (!Number.isFinite(value) || value < 1) {
      setError("Enter a pick number of 1 or more.");
      return;
    }
    setError(null);
    setCurrentPick.mutate(Math.trunc(value), {
      onError: (err) => setError(getApiErrorMessage(err, "Couldn't set the current pick.")),
    });
    setDraftValue("");
  }

  const picksUntilLabel = data?.draft_over
    ? "Draft over"
    : data?.picks_until_next === 0
      ? "You're up"
      : (data?.picks_until_next ?? "—");

  return (
    <div className="card current-pick-bar" data-testid="current-pick">
      <div className="stat">
        <div className="value">{data?.current_overall_pick ?? "—"}</div>
        <div className="label">Overall Pick</div>
      </div>
      <div className="stat">
        <div className="value">{data?.current_round ?? "—"}</div>
        <div className="label">Round</div>
      </div>
      <div className="stat">
        <div className="value">{picksUntilLabel}</div>
        <div className="label">Until Your Turn</div>
      </div>
      <form onSubmit={handleSubmit}>
        <input
          type="number"
          min={1}
          aria-label="Set current overall pick"
          placeholder="Set pick #"
          value={draftValue}
          onChange={(event) => setDraftValue(event.target.value)}
        />
        <button type="submit" className="btn" disabled={setCurrentPick.isPending}>
          Set
        </button>
      </form>
      {error && (
        <span style={{ color: "var(--espn)", fontSize: 12, width: "100%" }} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
