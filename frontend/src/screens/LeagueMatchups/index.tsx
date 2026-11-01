// League → All Matchups: every pairing in the selected team's league for one week.
//
// Nested under the League tab (`/team/:teamId/league/matchups`) for the same reason
// LeagueTeam is: the shell reads the active team from the first id in the URL, so the
// user's team stays the active one while they browse other managers' games.
//
// The week arrows here drive the app's one global week (the Topbar's), so stepping back
// a week and then opening your own matchup lands on that same week's Head-to-Head. Your
// own matchup opens the Matchup tab, with its win probability and projections; anyone
// else's opens a read-only head-to-head beneath this screen.

import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useLeagueMatchups } from "../../api/leagueMatchups";
import { IconArrowL, IconArrowR, Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { teamRoutePath } from "../../hooks/teamRoute";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { matchupDetailPath } from "./format";
import { MatchupCard } from "./MatchupCard";
import "../../styles/league-matchups.css";

function MatchupsSkeleton() {
  return (
    <div data-testid="league-matchups-loading" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="card lm-card">
          {Array.from({ length: 2 }).map((__, j) => (
            <div key={j} className="lm-row">
              <Skeleton width={16} height={16} />
              <Skeleton width={40} height={40} circle />
              <div className="lm-team">
                <Skeleton width="60%" height={17} />
                <div style={{ height: 6 }} />
                <Skeleton width="40%" height={13} />
              </div>
              <Skeleton width={56} height={20} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export default function LeagueMatchups() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const setWeek = useUiStore((s) => s.setWeek);
  const queryClient = useQueryClient();

  const query = useLeagueMatchups(teamId, week);
  const platformsDisconnected = usePlatformsDisconnected(query.data?.meta);
  const data = query.data?.data;

  // Future weeks have no pairings stored (discovery writes current and past weeks only),
  // so the forward arrow stops at the league's current week.
  const lastWeek = data?.league.current_week;
  const weekNav = (
    <div className="lm-week-nav" role="group" aria-label="Week">
      <button
        type="button"
        className="icon-btn"
        onClick={() => setWeek(week - 1)}
        disabled={week <= 1}
        aria-label="Previous week"
      >
        <IconArrowL size={16} />
      </button>
      <span className="lm-week-label" aria-live="polite">
        Week {week}
      </span>
      <button
        type="button"
        className="icon-btn"
        onClick={() => setWeek(week + 1)}
        disabled={lastWeek !== undefined && week >= lastWeek}
        aria-label="Next week"
      >
        <IconArrowR size={16} />
      </button>
    </div>
  );

  const back = (
    <Link to={teamRoutePath(teamId, "league")} className="back-link">
      <IconArrowL size={20} />
      {data?.league.name ?? "League"}
    </Link>
  );

  if (platformsDisconnected) {
    return <EmptyState testId="league-matchups-empty" />;
  }

  if (query.isError) {
    return (
      <>
        {back}
        <ErrorCard
          error={query.error}
          fallbackMessage="Couldn't load this league's matchups."
          onRetry={() =>
            void queryClient.invalidateQueries({ queryKey: ["league-matchups", teamId] })
          }
          testId="league-matchups-error"
        />
      </>
    );
  }

  return (
    <>
      {back}
      <div className="lm-header">
        <div style={{ minWidth: 0 }}>
          <h1 className="large-title">All Matchups</h1>
          <p className="large-subtitle">{data?.league.name ?? " "}</p>
        </div>
        {weekNav}
      </div>

      {query.isLoading || !data ? (
        <MatchupsSkeleton />
      ) : data.matchups.length === 0 ? (
        <div className="card" style={{ padding: 24, textAlign: "center" }}>
          <div className="muted">No matchups synced for week {data.week} yet.</div>
        </div>
      ) : (
        <div className="lm-list">
          {data.matchups.map((entry) => (
            <MatchupCard
              key={entry.matchup.id}
              entry={entry}
              href={
                entry.is_user_matchup
                  ? teamRoutePath(teamId, "h2h")
                  : matchupDetailPath(teamId, entry.matchup.id)
              }
            />
          ))}
        </div>
      )}
    </>
  );
}
