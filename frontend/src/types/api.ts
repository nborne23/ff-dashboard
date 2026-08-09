// Normalized data-model types shared between the frontend and the FastAPI
// backend. These are a 1:1 port of design.md's "D12. Data model TypeScript
// interfaces" — see
// openspec/changes/scaffold-gridiron/design.md and
// backend/gridiron/schemas/*.py (source of truth for exact field names;
// read-only reference, never edited from here).
//
// Frontend code should only ever consume these normalized types, never raw
// Yahoo/ESPN payloads (specs/fantasy-data-model/spec.md, "Normalized
// internal entities").

export type Platform = "yahoo" | "espn";
export type LiveState = "live" | "game_day" | "off_day";

/** The internal roster/matchup slot vocabulary (design.md D12). */
export type Slot = "QB" | "RB1" | "RB2" | "WR1" | "WR2" | "TE" | "FLEX" | "K" | "DST" | "BN" | "IR";

export interface PlatformStatus {
  ok: boolean;
  error?: string;
}

export interface Meta {
  live_state: LiveState;
  /** ISO timestamp of the cached row. */
  as_of: string;
  /** ISO timestamp of the scheduler's next planned run. */
  next_refresh_at: string;
  platforms: Record<Platform, PlatformStatus>;
}

/** The envelope every read endpoint returns. */
export interface Envelope<T> {
  data: T;
  meta: Meta;
}

export interface Connection {
  platform: Platform;
  is_connected: boolean;
  display_name: string | null;
  last_verified_at: string | null;
  error?: { code: string; message: string };
}

export type ScoringType = "standard" | "half_ppr" | "ppr" | "custom";

export interface League {
  /** "yahoo:nfl.l.123456" */
  id: string;
  platform: Platform;
  platform_id: string;
  name: string;
  season: number;
  team_count: number;
  scoring_type: ScoringType;
  current_week: number;
}

export interface Team {
  /** "yahoo:nfl.l.123456.t.4" — stable, `{platform}:{platform_id}`. */
  id: string;
  league_id: string;
  name: string;
  manager_name: string;
  record: { w: number; l: number; t: number };
  rank: { current: number; total: number };
  points_for: number;
  points_against: number;
  is_user_team: boolean;
  current_score: number;
  current_opp_score: number;
  current_opponent_name: string;
  is_live: boolean;
  spark_last_6: number[];
  accent_color: string;
}

export type Position = "QB" | "RB" | "WR" | "TE" | "K" | "DST";
export type InjuryStatus = "ACTIVE" | "Q" | "D" | "O" | "IR" | "PUP";

export interface Player {
  id: string;
  name: string;
  position: Position;
  nfl_team: string;
  nfl_opponent: string | null;
  nfl_game_id: string | null;
  /** Served from local disk cache, e.g. "/api/headshots/yahoo/123456.png". */
  headshot_url: string;
  bye_week: number | null;
  injury_status: InjuryStatus | null;
}

export type GameState = "pre" | "in" | "post" | "bye";

export interface RosterSlot {
  team_id: string;
  week: number;
  slot: Slot;
  player: Player;
  proj_points: number;
  actual_points: number;
  is_live: boolean;
  game_state: GameState | null;
  status_text: string;
}

export interface Matchup {
  id: string;
  league_id: string;
  week: number;
  home_team_id: string;
  away_team_id: string;
  home_score: number;
  away_score: number;
  home_proj: number;
  away_proj: number;
  is_complete: boolean;
}

export interface MatchupSlot {
  matchup_id: string;
  slot: Slot;
  home_player: Player;
  away_player: Player;
  home_pts: number;
  away_pts: number;
}

export interface SeasonWeek {
  team_id: string;
  week: number;
  score: number;
  opp_score: number;
  opp_team_name: string;
  is_win: boolean;
  is_current: boolean;
}

export type NflGameState = "pre" | "in" | "post" | "postponed";

export interface LiveNflGame {
  nfl_game_id: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  state: NflGameState;
  clock: string | null;
  period: number | null;
  /** ISO timestamp. */
  kickoff_at: string;
}

/** `{platform}:{platform_id}` → the platform prefix, per the stable-id scheme. */
export function platformFromId(id: string): Platform | null {
  const prefix = id.split(":")[0];
  return prefix === "yahoo" || prefix === "espn" ? prefix : null;
}
