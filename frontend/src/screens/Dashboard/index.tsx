// Screen 1: Dashboard — ported from design/screen-dashboard.jsx. Data comes
// from useTeams(week) (frontend/src/api/teams.ts); tweaks.teamCols and
// tweaks.showInsights (frontend/src/stores/ui.ts) are applied here, matching
// design/app.jsx's tweaks wiring but via a plain conditional class/style
// instead of the prototype's runtime CSS-injection trick.

import type { CSSProperties } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useTeams } from "../../api/teams";
import { Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { useUiStore } from "../../stores/ui";
import { InsightLiveGames } from "./InsightLiveGames";
import { InsightTopPerformer } from "./InsightTopPerformer";
import { InsightWeeklyTrend } from "./InsightWeeklyTrend";
import { TeamCard } from "./TeamCard";

function TeamCardSkeleton() {
  return (
    <div className="team-card" data-testid="team-card-skeleton" aria-hidden="true">
      <div className="left">
        <div className="top-row">
          <Skeleton width="60%" height={12} />
        </div>
        <div className="score">
          <Skeleton width="70%" height={26} />
        </div>
        <div className="sub">
          <Skeleton width="80%" height={10} />
        </div>
      </div>
      <div className="spark" />
    </div>
  );
}

function dashboardDateSubtitle(week: number): string {
  const dateLabel = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  return `${dateLabel} · Week ${week}`;
}

export default function Dashboard() {
  const week = useUiStore((s) => s.week);
  const tweaks = useUiStore((s) => s.tweaks);
  const teamsQuery = useTeams(week);
  const queryClient = useQueryClient();

  const envelope = teamsQuery.data;
  const teams = envelope?.data.teams ?? [];
  const liveCount = teams.filter((t) => t.is_live).length;

  // "Both platforms report !ok" — read literally rather than via
  // Object.values().every(), since meta.platforms may only list the
  // platforms that failed (spec: "lists any platform that failed").
  const bothPlatformsDown = envelope
    ? envelope.meta.platforms.yahoo?.ok === false && envelope.meta.platforms.espn?.ok === false
    : false;
  const needsConnection = Boolean(envelope) && (bothPlatformsDown || teams.length === 0);

  const retry = () => void queryClient.invalidateQueries({ queryKey: ["teams"] });

  if (!teamsQuery.isError && needsConnection) {
    return <EmptyState testId="connect-required" />;
  }

  return (
    <>
      <h1 className="large-title">Dashboard</h1>
      <p className="large-subtitle">{dashboardDateSubtitle(week)}</p>

      {teamsQuery.isError && (
        <ErrorCard
          error={teamsQuery.error}
          fallbackMessage="Couldn't load your teams."
          onRetry={retry}
          testId="teams-error"
        />
      )}

      {!teamsQuery.isError && (
        <div
          className="dashboard-grid"
          style={!tweaks.showInsights ? { gridTemplateColumns: "1fr" } : undefined}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
              <div className="section-label" style={{ color: "var(--move)", margin: 0 }}>
                Scoring
              </div>
              <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-secondary)" }}>
                {teamsQuery.isLoading ? "…" : `${teams.length} teams · ${liveCount} live`}
              </span>
            </div>
            <div className="team-grid" style={{ "--team-cols": tweaks.teamCols } as CSSProperties}>
              {teamsQuery.isLoading
                ? Array.from({ length: tweaks.teamCols * 2 }).map((_, i) => (
                    <TeamCardSkeleton key={i} />
                  ))
                : teams.map((team) => <TeamCard key={team.id} team={team} />)}
            </div>
          </div>

          {tweaks.showInsights && (
            <div className="rail">
              <div className="section-label" style={{ margin: 0 }}>
                Insights
              </div>
              <InsightTopPerformer teams={teams} week={week} isLoading={teamsQuery.isLoading} />
              <InsightWeeklyTrend teams={teams} week={week} />
              <InsightLiveGames />
            </div>
          )}
        </div>
      )}
    </>
  );
}
