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
/**
 * Repeatable starter slots are numbered by order of appearance, the same rule that
 * governs RB1/RB2 and WR1/WR2 — a lineup can hold several flex spots, and one shared
 * `FLEX` label collapsed them. `"FLEX"` unnumbered is retained as a legacy value: the
 * backend still validates it on read for rows written by earlier syncs.
 */
export type Slot =
  | "QB"
  | "RB1"
  | "RB2"
  | "WR1"
  | "WR2"
  | "TE"
  | "FLEX"
  | "FLEX1"
  | "FLEX2"
  | "FLEX3"
  | "FLEX4"
  | "OP1"
  | "OP2"
  | "K"
  | "DST"
  | "BN"
  | "IR";

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
  /** A LOCAL url pointing at this app's own logo route, or null when the team has no
   *  logo. Never the upstream URL: ESPN's uploaded-logo host returns 401 to an
   *  unauthenticated client, so pointing an <img> at it renders a broken image. */
  logo_url: string | null;
}

export type Position = "QB" | "RB" | "WR" | "TE" | "K" | "DST";
/** Mirrors `backend/gridiron/schemas/players.py`'s `InjuryStatus` — the two are
 *  hand-duplicated, so widening one means widening the other.
 *
 *  `null` means "we don't know", NOT "healthy": both mappers now return null for a
 *  platform code they can't parse rather than asserting ACTIVE. */
export type InjuryStatus = "ACTIVE" | "Q" | "D" | "O" | "IR" | "PUP" | "DTD" | "SUSP" | "NFI";

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
  /** An independent weekly projection (Rotowire, via Sleeper's public feed) in this
   *  league's scoring format. Shown NEXT TO `proj_points`, never blended with it —
   *  the two disagreeing is the signal.
   *
   *  null when the player didn't match the feed, the projection job hasn't run, or the
   *  league scores `custom`. */
  ext_proj_points: number | null;
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
  // Per-side live state, mirrored from the roster_slots rows for the same
  // players (fantasy-data-model spec, "Per-side live state on matchup slots").
  // `*_state` distinguishes "0.0 because he hasn't played" (`pre`) from "0.0
  // because he was shut out" (`post`); panel-level live/settled state comes
  // from `*_is_live` and `Matchup.is_complete`, never from these (design D4).
  home_state: GameState | null;
  away_state: GameState | null;
  home_is_live: boolean;
  away_is_live: boolean;
}

/**
 * One entry of `GET /api/teams/game-day` — a user team's complete head-to-head,
 * already oriented onto the user's perspective (`team_*` is always the user's
 * side, `opp_*` the opponent's, whichever side of the matchup they sit on).
 *
 * `slots` keeps the raw home/away shape and is oriented client-side with
 * `orientSlot(slot, iAmHome)`. There is deliberately no `win_prob` (design D7)
 * — `proj`, `opp_proj` and `remaining` are `computeProjectedFinal`'s only
 * inputs, so win probability has exactly one implementation, client-side.
 */
export interface GameDayMatchup {
  team_id: string;
  team_name: string;
  opp_team_id: string;
  opp_team_name: string;
  league_id: string;
  league_name: string;
  /** Derived from the team id's `{platform}:` prefix — `Team` has no platform field. */
  platform: Platform;
  /** Local logo routes for both sides. This is a flattened projection rather than a
   *  pair of `Team` objects, so logos are carried explicitly. */
  team_logo_url: string | null;
  opp_logo_url: string | null;
  record: { w: number; l: number; t: number };
  rank: { current: number; total: number };
  score: number;
  opp_score: number;
  proj: number;
  opp_proj: number;
  remaining: { mine: number; theirs: number };
  is_complete: boolean;
  /**
   * Which side of the underlying matchup the user's team sits on. Every other field
   * here is already oriented; `slots` keeps the raw home/away shape so Head-to-Head's
   * `orientSlot(slot, iAmHome)` can be reused unchanged — and since `MatchupSlot`
   * carries no team ids, this flag is that function's only possible input.
   */
  i_am_home: boolean;
  slots: MatchupSlot[];
}

export interface GameDayData {
  matchups: GameDayMatchup[];
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

export interface LeagueStandingsRow {
  team: Team;
  division_id: number;
  /** The rendered rank, from the applied ordering — not `team.rank.current`, which is
   *  the platform's playoff seed and is 0 for every team in some leagues. */
  position: number;
}

export interface LeagueStandingsData {
  league: League;
  rows: LeagueStandingsRow[];
}

export type PoolStatus = "FREEAGENT" | "WAIVERS" | "ONTEAM";

/** One player's availability and season projection *within one league*. Both facts
 *  are league-scoped: a player free in one league may be rostered in another, and
 *  `season_proj_points` is scored under that league's rules, so the same player
 *  projects differently in a PPR league than in a half-PPR one. */
export interface PlayerPoolEntry {
  league_id: string;
  player: Player;
  status: PoolStatus;
  on_team_id: string | null;
  percent_owned: number;
  percent_started: number;
  /** null when no projection was published — distinct from 0.0, which is a real
   *  value for a player projected to score nothing. Render as an em dash. */
  season_proj_points: number | null;
  /** ESPN's UNNUMBERED slot vocabulary — "QB", "RB", "WR", "TE", "FLEX", "RB/WR",
   *  "WR/TE", "REC_FLEX", "OP", "K", "DST". Deliberately not `Slot`, which numbers
   *  its positions (RB1, RB2) from per-roster counters; a pool player is on no
   *  roster, so there is no basis for that numbering. */
  eligible_slots: string[];
}

/** A pool entry presented as claimable. `status` is inherited and is always
 *  "FREEAGENT" or "WAIVERS" here — "ONTEAM" rows are ingested so incumbent starters
 *  have a season projection to be compared against, but are never listed. */
export interface WaiverCandidate extends PlayerPoolEntry {
  /** Season projection minus that of the weakest starter the user rosters at an
   *  eligible slot. null — never 0 — when either side has no projection or no
   *  eligible starter exists. Render as an em dash. */
  delta_vs_worst_starter: number | null;
  /** Independent SEASON projection (Rotowire, via Sleeper). Shown beside
   *  `season_proj_points`; deliberately not an input to `delta_vs_worst_starter`. */
  ext_season_proj_points: number | null;
  /** This week only. A claim is a decision about this Sunday as much as about the rest
   *  of the year, and the two can disagree — a bye-week starter is a season-long keep
   *  and a week-one hole. Independent source only: the platform publishes no weekly
   *  number for an unrostered player. */
  week_proj_points: number | null;
  /** Weekly counterpart of `delta_vs_worst_starter`. */
  delta_vs_worst_starter_week: number | null;
}

export interface WaiversData {
  team_id: string;
  league_id: string;
  week: number;
  candidates: WaiverCandidate[];
}

/** `{platform}:{platform_id}` → the platform prefix, per the stable-id scheme. */
export function platformFromId(id: string): Platform | null {
  const prefix = id.split(":")[0];
  return prefix === "yahoo" || prefix === "espn" ? prefix : null;
}

/** `GET /api/players/{id}/injury` — the detail behind the badge.
 *
 *  Every field is optional because ESPN files a practice-report entry (status + date)
 *  days before the detail and comments land. */
export interface PlayerInjuryReport {
  status: string | null;
  injury_type: string | null;
  location: string | null;
  detail: string | null;
  side: string | null;
  /** ESPN publishes an un-timezoned `YYYY-MM-DD` estimate, kept verbatim. */
  return_date: string | null;
  short_comment: string | null;
  long_comment: string | null;
  reported_at: string | null;
  fetched_at: string;
}

export interface PlayerInjuryData {
  player_id: string;
  injury_status: InjuryStatus | null;
  /** null is the ordinary "nothing on file" answer, not an error. */
  report: PlayerInjuryReport | null;
  /** false for D/ST rows and Yahoo-sourced players — no ESPN athlete to look up. */
  detail_supported: boolean;
}

/** Which projection the lineup advice was computed from. Never a blend. */
export type ProjectionSource = "platform" | "rotowire";

/** `unstartable` — the current starter can't play (O/IR/PUP/SUSP/NFI). A different
 *  recommendation from `higher_projection`, which is a judgement the user may decline. */
export type MoveReason = "unstartable" | "higher_projection";

export interface LineupMove {
  slot: Slot;
  out_player: Player;
  in_player: Player;
  out_points: number;
  in_points: number;
  delta: number;
  reason: MoveReason;
  /** The other projection source independently agrees with this swap. */
  consensus: boolean;
}

export interface LineupAdvice {
  team_id: string;
  week: number;
  source: ProjectionSource;
  current_points: number;
  optimal_points: number;
  /** Always equals the sum of `moves` — immaterial swaps are reverted, not hidden. */
  gain: number;
  moves: LineupMove[];
  sources_agree: boolean;
  comparison_available: boolean;
  /** False when the source could evaluate nothing — an unsynced roster, or a projections
   *  job that has never run. Distinct from "already optimal". */
  advice_available: boolean;
  unevaluated: Player[];
}
