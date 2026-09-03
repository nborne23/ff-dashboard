# lineup-advice

## ADDED Requirements

### Requirement: Optimal legal lineup
The system SHALL compute the point-maximising assignment of rostered players to starting
slots, subject to each player's platform-declared slot eligibility, and SHALL never leave
a slot empty in order to score more.

#### Scenario: The best player blocks a restricted slot
- **WHEN** two quarterbacks are eligible for both QB and OP, and a receiver is eligible
  for OP only
- **THEN** both quarterbacks start, rather than the receiver taking OP

#### Scenario: An IR player
- **WHEN** a player occupies the IR roster slot
- **THEN** they are never recommended to start, regardless of injury designation

### Requirement: Advice is scored consistently on both sides
The system SHALL apply identical scoring rules to the current lineup and the optimal one.

#### Scenario: An unstartable starter
- **WHEN** a starter is designated OUT and a healthy bench player projects less
- **THEN** the swap is still recommended, with reason `unstartable`

#### Scenario: A questionable starter
- **WHEN** a starter is designated Questionable
- **THEN** their projection is used unchanged

### Requirement: Only material changes are recommended
The system SHALL revert recommended swaps whose projected gain is below the materiality
threshold, and SHALL report a gain equal to the sum of the moves it presents.

#### Scenario: A trivial upgrade
- **WHEN** the optimal lineup beats the current one by 0.2 points
- **THEN** no move is presented **AND** the reported gain is 0

### Requirement: The two projection sources are compared, never blended
The system SHALL compute the lineup under both sources and report whether they agree,
using one named source for the recommendation itself.

#### Scenario: Both sources pick the same lineup
- **WHEN** the platform and independent projections produce the same materialised lineup
- **THEN** `sources_agree` is true

### Requirement: Absent data is distinguishable from an optimal lineup
The system SHALL report whether it could evaluate the roster at all.

#### Scenario: No projections stored
- **WHEN** the chosen source has no projection for any player
- **THEN** `advice_available` is false and the UI does not claim the lineup is optimal

### Requirement: Cross-platform injury detail
The system SHALL resolve an ESPN athlete id for players whose own platform id is not one,
so injury detail is available on every platform.

#### Scenario: A Yahoo-sourced player
- **WHEN** the player's `espn_athlete_id` is populated
- **THEN** `detail_supported` is true and the injury sweep includes them

#### Scenario: A team defense
- **WHEN** the player is a D/ST
- **THEN** `detail_supported` is false whatever the bridge holds
