## ADDED Requirements

### Requirement: League-scoped player availability

The system SHALL persist, per league, the availability and season projection of every player in that league — both those in the free-agent/waiver pool and those on a roster.

#### Scenario: Entity shape

- **WHEN** a `PlayerPoolEntry` is persisted
- **THEN** it is keyed `(league_id, player_id)` and carries: `status` (`FREEAGENT` | `WAIVERS` | `ONTEAM`), `on_team_id` (nullable), `percent_owned`, `percent_started`, `season_proj_points` (nullable), `eligible_slots`, and `updated_at`
- **AND** the player's platform-agnostic attributes (name, position, NFL team, headshot, bye week, injury status) live on the existing `Player` entity, not on this one.

#### Scenario: Availability is per league, not per player

- **WHEN** the same player is in the pool of one league and rostered in another
- **THEN** each league has its own `PlayerPoolEntry` row with its own `status`
- **AND** no availability or projection field is added to `Player`, which is shared across leagues and would otherwise hold whichever league synced last.

#### Scenario: Eligibility is persisted, not derived from position

- **WHEN** a `PlayerPoolEntry` records which slots a player can fill
- **THEN** it stores the platform's own eligibility list, using that platform's unnumbered slot vocabulary (`RB`, `RB/WR`, `FLEX`, `REC_FLEX`, `OP`, …)
- **AND** it SHALL NOT be derived from the player's position at read time, because eligibility is league-specific: a superflex league admits a QB to `OP` and a TE-premium league admits a TE to `REC_FLEX`, neither of which follows from position alone
- **AND** the list SHALL NOT use the internal numbered `Slot` vocabulary (`RB1`, `RB2`), whose numbering comes from per-roster counters that do not exist for a player on no roster.

#### Scenario: Bench and reserve slots are not starting slots

- **WHEN** eligibility is used to choose which starter a candidate competes with
- **THEN** bench and injured-reserve slots SHALL be excluded from consideration
- **AND** this matters because the platform lists them as eligible for essentially every player, so treating them as startable would match every candidate against every roster spot.

#### Scenario: Pool snapshot is authoritative per league

- **WHEN** a league's pool is refreshed
- **THEN** that league's existing entries are replaced wholesale rather than merged, so a player who has been claimed since the last sync disappears from the pool rather than persisting as a stale row.

## MODIFIED Requirements

### Requirement: Read API for the frontend

The system SHALL expose REST endpoints that the frontend consumes, returning JSON shaped exactly like the normalized entities above.

#### Scenario: Waiver candidates for a team

- **WHEN** the frontend requests `GET /api/teams/{team_id}/waivers?week={n}&position={pos}&limit={n}`
- **THEN** the response envelope carries the pool for that team's league, ranked by `season_proj_points` descending with null projections sorted last, optionally filtered to one position
- **AND** only players whose `status` is `FREEAGENT` or `WAIVERS` are listed as candidates; `ONTEAM` rows are ingested for comparison and never presented as claimable
- **AND** each candidate carries `delta_vs_worst_starter`: its season projection minus that of the lowest-projected starter the user currently rosters at a slot the candidate is eligible for
- **AND** `delta_vs_worst_starter` is null — never `0.0` — when the candidate has no projection or the user starts nobody at an eligible slot.

#### Scenario: Both operands of the delta are season-scoped

- **WHEN** the incumbent starter's projection is resolved
- **THEN** it SHALL come from that starter's own league-scoped season projection, and SHALL NOT come from `RosterSlot.proj_points`
- **AND** the distinction is not stylistic: `RosterSlot.proj_points` is a single week's projection, roughly an order of magnitude smaller than a season total, so mixing the two scales yields a large positive delta for every candidate regardless of merit — a wrong answer that looks plausible.

#### Scenario: Ranking answers a replacement question

- **WHEN** candidates are ranked for presentation
- **THEN** the delta is computed against the user's own weakest eligible starter rather than a positional average, so a FLEX-eligible running back is compared against the weakest of the RB/FLEX starters actually rostered
- **AND** this is the ranking's purpose: "is this player better than what I would drop" is the decision being made, and a raw projection leaderboard does not answer it.

#### Scenario: Unknown team

- **WHEN** `team_id` does not resolve to a known team
- **THEN** the endpoint returns 404.

#### Scenario: Empty pool

- **WHEN** a team's league has no pool entries yet — the refresh job has not run
- **THEN** the endpoint returns an empty candidate list in a well-formed envelope rather than an error.
