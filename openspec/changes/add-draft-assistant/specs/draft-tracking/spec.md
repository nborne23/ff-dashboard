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

### Requirement: ESPN and manual pick reconciliation

The system SHALL reconcile polled ESPN picks against manually entered picks without silently discarding the user's input.

#### Scenario: ESPN corrects a manual pick

- **WHEN** a poll returns a pick at an `overall_pick` that already holds a manual row naming a different player
- **THEN** the ESPN player becomes authoritative, `source` is upgraded to `espn`, and the correction is surfaced in the UI as an explicit corrected-pick notice rather than applied silently.

#### Scenario: Manual entry ahead of the poll is preserved

- **WHEN** manual rows exist at pick numbers beyond the highest pick ESPN has reported
- **THEN** those rows are left untouched, because the user is running ahead of the poll rather than disagreeing with it.

#### Scenario: Agreement is a no-op

- **WHEN** a polled pick matches an existing row's player at the same `overall_pick`
- **THEN** only `source` is upgraded to `espn`, no duplicate row is written, and no fingerprint change is published.

### Requirement: League settings resolved from the platform

The system SHALL read team count, roster slots, scoring, roster size, and draft order from ESPN `mSettings`/`mDraftDetail`, falling back to the static `league_config.json` only when the platform is unreachable, and SHALL warn when the two disagree. The static file's values — 12 teams, half-PPR, 1 QB / 2 RB / 2 WR / 1 TE / 2 FLEX / 1 DST, no kicker, user at slot 1 — are unconfirmed and SHALL NOT be assumed.

#### Scenario: Platform settings preferred

- **WHEN** ESPN league settings are available
- **THEN** they populate the active league configuration and the static file is used only for fields ESPN does not expose.

#### Scenario: Disagreement warns loudly

- **WHEN** an ESPN-reported setting differs from the static file
- **THEN** a persistent warning naming each differing field is shown on the Draft screen, and the ESPN value is used.

#### Scenario: Fallback is explicit

- **WHEN** ESPN settings cannot be read
- **THEN** the static configuration is used and the screen displays a persistent banner naming every field that could not be confirmed.

#### Scenario: Lineup slot translation reused

- **WHEN** roster slots are read from ESPN `mSettings`, which returns `lineupSlotCounts` keyed by `lineupSlotId`
- **THEN** the existing `platforms/espn/slot_table.py` translation is used rather than a second lookup table.

#### Scenario: Bench size defaults

- **WHEN** neither ESPN nor the static config states a bench size
- **THEN** bench size defaults to 6 and remains user-configurable.

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

#### Scenario: Off-board tail

- **WHEN** the board's 161 entries are exhausted, as happens before the end of a 12-team 15-round draft
- **THEN** remaining players are supplied from ESPN `kona_player_info` ordered by ADP, marked as off-board, and visually separated from board players.

### Requirement: Armed-only ESPN draft polling

The system SHALL register a `poll_draft` job in the scheduler registry **without** a trigger and SHALL activate it only on explicit request. When no draft session is armed, the feature SHALL add no background work and SHALL NOT alter the existing adaptive refresh cadence.

#### Scenario: No trigger at boot

- **WHEN** the process starts
- **THEN** `poll_draft` is present in the `JOBS` registry and invokable via `POST /api/admin/refresh`, but the scheduler holds no trigger for it and it never runs on its own.

#### Scenario: Arming starts the poll

- **WHEN** the frontend POSTs `/api/draft/arm` with a league
- **THEN** a `draft_sessions` row is created with status `armed`, an interval trigger is added at the configured poll interval (default 3 seconds, valid range 2–5), and a wall-clock ceiling is set at `armed_at + 6 hours`.

#### Scenario: Picks ingested while in progress

- **WHEN** a poll returns `inProgress: true`
- **THEN** every pick in the payload is upserted through the same path as manual picks with `source='espn'`, the current round and overall pick and on-the-clock team are recorded on the session, and the `draft` scope is published if anything changed.

#### Scenario: Auto-disarm on completion

- **WHEN** three consecutive polls return `inProgress: false` **and** the pick set is complete for the league's round count
- **THEN** the session is disarmed, its trigger is removed, and status becomes `completed`. A single `inProgress: false` tick SHALL NOT disarm the session, because a pre-draft pause reports the same flag.

#### Scenario: Wall-clock ceiling

- **WHEN** a session remains armed past its ceiling
- **THEN** it disarms regardless of `inProgress`, so a stalled draft or an unexpected payload shape cannot poll indefinitely.

#### Scenario: Upstream errors back off then stop

- **WHEN** a poll returns HTTP 429 or 5xx
- **THEN** the poll interval backs off to 10 seconds; after five consecutive failures the session disarms and the UI states plainly that live tracking has stopped and manual entry is the path forward.

#### Scenario: Explicit disarm

- **WHEN** the frontend POSTs `/api/draft/disarm`
- **THEN** the trigger is removed immediately, the session's `disarmed_at` is set, and all recorded picks are retained.

### Requirement: Draft polling bypasses the HTTP cache

The draft poll SHALL fetch `mDraftDetail` without consulting or writing `http_cache`. The existing cached-fetch path applies TTLs of one to six hours, which would serve stale draft state through a three-second poll loop with no error surfaced anywhere.

#### Scenario: No cache read

- **WHEN** the draft poller fetches draft detail
- **THEN** the request goes to ESPN on every tick and no `http_cache` lookup occurs, even when a matching entry exists.

#### Scenario: No cache write

- **WHEN** a draft fetch completes
- **THEN** no `http_cache` row is created or updated, verified by an explicit regression test so that a future consolidation of ESPN fetch paths cannot silently reintroduce caching.

### Requirement: Draft polling suppresses per-tick audit rows

The system SHALL NOT write a `refresh_runs` row per draft poll. At a three-second cadence across a three-hour draft this would add roughly 3,600 rows to the table the Settings screen reads for last-refresh status.

#### Scenario: Audit suppressed

- **WHEN** `poll_draft` executes through the shared job runner
- **THEN** no `refresh_runs` row is written, and instead `last_poll_at` and `last_error` are updated on the single `draft_sessions` row.

#### Scenario: Failures remain visible

- **WHEN** a draft poll fails
- **THEN** the failure is logged at WARN level and recorded in `last_error`, so suppressing the audit row does not make failures invisible.

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
