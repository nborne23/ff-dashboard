## RENAMED Requirements

- FROM: `### Requirement: Five-screen application shell`
- TO: `### Requirement: Six-screen application shell`

## MODIFIED Requirements

### Requirement: Six-screen application shell

The frontend SHALL implement exactly six primary screens, each routed and reachable from the persistent sidebar: Dashboard, Game Day, My Team, Head-to-Head, Season, Settings.

#### Scenario: Routing

- **WHEN** the user clicks a sidebar item
- **THEN** the URL updates to one of `/`, `/gameday`, `/team/:teamId`, `/team/:teamId/h2h`, `/team/:teamId/season`, `/settings`, and the corresponding screen renders without unmounting the persistent shell (sidebar + topbar).

#### Scenario: Sub-navigation under "My Teams"

- **WHEN** the user expands the "My Teams" sidebar group
- **THEN** every connected team renders as a sub-item with its platform color dot (purple for Yahoo, red for ESPN), and selecting one navigates to `/team/:teamId`.

#### Scenario: Game Day sidebar placement

- **WHEN** the sidebar renders
- **THEN** the Game Day entry sits between Dashboard and the "My Teams" group, and — unlike the Matchups and Season entries — links to `/gameday` directly rather than to a selected team, since the screen spans every team.

## ADDED Requirements

### Requirement: Game Day is a lean-back surface

The Game Day screen SHALL be designed for full-screen, unattended, across-the-room reading on the iMac deployment, which constrains it more tightly than the arm's-length screens.

#### Scenario: Minimum type size

- **WHEN** any Game Day value carrying meaning renders at any density
- **THEN** it is at least 15px, and panel scores range from 26px at the narrowest density to 64px in spotlight.

#### Scenario: Interaction is for setup, not reading

- **WHEN** the screen is left untouched during live games
- **THEN** it remains fully informative without any interaction — the roster reveals itself by width rather than by click, and no cue requires hovering to interpret.

#### Scenario: Per-screen aurora

- **WHEN** the Game Day screen is active
- **THEN** the shell's `--aurora-color` is set for this screen the same way every other screen sets it, so the shell treatment stays consistent.

#### Scenario: Visual parity with the prototype

- **WHEN** Game Day is rendered from real data
- **THEN** it matches the design prototype's `gameday.css` output in alignment, color, font weight, and spacing, subject to the same pixel-fidelity rule as the other screens — colors sourced from tokens, no hex codes outside `tokens.css`, no Tailwind.
