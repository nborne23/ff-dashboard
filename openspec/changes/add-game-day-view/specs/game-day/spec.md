## ADDED Requirements

### Requirement: Game Day screen

The frontend SHALL provide a `/gameday` screen rendering one panel per matchup involving a user team, all visible simultaneously, sourced from a single `useGameDay(week)` query.

#### Scenario: One panel per matchup

- **WHEN** the Game Day screen loads with N matchups in the envelope
- **THEN** exactly N panels render, each keyed by `team_id`, and no panel issues a request of its own.

#### Scenario: Header summary

- **WHEN** panels have rendered
- **THEN** the screen header states the matchup count, the number of matchups where the user's team leads (in `--move`), and — only when at least one player is live — the total live-player count (in `--live`).

#### Scenario: Nothing connected

- **WHEN** no platform is connected
- **THEN** the screen renders the shared `EmptyState` prompting the user to connect a league, and no panels or control bar are shown.

#### Scenario: Envelope error

- **WHEN** the Game Day request fails
- **THEN** the shared `ErrorCard` renders in place of the stage, and any previously-rendered layout controls remain interactive.

#### Scenario: Loading

- **WHEN** the Game Day query is loading with no cached data
- **THEN** skeleton panels render matching the loaded panel geometry for the active arrangement, so the stage does not reflow when data arrives.

### Requirement: Panel anatomy and score identity

Each panel SHALL render the complete head-to-head for its matchup in a fixed vertical order: meta row, score row, stat strip, roster disclosure, mirrored roster.

#### Scenario: Meta row

- **WHEN** a panel renders
- **THEN** the meta row shows the platform pill (`YAHOO` or `ESPN`), the user's team name, the league name, a live pill with the panel's live-player count when that count is greater than zero, a `FINAL` pill when the matchup is complete, and a spotlight control.

#### Scenario: Score identity by color and brightness

- **WHEN** a panel renders both scores
- **THEN** the user's team label uses `--move` and the opponent's uses `--stand`, both score *values* render white, and the trailing side's value drops to `--text-secondary` — so the leader is distinguishable by brightness alone without reading a number.

#### Scenario: Margin chip

- **WHEN** the two scores differ by at least 0.05
- **THEN** a margin chip renders between them carrying the explicit sign (`+16.2` / `-13.5`), styled positive when the user leads and negative when trailing.

#### Scenario: Tied score

- **WHEN** the two scores differ by less than 0.05
- **THEN** the margin chip reads `TIED` in its neutral style and neither side is marked as trailing.

#### Scenario: Stat strip

- **WHEN** a panel renders
- **THEN** the stat strip shows Projected (`proj` vs `opp_proj`, rounded to whole points), Win prob (whole percent), and Yet to play (`remaining.mine` vs `remaining.theirs`).

### Requirement: Mirrored roster rows

The panel roster SHALL render each starter slot as a single row carrying both teams, reading outward from a center cell, rather than as a three-column table.

#### Scenario: Row layout

- **WHEN** a roster row renders
- **THEN** the user's player (name, NFL team, points) is left-aligned against the center cell, the opponent's mirrors it on the right, and the center cell holds the slot label and the per-slot differential.

#### Scenario: Orientation

- **WHEN** the user's team is the away side of the matchup
- **THEN** the user's players still render on the left of every row, derived via `orientSlot(slot, iAmHome)` from the existing Head-to-Head orientation module rather than a re-derived ternary.

#### Scenario: Per-slot differential

- **WHEN** the two players' points differ by less than 0.05
- **THEN** the center cell shows a neutral em-dash; **OTHERWISE** it shows the signed difference styled positive or negative from the user's perspective.

#### Scenario: Unplayed players are not real zeros

- **WHEN** a player's side has `game_state` of `pre`
- **THEN** that side renders visually dimmed to distinguish "has not played" from a player who scored zero, whose state is `post`.

#### Scenario: Live player marker

- **WHEN** a player's side is live
- **THEN** a pulsing live dot renders on that side. This dot SHALL be the only continuously-animating element in the view.

### Requirement: Container-query density ladder

Panel density SHALL be a function of the panel's own rendered width via CSS container queries, not of the viewport, the arrangement mode, or a React prop.

#### Scenario: Density steps

- **WHEN** a panel's inline size falls in a band
- **THEN** it renders at that band's density: below 360px, 26px score and 12px player names with the NFL team hidden; 360–539px, 32px score and 13px names; 540px and above, 46px score and 15px names; 900px and above, 64px score and 17px names.

#### Scenario: Roster renders unconditionally

- **WHEN** a panel renders at any width
- **THEN** the roster markup is present in the DOM regardless of width or arrangement, and visibility below 540px is controlled by CSS alone — so a manually widened panel reveals its roster without any width-measuring JavaScript.

#### Scenario: Manual disclosure overrides the query

- **WHEN** the user activates the panel's disclosure control
- **THEN** an explicit open/shut attribute on the panel overrides the container query in both directions, and that override is recorded in the persisted layout.

#### Scenario: The override is three-valued

- **WHEN** a panel's disclosure state is stored
- **THEN** it is one of open, shut, or **no preference** — and no-preference is the default, in which case no attribute is emitted at all and the container query alone decides. Open and shut are therefore recorded in two separate id lists (`openIds` / `shutIds`), because a single list cannot distinguish "the user shut this" from "the user has not chosen", and conflating them would make a panel that the query opened impossible to close.

#### Scenario: Minimum legible size

- **WHEN** any density band renders
- **THEN** no value carrying meaning renders below 15px, per the across-the-room reading constraint.

### Requirement: Attention model

The panel SHALL signal change through four cues, each bound to a distinct event class so they never compete.

#### Scenario: Points change flashes its row

- **WHEN** a player's points change between refreshes
- **THEN** that row flashes `--live` at 26% opacity decaying to transparent, driven by the existing `useChangedValuePulse` hook. The duration matches that hook's `PULSE_ANIMATION_MS`, which is the authority: the hook clears its attribute on that timer, so a CSS animation declared longer would simply be cut off mid-cycle rather than running to completion.

#### Scenario: Lead flip pulses the panel

- **WHEN** the sign of a panel's margin changes between refreshes
- **THEN** the panel background double-pulses `--move` at 22% over roughly 1.4s.

#### Scenario: Lead flip ignores magnitude

- **WHEN** a panel's margin changes without crossing zero
- **THEN** no lead-flip pulse fires.

#### Scenario: Live panels are outlined

- **WHEN** any slot in a panel reports `home_is_live` or `away_is_live`
- **THEN** the panel border renders `--live` at 45% with a soft outer glow, persistently, for as long as that holds.

#### Scenario: Settled panels dim

- **WHEN** a panel's `matchup.is_complete` is true
- **THEN** the panel drops to 52% opacity persistently, and hovering it restores full opacity.

#### Scenario: Panel state derives from authoritative fields

- **WHEN** the panel computes its live and settled states
- **THEN** it reads `is_complete` from the matchup and `*_is_live` from the slots, and SHALL NOT derive either by comparing `game_state` values — `game_state` is null for rows written by discovery, which would make a state derived from it permanently false.

#### Scenario: Position is stable

- **WHEN** any attention cue fires
- **THEN** no panel changes position or size. Panels reposition only on an explicit arrangement, sort, resize, or reorder action by the user.

### Requirement: Arrangement, ordering, and resize

The screen SHALL provide a control bar for arranging panels, and the arrangement SHALL persist across restarts.

#### Scenario: Arrangement modes

- **WHEN** the user selects an arrangement
- **THEN** the stage switches between 2-across, 3-across, 4-column, and spotlight (one large panel plus a rail), and the active mode is reflected as a data attribute on the stage.

#### Scenario: Manual resize

- **WHEN** the user drags a panel's resize handle
- **THEN** that panel's span is set to 1 or 2 columns and 1 or 2 rows, and — because density follows rendered width — the widened panel adopts the corresponding density band with no further action.

#### Scenario: Drag to reorder

- **WHEN** the user drags one panel onto another
- **THEN** the dragged panel takes the target's position in the order.

#### Scenario: Reordering cancels auto-sort

- **WHEN** a drag-reorder completes while an auto-sort mode is active
- **THEN** `sortMode` reverts to `"manual"`. An auto-sort mode and a hand-placed order are mutually exclusive states, not layers.

#### Scenario: Auto-sort modes

- **WHEN** `sortMode` is `"margin"`
- **THEN** panels order by smallest absolute margin first; **WHEN** it is `"live"`, panels order by descending live-player count.

#### Scenario: Spotlight

- **WHEN** the user activates a panel's spotlight control or double-clicks its header
- **THEN** that panel renders alone in an overlay at spotlight density with its roster shown, and Escape or a click outside dismisses it.

#### Scenario: Gestures do not collide

- **WHEN** the user begins a resize drag
- **THEN** the panel-reorder drag does not start, and vice versa — resize is bound to a corner handle and reorder to the panel header.

### Requirement: Layout persistence and reconciliation

The layout SHALL persist to the existing `gridiron-ui-tweaks` store and SHALL reconcile against the live team set on every read.

#### Scenario: Persisted shape

- **WHEN** the layout is written
- **THEN** it stores `mode`, `order` (team ids), `spans`, `openIds`, `shutIds`, and `sortMode`, with the id collections serialized as arrays so they survive JSON round-tripping — never as `Set`s, which rehydrate empty.

#### Scenario: Survives restart

- **WHEN** the app process restarts and the screen reloads
- **THEN** the previous arrangement, order, spans, disclosure overrides, and sort mode are restored.

#### Scenario: Departed teams are dropped

- **WHEN** the persisted order names a team id absent from the current envelope
- **THEN** that id is ignored and no empty panel renders.

#### Scenario: New teams are appended

- **WHEN** the envelope contains a team id absent from the persisted order
- **THEN** that id is appended to the order and its panel renders. A newly connected league SHALL NOT be invisible because the stored order predates it.
