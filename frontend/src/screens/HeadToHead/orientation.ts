// The design prototype (design/screen-h2h.jsx) hardcodes "me = home team".
// The real Matchup entity (design.md D12) can have the route's teamId on
// either side, so every H2H view needs to orient home/away onto mine/theirs
// once, from a single source of truth, rather than re-deriving the ternary
// in every component.

import type { Matchup, MatchupSlot, Player } from "../../types/api";

export interface OrientedMatchup {
  iAmHome: boolean;
  myTeamId: string;
  oppTeamId: string;
  myScore: number;
  oppScore: number;
  myProj: number;
  oppProj: number;
}

export function orientMatchup(matchup: Matchup, teamId: string): OrientedMatchup {
  const iAmHome = matchup.home_team_id === teamId;
  return {
    iAmHome,
    myTeamId: iAmHome ? matchup.home_team_id : matchup.away_team_id,
    oppTeamId: iAmHome ? matchup.away_team_id : matchup.home_team_id,
    myScore: iAmHome ? matchup.home_score : matchup.away_score,
    oppScore: iAmHome ? matchup.away_score : matchup.home_score,
    myProj: iAmHome ? matchup.home_proj : matchup.away_proj,
    oppProj: iAmHome ? matchup.away_proj : matchup.home_proj,
  };
}

export interface OrientedSlot {
  myPlayer: Player;
  oppPlayer: Player;
  myPts: number;
  oppPts: number;
}

export function orientSlot(slot: MatchupSlot, iAmHome: boolean): OrientedSlot {
  return {
    myPlayer: iAmHome ? slot.home_player : slot.away_player,
    oppPlayer: iAmHome ? slot.away_player : slot.home_player,
    myPts: iAmHome ? slot.home_pts : slot.away_pts,
    oppPts: iAmHome ? slot.away_pts : slot.home_pts,
  };
}
