## ADDED Requirements

### Requirement: Five-screen application shell

The frontend SHALL implement exactly five primary screens, each routed and reachable from the persistent sidebar: Dashboard, My Team, Head-to-Head, Season, Settings.

#### Scenario: Routing

- **WHEN** the user clicks a sidebar item
- **THEN** the URL updates to one of `/`, `/team/:teamId`, `/team/:teamId/h2h`, `/team/:teamId/season`, `/settings`, and the corresponding screen renders without unmounting the persistent shell (sidebar + topbar).

#### Scenario: Sub-navigation under "My Teams"

- **WHEN** the user expands the "My Teams" sidebar group
- **THEN** every connected team renders as a sub-item with its platform color dot (purple for Yahoo, red for ESPN), and selecting one navigates to `/team/:teamId`.

### Requirement: Pixel-fidelity to the design bundle

The frontend SHALL match the prototype's visual output. Specifically: backgrounds (`#000` body, `#1C1C1E` cards, 12px radius, no borders/shadows), inset 0.5px `#38383A` separators, category color usage (label/icon/chart only — values stay white), aurora gradient at top, sidebar 3px pink active-edge, topbar week navigator + day-of-week activity rings + live badge.

#### Scenario: Design tokens

- **WHEN** the frontend boots
- **THEN** every color, spacing, font-size, border-radius, and breakpoint is defined as a CSS custom property under `:root`, sourced from a single `tokens.css` lifted from the prototype's `styles.css`. No hex codes outside `tokens.css`. No Tailwind.

#### Scenario: Per-screen aurora

- **WHEN** the active screen changes
- **THEN** the `--aurora-color` CSS variable is set to:
  - Dashboard / My Team: `rgba(255, 45, 85, 0.18)`
  - H2H: `rgba(191, 90, 242, 0.18)`
  - Season: `rgba(100, 210, 255, 0.18)`
  - Settings: `rgba(142, 142, 147, 0.18)`

#### Scenario: Responsive breakpoints

- **WHEN** viewport width crosses thresholds
- **THEN** at `≤ 1023px` the sidebar collapses to a 56px icon rail (labels hidden, sub-items hidden); at `≤ 767px` the sidebar is hidden entirely and `dashboard-grid` / `team-grid` collapse to single column.

### Requirement: Dashboard screen

The Dashboard SHALL show all connected teams as a card grid alongside an Insights rail.

#### Scenario: Team grid

- **WHEN** Dashboard loads with N connected teams
- **THEN** N team cards render in an 8/4 split (team grid : insights rail), each card showing team name + platform pill + live dot (if any roster player is live), score line (winning side white / losing side secondary), `vs {opp}`, record, rank, and a 6-week sparkline.

#### Scenario: Insights rail

- **WHEN** Dashboard loads
- **THEN** the rail shows three cards: Top Performer (highest-scoring player across all of the user's teams this week, with a horizontal-bar comparison vs position median), Weekly Trend (6-week sparkline + delta), Live Games (NFL games with at least one of the user's players, marked with quarter and live indicator).

#### Scenario: Tweaks panel layout overrides

- **WHEN** the user adjusts the Tweaks panel
- **THEN** sidebar width (200–280px), team cards per row (2 or 3), roster row height (48–72px), Insights rail visibility, sparkline thickness (1–3px), and aurora intensity are all wired to `--sidebar-w`, `--team-cols`, `--row-h`, `--spark-thick`, and `--aurora-color` CSS variables, persisting to `localStorage`.

### Requirement: My Team screen

The My Team screen SHALL render the full roster as a table with Starters and Bench sections, plus side cards.

#### Scenario: Roster table

- **WHEN** the screen renders
- **THEN** columns are `Slot | Player | Opp | Status | Proj | Actual | +/–`. Live rows have `var(--live-row-bg)` background, OUT players show red `OUT` text, projected-only rows show `—` in the actual column, and the +/– delta uses cyan for positive and pink for negative.

#### Scenario: Side cards

- **WHEN** the screen renders
- **THEN** the right rail shows three cards: Score (activity ring of `actual / projected`, percent label, "5 games left" sub), Scoring Today (intra-day Move-style bar chart with dashed reference line at projected pace), Record (cumulative W/L sparkline + W/L pill grid).

#### Scenario: Week navigation

- **WHEN** the user selects a different week from the topbar
- **THEN** the roster table and all three side cards refetch for that week with TanStack Query keyed by `(team_id, week)`.

### Requirement: Head-to-Head screen

The H2H screen SHALL render concentric activity rings comparing the user's team to the opponent, plus a slot-by-slot comparison table and remaining-players + projected-final cards.

#### Scenario: Concentric rings

- **WHEN** the screen renders
- **THEN** an `ActivityRing` of size 200 with two tracks renders: outer pink (user's `score / proj`), inner cyan (opponent's `score / proj`). Center label shows the lead differential in pink (positive) or cyan (negative).

#### Scenario: Slot comparison table

- **WHEN** the screen renders
- **THEN** every slot is rendered as a row with the user's player on the left, slot pill + signed-differential chip in the center, and the opponent's player mirrored on the right.

#### Scenario: Projected-final card

- **WHEN** the screen renders
- **THEN** a probability range bar shows floor / likely / ceiling using the matchup's `home_proj`, `away_proj`, and a confidence percentage derived from remaining-game variance (`σ ≈ 12 pts per remaining player`).

### Requirement: Season screen

The Season screen SHALL render the full-season weekly bar chart, highlights cards, a record donut, and a week-by-week history list.

#### Scenario: Weekly chart

- **WHEN** the screen renders
- **THEN** an SVG chart renders one bar per played week, cyan for wins / pink for losses, with a thinner ghost bar for the opponent score; the current week is highlighted with a subtle white-tinted column overlay; a horizontal dashed line marks season-average points.

#### Scenario: Highlights

- **WHEN** the screen renders
- **THEN** three highlight cards show Win Streak (longest run of consecutive wins, with the week range), Season High (highest single-week score with opponent), and Most Started (the player started in the most weeks with games started + average points).

### Requirement: Settings screen

The Settings screen SHALL allow the user to manage platform connections, ESPN credentials, polling preferences, theming, and data management.

#### Scenario: Yahoo OAuth connect / disconnect

- **WHEN** the user toggles Yahoo off
- **THEN** the backend deletes the encrypted Yahoo tokens, marks Yahoo disconnected, and the row updates to "Connect Yahoo" with an OAuth start link.

#### Scenario: ESPN credential entry

- **WHEN** the user types into the SWID and `espn_s2` fields and clicks "Test Connection"
- **THEN** the backend probes ESPN and the row updates to "Connected · Last verified just now" on success or shows a typed error message on failure.

#### Scenario: Live-tier override

- **WHEN** the user picks `10s | 30s | 1m` in the live-refresh segmented control
- **THEN** the value is sent to the backend, persisted, the running `refresh_fantasy` job is rescheduled to the new cadence, and a `tier.change` event is emitted to all open SSE clients.

#### Scenario: Data management buttons

- **WHEN** the user clicks "Refresh all data"
- **THEN** the backend invalidates the entire `http_cache` table and triggers an immediate poll across both platforms. "Clear cache" deletes only `http_cache`. "Export JSON" downloads a single file containing all teams, leagues, rosters, and season weeks.

### Requirement: SSE-driven UI patching

The frontend SHALL drive live-feel from the `/api/events` SSE stream: `data.changed` events invalidate the matching TanStack Query keys, whose refetches re-render the affected components. Re-renders SHALL be incremental — components diff their props and pulse only the values that changed. Timer-based refetching exists only as a fallback while SSE is disconnected.

#### Scenario: Event-driven invalidation

- **WHEN** a `data.changed` SSE event arrives with scopes (e.g., `["teams", "team:yahoo:nfl.l.123456.t.4"]`)
- **THEN** `useLiveEvents()` invalidates the TanStack Query keys matching those scopes for the currently-viewed week, and the refetched values render within ~1 s of the backend cache write.

#### Scenario: Background tabs

- **WHEN** `document.visibilityState == "hidden"`
- **THEN** the client lets the browser suspend the EventSource. On `visibilitychange` back to `visible`, it issues a single immediate refetch of active queries and re-establishes the stream.

#### Scenario: Degraded mode while disconnected

- **WHEN** the SSE connection has been down for more than 30 s
- **THEN** the sidebar footer shows "Live connection lost — retrying", a 5-minute `refetchInterval` fallback activates on data queries, and both revert on reconnect.

#### Scenario: Pulse on changed values

- **WHEN** a refetch delivers a numeric value (`actual_points`, `score`, `proj`, `points_for`, `points_against`, etc.) that differs from the previously-rendered value
- **THEN** the corresponding DOM element receives a `data-just-changed` attribute and a CSS animation (`opacity 0.4 → 1` over 600 ms ease-out) plays once, controlled by a small custom hook (`useChangedValuePulse`) that compares against a `useRef` of the prior render.

#### Scenario: Last-updated indicator

- **WHEN** a query response is rendered
- **THEN** the sidebar footer reads `Last updated Xs ago` where `X = now() - response.meta.as_of`, ticking upward in real time. After 90 s past the expected refresh cadence without fresh data, the label switches to `Stale` styling.
