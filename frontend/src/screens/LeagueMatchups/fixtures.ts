// All Matchups fixtures, typed as the real API payloads. One week of a four-team league:
// the user's matchup (live, user trailing), and another pairing that is final and was
// won by the away side — so the cards' leader emphasis is exercised on both sides.

import type {
  LeagueMatchupDetailData,
  LeagueMatchupEntry,
  LeagueMatchupSide,
  LeagueMatchupsData,
} from "../../api/leagueMatchups";
import type { League, Matchup, Player, Team } from "../../types/api";

const LEAGUE_ID = "yahoo:461.l.123456";

export const MATCHUPS_LEAGUE: League = {
  id: LEAGUE_ID,
  platform: "yahoo",
  platform_id: "461.l.123456",
  name: "GAI IT Battle Royale",
  season: 2026,
  team_count: 4,
  scoring_type: "ppr",
  current_week: 8,
};

function team(n: number, name: string, manager: string, w: number, user = false): Team {
  return {
    id: `${LEAGUE_ID}.t.${n}`,
    league_id: LEAGUE_ID,
    name,
    manager_name: manager,
    record: { w, l: 7 - w, t: 0 },
    rank: { current: 0, total: 4 },
    points_for: 0,
    points_against: 0,
    is_user_team: user,
    current_score: 0,
    current_opp_score: 0,
    current_opponent_name: "",
    is_live: false,
    spark_last_6: [],
    accent_color: "#FF2D55",
    logo_url: null,
  };
}

function side(t: Team, position: number, remaining = 0, is_live = false): LeagueMatchupSide {
  return { team: t, position, remaining, is_live };
}

export const USER_TEAM = team(8, "Scranton Stranglers", "Nick", 3, true);
const PRACTICE_SQUAD = team(9, "The Practice Squad", "Shannon", 2);
const HELLFIRE = team(7, "HellFire Club", "Tony", 3);
const TRASH_PANDAS = team(3, "Trash Pandas", "Matt", 6);

function matchup(
  id: string,
  home: Team,
  away: Team,
  hs: number,
  as_: number,
  complete: boolean,
): Matchup {
  return {
    id,
    league_id: LEAGUE_ID,
    week: 8,
    home_team_id: home.id,
    away_team_id: away.id,
    home_score: hs,
    away_score: as_,
    home_proj: hs + 10,
    away_proj: as_ + 12,
    is_complete: complete,
  };
}

export const USER_ENTRY: LeagueMatchupEntry = {
  matchup: matchup("yahoo:461.l.123456.mu.8", USER_TEAM, PRACTICE_SQUAD, 84.7, 85.96, false),
  home: side(USER_TEAM, 8, 3, true),
  away: side(PRACTICE_SQUAD, 9, 1, false),
  is_user_matchup: true,
};

export const OTHER_ENTRY: LeagueMatchupEntry = {
  matchup: matchup("yahoo:461.l.123456.mu.8.7v3", HELLFIRE, TRASH_PANDAS, 103.28, 114.78, true),
  home: side(HELLFIRE, 7),
  away: side(TRASH_PANDAS, 3),
  is_user_matchup: false,
};

export const MATCHUPS_FIXTURE: LeagueMatchupsData = {
  league: MATCHUPS_LEAGUE,
  week: 8,
  matchups: [USER_ENTRY, OTHER_ENTRY],
};

function player(id: string, name: string, position: Player["position"]): Player {
  return {
    id,
    name,
    position,
    nfl_team: "KC",
    nfl_opponent: null,
    nfl_game_id: null,
    headshot_url: "",
    bye_week: null,
    injury_status: null,
  };
}

export const DETAIL_FIXTURE: LeagueMatchupDetailData = {
  ...OTHER_ENTRY,
  league: MATCHUPS_LEAGUE,
  week: 8,
  slots: [
    {
      matchup_id: OTHER_ENTRY.matchup.id,
      slot: "QB",
      home_player: player("yahoo:p.1", "Drake Maye", "QB"),
      away_player: player("yahoo:p.2", "Caleb Williams", "QB"),
      home_pts: 28.44,
      away_pts: 22.12,
      home_state: "post",
      away_state: "post",
      home_is_live: false,
      away_is_live: false,
    },
  ],
};
