## ADDED Requirements

### Requirement: Draft pick log with source provenance

The system SHALL record draft picks in a single `draft_picks` table carrying `overall_pick` (unique), the drafted player, `drafted_by_team`, `is_my_pick`, and `source` (`manual` | `espn`). Manually entered picks and ESPN-polled picks SHALL be written through the same service path. Draft state SHALL NOT be modeled as a mirror of ESPN with manual entry as an escape hatch.

#### Scenario: Manual pick recorded

- **WHEN** the user marks a player drafted from the Draft screen
- **THEN** a `draft_picks` row is written with `source='manual'` and `overall_pick` set to the next unused pick number, the player leaves the undrafted pool, and the `draft` SSE scope is published.

#### Scenario: Pick attributed to the user

- **WHEN** a pick is marked as the user's own rather than another team's
- **THEN** `is_my_pick` is true and the player is counted toward the user's roster construction; picks by other teams remove the player from the pool without affecting roster need.

#### Scenario: Undo restores exact prior state

- **WHEN** the user undoes the most recent pick
- **THEN** the row at the highest `overall_pick` is deleted regardless of its `source`, the player returns to the undrafted pool, roster counts revert, and recommendations recompute — producing state identical to before that pick was recorded.

#### Scenario: State survives a restart

- **WHEN** the backend process restarts mid-draft
- **THEN** every recorded pick and the active session are recovered from SQLite and the Draft screen resumes with no loss.

### Requirement: Explicit current pick number

The system SHALL track the current overall pick as an explicit, user-correctable value rather than inferring it from the count of recorded picks. `picks_until_next` — the sole input to tier urgency and the tier-break alarm — derives from it, and during a real draft the user marks only some picks, so an inferred count drifts below the true pick number and every urgency calculation silently fires against a wrong value.

#### Scenario: Manual marking advances the pick

- **WHEN** the user marks a pick
- **THEN** the current overall pick advances by one.

#### Scenario: User corrects the pick number

- **WHEN** the user has skipped marking some picks and sets the current overall pick directly
- **THEN** that value is stored, `picks_until_next` recomputes from it, and the tier alarm re-evaluates.

#### Scenario: ESPN overrides when armed

- **WHEN** a draft session is armed and a poll reports the authoritative current pick
- **THEN** the polled value replaces the locally tracked one.

### Requirement: League settings resolution with explicit unconfirmed reporting

The system SHALL resolve league shape through a single layer that prefers platform-sourced values, falls back to the static `league_config.json`, and returns a per-field conflict list naming every field that disagrees or could not be confirmed. The static file's values SHALL NOT be presented as authoritative.

The board's original static assumptions were wrong on nearly every axis. Confirmed from ESPN `mSettings` for the user's real league: **10 teams** (not 12), **3 FLEX slots** (not 2), 10 starters, 5 bench, 1 IR, no kicker, user at slot 1. `league_config.json` now records these as confirmed-from-platform rather than assumed.

#### Scenario: Conflict list drives a persistent banner

- **WHEN** a resolved field comes from the static file rather than the platform
- **THEN** it appears in the conflict list with its static value and a note that it is unconfirmed, and the Draft screen renders a persistent banner naming each such field.

#### Scenario: Lineup slot translation reused

- **WHEN** roster slots are read from ESPN `mSettings`, which returns `lineupSlotCounts` keyed by `lineupSlotId`
- **THEN** the existing `platforms/espn/slot_table.py` translation is used rather than a second lookup table.

#### Scenario: Bench size defaults

- **WHEN** neither the platform nor the static config states a bench size
- **THEN** bench size defaults to 6 and remains user-configurable.

#### Scenario: Only team count is platform-read today

- **WHEN** league shape is resolved
- **THEN** team count is taken from the persisted `League` row when an enabled ESPN league exists, and every other field resolves from the static file and is reported unconfirmed — because no raw `mSettings` payload is persisted yet. Reading roster slots, scoring, and draft slot live from the platform is deferred.

### Requirement: Snake pick-number math for arbitrary slot and team count

The system SHALL compute the user's pick numbers from `(teams, slot, rounds)` rather than reading the hardcoded 12-team slot-1 list in `league_config.json`. Structural reasoning about back-to-back picks SHALL derive from that computation.

#### Scenario: Slot 1 in a 12-team draft

- **WHEN** slot is 1, teams is 12, and rounds is 15
- **THEN** the computed pick numbers are 1, 24, 25, 48, 49, 72, 73, 96, 97, 120, 121, 144, 145, 168, 169.

#### Scenario: Arbitrary slot

- **WHEN** slot is 7 in a 10-team, 16-round draft
- **THEN** pick numbers follow the snake order for that slot and no value from the static 12-team list appears.

#### Scenario: Back-to-back pairs identified

- **WHEN** two of the user's consecutive picks differ by exactly 1
- **THEN** they are flagged as a turn pair, and the recommender is given the pair rather than being asked for two independent single-pick answers.

#### Scenario: Picks until next turn

- **WHEN** the current overall pick is known
- **THEN** the system reports how many picks remain before the user's next selection, which is the input the tier-urgency calculation depends on.

### Requirement: Undrafted player pool

The system SHALL expose the set of draftable players as the board minus recorded picks, extended past the end of the board by ESPN ADP ordering.

#### Scenario: Pool excludes drafted players

- **WHEN** the pool is requested
- **THEN** every player with a `draft_picks` row is excluded, regardless of pick source.

#### Scenario: Season-ending injuries excluded but searchable

- **WHEN** a board entry has `out_for_season` true
- **THEN** it is excluded from the draftable pool and from every recommendation, but remains findable by search so the user does not wonder where the player went.


### Requirement: Draft change signalling over SSE

The system SHALL publish draft changes on the existing SSE channel using a new `draft` scope, following the established principle that events carry scope names and clients refetch through REST.

#### Scenario: Fingerprint published on change

- **WHEN** a poll or manual entry changes the highest recorded pick, the pick count, the current overall pick, or the session status
- **THEN** a `data.changed` event is published carrying scope `"draft"`.

#### Scenario: Fingerprint works without a session

- **WHEN** picks exist but no `draft_sessions` row does, which is the normal state in manual-only operation before live tracking has ever been armed
- **THEN** the fingerprint is computed from the pick terms alone and the session term is omitted rather than raising.

#### Scenario: Unchanged polls are silent

- **WHEN** a poll returns state identical to the previous tick
- **THEN** no event is published, so an idle draft produces no SSE traffic beyond the existing heartbeat.
