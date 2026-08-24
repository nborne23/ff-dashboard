## ADDED Requirements

### Requirement: Draft screen

The system SHALL provide a Draft screen at `/draft`, reachable from the sidebar, built from the existing design tokens and primitives so it is visually continuous with the rest of GridIron.

#### Scenario: Route and navigation

- **WHEN** the user opens `/draft`
- **THEN** the Draft screen renders inside the existing app shell with sidebar, topbar, and aurora, and the sidebar Draft item shows as active.

#### Scenario: Design system reuse

- **WHEN** the screen is built
- **THEN** it uses the existing CSS custom properties and existing primitives rather than introducing a parallel styling approach or a chart dependency.

#### Scenario: Usable on a phone

- **WHEN** the screen is viewed at the existing narrow breakpoint
- **THEN** the board, roster panel, and recommendation shortlist remain usable with large tap targets for mark-drafted, because the screen is used on a phone during a live draft.

### Requirement: Live board

The Draft screen SHALL present the full player pool, filterable and sortable, with drafted players visibly removed from consideration.

#### Scenario: Filter and sort

- **WHEN** the user filters by position or sorts by ADP, tier, or risk
- **THEN** the list updates immediately without a server round trip beyond the already-loaded pool.

#### Scenario: Drafted players de-emphasized

- **WHEN** a player has been drafted
- **THEN** he is greyed out and struck through rather than removed from the list, so the user can see what went and to whom.

#### Scenario: Off-board players separated

- **WHEN** the pool extends past the end of the board
- **THEN** off-board players appear in a visually distinct section labelled as not on the user's board.

#### Scenario: Out-for-season players findable

- **WHEN** the user searches for a player flagged `out_for_season`
- **THEN** he is found and shown with a clear season-ending marker, while remaining excluded from the draftable pool.

### Requirement: Mark drafted and undo

The screen SHALL make marking a pick a single tap and SHALL make undo immediately available, because mis-taps happen constantly during a live draft.

#### Scenario: One-tap mark

- **WHEN** the user taps a player's mark-drafted control
- **THEN** the pick is recorded, distinguishing a pick by the user from a pick by another team, and the board updates within one render.

#### Scenario: Undo always reachable

- **WHEN** any pick has been recorded
- **THEN** an undo control is visible without scrolling and reverses the most recent pick.

### Requirement: Current pick control

The screen SHALL always display the current overall pick and round, and SHALL let the user correct it, because tier urgency and the tier-break alarm are computed from it and a user who marks only some picks would otherwise see alarms fire against a wrong pick number.

#### Scenario: Pick number visible

- **WHEN** the Draft screen is open
- **THEN** the current overall pick, the round, and the number of picks until the user's next turn are visible without interaction.

#### Scenario: Pick number correctable

- **WHEN** the user has skipped marking picks and sets the current overall pick directly
- **THEN** the value updates and recommendations, tier urgency, and the alarm all recompute against it.

### Requirement: Roster construction panel

The screen SHALL show the user's roster as it fills, against the league's actual starter requirements.

#### Scenario: Slots filled and unfilled

- **WHEN** the user has drafted players
- **THEN** the panel shows each starter slot as filled or unfilled using the league's real roster shape, with FLEX shown as its own slots.

#### Scenario: Bye collisions surfaced

- **WHEN** 3 or more projected starters share a bye week
- **THEN** the panel warns, naming the week and the players.

#### Scenario: No kicker slot

- **WHEN** the league has no kicker slot
- **THEN** none is shown, and the freed bench slot is surfaced as a handcuff or second-DST opportunity.

### Requirement: Recommendations surfaced prominently

The screen SHALL make the recommended next pick the most prominent element when the user is on the clock, with its reasoning visible without interaction.

#### Scenario: Shortlist with reasons

- **WHEN** the user is on the clock
- **THEN** the 3–5 ranked candidates are shown at the top of the screen, each with its one-line reason, and the cited heuristic is inspectable.

#### Scenario: Tier-break alarm is loud

- **WHEN** the tier-break condition fires
- **THEN** the warning is visually prominent and states the position, the count remaining, and the picks until the user's next turn.

#### Scenario: Turn pair shown together

- **WHEN** the user holds back-to-back picks
- **THEN** both are presented as a pair rather than as one pick at a time.

### Requirement: Player detail

The screen SHALL expose the full scouting content of the board for any player, with attribution that distinguishes measured-accuracy analysts from unverified ones.

#### Scenario: Detail content

- **WHEN** the user opens a player
- **THEN** the note, thesis, take-in-round, sleeper category, catalyst, format fit, injury tags, bye, tier labels, risk, and analyst takes are shown.

#### Scenario: Attribution distinguishes accuracy

- **WHEN** analyst takes are displayed
- **THEN** each source is marked according to its `verified_accuracy` flag, so a measured-accuracy analyst is visually distinguishable from a popular-but-unverified one.

#### Scenario: Injury tags labelled as advisory

- **WHEN** injury tags are shown
- **THEN** they are presented as a search aid rather than as curated fact, because they are keyword-derived from note prose and produce false positives.

### Requirement: Live updates over SSE with a draft-scoped fallback

The screen SHALL receive pick updates by invalidating query keys on the existing SSE channel and SHALL NOT poll the backend while SSE is connected. The `draft` scope SHALL be registered in the frontend's scope-to-query-key mapping.

#### Scenario: Scope mapping registered

- **WHEN** a `data.changed` event carrying scope `"draft"` arrives
- **THEN** the mapping resolves it to the draft query keys and they are invalidated. The mapping is a hardcoded whitelist that returns null and silently does nothing for unknown scopes, so this SHALL be covered by an explicit test.

#### Scenario: No polling while connected

- **WHEN** SSE is connected and the Draft screen is mounted
- **THEN** the screen performs no interval polling and updates only on invalidation.

#### Scenario: Fast fallback when disconnected

- **WHEN** SSE is disconnected while the Draft screen is mounted
- **THEN** draft queries poll at approximately 5 seconds, overriding the app-wide 5-minute fallback which is far too slow for a live draft. This override SHALL apply only while the Draft screen is mounted.

### Requirement: Draft screen works without live integration

The screen SHALL be fully usable with no working ESPN draft integration, since manual entry is the primary path and the integration is an accelerator.

#### Scenario: Manual-only operation

- **WHEN** live tracking has never been armed or is unavailable
- **THEN** the board, mark-drafted, undo, roster panel, tier alarm, and recommendations all function normally against manually entered picks.

#### Scenario: Unresolved matches gate live mode only

- **WHEN** board entries remain below the match-confidence threshold
- **THEN** the screen presents the match-resolution list and blocks live mode, while manual operation remains fully available.

### Requirement: Draft screen is gated by a build-time flag

The Draft screen and its sidebar entry SHALL be gated behind a single build-time flag, so the feature can be hidden between drafts without deleting code. The backend API and board import SHALL remain available regardless of the flag.

#### Scenario: Flag off

- **WHEN** the flag is false
- **THEN** the sidebar shows no Draft entry, `/draft` does not route, and the screen tree-shakes out of the production bundle.

#### Scenario: Backend unaffected

- **WHEN** the flag is false
- **THEN** `/api/draft/*` continues to serve and the board import CLI continues to run, because the flag gates only the UI surface.
