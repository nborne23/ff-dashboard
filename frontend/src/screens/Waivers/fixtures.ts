// Waiver-candidate fixture, typed as the real `WaiversData` envelope payload.
//
// Authored from specs/fantasy-data-model/spec.md ("Waiver candidates for a team")
// and design.md D2/D7. It unblocks the screen lane before the endpoint exists, and
// it deliberately spans the cases the UI is required to get right:
//
//   1. A strong upgrade — positive delta, the ordinary case.
//   2. A marginal add — small positive delta.
//   3. A DOWNGRADE — negative delta. This one matters: computed against weekly
//      `roster_slots.proj_points` instead of a season projection, every candidate
//      comes out hugely positive, so a fixture where a real player ranks below the
//      user's starter is what makes that bug visible in the UI layer too.
//   4. Null projection — ESPN published none. Must render as an em dash, NOT 0.0.
//   5. Projection of exactly 0.0 — a GENUINE value (Tommy DeVito projects 0.0 in
//      the live data). Must render as "0.0", not as an em dash. Cases 4 and 5 exist
//      as a pair; rendering them identically is the bug.
//   6. Null delta with a present projection — the user starts nobody at an eligible
//      slot, so there is nothing to compare against.

// `eligible_slots` uses ESPN's UNNUMBERED slot names, verified against a live pull:
// the 1030-player pool yields exactly these lineupSlotIds, all covered by
// LINEUP_SLOT_MAP — QB, RB, RB/WR, WR, WR/TE, TE, OP, CB, DB, DP, DST, K, BN, IR,
// FLEX, REC_FLEX. Numbered internal Slots (RB1, RB2) cannot appear here: that
// numbering comes from per-roster counters, and a pool player is on no roster.

import type { Player, WaiverCandidate, WaiversData } from "../../types/api";

const LEAGUE_ID = "espn:705139273";

function player(
  id: string,
  name: string,
  position: Player["position"],
  nflTeam: string,
  injury: Player["injury_status"] = null,
): Player {
  return {
    id: `espn:p-${id}`,
    name,
    position,
    nfl_team: nflTeam,
    nfl_opponent: null,
    nfl_game_id: null,
    headshot_url: `/api/headshots/espn/${id}.png`,
    bye_week: 9,
    injury_status: injury,
  };
}

function candidate(
  p: Player,
  seasonProj: number | null,
  delta: number | null,
  eligible: string[],
  percentOwned: number,
  /** Rotowire's independent season projection. Defaults to `null` — the "no second
   *  opinion on file" case, which is what every pre-existing fixture row means. */
  extSeasonProj: number | null = null,
): WaiverCandidate {
  return {
    league_id: LEAGUE_ID,
    player: p,
    status: percentOwned > 40 ? "WAIVERS" : "FREEAGENT",
    on_team_id: null,
    percent_owned: percentOwned,
    percent_started: Math.max(0, percentOwned - 18.4),
    season_proj_points: seasonProj,
    delta_vs_worst_starter: delta,
    eligible_slots: eligible,
    ext_season_proj_points: extSeasonProj,
  };
}

export const WAIVERS_FIXTURE: WaiversData = {
  team_id: "espn:l-705139273-t-4",
  league_id: LEAGUE_ID,
  week: 1,
  candidates: [
    // 1. Clear upgrade.
    candidate(
      player("3116385", "Tyler Boyd", "WR", "CIN"),
      168.4,
      42.7,
      ["WR", "RB/WR", "WR/TE", "FLEX", "REC_FLEX"],
      61.2,
    ),
    // 2. Marginal add.
    candidate(
      player("4262921", "Rachaad White", "RB", "TB"),
      131.9,
      6.3,
      ["RB", "RB/WR", "FLEX"],
      48.9,
    ),
    // 3. Downgrade — negative delta. Guards the weekly-vs-season unit mismatch.
    candidate(
      player("4429013", "Jaleel McLaughlin", "RB", "DEN"),
      88.2,
      -37.5,
      ["RB", "RB/WR", "FLEX"],
      22.4,
    ),
    // 4. No projection published — em dash, never 0.0.
    candidate(
      player("4685702", "Malik Washington", "WR", "MIA"),
      null,
      null,
      ["WR", "RB/WR", "WR/TE", "FLEX", "REC_FLEX"],
      9.8,
    ),
    // 5. A GENUINE 0.0 projection — renders as "0.0". Pairs with case 4.
    candidate(player("3915511", "Tommy DeVito", "QB", "NYG"), 0.0, -204.6, ["QB", "OP"], 1.1),
    // 6. Projection present, but no eligible starter to compare against.
    candidate(player("4361050", "Blake Grupe", "K", "NO"), 121.5, null, ["K"], 33.7),
  ],
};
