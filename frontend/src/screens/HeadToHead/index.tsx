// Screen 3: Head-to-Head — ported from design/screen-h2h.jsx. Unlike the
// prototype (which hardcodes "me = home"), useTeamH2H's matchup can have the
// route's teamId on either side of home/away, so every value is oriented via
// ./orientation.ts before it reaches a component. useTeamH2H doesn't return
// team names/records/league — those come from useTeam(teamId, week) for my
// side and useTeam(oppId, week) for the opponent's, once the matchup (and
// therefore oppId) is known.

import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { useTeam, useTeamH2H } from "../../api/teams";
import { Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { ordinal } from "../Dashboard/ordinal";
import { H2HRings } from "./H2HRings";
import { H2HTable } from "./H2HTable";
import { orientMatchup } from "./orientation";
import { computeProjectedFinal } from "./projectedFinal";
import { ProjectedFinalCard } from "./ProjectedFinalCard";
import { RemainingPlayersCard } from "./RemainingPlayersCard";

/** Matches the loaded layout's h2h-top / three-stat / h2h-table shapes (task 10.1). */
function H2HSkeleton() {
  return (
    <div data-testid="h2h-loading" aria-hidden="true">
      <Skeleton width="30%" height={34} radius={6} />
      <div style={{ height: 8 }} />
      <Skeleton width="40%" height={15} />
      <div className="spacer-md" />

      <div className="card" style={{ padding: "32px 24px", marginBottom: 24 }}>
        <div className="h2h-top">
          <div className="h2h-side me">
            <Skeleton width="70%" height={16} style={{ margin: "0 auto 8px" }} />
            <Skeleton width="60%" height={48} style={{ margin: "0 auto" }} />
          </div>
          <Skeleton width={96} height={96} circle />
          <div className="h2h-side opp">
            <Skeleton width="70%" height={16} style={{ margin: "0 auto 8px" }} />
            <Skeleton width="60%" height={48} style={{ margin: "0 auto" }} />
          </div>
        </div>
        <div style={{ borderTop: "0.5px solid var(--separator)", paddingTop: 24, marginTop: 8 }}>
          <div className="three-stat">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i}>
                <Skeleton width="50%" height={12} />
                <div style={{ height: 6 }} />
                <Skeleton width="70%" height={24} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} width="100%" height={44} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function HeadToHead() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();

  const teamQuery = useTeam(teamId, week);
  const h2hQuery = useTeamH2H(teamId, week);
  const platformsDisconnected = usePlatformsDisconnected(
    teamQuery.data?.meta ?? h2hQuery.data?.meta,
  );

  const matchup = h2hQuery.data?.data.matchup;
  const oriented = matchup ? orientMatchup(matchup, teamId) : null;
  const oppTeamId = oriented?.oppTeamId ?? "";
  const oppTeamQuery = useTeam(oppTeamId, week);

  const isError = teamQuery.isError || h2hQuery.isError || oppTeamQuery.isError;
  const isLoading =
    teamQuery.isLoading || h2hQuery.isLoading || (Boolean(oppTeamId) && oppTeamQuery.isLoading);

  const retry = () => void queryClient.invalidateQueries({ queryKey: ["team", teamId] });

  if (platformsDisconnected) {
    return <EmptyState testId="h2h-empty" />;
  }

  if (isError) {
    return (
      <ErrorCard
        error={teamQuery.error ?? h2hQuery.error ?? oppTeamQuery.error}
        fallbackMessage="Couldn't load this matchup."
        onRetry={retry}
        testId="h2h-error"
      />
    );
  }

  if (isLoading || !teamQuery.data || !h2hQuery.data || !oriented || !oppTeamQuery.data) {
    return <H2HSkeleton />;
  }

  const myTeam = teamQuery.data.data.team;
  const oppTeam = oppTeamQuery.data.data.team;
  const league = teamQuery.data.data.league;
  const { slots, remaining } = h2hQuery.data.data;

  const projFinal = computeProjectedFinal({
    myProj: oriented.myProj,
    oppProj: oriented.oppProj,
    myRemaining: remaining.mine,
    oppRemaining: remaining.theirs,
  });

  return (
    <>
      <h1 className="large-title">Head-to-Head</h1>
      <p className="large-subtitle">
        {league.name} · Week {week}
      </p>

      <div className="card" style={{ padding: "32px 24px", marginBottom: 24 }}>
        <div className="h2h-top">
          <div className="h2h-side me">
            <div className="name">{myTeam.name.toUpperCase()}</div>
            <div className="score-big">{oriented.myScore.toFixed(1)}</div>
            <div className="record">
              {myTeam.record.w}–{myTeam.record.l} · {ordinal(myTeam.rank.current)} place
            </div>
          </div>
          <H2HRings
            myScore={oriented.myScore}
            myProj={oriented.myProj}
            oppScore={oriented.oppScore}
            oppProj={oriented.oppProj}
            gamesLeft={remaining.mine}
          />
          <div className="h2h-side opp">
            <div className="name">{oppTeam.name.toUpperCase()}</div>
            <div className="score-big">{oriented.oppScore.toFixed(1)}</div>
            <div className="record">
              {oppTeam.record.w}–{oppTeam.record.l} · {ordinal(oppTeam.rank.current)} place
            </div>
          </div>
        </div>

        <div style={{ borderTop: "0.5px solid var(--separator)", paddingTop: 24, marginTop: 8 }}>
          <div className="three-stat">
            <div>
              <div className="stat-label" style={{ color: "var(--move)" }}>
                Points
              </div>
              <div className="stat-val">
                {oriented.myScore.toFixed(1)}
                <span className="stat-unit">vs {oriented.oppScore.toFixed(1)}</span>
              </div>
            </div>
            <div>
              <div className="stat-label" style={{ color: "var(--exercise)" }}>
                Projected
              </div>
              <div className="stat-val">
                {oriented.myProj.toFixed(1)}
                <span className="stat-unit">vs {oriented.oppProj.toFixed(1)}</span>
              </div>
            </div>
            <div>
              <div className="stat-label" style={{ color: "var(--stand)" }}>
                Win Prob.
              </div>
              <div className="stat-val">
                {projFinal.confidencePct}
                <span className="stat-unit">%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <H2HTable
        slots={slots}
        iAmHome={oriented.iAmHome}
        myTeamName={myTeam.name}
        oppTeamName={oppTeam.name}
      />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <RemainingPlayersCard mine={remaining.mine} theirs={remaining.theirs} />
        <ProjectedFinalCard
          myProj={oriented.myProj}
          oppProj={oriented.oppProj}
          myRemaining={remaining.mine}
          oppRemaining={remaining.theirs}
        />
      </div>
    </>
  );
}
