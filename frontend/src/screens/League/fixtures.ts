// Standings fixture, typed as the real `LeagueStandingsData` payload.
//
// Deliberately spans the cases the screen and the ordering have to get right:
//
//   1. A team with an ESPN VECTOR logo (stock SVG) — logo_url present.
//   2. A team with a CUSTOM_UPLOAD logo — logo_url present, indistinguishable from
//      the above to the frontend, which is the point: the format difference is the
//      backend's problem, and the client only ever sees a local URL.
//   3. A team with NO logo at all — logo_url null, which must render a placeholder
//      WITHOUT issuing an image request.
//   4. The user's own team, which the table highlights.
//   5. TWO TEAMS WITH IDENTICAL RECORDS AND ZERO SEEDS. This is the important one:
//      in the preseason every team is 0-0-0 with 0.0 points and ESPN reports seed 0
//      for whole leagues, so without a deterministic final tiebreak the rendered
//      order is whatever the query returned and can differ between two loads. These
//      two rows are what makes that visible in a test.

import type { LeagueStandingsData, League, Team } from "../../types/api";

const LEAGUE_ID = "espn:705139273";

export const LEAGUE_FIXTURE: League = {
  id: LEAGUE_ID,
  platform: "espn",
  platform_id: "705139273",
  name: "THE LEAGUE",
  season: 2026,
  team_count: 10,
  scoring_type: "half_ppr",
  current_week: 1,
};

function team(
  id: string,
  name: string,
  manager: string,
  w: number,
  l: number,
  seed: number,
  pf: number,
  pa: number,
  overrides: Partial<Team> = {},
): Team {
  return {
    id: `espn:l-705139273-t-${id}`,
    league_id: LEAGUE_ID,
    name,
    manager_name: manager,
    record: { w, l, t: 0 },
    rank: { current: seed, total: 10 },
    points_for: pf,
    points_against: pa,
    is_user_team: false,
    current_score: 0,
    current_opp_score: 0,
    current_opponent_name: "",
    is_live: false,
    spark_last_6: [],
    accent_color: "#FF2D55",
    logo_url: `/api/team-logos/espn/${id}`,
    ...overrides,
  };
}

export const STANDINGS_FIXTURE: LeagueStandingsData = {
  league: LEAGUE_FIXTURE,
  rows: [
    // 1-2. Real seeds, real records — ESPN's order is authoritative here.
    { team: team("1", "Fresh Meat", "Dana", 3, 0, 1, 402.5, 331.2), division_id: 0, position: 1 },
    {
      team: team("2", "Paint'n Nails", "Rory", 2, 1, 2, 388.1, 350.9),
      division_id: 0,
      position: 2,
    },
    // 3. The user's own team — highlighted.
    {
      team: team("4", "Hingle McCringleberry", "Nick", 2, 1, 3, 371.0, 344.4, {
        is_user_team: true,
      }),
      division_id: 0,
      position: 3,
    },
    // 4. No logo at all — placeholder, and no image request.
    {
      team: team("5", "Baby Got Dak", "Sam", 1, 2, 4, 340.8, 366.1, { logo_url: null }),
      division_id: 0,
      position: 4,
    },
    // 5-6. The tie case: identical 0-0-0 records, zero points, zero seeds. Only the
    // stable id tiebreak separates these, and it must separate them the same way twice.
    { team: team("8", "Garbage", "Alex", 0, 0, 0, 0, 0), division_id: 0, position: 5 },
    { team: team("9", "Scarecrow Boat", "Jordan", 0, 0, 0, 0, 0), division_id: 0, position: 6 },
  ],
};
