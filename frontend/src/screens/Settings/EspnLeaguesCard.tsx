// "ESPN Leagues" settings-group — matches design/screen-settings.jsx's ESPN Leagues
// group. Lists every discovered ESPN league (GET /api/leagues, both platforms — this
// card filters to platform === "espn") with a per-league enable Switch; disabling a
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

function leagueSub(league: LeagueSetting): string {
  const scoring = SCORING_LABELS[league.scoring_type] ?? league.scoring_type;
  return `ESPN · ${league.season} · ${league.team_count} teams · ${scoring}`;
}

export function EspnLeaguesCard() {
  const leaguesQuery = useLeagues();
  const updateLeague = useUpdateLeague();

  const espnLeagues = (leaguesQuery.data ?? []).filter((league) => league.platform === "espn");

  return (
    <div className="settings-group">
      <h3>ESPN Leagues</h3>

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

      {leaguesQuery.data && espnLeagues.length === 0 && (
        <SettingsRow label="No ESPN leagues found" sub="Connect ESPN below to discover leagues." />
      )}

      {espnLeagues.map((league) => (
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
