## ADDED Requirements

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
  - `MatchupSlot`: `matchup_id`, `slot`, `home_player`, `away_player`, `home_pts`, `away_pts`
  - `SeasonWeek`: `team_id`, `week`, `score`, `opp_score`, `opp_team_name`, `is_win`, `is_current`
  - `LiveNflGame`: `nfl_game_id`, `home_team`, `away_team`, `home_score`, `away_score`, `state` (`pre` | `in` | `post` | `postponed`), `clock`, `period`, `kickoff_at`
  - `Connection`: `platform`, `is_connected: boolean`, `display_name`, `last_verified_at`, `error?`

### Requirement: Per-platform mappers

For each external platform, the system SHALL provide a mapper module that converts raw API payloads into normalized entities. Mappers SHALL be the only code with knowledge of platform-specific shapes.

#### Scenario: Yahoo roster mapping

- **WHEN** a Yahoo `/team/{key}/roster/players/stats` payload is received
- **THEN** `yahoo.map_roster(payload, week)` returns `RosterSlot[]` with Yahoo's slot codes (`QB`, `RB`, `WR`, `TE`, `W/R/T`, `K`, `DEF`, `BN`, `IR`) translated to the internal slot vocabulary, and Yahoo's `player_points` rendered into `actual_points` (or `0` for not-yet-played).

#### Scenario: ESPN matchup mapping

- **WHEN** an ESPN `view=mMatchupScore&view=mBoxscore` payload is received
- **THEN** `espn.map_matchup(payload, week)` returns `Matchup` + `MatchupSlot[]` for the user's team, with ESPN's `lineupSlotId` integers translated into the internal slot vocabulary using a static lookup table.

#### Scenario: Mapper purity

- **WHEN** a mapper runs
- **THEN** it performs no I/O, throws on unknown slot codes (so we fail loud on platform schema drift), and is unit-testable from a captured fixture file.

### Requirement: Persistence layer

The system SHALL persist normalized entities and platform credentials in a single SQLite database at `data/gridiron.db`, accessed via SQLAlchemy async + `aiosqlite`. Cache entries SHALL live in the same database in an `http_cache` table keyed by `(platform, endpoint, params_hash)`. Schema SQL SHALL stay dialect-neutral (raw JSON stored as TEXT, no SQLite-only operators in queries) so a future Postgres move is a connection-string change plus migration replay.

#### Scenario: Schema migrations

- **WHEN** the project is deployed (`make deploy`) or booted in dev (`make dev`)
- **THEN** `alembic upgrade head` runs before the app starts, creating tables on first run and applying any new migrations idempotently on subsequent runs. Migrations are committed to git under `backend/alembic/versions/`.

#### Scenario: Concurrency configuration

- **WHEN** the engine is created at process startup
- **THEN** it enables WAL journal mode and sets `busy_timeout=5000` on each connection, so scheduler writes never block reads and rare write contention waits instead of erroring. The single backend process is the only writer by design.

#### Scenario: Encrypted credential storage

- **WHEN** Yahoo refresh tokens or ESPN cookies are written to the `connections` table
- **THEN** they are encrypted with Fernet using a key derived from `GRIDIRON_SECRET_KEY` env var. Reads transparently decrypt; if the env var is missing or wrong, reads raise a typed `CredentialDecryptError` and the platform is shown as disconnected in the UI.

#### Scenario: Single-user assumption

- **WHEN** any persistence operation runs
- **THEN** there is no `user_id` column on any table — the database belongs to one local user. Future multi-tenant migration is explicitly out of scope.

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
