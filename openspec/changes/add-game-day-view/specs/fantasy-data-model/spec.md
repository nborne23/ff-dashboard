## MODIFIED Requirements

### Requirement: Normalized internal entities

The system SHALL define a single set of internal entities that is platform-agnostic. Frontend code SHALL only ever consume these normalized types — never raw Yahoo or ESPN payloads.

The entities are: `Platform`, `League`, `Team`, `Player`, `RosterSlot`, `Matchup`, `MatchupSlot`, `SeasonWeek`, `LiveNflGame`, `Connection`.

#### Scenario: Platform identifier

- **WHEN** any normalized entity references its source
- **THEN** it carries a `platform: "yahoo" | "espn"` discriminator and a `platform_id: string` (the source-system primary key, e.g., Yahoo `team_key` or ESPN `team_id`).

#### Scenario: Stable internal id

- **WHEN** an entity is persisted
- **THEN** it has an internal id of the form `{platform}:{platform_id}` (e.g., `yahoo:nfl.l.123456.t.4`, `espn:l-1234567-t-2`) which is stable across syncs and used by the frontend for keys and routing.

#### Scenario: Required fields per entity

- **WHEN** the model defines each entity
- **THEN** the following fields are required (additional fields permitted):
  - `League`: `id`, `platform`, `platform_id`, `name`, `season`, `team_count`, `scoring_type`, `current_week`
  - `Team`: `id`, `league_id`, `name`, `manager_name`, `record_w`, `record_l`, `record_t`, `rank`, `points_for`, `points_against`, `is_user_team: boolean`
  - `Player`: `id`, `name`, `position`, `nfl_team`, `nfl_opponent`, `nfl_game_id`, `headshot_url`, `bye_week`, `injury_status`
  - `RosterSlot`: `team_id`, `week`, `slot` (e.g., `QB`, `RB1`, `WR2`, `FLEX`, `K`, `DST`, `BN`, `IR`), `player`, `proj_points`, `actual_points`, `is_live: boolean`, `game_state`
  - `Matchup`: `id`, `league_id`, `week`, `home_team_id`, `away_team_id`, `home_score`, `away_score`, `home_proj`, `away_proj`, `is_complete`
  - `MatchupSlot`: `matchup_id`, `slot`, `home_player`, `away_player`, `home_pts`, `away_pts`, `home_state`, `away_state`, `home_is_live: boolean`, `away_is_live: boolean`
  - `SeasonWeek`: `team_id`, `week`, `score`, `opp_score`, `opp_team_name`, `is_win`, `is_current`
  - `LiveNflGame`: `nfl_game_id`, `home_team`, `away_team`, `home_score`, `away_score`, `state` (`pre` | `in` | `post` | `postponed`), `clock`, `period`, `kickoff_at`
  - `Connection`: `platform`, `is_connected: boolean`, `display_name`, `last_verified_at`, `error?`

#### Scenario: Per-side live state on matchup slots

- **WHEN** a `MatchupSlot` is serialized
- **THEN** `home_state` and `away_state` carry that side's `GameState` (`pre` | `in` | `post` | `bye`) or null, and `home_is_live` / `away_is_live` carry that side's live flag — the same values the corresponding `RosterSlot` rows already hold, so a consumer can distinguish a player who has not played from one who scored zero.

#### Scenario: Live state joins on player identity

- **WHEN** per-side state is resolved for a matchup slot
- **THEN** it is joined from `RosterSlot` on `(team_id, week, player_id)` — keyed on **player identity, not the slot label**, and scoped to the side's own team. The Yahoo path pairs matchup slots by slot label while the ESPN path receives them natively, so slot labels are not a reliable join key across platforms; player identity is. The team id is part of the key because `(player_id, week)` alone is **not** unique: `roster_slots`' constraint is `uq_roster_slots_team_week_player` — uniqueness is per team-week — so one player rostered in two of the user's leagues has one row per team, and an unscoped join would resolve the wrong league's state.

#### Scenario: No schema migration required

- **WHEN** the per-side state fields are added
- **THEN** they are Pydantic-schema additions computed from existing `roster_slots` columns, and no database migration is introduced.

### Requirement: Read API for the frontend

The system SHALL expose REST endpoints that the frontend consumes, returning JSON shaped exactly like the normalized entities above.

All read endpoints use the envelope defined in the `live-updates` capability: `{ data: <endpoint-specific>, meta: { live_state, as_of, next_refresh_at, platforms } }`.

#### Scenario: List teams across platforms

- **WHEN** the frontend GETs `/api/teams?week=14`
- **THEN** `data` is `{ teams: Team[] }` and `meta.platforms` lists any platform that failed (so the UI can show partial-data banners).

#### Scenario: Team detail with roster

- **WHEN** the frontend GETs `/api/teams/{id}?week=14`
- **THEN** `data` is `{ team: Team, league: League, starters: RosterSlot[], bench: RosterSlot[], record_history: SeasonWeek[] }`.

#### Scenario: Head-to-head detail

- **WHEN** the frontend GETs `/api/teams/{id}/h2h?week=14`
- **THEN** `data` is `{ matchup: Matchup, slots: MatchupSlot[], remaining: { mine: number, theirs: number } }`.

#### Scenario: Season detail

- **WHEN** the frontend GETs `/api/teams/{id}/season`
- **THEN** `data` is `{ weeks: SeasonWeek[], highlights: { season_high: SeasonWeek, win_streak: number, most_started: { player: Player, starts: number, avg_points: number } } }`.

#### Scenario: Connections / settings

- **WHEN** the frontend GETs `/api/connections`
- **THEN** `data` is `{ yahoo: Connection, espn: Connection, leagues: League[] }`.

#### Scenario: Bulk game-day matchups

- **WHEN** the frontend GETs `/api/teams/game-day?week=14`
- **THEN** `data` is `{ matchups: GameDayMatchup[] }`, where each entry carries `team_id`, `team_name`, `opp_team_id`, `opp_team_name`, `league_id`, `league_name`, `platform`, `record`, `rank`, `score`, `opp_score`, `proj`, `opp_proj`, `remaining`, `is_complete`, `i_am_home`, and `slots: MatchupSlot[]` — one entry per matchup involving a user team, replacing what would otherwise be a per-team `/h2h` plus `/{id}` request pair.

#### Scenario: Slots carry their own orientation flag

- **WHEN** an entry is serialized
- **THEN** `i_am_home` states which side of the underlying matchup the user's team occupies. Every panel-level field is already oriented, but `slots` deliberately keeps the raw home/away shape so the client reuses the existing `orientSlot(slot, iAmHome)` — and since `MatchupSlot` carries no team ids, this flag is that function's only possible input.

#### Scenario: Week defaulting

- **WHEN** `/api/teams/game-day` is requested without a `week` parameter
- **THEN** it resolves to the current week using the same resolution the other team endpoints use.

#### Scenario: Team-level fields honor the requested week

- **WHEN** `/api/teams/game-day?week=3` is requested for a past week
- **THEN** `score`, `opp_score`, and `opp_team_name` are that week's values, not the current week's — they derive from the week-scoped `matchups` row, so the margin between them is correct for the requested week rather than mixing past slots with present scores.

#### Scenario: Platform discriminator

- **WHEN** an entry is serialized
- **THEN** `platform` is derived from the team id's `{platform}:` prefix. It is not carried on the `Team` entity, so it SHALL NOT be read from there.

#### Scenario: Both matchup orientations

- **WHEN** a user team is the away side of its matchup
- **THEN** its entry still reports that team as `team_id`/`team_name`/`score` and the opponent as `opp_*`, so the consumer never re-derives home/away.

#### Scenario: Route registration order

- **WHEN** the router registers `/api/teams/game-day`
- **THEN** it is registered before `/api/teams/{team_id}`, so the literal path is not captured by the path parameter — the same ordering constraint `/api/teams/day-rings` already observes.

#### Scenario: No N+1 queries

- **WHEN** the endpoint builds its response for N user teams
- **THEN** it issues a bounded number of queries independent of N, rather than one query pass per team.

#### Scenario: Disabled leagues are excluded

- **WHEN** a league has been switched off in Settings (`is_enabled` false)
- **THEN** its teams produce no entries, the same filter `/api/teams` and `/api/teams/day-rings` apply. Discovery leaves a disabled league's rows in place rather than deleting them, so the exclusion SHALL be applied on read.

#### Scenario: Nothing connected

- **WHEN** no platform is connected or no user team has a matchup that week
- **THEN** `data` is `{ matchups: [] }` with a well-formed envelope, not an error.

#### Scenario: Caching

- **WHEN** the endpoint responds
- **THEN** it sets the same `Cache-Control` header as the other `/api/teams*` read endpoints, and reads only from normalized tables.

## ADDED Requirements

### Requirement: Win probability has a single implementation

Win probability SHALL be computed in exactly one place. The system SHALL NOT return a `win_prob` field from the game-day envelope while an equivalent client-side computation exists.

#### Scenario: Computed from envelope fields

- **WHEN** a consumer needs win probability for a matchup
- **THEN** it derives it from `proj`, `opp_proj`, and `remaining` — all present on the envelope — using the shared projected-final module.

#### Scenario: Favorite-view clamp is opt-in

- **WHEN** the shared computation is called without an explicit clamp choice
- **THEN** it retains the existing `[50, 99]` floored "favorite view" behavior, so existing callers are unaffected.

#### Scenario: True probability for multi-matchup views

- **WHEN** a view renders several matchups at once
- **THEN** it requests the unclamped value, so a matchup the user is losing reports below 50% rather than being floored — a display asserting the user is favored in every league at once is misleading.
