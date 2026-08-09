// Screen 4: Season Overview — ported from design/screen-season.jsx. Data
// comes from useTeam(teamId, week) (name/league) and useTeamSeason(teamId)
// (weeks + highlights). highlights.season_high / most_started can be null
// (backend/gridiron/services/fantasy_service.py's Highlights model — see
// task 6.1 / src/api/teams.ts's TeamSeasonData), so each HighlightCard falls
// back to a placeholder rather than assuming they're always present.

import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { useTeam, useTeamSeason } from "../../api/teams";
import { IconBolt, IconFlame, IconStar, Skeleton } from "../../components/primitives";
import { EmptyState } from "../../components/shared/EmptyState";
import { ErrorCard } from "../../components/shared/ErrorCard";
import { usePlatformsDisconnected } from "../../hooks/usePlatformsDisconnected";
import { useUiStore } from "../../stores/ui";
import { HighlightCard } from "./HighlightCard";
import { RecordDonut } from "./RecordDonut";
import { SeasonChart } from "./SeasonChart";
import { WeekHistory } from "./WeekHistory";

/** Matches the loaded layout's chart card + 3-column highlights/donut/history row
 * (task 10.1). */
function SeasonSkeleton() {
  return (
    <div data-testid="season-loading" aria-hidden="true">
      <Skeleton width="20%" height={34} radius={6} />
      <div style={{ height: 8 }} />
      <Skeleton width="35%" height={15} />
      <div className="spacer-md" />

      <div className="card" style={{ marginBottom: 24, padding: "20px 16px 12px" }}>
        <Skeleton width="30%" height={13} />
        <div style={{ height: 16 }} />
        <Skeleton width="100%" height={180} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "4fr 4fr 4fr", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card" style={{ padding: 14, minHeight: 68 }}>
              <Skeleton width="50%" height={12} />
              <div style={{ height: 8 }} />
              <Skeleton width="70%" height={20} />
            </div>
          ))}
        </div>
        <div>
          <Skeleton width="40%" height={13} />
          <div style={{ height: 12 }} />
          <Skeleton width="100%" height={160} />
        </div>
        <div>
          <Skeleton width="40%" height={13} />
          <div style={{ height: 12 }} />
          <Skeleton width="100%" height={160} />
        </div>
      </div>
    </div>
  );
}

export default function Season() {
  const { teamId = "" } = useParams();
  const week = useUiStore((s) => s.week);
  const queryClient = useQueryClient();

  const teamQuery = useTeam(teamId, week);
  const seasonQuery = useTeamSeason(teamId);
  const platformsDisconnected = usePlatformsDisconnected(teamQuery.data?.meta);

  const isError = teamQuery.isError || seasonQuery.isError;
  const isLoading = teamQuery.isLoading || seasonQuery.isLoading;

  const retry = () => void queryClient.invalidateQueries({ queryKey: ["team", teamId] });

  if (platformsDisconnected) {
    return <EmptyState testId="season-empty" />;
  }

  if (isError) {
    return (
      <ErrorCard
        error={teamQuery.error ?? seasonQuery.error}
        fallbackMessage="Couldn't load season data."
        onRetry={retry}
        testId="season-error"
      />
    );
  }

  if (isLoading || !teamQuery.data || !seasonQuery.data) {
    return <SeasonSkeleton />;
  }

  const team = teamQuery.data.data.team;
  const league = teamQuery.data.data.league;
  const { weeks, highlights } = seasonQuery.data.data;

  const winStreakLabel = `${highlights.win_streak} week${highlights.win_streak === 1 ? "" : "s"}`;

  return (
    <>
      <h1 className="large-title">Season</h1>
      <p className="large-subtitle">
        {team.name} · {league.season}
      </p>

      <div className="card" style={{ marginBottom: 24, padding: "20px 16px 12px" }}>
        <div className="card-header" style={{ padding: "0 8px" }}>
          <span className="cat-dot" style={{ background: "var(--move)" }}>
            <IconBolt size={9} />
          </span>
          <span className="cat-label" style={{ color: "var(--move)" }}>
            Weekly Scores
          </span>
          <span className="ts">All weeks · cyan = win, pink = loss</span>
        </div>
        <SeasonChart weeks={weeks} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "4fr 4fr 4fr", gap: 24 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="section-label" style={{ marginBottom: 0 }}>
            Highlights
          </div>
          <HighlightCard
            accent="var(--live)"
            icon={<IconFlame size={9} />}
            label="Win Streak"
            value={winStreakLabel}
            sub={highlights.win_streak > 0 ? "Longest win streak this season" : "No win streak yet"}
          />
          <HighlightCard
            accent="var(--move)"
            icon={<IconBolt size={9} />}
            label="Season High"
            value={highlights.season_high ? `${highlights.season_high.score.toFixed(1)} pts` : "—"}
            sub={
              highlights.season_high
                ? `Week ${highlights.season_high.week} vs ${highlights.season_high.opp_team_name}`
                : "No games played yet"
            }
          />
          <HighlightCard
            accent="var(--exercise)"
            icon={<IconStar size={9} />}
            label="Most Started"
            value={highlights.most_started ? highlights.most_started.player.name : "—"}
            sub={
              highlights.most_started
                ? `${highlights.most_started.starts} starts · ${highlights.most_started.avg_points.toFixed(1)} avg pts`
                : "No data yet"
            }
          />
        </div>
        <div>
          <div className="section-label">Record</div>
          <RecordDonut weeks={weeks} />
        </div>
        <div>
          <div className="section-label">History</div>
          <WeekHistory weeks={weeks} />
        </div>
      </div>
    </>
  );
}
