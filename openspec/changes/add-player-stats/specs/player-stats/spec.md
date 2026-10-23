# player-stats

## ADDED Requirements

### Requirement: Player stats card
The system SHALL open a stats card when a player's name or headshot is clicked on My Team,
Matchups, Game Day, Waivers, or the lineup advice card.

#### Scenario: Opponent's player
- **WHEN** the user clicks an opponent's player on Matchups
- **THEN** the card shows that player's points from his slot in the same league

### Requirement: This week's stat line and points breakdown
The system SHALL show the league's points and projection, live status, the stat line, and a
line-by-line points breakdown for the selected week.

#### Scenario: ESPN league
- **WHEN** the player is on a roster in an ESPN league with a cached roster payload
- **THEN** the breakdown uses ESPN's per-stat league scoring **AND** sums to ESPN's total

#### Scenario: Estimated breakdown, week in progress
- **WHEN** no ESPN payload applies and the week is not final
- **THEN** the breakdown is labelled an estimate **AND** is not reconciled to the league score

#### Scenario: Estimated breakdown, final week
- **WHEN** no ESPN payload applies and the week is final
- **THEN** a reconciling line makes the breakdown total equal the league's score

### Requirement: Historical stats
The system SHALL show a per-week game log for each of the current and nine previous
regular seasons, with season totals and a by-season table, in the league's points format.

### Requirement: No upstream request on read
`GET /api/players/{id}/stats` SHALL serve only stored rows and cached payloads.
