## ADDED Requirements

### Requirement: League standings

The system SHALL expose every team in a league, ordered as standings, so a user can see the whole league rather than only their own team and its current opponent.

#### Scenario: Standings row shape

- **WHEN** a standings row is returned
- **THEN** it carries the full `Team` entity, its division id, and its position in the ordering
- **AND** the user's own team is identifiable from the existing `is_user_team` flag rather than a separate marker.

#### Scenario: Ordering follows the platform's own seed

- **WHEN** teams are ordered
- **THEN** the platform's reported playoff seed is the primary key, so the standings match what the platform's own site displays.

#### Scenario: Ordering stays deterministic when the platform reports no seed

- **WHEN** the platform reports a seed of zero for every team in a league, as it does before a season begins
- **THEN** ordering falls back to wins, then points for, then the team's stable id
- **AND** the final id tiebreak is required, not decorative: in the preseason every team has an identical record and zero points, so without it the rendered order is whatever the database happened to return and can differ between two loads of the same page.

#### Scenario: Divisions do not interleave

- **WHEN** a league has more than one division
- **THEN** rows are grouped by division before the seed is applied, so two divisions' seeds do not interleave into an order that looks scrambled rather than obviously wrong.

## MODIFIED Requirements

### Requirement: Normalized internal entities

The system SHALL define a single set of internal entities that is platform-agnostic. Frontend code SHALL only ever consume these normalized types — never raw Yahoo or ESPN payloads.

The entities are: `Platform`, `League`, `Team`, `Player`, `RosterSlot`, `Matchup`, `MatchupSlot`, `SeasonWeek`, `LiveNflGame`, `Connection`, `PlayerPoolEntry`.

#### Scenario: Team carries a logo URL

- **WHEN** a `Team` is serialized
- **THEN** it carries `logo_url`, a **local** URL pointing at this application's own logo route, or null when the team has no logo
- **AND** it SHALL NOT carry the upstream logo URL, because the upstream host rejects unauthenticated requests for uploaded logos — a client given that URL would render a broken image.

#### Scenario: The logo URL is derived, not stored

- **WHEN** `logo_url` is produced
- **THEN** it is derived by convention from the team's platform and id, the same way the player headshot URL already is, so no local URL is persisted and the route can change without a migration.

### Requirement: Read API for the frontend

The system SHALL expose REST endpoints that the frontend consumes, returning JSON shaped exactly like the normalized entities above.

#### Scenario: League standings for a team

- **WHEN** the frontend requests `GET /api/teams/{team_id}/league`
- **THEN** the envelope carries that team's league metadata and every team in it, ordered as standings.

#### Scenario: Unknown team for standings

- **WHEN** `team_id` does not resolve to a known team
- **THEN** the endpoint returns 404.

#### Scenario: Team logo image route

- **WHEN** the frontend requests `GET /api/team-logos/{platform}/{team_id}`
- **THEN** the cached image is returned with the content type recorded at fetch time, and a generic crest is returned when no usable logo exists
- **AND** the path carries **no file extension**, because the cached bytes may be vector or raster and the format is a property of the stored record rather than of the URL.
