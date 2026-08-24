## ADDED Requirements

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

### Requirement: Off-board tail from platform ADP

The undrafted pool SHALL extend past the end of the board using ESPN `kona_player_info` ADP ordering.

#### Scenario: Off-board tail

- **WHEN** the board's 161 entries are exhausted, as happens before the end of a 15-round draft
- **THEN** remaining players are supplied from ESPN `kona_player_info` ordered by ADP, marked as off-board, visually separated from board players, and never ranked above a board player in the shortlist.
