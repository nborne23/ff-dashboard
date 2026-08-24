## ADDED Requirements

### Requirement: Session control and status

The screen SHALL let the user start and stop live tracking explicitly and SHALL always make the current tracking state legible.

#### Scenario: Arm and disarm

- **WHEN** the user starts live tracking
- **THEN** the session arms and the screen shows the current round, overall pick, and which team is on the clock; stopping tracking disarms it while retaining all recorded picks.

#### Scenario: Tracking failure is loud

- **WHEN** live tracking stops because of repeated upstream failures
- **THEN** a prominent banner states that live tracking has stopped and that manual entry continues to work; the screen SHALL NOT appear to be tracking when it is not.

#### Scenario: Settings disagreement warned

- **WHEN** ESPN-reported league settings differ from the static configuration, or could not be read
- **THEN** a persistent banner names the affected fields.

