// Six-matchup Game Day fixture, typed as the real `GameDayData` envelope payload.
//
// The change's tasks.md called for porting this from a `design/data-gameday.jsx`
// prototype; no such file exists in this repo (`design/` has no Game Day screen and
// git history has never carried one). It is therefore authored directly from
// specs/game-day/spec.md and design.md D1/D4, which specify the panel anatomy and the
// attention model in full. The `redzone` field the prototype reportedly carried is
// deliberately absent — red-zone cues are an explicit non-goal, deferred to
// `add-nfl-redzone`.
//
// The six entries deliberately span every state a panel has to render:
//
//   1. yahoo:t1  live, user leading, mixed pre/in/post slots
//   2. yahoo:t2  live, user trailing (the case a floored win prob would misreport)
//   3. espn:t3   complete — the settled-dim case (design D4), with every game_state
//                left null to prove the dim does NOT derive from game_state
//   4. espn:t4   effectively tied (< 0.05 margin) — the TIED chip case
//   5. yahoo:t5  user is the AWAY side — orientation must still put them on the left
//   6. espn:t6   nothing has kicked off: all `pre`, no live, zeros that are not
//                real zeros

import type {
  GameDayData,
  GameDayMatchup,
  GameState,
  MatchupSlot,
  Player,
  Slot,
} from "../../types/api";

const STARTERS: Slot[] = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX", "K", "DST"];

const POSITION_FOR_SLOT: Record<string, Player["position"]> = {
  QB: "QB",
  RB1: "RB",
  RB2: "RB",
  WR1: "WR",
  WR2: "WR",
  TE: "TE",
  FLEX: "WR",
  K: "K",
  DST: "DST",
};

function player(id: string, name: string, slot: Slot, nflTeam: string): Player {
  return {
    id,
    name,
    position: POSITION_FOR_SLOT[slot] ?? "WR",
    nfl_team: nflTeam,
    nfl_opponent: null,
    nfl_game_id: null,
    headshot_url: "",
    bye_week: null,
    injury_status: null,
  };
}

const NFL_TEAMS = ["KC", "BUF", "SF", "PHI", "DAL", "MIA", "BAL", "DET", "CIN"];

interface SlotSpec {
  homePts: number;
  awayPts: number;
  homeState: GameState | null;
  awayState: GameState | null;
  homeLive?: boolean;
  awayLive?: boolean;
}

function buildSlots(matchupId: string, specs: SlotSpec[]): MatchupSlot[] {
  return STARTERS.map((slot, i) => {
    const spec = specs[i];
    return {
      matchup_id: matchupId,
      slot,
      home_player: player(`${matchupId}:h${i}`, `${HOME_NAMES[i]}`, slot, NFL_TEAMS[i]),
      away_player: player(`${matchupId}:a${i}`, `${AWAY_NAMES[i]}`, slot, NFL_TEAMS[8 - i]),
      home_pts: spec.homePts,
      away_pts: spec.awayPts,
      home_state: spec.homeState,
      away_state: spec.awayState,
      home_is_live: spec.homeLive ?? false,
      away_is_live: spec.awayLive ?? false,
    };
  });
}

const HOME_NAMES = [
  "P. Mahomes",
  "B. Robinson",
  "K. Walker",
  "A. St. Brown",
  "D. Smith",
  "T. Kelce",
  "J. Jefferson",
  "H. Butker",
  "Ravens D/ST",
];

const AWAY_NAMES = [
  "J. Allen",
  "S. Barkley",
  "J. Gibbs",
  "C. Lamb",
  "T. Hill",
  "M. Andrews",
  "P. Nacua",
  "J. Tucker",
  "49ers D/ST",
];

/** All-`post`, nothing live — the settled shape. */
function settled(homePts: number[], awayPts: number[]): SlotSpec[] {
  return STARTERS.map((_, i) => ({
    homePts: homePts[i],
    awayPts: awayPts[i],
    homeState: "post" as GameState,
    awayState: "post" as GameState,
  }));
}

/** Every state left null — what discovery writes before classification (design D4). */
function unclassified(homePts: number[], awayPts: number[]): SlotSpec[] {
  return STARTERS.map((_, i) => ({
    homePts: homePts[i],
    awayPts: awayPts[i],
    homeState: null,
    awayState: null,
  }));
}

/** Nothing kicked off yet: all `pre`, all zero — zeros that are not real zeros. */
function untouched(): SlotSpec[] {
  return STARTERS.map(() => ({
    homePts: 0,
    awayPts: 0,
    homeState: "pre" as GameState,
    awayState: "pre" as GameState,
  }));
}

/** Mixed: the first `liveCount` slots are in-progress, the rest split post/pre. */
function inPlay(homePts: number[], awayPts: number[], liveCount: number): SlotSpec[] {
  return STARTERS.map((_, i) => {
    if (i < liveCount) {
      return {
        homePts: homePts[i],
        awayPts: awayPts[i],
        homeState: "in" as GameState,
        awayState: "in" as GameState,
        homeLive: true,
        awayLive: true,
      };
    }
    const done = i < liveCount + 3;
    return {
      homePts: done ? homePts[i] : 0,
      awayPts: done ? awayPts[i] : 0,
      homeState: (done ? "post" : "pre") as GameState,
      awayState: (done ? "post" : "pre") as GameState,
    };
  });
}

function sum(values: number[]): number {
  return Number(values.reduce((a, b) => a + b, 0).toFixed(1));
}

interface MatchupSpec {
  teamId: string;
  teamName: string;
  oppTeamId: string;
  oppTeamName: string;
  leagueId: string;
  leagueName: string;
  platform: GameDayMatchup["platform"];
  record: GameDayMatchup["record"];
  rank: GameDayMatchup["rank"];
  /** True when the user's team is the HOME side of the underlying matchup. */
  iAmHome: boolean;
  slots: SlotSpec[];
  proj: number;
  oppProj: number;
  remaining: GameDayMatchup["remaining"];
  isComplete: boolean;
}

function build(spec: MatchupSpec): GameDayMatchup {
  const matchupId = `${spec.platform}:m-${spec.teamId}`;
  const slots = buildSlots(matchupId, spec.slots);
  const homeTotal = sum(slots.map((s) => s.home_pts));
  const awayTotal = sum(slots.map((s) => s.away_pts));
  return {
    team_id: spec.teamId,
    team_name: spec.teamName,
    opp_team_id: spec.oppTeamId,
    opp_team_name: spec.oppTeamName,
    league_id: spec.leagueId,
    league_name: spec.leagueName,
    platform: spec.platform,
    record: spec.record,
    rank: spec.rank,
    // Panel-level score is already oriented onto the user's side; the slots keep the
    // raw home/away shape, so an away-side user reads the away totals here.
    score: spec.iAmHome ? homeTotal : awayTotal,
    opp_score: spec.iAmHome ? awayTotal : homeTotal,
    proj: spec.proj,
    opp_proj: spec.oppProj,
    remaining: spec.remaining,
    is_complete: spec.isComplete,
    i_am_home: spec.iAmHome,
    slots,
  };
}

const A = [19.8, 24.1, 11.4, 16.9, 8.2, 12.6, 21.3, 9.0, 7.0];
const B = [23.4, 18.2, 14.7, 9.8, 15.1, 6.4, 17.9, 11.0, 4.0];

export const GAME_DAY_FIXTURE: GameDayData = {
  matchups: [
    // 1 — live, user leading, mixed slot states.
    build({
      teamId: "yahoo:t1",
      teamName: "Highland Bombers",
      oppTeamId: "yahoo:t1-opp",
      oppTeamName: "Touchdown Club",
      leagueId: "yahoo:l1",
      leagueName: "Highland Bros Dynasty",
      platform: "yahoo",
      record: { w: 8, l: 3, t: 0 },
      rank: { current: 2, total: 12 },
      iAmHome: true,
      slots: inPlay(A, B, 3),
      proj: 113.2,
      oppProj: 98.4,
      remaining: { mine: 3, theirs: 5 },
      isComplete: false,
    }),
    // 2 — live, user TRAILING. A floored [50,99] win prob would misreport this as a
    // favorite, which is exactly why Game Day passes `clamp: false` (design D7).
    build({
      teamId: "yahoo:t2",
      teamName: "Sunday Scaries",
      oppTeamId: "yahoo:t2-opp",
      oppTeamName: "Gridiron Ghosts",
      leagueId: "yahoo:l2",
      leagueName: "Office League",
      platform: "yahoo",
      record: { w: 5, l: 6, t: 0 },
      rank: { current: 8, total: 10 },
      iAmHome: true,
      slots: inPlay(B, A, 2),
      proj: 92.7,
      oppProj: 121.5,
      remaining: { mine: 2, theirs: 4 },
      isComplete: false,
    }),
    // 3 — COMPLETE with every game_state null. The panel must still dim: the settled
    // cue reads `is_complete`, never a `game_state === "post"` comparison (design D4).
    build({
      teamId: "espn:t3",
      teamName: "Red Zone Rebels",
      oppTeamId: "espn:t3-opp",
      oppTeamName: "Play Action Heroes",
      leagueId: "espn:l3",
      leagueName: "Neighborhood Keeper",
      platform: "espn",
      record: { w: 9, l: 2, t: 0 },
      rank: { current: 1, total: 12 },
      iAmHome: true,
      slots: unclassified(A, B),
      proj: 130.3,
      oppProj: 120.5,
      remaining: { mine: 0, theirs: 0 },
      isComplete: true,
    }),
    // 4 — tied within 0.05, so the margin chip reads TIED and neither side trails.
    build({
      teamId: "espn:t4",
      teamName: "Fourth and Long",
      oppTeamId: "espn:t4-opp",
      oppTeamName: "Hail Mary Inc",
      leagueId: "espn:l4",
      leagueName: "Dynasty Devils",
      platform: "espn",
      record: { w: 6, l: 5, t: 0 },
      rank: { current: 5, total: 12 },
      iAmHome: true,
      slots: settled(A, A),
      proj: 118.0,
      oppProj: 118.0,
      remaining: { mine: 0, theirs: 0 },
      isComplete: true,
    }),
    // 5 — the user is the AWAY side. Their players must still render on the left of
    // every mirrored row, via `orientSlot(slot, iAmHome)`.
    build({
      teamId: "yahoo:t5",
      teamName: "Audible Nation",
      oppTeamId: "yahoo:t5-opp",
      oppTeamName: "Two Minute Drill",
      leagueId: "yahoo:l5",
      leagueName: "College Friends",
      platform: "yahoo",
      record: { w: 7, l: 4, t: 0 },
      rank: { current: 3, total: 12 },
      iAmHome: false,
      slots: inPlay(A, B, 1),
      proj: 104.6,
      oppProj: 109.1,
      remaining: { mine: 5, theirs: 4 },
      isComplete: false,
    }),
    // 6 — kickoff hasn't happened. Every zero is a `pre` zero, not a real one.
    build({
      teamId: "espn:t6",
      teamName: "Snap Judgement",
      oppTeamId: "espn:t6-opp",
      oppTeamName: "Backfield Bandits",
      leagueId: "espn:l6",
      leagueName: "Family League",
      platform: "espn",
      record: { w: 4, l: 7, t: 0 },
      rank: { current: 10, total: 12 },
      iAmHome: true,
      slots: untouched(),
      proj: 107.8,
      oppProj: 102.2,
      remaining: { mine: 9, theirs: 9 },
      isComplete: false,
    }),
  ],
};
