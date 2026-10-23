// League → one team: another manager's roster, opened from a standings row.
//
// Nested under the League tab (`/team/:teamId/league/:rosterTeamId`) instead of linking
// to `/team/:rosterTeamId`, because the shell reads the active team from the first id in
// the URL. Linking straight to an opponent would make them "your" team: the switcher,
// the remembered team and every other tab would follow them. Here the League tab stays
// selected and a back link returns to the standings.
//
// Read-only on purpose: no lineup advice or score cards, which only make sense for a
// team you manage. The roster table is My Team's, so a player name still opens the
// player stats card.

import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useTeam } from "../../api/teams";
import { IconArrowL, Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { ordinal } from "../../components/shared/ordinal";
import { TeamLogo } from "../../components/shared/TeamLogo";
import { teamRoutePath } from "../../hooks/teamRoute";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { RosterTable } from "../MyTeam/RosterTable";

function recordText(record: { w: number; l: number; t: number }): string {
  return record.t > 0 ? `${record.w}-${record.l}-${record.t}` : `${record.w}-${record.l}`;
}

function LeagueTeamSkeleton() {
  return (
    <div data-testid="league-team-loading" aria-hidden="true">
      <div className="team-header">
        <Skeleton width={56} height={56} radius={12} />
        <div style={{ flex: 1 }}>
          <Skeleton width="40%" height={34} radius={6} />
          <div style={{ height: 8 }} />
          <Skeleton width="30%" height={15} />
        </div>
      </div>
      <div className="card" style={{ padding: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} width="100%" height={36} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LeagueTeam() {
  const { teamId = "", rosterTeamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();
  const rosterQuery = useTeam(rosterTeamId, week);
  const platformsDisconnected = usePlatformsDisconnected(rosterQuery.data?.meta);

  const back = (
    <Link to={teamRoutePath(teamId, "league")} className="back-link">
      <IconArrowL size={20} />
      {rosterQuery.data?.data.league.name ?? "League"}
    </Link>
  );

  if (platformsDisconnected) {
    return <EmptyState testId="league-team-empty" />;
  }

  if (rosterQuery.isError) {
    return (
      <>
        {back}
        <ErrorCard
          error={rosterQuery.error}
          fallbackMessage="Couldn't load this team's roster."
          onRetry={() => void queryClient.invalidateQueries({ queryKey: ["team", rosterTeamId] })}
          testId="league-team-error"
        />
      </>
    );
  }

  if (rosterQuery.isLoading || !rosterQuery.data) {
    return (
      <>
        {back}
        <LeagueTeamSkeleton />
      </>
    );
  }

  const { team, starters, bench } = rosterQuery.data.data;
  const subtitle = [
    team.manager_name,
    recordText(team.record),
    team.rank.current > 0 ? `${ordinal(team.rank.current)} of ${team.rank.total}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      {back}
      <header className="team-header">
        <TeamLogo team={team} size={56} />
        <div style={{ minWidth: 0 }}>
          <h1 className="large-title">{team.name}</h1>
          <p className="large-subtitle">{subtitle}</p>
        </div>
      </header>

      {starters.length === 0 && bench.length === 0 ? (
        <div className="card" style={{ padding: 24, textAlign: "center" }}>
          <div className="muted">No roster synced for week {week}.</div>
        </div>
      ) : (
        <RosterTable starters={starters} bench={bench} />
      )}
    </>
  );
}
