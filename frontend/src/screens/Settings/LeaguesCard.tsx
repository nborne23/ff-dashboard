// "<Platform> Leagues" settings-group — matches design/screen-settings.jsx's ESPN Leagues
// group, rendered once per connected platform. Lists every discovered league for that
// platform (GET /api/leagues returns both) with a per-league enable Switch; disabling a
// league excludes its teams from GET /api/teams aggregation (backend/gridiron/
// services/fantasy_service.py:list_teams) without dropping the discovered rows.

import { getApiErrorMessage } from "../../api/client";
import type { LeagueSetting } from "../../api/leagues";
import { useLeagues, useUpdateLeague } from "../../api/leagues";
import { SettingsRow, SkeletonRow } from "./SettingsRow";
import { Switch } from "./Switch";

const SCORING_LABELS: Record<LeagueSetting["scoring_type"], string> = {
  standard: "standard scoring",
  half_ppr: "half PPR",
  ppr: "full PPR",
  custom: "custom scoring",
};

const PLATFORM_LABELS: Record<LeagueSetting["platform"], string> = {
  espn: "ESPN",
  yahoo: "Yahoo",
};

function leagueSub(league: LeagueSetting): string {
  const scoring = SCORING_LABELS[league.scoring_type] ?? league.scoring_type;
  const platform = PLATFORM_LABELS[league.platform] ?? league.platform;
  return `${platform} · ${league.season} · ${league.team_count} teams · ${scoring}`;
}

export function LeaguesCard({ platform }: { platform: LeagueSetting["platform"] }) {
  const leaguesQuery = useLeagues();
  const updateLeague = useUpdateLeague();

  const label = PLATFORM_LABELS[platform] ?? platform;
  const leagues = (leaguesQuery.data ?? []).filter((league) => league.platform === platform);

  return (
    <div className="settings-group">
      <h3>{label} Leagues</h3>

      {leaguesQuery.isLoading && (
        <>
          <SkeletonRow />
          <SkeletonRow />
        </>
      )}

      {leaguesQuery.isError && (
        <SettingsRow
          label="Couldn't load leagues"
          sub={getApiErrorMessage(leaguesQuery.error, "Check your connection and try again.")}
        />
      )}

      {leaguesQuery.data && leagues.length === 0 && (
        <SettingsRow
          label={`No ${label} leagues found`}
          sub={`Connect ${label} above to discover leagues.`}
        />
      )}

      {leagues.map((league) => (
        <SettingsRow
          key={league.id}
          label={league.name}
          sub={leagueSub(league)}
          right={
            <Switch
              on={league.is_enabled}
              onChange={(next) => updateLeague.mutate({ leagueId: league.id, isEnabled: next })}
              disabled={updateLeague.isPending}
              label={`${league.name} enabled`}
            />
          }
        />
      ))}
    </div>
  );
}
