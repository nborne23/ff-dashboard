## ADDED Requirements

### Requirement: ESPN player pool fetching

The system SHALL fetch every player in a league — available and rostered alike — together with each player's season-level projection under that league's scoring rules, from ESPN's `kona_player_info` view.

#### Scenario: Pool selection by filter header

- **WHEN** the system requests a league's player pool
- **THEN** it issues `GET /apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}?view=kona_player_info` with an `x-fantasy-filter` request **header** carrying `filterStatus: ["FREEAGENT", "WAIVERS", "ONTEAM"]` and a `limit`
- **AND** the filter header — not a query parameter — is what selects the pool; a request without it returns a different, unbounded result.

#### Scenario: Rostered players are ingested, not only available ones

- **WHEN** the filter is constructed
- **THEN** it SHALL include `ONTEAM` alongside `FREEAGENT` and `WAIVERS`
- **AND** this is required for correctness, not completeness: the season projection is the only scale on which a candidate and an incumbent starter can be compared, and it exists for a rostered player nowhere else in the system — the stored `RosterSlot.proj_points` is a *weekly* value roughly an order of magnitude smaller.

#### Scenario: The result set is not server-capped

- **WHEN** a `limit` well above the league's player count is requested
- **THEN** the response carries the true count and does not truncate, so the fetch SHALL be a single request and SHALL NOT require `offset` pagination.

#### Scenario: Season projection is league-scoped

- **WHEN** the same `playerId` is fetched from two leagues with different scoring types
- **THEN** the system SHALL treat the returned `appliedTotal` as a per-league value and persist it per `(league_id, player_id)`
- **AND** it SHALL NOT store a season projection on the platform-agnostic `Player` entity, because a PPR league and a half-PPR league report different totals for the same pass-catching player.

#### Scenario: Season projection accessor keys on season

- **WHEN** the season projection is read from a player's `stats` array
- **THEN** the matching row SHALL satisfy `scoringPeriodId == 0`, `statSourceId == 1`, `statSplitTypeId == 0`, **and** `seasonId == {the current season}`
- **AND** matching on the first three alone is insufficient: the payload contains a prior-season projection row with an identical tuple, so an accessor without the `seasonId` predicate returns a nondeterministic value.

#### Scenario: Missing projection is distinguishable from zero

- **WHEN** no season-projection row exists for a player
- **THEN** the accessor returns null rather than `0.0`, because a genuine `0.0` projection is a distinct and observed value.

#### Scenario: Unmappable positions do not abort the sync

- **WHEN** a pool entry carries a `defaultPositionId` with no internal position translation
- **THEN** that entry is skipped and counted, the remaining entries are persisted, and the skip count is reported in the refresh run's summary
- **AND** the sync SHALL NOT fail, because the pool is a league-wide catalog that legitimately contains positions this app has no vocabulary for — unlike a roster, where dropping a player silently would corrupt a lineup.

## MODIFIED Requirements

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
  - Player pool: 6h
  - Player headshot binary: 24h
  - NFL scoreboard: 30s

#### Scenario: Cache keys incorporate request headers

- **WHEN** an endpoint's result varies by request header rather than by query parameter
- **THEN** the header value SHALL be folded into the cache key, serialized with sorted keys
- **AND** sorting is required for correctness, not tidiness: JSON serialization preserves insertion order, so an unsorted filter yields a different key hash per call, producing permanent cache misses and a full refetch on every tick.

#### Scenario: Raw response retention exemption for bulk payloads

- **WHEN** a cached response exceeds a size at which raw retention would materially grow the database — specifically the player pool, at ~3.7 MB per league and ~18.5 MB across the user's five leagues per refresh
- **THEN** the cache entry SHALL be stored with empty raw content, and the mapped rows in `player_pool_entries` SHALL serve as the durable record
- **AND** the replay-debugging capability that raw retention exists to provide SHALL be preserved by an on-demand probe script rather than by continuous storage.

#### Scenario: Live-game invalidation

- **WHEN** the scheduler observes a game transitioning from "pre" to "in-progress"
- **THEN** all roster + matchup cache entries whose players' NFL teams are in that game are marked `expires_at = now()` so the next refresh tick refetches them
- **AND** player pool entries are NOT invalidated, because pool availability changes on waiver-processing timescales, not during play.
