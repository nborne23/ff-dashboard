## RENAMED Requirements

- FROM: `### Requirement: Six-screen application shell`
- TO: `### Requirement: Seven-screen application shell`

## MODIFIED Requirements

### Requirement: Seven-screen application shell

The frontend SHALL implement exactly seven primary screens, each routed and reachable from the persistent sidebar: Dashboard, Game Day, My Team, Head-to-Head, Season, Waivers, Settings.

#### Scenario: Routing

- **WHEN** the user clicks a sidebar item
- **THEN** the URL updates to one of `/`, `/gameday`, `/team/:teamId`, `/team/:teamId/h2h`, `/team/:teamId/season`, `/team/:teamId/waivers`, `/settings`, and the corresponding screen renders without unmounting the persistent shell (sidebar + topbar).

#### Scenario: Sub-navigation under "My Teams"

- **WHEN** the user expands the "My Teams" sidebar group
- **THEN** every connected team renders as a sub-item with its platform color dot (purple for Yahoo, red for ESPN), and selecting one navigates to `/team/:teamId`.

#### Scenario: Game Day sidebar placement

- **WHEN** the sidebar renders
- **THEN** the Game Day entry sits between Dashboard and the "My Teams" group, and — unlike the Matchups and Season entries — links to `/gameday` directly rather than to a selected team, since the screen spans every team.

#### Scenario: Waivers is team-scoped

- **WHEN** the sidebar's Waivers entry is activated
- **THEN** it resolves to the remembered team exactly as Matchups and Season do, because the free-agent pool is a property of one league and there is no cross-league pool to show.

## ADDED Requirements

### Requirement: Waivers screen

The Waivers screen SHALL present the free-agent and waiver pool for one team's league as a ranked, filterable table.

#### Scenario: Ranked table

- **WHEN** the screen loads
- **THEN** candidates render ranked by season projection descending, each row showing headshot, name, position pill, NFL team, percent owned, season projection, and the delta against the user's weakest eligible starter.

#### Scenario: Position filter

- **WHEN** the user selects a position filter
- **THEN** the table narrows to that position without a full-page loading state, and clearing the filter restores the full pool.

#### Scenario: Absent values render as absent

- **WHEN** a candidate has no season projection, or no comparable starter exists at an eligible slot
- **THEN** that cell renders an em dash — never `0.0` — because a genuine zero projection is a distinct and observed value, and rendering both identically would misrepresent a player the system knows nothing about as one it expects to score nothing.

#### Scenario: Reuses the roster table's column vocabulary

- **WHEN** the table is styled
- **THEN** it reuses the existing `.roster` table classes and `roster-col-*` width vocabulary rather than defining a parallel set, so the mobile column-hiding and fixed-layout percentage widths already established apply without duplication.

#### Scenario: Empty and error states

- **WHEN** the pool has not been synced, or the request fails, or no platform is connected
- **THEN** the screen renders the shared `EmptyState` / `ErrorCard` components through `usePlatformsDisconnected`, matching Head-to-Head and Season.
