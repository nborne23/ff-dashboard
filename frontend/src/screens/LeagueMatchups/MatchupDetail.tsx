// League → All Matchups → one pairing: a read-only head-to-head between two teams that
// may not include yours.
//
// Built from Head-to-Head's pieces (the `.h2h-top` header and `H2HTable`) but neutral:
// home sits on the left in the `--move` color and away on the right in `--stand`, the
// same two colors as the ring's tracks. There's no win probability or "mine/theirs"
// card, since neither side is necessarily yours.
//
// The week comes from the matchup itself, not the global week, so a link to a past
// week's game keeps showing that game after the Topbar moves on.

import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useLeagueMatchup } from "../../api/leagueMatchups";
import { ActivityRing, IconArrowL, Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { ordinal } from "../../components/shared/ordinal";
import { TeamLogo } from "../../components/shared/TeamLogo";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { H2HTable } from "../HeadToHead/H2HTable";
import { leader, matchupsPath, recordText } from "./format";
import "../../styles/league-matchups.css";

function DetailSkeleton() {
  return (
    <div data-testid="league-matchup-loading" aria-hidden="true">
      <Skeleton width="40%" height={34} radius={6} />
      <div style={{ height: 8 }} />
      <Skeleton width="30%" height={15} />
      <div className="spacer-md" />
      <div className="card" style={{ padding: "32px 24px", marginBottom: 24 }}>
        <div className="h2h-top">
          <Skeleton width="70%" height={64} style={{ margin: "0 auto" }} />
          <Skeleton width={160} height={160} circle />
          <Skeleton width="70%" height={64} style={{ margin: "0 auto" }} />
        </div>
      </div>
    </div>
  );
}

export default function MatchupDetail() {
  const { teamId = "", matchupId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useLeagueMatchup(teamId, matchupId);
  const platformsDisconnected = usePlatformsDisconnected(query.data?.meta);

  const back = (
    <Link to={matchupsPath(teamId)} className="back-link">
      <IconArrowL size={20} />
      All Matchups
    </Link>
  );

  if (platformsDisconnected) {
    return <EmptyState testId="league-matchup-empty" />;
  }

  if (query.isError) {
    return (
      <>
        {back}
        <ErrorCard
          error={query.error}
          fallbackMessage="Couldn't load this matchup."
          onRetry={() =>
            void queryClient.invalidateQueries({
              queryKey: ["league-matchups", teamId, "detail", matchupId],
            })
          }
          testId="league-matchup-error"
        />
      </>
    );
  }

  if (query.isLoading || !query.data) {
    return (
      <>
        {back}
        <DetailSkeleton />
      </>
    );
  }

  const { league, week, matchup, home, away, slots } = query.data.data;
  const lead = leader(matchup.home_score, matchup.away_score);
  const margin = Math.abs(matchup.home_score - matchup.away_score);
  const leaderName = lead === 1 ? home.team.name : lead === -1 ? away.team.name : null;
  const live = home.is_live || away.is_live;

  const side = (s: typeof home, score: number, className: string) => (
    <div className={`h2h-side ${className}`}>
      <div className="name">
        <TeamLogo team={s.team} size={28} />
        <span className="lm-side-name">{s.team.name.toUpperCase()}</span>
      </div>
      <div className="score-big">{score.toFixed(1)}</div>
      <div className="record">
        {recordText(s.team.record)}
        {s.position > 0 ? ` · ${ordinal(s.position)}` : ""}
      </div>
      <div className="record">{s.team.manager_name}</div>
    </div>
  );

  return (
    <>
      {back}
      <h1 className="large-title">Matchup</h1>
      <p className="large-subtitle">
        {league.name} · Week {week}
        {live ? " · Live" : matchup.is_complete ? " · Final" : ""}
      </p>

      <div className="card" style={{ padding: "32px 24px", marginBottom: 24 }}>
        <div className="h2h-top">
          {side(home, matchup.home_score, "me")}
          <div className="lm-ring">
            <ActivityRing
              size={160}
              stroke={14}
              gap={4}
              tracks={[
                {
                  value: matchup.home_proj > 0 ? matchup.home_score / matchup.home_proj : 0,
                  color: "var(--move)",
                },
                {
                  value: matchup.away_proj > 0 ? matchup.away_score / matchup.away_proj : 0,
                  color: "var(--stand)",
                },
              ]}
            />
            <div className="lm-ring-center">
              <div className="lm-ring-caption">{leaderName ? "Leads by" : "Tied"}</div>
              <div className="lm-ring-margin tnum">{margin.toFixed(1)}</div>
              {leaderName && <div className="lm-ring-leader">{leaderName}</div>}
            </div>
          </div>
          {side(away, matchup.away_score, "opp")}
        </div>

        <div style={{ borderTop: "0.5px solid var(--separator)", paddingTop: 24, marginTop: 8 }}>
          <div className="three-stat">
            <div>
              <div className="stat-label" style={{ color: "var(--text-secondary)" }}>
                Points
              </div>
              <div className="stat-val">
                {matchup.home_score.toFixed(1)}
                <span className="stat-unit">vs {matchup.away_score.toFixed(1)}</span>
              </div>
            </div>
            <div>
              <div className="stat-label" style={{ color: "var(--text-secondary)" }}>
                Projected
              </div>
              <div className="stat-val">
                {matchup.home_proj.toFixed(1)}
                <span className="stat-unit">vs {matchup.away_proj.toFixed(1)}</span>
              </div>
            </div>
            <div>
              <div className="stat-label" style={{ color: "var(--text-secondary)" }}>
                Yet to Play
              </div>
              <div className="stat-val">
                {home.remaining}
                <span className="stat-unit">vs {away.remaining}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {slots.length === 0 ? (
        <div className="card" style={{ padding: 24, textAlign: "center" }}>
          <div className="muted">Lineups weren't synced for week {week}.</div>
        </div>
      ) : (
        <H2HTable
          slots={slots}
          iAmHome={true}
          myTeamName={home.team.name}
          oppTeamName={away.team.name}
        />
      )}
    </>
  );
}
