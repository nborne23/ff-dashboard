# player-projections

## ADDED Requirements

### Requirement: Independent projections alongside the platform's own
The system SHALL store a third-party point projection per player, season and scope, and
present it beside the league platform's projection without replacing or blending it.

#### Scenario: The two sources disagree
- **WHEN** the platform projects 16.2 and the third party projects 21.4
- **THEN** both numbers are shown **AND** the divergence is visually marked

#### Scenario: The two sources agree
- **WHEN** the projections differ by less than 1.5 points
- **THEN** the second number renders without emphasis

### Requirement: Scoring format resolved per league
The system SHALL store PPR, half-PPR and standard points for every projection and resolve
which to show from the requesting league's `scoring_type`.

#### Scenario: A custom-scoring league
- **WHEN** the league's `scoring_type` is `custom`
- **THEN** the projection is reported as `null` rather than defaulting to PPR

### Requirement: Matching never attaches the wrong player
The system SHALL match feed rows to players by ESPN id, then by normalized name plus NFL
team, then by team abbreviation for defenses.

#### Scenario: An ambiguous name
- **WHEN** two feed rows share a normalized name and NFL team
- **THEN** neither is matched

#### Scenario: A player with no NFL team
- **WHEN** a player's `nfl_team` is `FA`
- **THEN** the name tier is not consulted for that player

### Requirement: A total match failure is reported
The system SHALL record an error on the refresh run when players exist but none matched.

#### Scenario: The feed shape changes
- **WHEN** a refresh matches zero of N players
- **THEN** the run is recorded as failed with the count, rather than succeeding with an
  empty projection column
