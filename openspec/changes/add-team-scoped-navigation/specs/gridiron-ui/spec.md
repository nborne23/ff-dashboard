## ADDED Requirements

### Requirement: Team scope is explicit and remembered

Screens SHALL divide into league-wide (Dashboard, Game Day, Settings) and team-scoped
(`/team/:teamId`, `/team/:teamId/h2h`, `/team/:teamId/season`). Navigating to a
team-scoped screen from the shell SHALL target the team the user most recently viewed,
never an arbitrary one.

#### Scenario: Remembered team drives the shell's team-scoped links

- **WHEN** the user has viewed a team and then activates the sidebar's Matchups or Season item
- **THEN** the link resolves to that team, not to the first team in the `GET /api/teams` response — whose ordering is not a guarantee of that endpoint.

#### Scenario: The remembered team is validated before use

- **WHEN** the persisted team id names a team absent from the current team list, because its league was disconnected
- **THEN** it is ignored and the first available team is used instead, so a stale id in local storage cannot produce a link to an error screen that survives every reload.

#### Scenario: Nothing connected

- **WHEN** no team is available
- **THEN** the Matchups and Season items link to the dashboard, which carries the "connect a league" empty state.

#### Scenario: The URL remains authoritative

- **WHEN** a team-scoped URL is opened directly, with no remembered team
- **THEN** the screen renders that team. The remembered team is written from the route and never read back to decide what renders, so a deep link, a back-button navigation, and a cold start behave identically.

#### Scenario: Leaving a team screen does not clear the memory

- **WHEN** the user navigates from a team screen to a league-wide one
- **THEN** the remembered team is retained, so returning via Matchups or Season lands on the same team.

### Requirement: Team context bar

A context bar SHALL render above the routed content on team-scoped screens only, naming
the team on screen and offering its sibling views.

#### Scenario: Present only on team-scoped routes

- **WHEN** a league-wide screen renders
- **THEN** no context bar is present.

#### Scenario: Section tabs

- **WHEN** the bar renders
- **THEN** it shows a tab per team view (Roster, Matchup, Season), the tab for the section on screen is marked current, and activating another navigates to that section of the same team.

#### Scenario: Switching teams preserves the section

- **WHEN** the user picks a different team from the switcher while a section is on screen
- **THEN** the app navigates to the same section of the newly chosen team, rather than to its roster.

#### Scenario: Rendered by the shell

- **WHEN** the user switches team or section
- **THEN** the bar does not unmount, because it is rendered by the shell rather than by each of the three screens.

#### Scenario: Switcher with nothing to switch to

- **WHEN** no teams are connected
- **THEN** the switcher is disabled rather than opening an empty menu.

#### Scenario: Phone layout

- **WHEN** the viewport is below 768px
- **THEN** the switcher and the tabs stack, each taking the full content width, and neither the bar nor its open menu causes horizontal overflow.

### Requirement: One route parser

The shell SHALL derive the active team and section from a single shared parser rather
than per-component pathname checks.

#### Scenario: Unrecognized sub-route

- **WHEN** a path under `/team/:teamId/` names no known section
- **THEN** the parser reports no match rather than defaulting to the roster, so no tab is marked current for a screen the user is not on.

#### Scenario: Percent-encoded team id

- **WHEN** a team id arrives percent-encoded in the path
- **THEN** it is decoded, so it matches the id the screens read from the route parameters.
