// Screen: Draft Assistant (task 3.12). Usable with ZERO ESPN integration -- no
// arm/disarm control here (phase 5). Manual entry + SSE-driven invalidation
// (events.ts's "draft" scope, task 3.6) is the whole mechanism.
//
// Layout, top to bottom: header (title + always-visible Undo, no scrolling needed for
// a mis-tap fix) -> current-pick bar -> recommendations (shortlist at the TOP per task
// 3.11) -> board + roster grid, reusing `.dashboard-grid`/`.rail` (MyTeam/index.tsx's
// same classes) so the existing >=767px responsive collapse to one column applies here
// for free.

import { useQueryClient } from "@tanstack/react-query";

import { useDraftState } from "../../api/draft";
import { Skeleton } from "../../components/primitives";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { BoardList } from "./BoardList";
import { CurrentPick } from "./CurrentPick";
import { UndoLastPickButton } from "./MarkDrafted";
import { MatchResolution } from "./MatchResolution";
import { Recommendations } from "./Recommendations";
import { RosterPanel } from "./RosterPanel";
import { SettingsConflictBanner } from "./SettingsConflictBanner";
import { SlotPlan } from "./SlotPlan";

function DraftSkeleton() {
  return (
    <div data-testid="draft-skeleton" aria-hidden="true">
      <Skeleton width="40%" height={34} radius={6} />
      <div style={{ height: 16 }} />
      <Skeleton width="100%" height={72} radius={12} />
      <div style={{ height: 16 }} />
      <Skeleton width="100%" height={160} radius={12} />
    </div>
  );
}

export default function Draft() {
  const stateQuery = useDraftState();
  const queryClient = useQueryClient();
  const retry = () => void queryClient.invalidateQueries({ queryKey: ["draft"] });

  if (stateQuery.isError) {
    return (
      <ErrorCard
        error={stateQuery.error}
        fallbackMessage="Couldn't load the draft."
        onRetry={retry}
        testId="draft-error"
      />
    );
  }

  if (stateQuery.isLoading || !stateQuery.data) {
    return <DraftSkeleton />;
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 8 }}>
        <div>
          <h1 className="large-title" style={{ marginBottom: 0 }}>
            Draft Assistant
          </h1>
          <p className="large-subtitle" style={{ marginBottom: 0 }}>
            Manual entry — no ESPN live sync yet.
          </p>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <UndoLastPickButton />
        </div>
      </div>

      <div className="spacer-md" />
      <SettingsConflictBanner conflicts={stateQuery.data.data.settings_conflicts} />
      <div className="spacer-md" />
      <MatchResolution />
      <div className="spacer-md" />
      <CurrentPick />
      <div className="spacer-md" />
      <SlotPlan />
      <div className="spacer-md" />
      <Recommendations />
      <div className="spacer-md" />
      <div className="dashboard-grid">
        <BoardList />
        <div className="rail">
          <RosterPanel />
        </div>
      </div>
    </>
  );
}
