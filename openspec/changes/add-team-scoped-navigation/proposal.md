# Add team-scoped navigation

## Why

The app has two kinds of screen and no way to tell them apart. Dashboard and Game Day
are league-wide — they show every team at once. My Team, Matchups, and Season are
team-scoped: each renders exactly one team, chosen by the `:teamId` in the URL. Nothing
in the UI communicates that split, so the app reads as inconsistent — "the dashboard
shows all my teams, but Matchups only shows one, and I never picked which one."

Worse, nobody *did* pick which one. The sidebar built its Matchups and Season links from
`teams[0]` — whichever team happened to sort first in the `GET /api/teams` response.
Opening a team from the dashboard and then clicking Matchups silently switched you to a
different team's matchup. Team order is not a documented guarantee of that endpoint, so
the target could also change between weeks.

There was also no way to move between a team's three views without going back out to the
sidebar, and no way to see which team was on screen short of reading the URL.

## What Changes

- The remembered team (`activeTeamId`) becomes the target of the sidebar's Matchups and
  Season links, replacing `teams[0]`. It is persisted, and validated against the live
  team list on every read so a disconnected league cannot leave a permanently broken link.
- A team context bar renders above the three team-scoped screens: a switcher naming the
  team on screen, and tabs for its three views. Switching teams preserves the section.
- The sidebar's "My Teams" group opens on arrival at a team screen, and the active team
  is highlighted across all three of its views rather than only its roster.
- One shared route parser (`hooks/teamRoute.ts`) replaces the ad-hoc `pathname.endsWith`
  checks the sidebar used to derive which section was active.

The URL stays authoritative for what renders. The persisted team is only a memory of the
last one visited, so deep links and cold starts are unaffected.

## Impact

- Affected specs: `gridiron-ui`
- Affected code: `frontend/src/hooks/teamRoute.ts`, `frontend/src/hooks/useActiveTeam.ts`,
  `frontend/src/components/shell/TeamContextBar.tsx`,
  `frontend/src/components/shell/Sidebar.tsx`, `frontend/src/App.tsx`,
  `frontend/src/stores/ui.ts`, `frontend/src/styles/global.css`
- No backend or API change.
