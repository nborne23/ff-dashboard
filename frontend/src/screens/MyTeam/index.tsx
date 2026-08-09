// Screen 2: My Team — ported from design/screen-myteam.jsx. Data comes from
// useTeam(teamId, week) (frontend/src/api/teams.ts); the week segmented
// control writes to the shared ui store so every week-scoped hook across the
// app (Topbar included) refetches in lockstep, matching design/app.jsx's
// single `week` state.

import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useTeam } from "../../api/teams";
import { Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { ordinal } from "../Dashboard/ordinal";
import { PlatformPill } from "../Dashboard/TeamCard";
import { useUiStore } from "../../stores/ui";
import { platformFromId } from "../../types/api";
import { RecordCard } from "./RecordCard";
import { RosterTable } from "./RosterTable";
import { ScoreCard } from "./ScoreCard";
import { WeeklyChartCard } from "./WeeklyChartCard";

/** Matches the loaded layout's `dashboard-grid` (roster table + 3-card rail) so there's
 * no layout shift once real data lands (task 10.1). */
function MyTeamSkeleton() {
  return (
    <div data-testid="myteam-skeleton" aria-hidden="true">
      <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <Skeleton width="40%" height={34} radius={6} />
          <div style={{ height: 8 }} />
          <Skeleton width="55%" height={15} />
        </div>
      </div>
      <div className="spacer-md" />
      <div className="dashboard-grid">
        <div className="card" style={{ padding: 16 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} width="100%" height={36} />
            ))}
          </div>
        </div>
        <div className="rail">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card" style={{ padding: 16, minHeight: 96 }}>
              <Skeleton width="50%" height={13} />
              <div style={{ height: 10 }} />
              <Skeleton width="80%" height={26} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function MyTeam() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const setWeek = useUiStore((s) => s.setWeek);
  const teamQuery = useTeam(teamId, week);
  const queryClient = useQueryClient();
  const platformsDisconnected = usePlatformsDisconnected(teamQuery.data?.meta);

  const data = teamQuery.data?.data;
  const retry = () => void queryClient.invalidateQueries({ queryKey: ["team", teamId] });

  // W{n-2}..W{n+1} around the current week, dropping anything below week 1
  // (the store's week can go negative via Topbar's prev-week button, which
  // has no lower clamp today).
  const segments = [week - 2, week - 1, week, week + 1].filter((w) => w >= 1);

  if (platformsDisconnected) {
    return <EmptyState testId="myteam-empty" />;
  }

  if (teamQuery.isError) {
    return (
      <ErrorCard
        error={teamQuery.error}
        fallbackMessage="Couldn't load this team."
        onRetry={retry}
        testId="myteam-error"
      />
    );
  }

  if (teamQuery.isLoading || !data) {
    return <MyTeamSkeleton />;
  }

  const platform = platformFromId(data.team.id);

  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 8 }}>
        <div>
          <h1 className="large-title">{data.team.name}</h1>
          <p className="large-subtitle" style={{ marginBottom: 0 }}>
            <PlatformPill platform={platform} />
            &nbsp;&nbsp;{data.league.name} · {ordinal(data.team.rank.current)}
          </p>
        </div>
        <div style={{ marginLeft: "auto", marginBottom: 4 }}>
          <div className="segmented">
            {segments.map((w) => (
              <button key={w} className={w === week ? "active" : ""} onClick={() => setWeek(w)}>
                W{w}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="spacer-md" />
      <div className="dashboard-grid">
        <div>
          <div className="section-label" style={{ marginBottom: 12 }}>
            Roster
          </div>
          <RosterTable starters={data.starters} bench={data.bench} />
        </div>
        <div className="rail">
          <ScoreCard starters={data.starters} week={week} />
          <WeeklyChartCard starters={data.starters} />
          <RecordCard recordHistory={data.record_history} team={data.team} />
        </div>
      </div>
    </>
  );
}
