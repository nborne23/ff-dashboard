// Screen 8: League — every team in one league, as standings.
//
// Team-scoped like Matchups, Season, and Waivers: the user is in several leagues and
// the league is derived from the selected team, so there is no separate league picker.
//
// Ordering comes from the backend and follows ESPN's own playoff seed, so the page
// agrees with what ESPN's site shows. Where ESPN reports no seed — it returns 0 for
// every team in some leagues — the backend falls back to record and then to a stable
// id, which is why the order does not shuffle between reloads in the preseason.

import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useLeagueStandings, useTeam } from "../../api/teams";
import { IconChevR, IconMatchups } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { LeagueSkeleton } from "./LeagueSkeleton";
import { matchupsPath } from "../LeagueMatchups/format";
import { StandingsTable } from "./StandingsTable";
import "../../styles/league-matchups.css";

export default function League() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();

  const teamQuery = useTeam(teamId, week);
  const standingsQuery = useLeagueStandings(teamId);
  const platformsDisconnected = usePlatformsDisconnected(teamQuery.data?.meta);

  const retry = () => void queryClient.invalidateQueries({ queryKey: ["league", teamId] });

  if (platformsDisconnected) {
    return <EmptyState testId="league-empty" />;
  }

  if (standingsQuery.isError || teamQuery.isError) {
    return (
      <ErrorCard
        error={standingsQuery.error ?? teamQuery.error}
        fallbackMessage="Couldn't load the standings."
        onRetry={retry}
        testId="league-error"
      />
    );
  }

  if (standingsQuery.isLoading || !standingsQuery.data) {
    return <LeagueSkeleton />;
  }

  const { league, rows } = standingsQuery.data.data;

  return (
    <>
      <h1 className="large-title">{league.name}</h1>
      <p className="large-subtitle">
        {league.season} · {rows.length} teams · {league.scoring_type.replace("_", " ")}
      </p>

      <Link to={matchupsPath(teamId)} className="card lm-entry">
        <IconMatchups size={22} />
        <span className="lm-entry-text">
          <span className="lm-entry-title">All Matchups</span>
          <span className="lm-entry-sub"> · Week {week} across the league</span>
        </span>
        <span className="row-chevron" aria-hidden="true">
          <IconChevR size={16} />
        </span>
      </Link>

      <StandingsTable rows={rows} viewingTeamId={teamId} />
    </>
  );
}
