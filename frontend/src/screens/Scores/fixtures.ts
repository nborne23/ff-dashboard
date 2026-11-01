// Test fixtures for the Scores screens: a Thursday final, a Sunday game in progress and a
// Sunday game not yet kicked off — the three states a scoreboard has to draw.

import type { FantasyPlayer, GameDetail, ScoreGame, ScoresWeek } from "../../api/scores";

const team = (
  abbr: string,
  name: string,
  record: string,
  score: number | null,
  extra: Partial<ScoreGame["home"]> = {},
): ScoreGame["home"] => ({
  abbr,
  name,
  location: "",
  record,
  score,
  logo: null,
  color: "0b2265",
  linescores: [],
  winner: false,
  ...extra,
});

export const FINAL_GAME: ScoreGame = {
  game_id: "401",
  kickoff_at: "2026-10-23T00:15:00Z",
  state: "post",
  status_text: "Final",
  period: null,
  clock: null,
  broadcast: "Prime Video",
  possession: null,
  down_distance: null,
  away: team("NE", "Patriots", "4-3", 24, { linescores: [0, 14, 7, 3] }),
  home: team("CHI", "Bears", "5-2", 30, { linescores: [10, 10, 7, 3], winner: true }),
  top_performer: {
    category: "passing",
    name: "Drake Maye",
    short_name: "D. Maye",
    position: "QB",
    team: "NE",
    headshot_url: "/api/headshots/espn/4431452.png",
    stat_line: "24/31, 321 YDS, 2 TD",
  },
};

export const LIVE_GAME: ScoreGame = {
  game_id: "402",
  kickoff_at: "2026-10-25T17:00:00Z",
  state: "in",
  status_text: "Q3 4:12",
  period: 3,
  clock: "4:12",
  broadcast: "CBS",
  possession: "CIN",
  down_distance: "3rd & 4",
  away: team("BAL", "Ravens", "4-3", 13, { linescores: [3, 7, 3] }),
  home: team("CIN", "Bengals", "4-2", 35, { linescores: [7, 21, 7] }),
  top_performer: null,
};

export const PRE_GAME: ScoreGame = {
  game_id: "403",
  kickoff_at: "2026-10-25T20:25:00Z",
  state: "pre",
  status_text: "10/25 - 4:25 PM EDT",
  period: null,
  clock: null,
  broadcast: "FOX",
  possession: null,
  down_distance: null,
  away: team("PIT", "Steelers", "5-2", null),
  home: team("NO", "Saints", "2-5", null),
  top_performer: null,
};

export const WEEK_FIXTURE: ScoresWeek = {
  season: 2026,
  week: 7,
  current_week: 8,
  weeks: Array.from({ length: 18 }, (_, i) => i + 1),
  byes: ["BUF", "BAL"],
  fetched_at: "2026-10-25T18:00:00Z",
  games: [FINAL_GAME, LIVE_GAME, PRE_GAME],
};

const fp = (overrides: Partial<FantasyPlayer>): FantasyPlayer => ({
  sleeper_id: "x",
  name: "Somebody",
  short_name: "S. Body",
  position: "QB",
  team: "NE",
  points: 0,
  projection: null,
  source: "estimated",
  stats: {},
  stat_line: [],
  player: null,
  fantasy_team: null,
  is_mine: false,
  ...overrides,
});

export const MAYE = fp({
  sleeper_id: "11564",
  name: "Drake Maye",
  short_name: "D. Maye",
  position: "QB",
  team: "NE",
  points: 28.44,
  projection: 21.7,
  source: "league",
  stats: {
    pass_cmp: 24,
    pass_att: 31,
    pass_yd: 321,
    pass_td: 2,
    pass_int: 1,
    rush_att: 4,
    rush_yd: 26,
    rush_td: 1,
  },
  stat_line: [
    { value: "24/31", label: "CMP" },
    { value: "321", label: "YD" },
    { value: "2", label: "TD" },
  ],
  player: {
    id: "espn:p-4431452",
    name: "Drake Maye",
    position: "QB",
    nfl_team: "NE",
    nfl_opponent: "CHI",
    nfl_game_id: null,
    headshot_url: "/api/headshots/espn/4431452.png",
    bye_week: 14,
    injury_status: null,
  },
  fantasy_team: "Scranton Stranglers",
  is_mine: true,
});

export const WILLIAMS = fp({
  sleeper_id: "12345",
  name: "Caleb Williams",
  short_name: "C. Williams",
  position: "QB",
  team: "CHI",
  points: 22.12,
  projection: 18.66,
  stats: { pass_cmp: 22, pass_att: 33, pass_yd: 308, pass_td: 2, rush_att: 5, rush_yd: 18 },
  stat_line: [
    { value: "22/33", label: "CMP" },
    { value: "308", label: "YD" },
  ],
});

export const STEVENSON = fp({
  sleeper_id: "7611",
  name: "Rhamondre Stevenson",
  short_name: "R. Stevenson",
  position: "RB",
  team: "NE",
  points: 20,
  projection: 9.98,
  stats: { rush_att: 6, rush_yd: 22, rec: 5, rec_tgt: 5, rec_yd: 93, rec_td: 1 },
  stat_line: [{ value: "6", label: "CAR" }],
  fantasy_team: "Da Bears",
});

export const DETAIL_FIXTURE: GameDetail = {
  season: 2026,
  week: 7,
  game: FINAL_GAME,
  leagues: [
    {
      league_id: "espn:1",
      name: "The League",
      platform: "espn",
      scoring_type: "ppr",
      team_id: "espn:l-1-t-1",
    },
    {
      league_id: "yahoo:2",
      name: "GAI IT Battle Royale",
      platform: "yahoo",
      scoring_type: "custom",
      team_id: "yahoo:2.t.1",
    },
  ],
  league_id: "espn:1",
  points_format: "ppr",
  points_format_fallback: false,
  groups: [
    { position: "QB", away: [MAYE], home: [WILLIAMS] },
    { position: "RB", away: [STEVENSON], home: [] },
  ],
  stats_as_of: "2026-10-23T04:00:00Z",
};
