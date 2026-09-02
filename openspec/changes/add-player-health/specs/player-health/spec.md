# player-health

## ADDED Requirements

### Requirement: Normalized injury designations
The system SHALL normalize every platform injury code to `ACTIVE|Q|D|O|IR|PUP|DTD|SUSP|NFI`,
or to `null` when the code is unrecognized.

#### Scenario: ESPN's healthy sentinel
- **WHEN** ESPN reports `injuryStatus: "NORMAL"`
- **THEN** the player's `injury_status` is `ACTIVE`, not `null`

#### Scenario: An unrecognized code is never asserted as healthy
- **WHEN** either platform reports a code outside the mapped set
- **THEN** `injury_status` is `null` and the code is logged at WARNING

### Requirement: Injury designation is visible wherever a player is listed
The system SHALL render a labelled badge for any non-`ACTIVE` designation on the MyTeam
roster, the Game Day mirrored roster, the Head-to-Head table and the Waivers table.

#### Scenario: A questionable starter keeps its kickoff time
- **WHEN** a starter is `Q` and their game has not kicked off
- **THEN** the row shows the `Q` badge beside the position pill **AND** the Status column
  still shows the kickoff time

### Requirement: Per-player health detail
The system SHALL expose `GET /api/players/{player_id}/injury` returning the most recent
stored report — injury type, body location, side, detail, projected return date, and ESPN's
short and long comments — without making an upstream request.

#### Scenario: No report stored
- **WHEN** no report exists for the player
- **THEN** the endpoint returns `200` with `report: null`

#### Scenario: A player with no ESPN athlete id
- **WHEN** the player is Yahoo-sourced or a D/ST
- **THEN** the endpoint returns `200` with `report: null` and `detail_supported: false`
