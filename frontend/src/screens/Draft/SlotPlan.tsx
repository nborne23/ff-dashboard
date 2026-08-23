// Task 6.4 — renders `board_heuristics._draft_slot_1_plan` (`GET /api/draft/slot-plan`)
// ONLY when the user's actual configured draft slot is 1: its pick numbers and its
// back-to-back reasoning (pick 24/25 in the same turn) are valid solely for slot 1 in
// a 12-team snake draft, so at any other slot this renders nothing at all rather than
// present a plan the user can't act on. `SlotPlanData.applicable` is the backend's own
// `league_shape.slot == 1` check (backend/gridiron/api/draft.py) -- this component
// trusts it rather than re-deriving slot from anywhere else on the Draft screen
// (DraftStateData doesn't even carry the configured slot).
//
// Each named target is tagged live against the draft (task 6.4's "recompute the
// remainder against the live pool"): sniped (drafted by another team, struck through),
// already yours, or still on the board -- never rendered as static plan text.

import type { SlotPlanTargetOut } from "../../api/draft";
import { useDraftSlotPlan } from "../../api/draft";
import { Skeleton } from "../../components/primitives";
import { ErrorCard } from "../../components/shared/ErrorCard";

function TargetPill({ target }: { target: SlotPlanTargetOut }) {
  if (target.drafted_by_me) {
    return (
      <span className="pill win" data-testid="slot-plan-target">
        {target.name} · yours
      </span>
    );
  }
  if (target.sniped) {
    return (
      <span
        className="pill loss"
        style={{ textDecoration: "line-through" }}
        data-testid="slot-plan-target"
      >
        {target.name} · sniped{target.drafted_by_team ? ` by ${target.drafted_by_team}` : ""}
      </span>
    );
  }
  if (!target.still_available) {
    // Not drafted by anyone, but also not in the live draftable pool -- e.g. ruled out
    // for the season since the plan was written. Distinct from "sniped" (no one took
    // him) and from a normal still-on-the-board target (he isn't one).
    return (
      <span
        className="pill bench"
        style={{ textDecoration: "line-through" }}
        data-testid="slot-plan-target"
      >
        {target.name} · unavailable
      </span>
    );
  }
  return (
    <span className="pill bench" data-testid="slot-plan-target">
      {target.name}
    </span>
  );
}

export function SlotPlan() {
  const planQuery = useDraftSlotPlan();

  if (planQuery.isError) {
    return (
      <ErrorCard
        error={planQuery.error}
        fallbackMessage="Couldn't load the slot-1 plan."
        onRetry={() => void planQuery.refetch()}
        testId="slot-plan-error"
      />
    );
  }

  if (planQuery.isLoading || !planQuery.data) {
    return (
      <div className="card" data-testid="slot-plan-skeleton" aria-hidden="true">
        <Skeleton width="40%" height={18} />
        <div style={{ height: 8 }} />
        <Skeleton width="100%" height={48} />
      </div>
    );
  }

  const data = planQuery.data.data;

  // Not slot 1 -- this plan's picks/reasoning don't apply, so don't present it at all.
  if (!data.applicable) return null;

  return (
    <div className="card" data-testid="slot-plan">
      <div className="section-label" style={{ fontSize: 16, marginBottom: 4 }}>
        Slot 1 Plan
      </div>
      {data.structural_note && (
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          {data.structural_note}
        </p>
      )}
      <div className="row-list">
        {data.entries.map((entry) => (
          <div
            key={entry.label}
            className="draft-row"
            style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}
            data-testid="slot-plan-entry"
          >
            <div style={{ fontWeight: 600 }}>
              {entry.label}
              {entry.confidence && (
                <span className="muted" style={{ fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
                  confidence: {entry.confidence}
                </span>
              )}
            </div>
            {entry.rule && (
              <div className="muted" style={{ fontSize: 12 }}>
                {entry.rule}
              </div>
            )}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {entry.targets.map((target) => (
                <TargetPill key={target.name} target={target} />
              ))}
            </div>
            {entry.avoid.length > 0 && (
              <div className="muted" style={{ fontSize: 12 }}>
                Avoid: {entry.avoid.join(", ")}
              </div>
            )}
          </div>
        ))}
      </div>
      {data.unplanned_pick_numbers.length > 0 && (
        <p className="muted" style={{ fontSize: 12, marginTop: 12, marginBottom: 0 }}>
          No specific plan yet for pick(s) {data.unplanned_pick_numbers.join(", ")} — fall back to
          the live recommendations above when you get there.
        </p>
      )}
    </div>
  );
}
