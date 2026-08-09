## ADDED Requirements

### Requirement: Yahoo OAuth 2.0 authentication

The system SHALL implement Yahoo Fantasy Sports' OAuth 2.0 authorization-code flow, including authorization URL generation, callback exchange, refresh-token rotation, and persistent encrypted token storage.

#### Scenario: First-time authorization

- **WHEN** the user clicks "Connect Yahoo" in Settings
- **THEN** the backend generates an authorization URL containing the configured `client_id`, `redirect_uri`, `response_type=code`, `scope=fspt-r`, and a CSRF-protected `state` token, and the frontend redirects the browser to it.

#### Scenario: Callback exchange

- **WHEN** Yahoo redirects to the configured callback with `code` and matching `state`
- **THEN** the backend POSTs to Yahoo's token endpoint, receives `access_token` (≈1h TTL) + `refresh_token`, encrypts both with the configured key, persists them keyed to the single user, and marks Yahoo as connected.

#### Scenario: Access token expiry

- **WHEN** any Yahoo API call returns 401 with body indicating expired token
- **THEN** the client refreshes once using the stored refresh token, retries the original call, and persists any new tokens. If the refresh itself fails, Yahoo is marked disconnected and the original call returns a typed `AuthRequiredError`.

#### Scenario: Rate limiting backoff

- **WHEN** a Yahoo response has status 429 or 999
- **THEN** the client waits with exponential backoff (1s, 2s, 4s, max 3 retries), and surfaces a typed `RateLimitedError` if the final attempt still fails.

### Requirement: Yahoo league and team discovery

The system SHALL discover all NFL fantasy leagues and teams the authenticated Yahoo user owns, dynamically resolving the active NFL `game_key` (which changes each season).

#### Scenario: Resolving the current NFL game key

- **WHEN** the discovery flow runs
- **THEN** the client calls `/users;use_login=1/games;game_codes=nfl?format=json`, picks the entry with the highest `season` and `is_registration_over=0` (or the most recent if season is over), and caches the resulting `game_key` for 24 hours.

#### Scenario: Listing the user's leagues

- **WHEN** discovery has the active `game_key`
- **THEN** the client calls `/users;use_login=1/games;game_keys={game_key}/leagues?format=json`, returning every `(league_key, league_name, num_teams, scoring_type)` tuple.

#### Scenario: Resolving the user's team within a league

- **WHEN** a league is selected
- **THEN** the client calls `/league/{league_key}/teams?format=json`, finds the team whose `is_owned_by_current_login=1`, and stores the resulting `team_key` (`{game_key}.l.{league_id}.t.{team_id}`).

### Requirement: Yahoo roster and matchup fetching

The system SHALL fetch the authenticated user's roster, weekly matchup, and live stats for any week within the active season.

#### Scenario: Current-week roster

- **WHEN** the dashboard or My Team screen needs roster data for week N
- **THEN** the client calls `/team/{team_key}/roster;week={N}/players/stats?format=json` and returns players with slot, name, position, NFL team, opponent, projected, and actual points.

#### Scenario: Head-to-head matchup

- **WHEN** the H2H screen requests week N
- **THEN** the client calls `/team/{team_key}/matchups;weeks={N}?format=json` and returns the opponent team key, both teams' projected and live point totals, and per-slot opponent player data via a follow-up roster fetch on the opponent team.

### Requirement: ESPN cookie-based authentication

The system SHALL accept user-provided `SWID` and `espn_s2` cookies, validate them against ESPN, and persist them encrypted at rest. The system SHALL detect cookie expiry and prompt the user to refresh credentials.

#### Scenario: Saving credentials

- **WHEN** the user enters `SWID` (must match `^\{[0-9A-F-]+\}$`) and `espn_s2` in Settings and clicks "Test Connection"
- **THEN** the backend issues a probe request to `/apis/v3/games/ffl/seasons/{currentYear}/segments/0/leagues?view=mTeam` with both cookies as `Cookie` header. If the response is 200, both cookies are encrypted and persisted, ESPN is marked connected, and `last_verified` is set to now. If 401/403, credentials are rejected and not persisted.

#### Scenario: Silent 401 / 403 during a normal call

- **WHEN** any ESPN API call returns 401 or 403
- **THEN** ESPN is marked `auth_required`, no further ESPN calls are issued from the live poller, and the UI shows a banner directing the user to update cookies.

#### Scenario: Configurable base URL

- **WHEN** the system is deployed
- **THEN** the ESPN base URL is read from configuration (default `https://lm-api-reads.fantasy.espn.com`) and never hardcoded at the call site, so an ESPN host change can be patched via `.env`.

### Requirement: ESPN league and team discovery

The system SHALL allow the user to add ESPN leagues by `league_id`, then auto-fetch league metadata and resolve which team in the league belongs to the authenticated user (via the `SWID` UUID matching `members[].id`).

#### Scenario: Adding a league by id

- **WHEN** the user enters an ESPN `league_id` in Settings
- **THEN** the backend calls `/seasons/{year}/segments/0/leagues/{league_id}?view=mSettings&view=mTeam`, returns league name, size, scoring type (`scoringPeriodId`/`scoringSettings.scoringType`), the user's `team_id` (whose `owners` array contains the user's SWID), and persists the league.

### Requirement: ESPN roster and matchup fetching

The system SHALL fetch ESPN rosters and matchups using stacked `view` query parameters, and SHALL support historical weeks via `scoringPeriodId` / `matchupPeriodId`.

#### Scenario: Current-week roster + matchup

- **WHEN** the system needs week N data for an ESPN league
- **THEN** it calls `/seasons/{year}/segments/0/leagues/{league_id}?view=mRoster&view=mMatchupScore&view=mBoxscore&scoringPeriodId={N}&matchupPeriodId={N}` once and parses both roster and matchup from the single response.

### Requirement: Unified fantasy service

The system SHALL expose a single `FantasyService` API that returns normalized data regardless of source platform. The service SHALL fan out per-platform fetches in parallel and merge results into the internal model defined in the `fantasy-data-model` capability.

#### Scenario: Aggregated dashboard fetch

- **WHEN** the dashboard requests "all teams for week 14"
- **THEN** `FantasyService.list_teams(week=14)` issues Yahoo and ESPN fetches concurrently, maps each into the normalized `Team` shape, and returns the combined list. Per-platform failures are isolated — one platform erroring does not block the other; the failed platform is annotated in the response.

### Requirement: Per-endpoint response caching

The system SHALL cache each external API response in SQLite with a TTL appropriate to the endpoint. Cache entries SHALL be refreshed by the scheduler jobs defined in the `live-updates` capability, NOT lazily on read — page loads stay instant regardless of upstream latency, and all upstream traffic flows through one throttled, backoff-aware path.

#### Scenario: Cache hit within TTL

- **WHEN** a request for an endpoint occurs within its TTL window
- **THEN** the cached response is returned without an outbound HTTP call.

#### Scenario: Cache TTL by endpoint class

- **WHEN** caching a response
- **THEN** the system SHALL apply these defaults (overridable in config):
  - League settings / scoring rules: 24h
  - Team metadata: 6h
  - Roster (off-day): 1h
  - Roster (game day, no live): 5min
  - Roster / matchup (live game in progress): 30s
  - Player headshot binary: 24h
  - NFL scoreboard: 30s

#### Scenario: Live-game invalidation

- **WHEN** the scheduler observes a game transitioning from "pre" to "in-progress"
- **THEN** all roster + matchup cache entries whose players' NFL teams are in that game are marked `expires_at = now()` so the next refresh tick refetches them.

### Requirement: Player headshot cache on local disk

The system SHALL cache player headshots on local disk so the browser never hot-links to ESPN/Yahoo CDNs and each image is fetched from upstream at most once.

#### Scenario: First request

- **WHEN** the frontend requests `/api/headshots/{platform}/{player_id}.png` and no file exists at `data/headshots/{platform}/{player_id}.png`
- **THEN** the backend fetches the source URL (ESPN: `https://a.espncdn.com/i/headshots/nfl/players/full/{id}.png`; Yahoo: from the player payload), writes the bytes to that path, and serves them with `Cache-Control: public, max-age=86400, immutable`.

#### Scenario: Cached request

- **WHEN** the frontend requests a headshot whose file already exists on disk
- **THEN** the backend serves it directly via `FileResponse` with the same immutable cache headers; no upstream call, no database lookup required.

#### Scenario: Source 404

- **WHEN** the upstream returns 404
- **THEN** the backend writes a built-in silhouette PNG at the same path (so we don't re-fetch on miss) and serves it. The negative-cache entry is replaced if a real headshot appears in a later discovery run.
