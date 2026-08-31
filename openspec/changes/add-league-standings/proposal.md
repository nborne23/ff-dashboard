## Why

Two gaps, one dependency between them.

**No league view.** Every screen shows the user's own team or its current opponent. Nothing shows the league — who else is in it, who is winning it, where the user sits. Answering "am I actually in the hunt" means opening ESPN's site, five times, once per league.

**No team identity.** Teams are rendered as a name and a platform-colored dot. ESPN gives every team a logo, the user's leaguemates have uploaded real ones, and a standings table of ten text rows is exactly where that identity earns its keep. The logos are also the reason these ship together: a league page without them is a spreadsheet.

The design here rests on a probe against the live account, not on assumption — in particular the fact that half of these images cannot be loaded by a browser at all without proxying.

## What Changes

**New logo pipeline**

- New table `team_logos`, keyed `(platform, team_id)`, storing `source_url`, `content_type`, and `fetched_at`. Bytes live on disk beside the headshot cache.
- New service `services/team_logos.py` and route `GET /api/team-logos/{platform}/{team_id}` — deliberately **extensionless**, unlike the headshot route's `.png`, because ESPN serves these as both `image/svg+xml` and `image/jpg`.
- `map_team` reads `logo` / `logoType`; `Team` gains `logo_url` pointing at the local route.
- `teams` gains `logo_source_url` and `logo_type`. One Alembic migration for both new tables/columns.

**New league view**

- `GET /api/teams/{team_id}/league` — every team in that team's league, ordered as standings, with the league's own metadata.
- New screen at `/team/:teamId/league`, team-scoped like Matchups, Season, and Waivers, with a sidebar entry and a tab in the team context bar.
- Standings columns: rank, logo + team name + manager, W-L-T, points for, points against. The user's own row is highlighted.

**Logos integrated across four surfaces** (all of them, per the request): the new League page, Dashboard team cards, the sidebar "My Teams" list and team switcher, and the Game Day / Head-to-Head matchup panels.

## Non-Goals

- **Rasterizing SVG.** Browsers render SVG in `<img>` natively. A rasterizer is a heavy new dependency for no gain, and the security concern it might address is handled by an allowlist instead (design D6).
- **Yahoo logos.** No Yahoo league is connected. `Team.logo_url` is platform-agnostic and the service dispatches on platform, so a Yahoo path is additive later.
- **Editing or uploading a logo.** Read-only, like everything else in this app.
- **Historical standings / playoff bracket projection.** The page shows the standings as they are. Week-by-week movement is `Season`'s job, and bracket odds need a Monte Carlo this change does not build.
- **Division grouping.** All five leagues are single-division (design D8). The ordering is division-aware in shape but renders one flat table.

## Capabilities

### Modified Capabilities

- `platform-integrations`: gains "ESPN team logo fetching", including its auth asymmetry and content-type handling.
- `fantasy-data-model`: `Team` gains `logo_url`; "Read API for the frontend" gains `GET /api/teams/{team_id}/league` and the logo route.
- `gridiron-ui`: the shell gains a team-scoped League screen, and team identity gains a logo across four surfaces.

> **Archive-order dependency — this change archives after `add-player-pool`.**
>
> The `gridiron-ui` delta renames **Seven-screen application shell → Eight-screen**, and "Seven-screen" is itself produced by `add-player-pool`'s rename from "Six-screen", which in turn follows `add-game-day-view`'s from "Five-screen". Required order: `scaffold-gridiron` → `add-game-day-view` → `add-player-pool` → `add-league-standings`. Verified on a throwaway copy of `openspec/` (see design "Archive order").

## Impact

**Backend** — new `models/team_logos.py`, new `services/team_logos.py`, new `api/team_logos.py`; touches `platforms/espn/mapper.py` (logo fields), `schemas/teams.py` (`logo_url`), `services/fantasy_service.py` (new `get_league_standings()`, logo URL derivation, logo persistence during discovery), `api/teams.py` (one route), one Alembic migration.

**Frontend** — new `screens/League/`; a shared `TeamLogo` component; touches `types/api.ts`, `api/teams.ts`, `routes.tsx`, `hooks/teamRoute.ts`, `components/shell/Sidebar.tsx`, `components/shell/TeamContextBar.tsx`, `screens/Dashboard/`, `screens/GameDay/`, `screens/HeadToHead/`.

**New dependencies** — none.

**Breaking changes** — none; every addition is additive.

**Notable constraint** — custom-uploaded logos return **401 without ESPN session cookies**, so they cannot be referenced directly from the browser and must be proxied. This is the finding that makes the local cache mandatory rather than a nicety.
