## RENAMED Requirements

- FROM: `### Requirement: Seven-screen application shell`
- TO: `### Requirement: Eight-screen application shell`

## MODIFIED Requirements

### Requirement: Eight-screen application shell

The frontend SHALL implement exactly eight primary screens, each routed and reachable from the persistent sidebar: Dashboard, Game Day, My Team, Head-to-Head, Season, Waivers, League, Settings.

#### Scenario: Routing

- **WHEN** the user clicks a sidebar item
- **THEN** the URL updates to one of `/`, `/gameday`, `/team/:teamId`, `/team/:teamId/h2h`, `/team/:teamId/season`, `/team/:teamId/waivers`, `/team/:teamId/league`, `/settings`, and the corresponding screen renders without unmounting the persistent shell (sidebar + topbar).

#### Scenario: Sub-navigation under "My Teams"

- **WHEN** the user expands the "My Teams" sidebar group
- **THEN** every connected team renders as a sub-item, and selecting one navigates to `/team/:teamId`.

#### Scenario: Game Day sidebar placement

- **WHEN** the sidebar renders
- **THEN** the Game Day entry sits between Dashboard and the "My Teams" group, and — unlike the team-scoped entries — links to `/gameday` directly rather than to a selected team, since the screen spans every team.

#### Scenario: Waivers is team-scoped

- **WHEN** the sidebar's Waivers entry is activated
- **THEN** it resolves to the remembered team exactly as Matchups and Season do, because the free-agent pool is a property of one league.

#### Scenario: League is team-scoped

- **WHEN** the sidebar's League entry is activated
- **THEN** it resolves to the remembered team, because the user belongs to several leagues and the league is derived from the selected team rather than chosen separately.

## ADDED Requirements

### Requirement: League screen

The League screen SHALL present every team in one league as a standings table.

#### Scenario: Standings table

- **WHEN** the screen loads
- **THEN** each row shows rank, the team's logo, team name, manager, win-loss-tie record, points for, and points against, ordered as standings.

#### Scenario: The user's own team is distinguishable

- **WHEN** the table renders
- **THEN** the user's own row is visually distinct, so their position is findable without reading every name.

#### Scenario: Reuses the roster table's column vocabulary

- **WHEN** the table is styled
- **THEN** it reuses the existing roster table classes and column-width vocabulary rather than defining a parallel set, so the established mobile column-hiding and fixed-layout widths apply without duplication
- **AND** the least decision-relevant column is the one assigned to a class the mobile rules hide.

#### Scenario: Empty and error states

- **WHEN** the request fails, or no platform is connected
- **THEN** the screen renders the shared empty-state and error components, matching Season and Waivers.

### Requirement: Team identity carries a logo

Teams SHALL render with their platform logo wherever a team is named across the application.

#### Scenario: Surfaces

- **WHEN** a team is displayed on the Dashboard's team cards, the sidebar team list, the team switcher, the Game Day and Head-to-Head matchup panels, or the League standings
- **THEN** its logo renders beside its name.

#### Scenario: A missing logo degrades to a placeholder

- **WHEN** a team has no logo, or the image fails to load
- **THEN** a placeholder renders in its place and no layout shift occurs
- **AND** a team with no logo URL SHALL NOT issue an image request at all.

#### Scenario: Small sizes stay legible

- **WHEN** a logo renders at sidebar scale
- **THEN** an uploaded image that is unreadable at that size may fall back to the generic placeholder, which is a presentation choice at the render site and SHALL NOT change what the cache stores.
