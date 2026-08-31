> **Parallelism.** Group 1 is the gate — schema and types both sides code against.
> After it, group 2 (logo pipeline) and group 3 (standings endpoint) are independent
> backend lanes, and group 5 (League screen) builds against group 1's fixture without
> waiting for either. Group 4 (the shared `TeamLogo` component) gates group 6, which
> spreads logos across the existing screens. Group 7 verifies.

## 1. Contract (gate — do first)

- [x] 1.1 Add `backend/gridiron/models/team_logos.py` — `TeamLogo`, `__tablename__ = "team_logos"`, composite PK `(platform, team_id)`, columns `source_url` (String(1024), nullable), `content_type` (String(64), nullable), `fetched_at` (DateTime, nullable), `created_at`. Model on `models/headshots.py`. Export from `models/__init__.py`.
- [x] 1.2 Add `logo_source_url` (String(1024), nullable) and `logo_type` (String(32), nullable) to the `Team` model — the values `map_team` reads off the payload, and what design D5 compares for invalidation.
- [x] 1.3 One Alembic revision for 1.1 + 1.2. Read the generated file; autogenerate does not reliably get composite PKs right.
- [x] 1.4 Add `logo_url: str | None` to `schemas.Team`, and `LeagueStandingsRow` / `LeagueStandingsData` to `fantasy_service.py` per the `fantasy-data-model` delta. A row carries the team, its division id, and its standings position.
- [x] 1.5 Mirror all of it in `frontend/src/types/api.ts`.
- [x] 1.6 Write `frontend/src/screens/League/fixtures.ts` — a typed fixture with at least: one team with a VECTOR logo, one with a CUSTOM_UPLOAD, one with **no** logo at all, the user's own team, and — critically — **two teams with identical records and zero seeds**, so the D7 tiebreak is visible in component tests.

## 2. Logo pipeline (lane A)

- [x] 2.1 Add `scripts/probe-espn-team-logos.py`, a read-only sibling of `probe-espn-player-pool.py`, reproducing the P1–P3 requests. It is the reproducer the design cites when ESPN changes something.
- [x] 2.2 In `platforms/espn/mapper.py`, read `logo` and `logoType` in `map_team` onto the new fields. Absent/empty logo is `None`, not `""` — "no logo" and "empty string" must not both mean the same thing to D5's comparison.
- [x] 2.3 Add `backend/gridiron/services/team_logos.py`: `resolve_logos_dir`, `logo_path`, `read_crest` (a generic crest, NOT `headshots.read_silhouette` — a player silhouette for a team is wrong), and `fetch_and_cache(session, platform, team_id)`.
- [x] 2.4 In 2.3, decrypt ESPN cookies and send them (design D3). Return the crest rather than raising when no ESPN connection exists, so a fresh install renders crests instead of erroring per team.
- [x] 2.5 Implement the D6 content-type allowlist: accept `image/svg+xml` **only** when the source host is `g.espncdn.com`; accept raster types otherwise; anything else falls back to the crest. This is an XSS control — an SVG on our own origin can carry same-origin script.
- [x] 2.6 Implement D4: a 404 from the source may be recorded, a **401 must not be** — expired cookies are recoverable, and caching that failure would blank every logo until the cache was cleared by hand.
- [x] 2.7 Implement D5: compare the team's stored `logo_source_url` against what the cached bytes were fetched for; refetch on mismatch. A leaguemate changing their logo changes the UUID in the URL.
- [x] 2.8 Add `backend/gridiron/api/team_logos.py` — `GET /api/team-logos/{platform}/{team_id}`, **no extension** (D2). Serve the stored `content_type`, set a long `Cache-Control`, and set `X-Content-Type-Options: nosniff`. Register in `main.py`.
- [x] 2.9 Derive `Team.logo_url` in `fantasy_service._team_schema` by convention (`/api/team-logos/{platform}/{platform_id}`), the way `_headshot_url` already does — do not store the local URL.
- [x] 2.10 Persist `logo_source_url` / `logo_type` in `_upsert_team`.
- [x] 2.11 Tests: the allowlist rejects an SVG from a non-ESPN host; a 401 is not cached and a later success succeeds; a changed `source_url` refetches; a team with no logo serves the crest; the stored content type is what the route returns.

## 3. Standings endpoint (lane B)

- [x] 3.1 Add `fantasy_service.get_league_standings(session, team_id)` — resolve the team's league, load every team in it, return league metadata plus ordered rows. `None` for an unknown team (the API 404s).
- [x] 3.2 Implement the D7 sort key exactly: `(division_id, seed_is_zero, seed, -wins, -points_for, team_id)`. Every element earns its place — read D7 before changing any of them.
- [x] 3.3 **Test the sort with fabricated records, not live data.** Every real team is `0-0-0` with `points_for = 0.0` until week 1 is played, so live data cannot demonstrate the tiebreak. Cover: a league with real seeds (ESPN order wins), a league with all-zero seeds (falls back to record), and a total tie (stable by team id — assert the same order twice).
- [x] 3.4 Register `GET /api/teams/{team_id}/league` in `api/teams.py` beside the other `/{team_id}/…` routes; 404 typed as `team_not_found`.
- [x] 3.5 API tests: shape, envelope, Cache-Control, the user's own row flagged, unknown team 404.

## 4. Shared logo component (gates group 6)

- [ ] 4.1 `frontend/src/components/shared/TeamLogo.tsx` — props `{ team, size }`. Renders `<img src={team.logo_url}>` with an `onError` fallback to an initials/crest element, mirroring how `RosterTable`'s `Headshot` already handles a missing image.
- [ ] 4.2 Render `null` `logo_url` as the fallback without issuing a request.
- [ ] 4.3 Component tests: renders the image, falls back on error, falls back on null without a network call.

## 5. League screen (lane C; builds against 1.6's fixture)

- [ ] 5.1 Add `useLeagueStandings(teamId)` to `frontend/src/api/teams.ts`, matching the file's existing hook shape.
- [ ] 5.2 `screens/League/StandingsTable.tsx` — rank, `TeamLogo` + team name + manager, W-L-T, PF, PA. Reuse the `.roster` table classes and `roster-col-*` widths rather than inventing a parallel set; put the columns that matter least (PA) on a class the mobile rules hide.
- [ ] 5.3 Highlight the user's own row distinctly.
- [ ] 5.4 `screens/League/index.tsx` — header, table, and `EmptyState` / `ErrorCard` via `usePlatformsDisconnected`, matching Season and Waivers.
- [ ] 5.5 `screens/League/LeagueSkeleton.tsx` matching loaded geometry.
- [ ] 5.6 Add `"league"` to `TeamSection` and `TEAM_SECTIONS` in `hooks/teamRoute.ts`, the route to `routes.tsx`, and a sidebar entry.
- [ ] 5.7 Component tests: ordered render, own-row highlight, a team with no logo, empty/error states.

## 6. Logos across the existing surfaces (after group 4)

- [ ] 6.1 Dashboard team cards.
- [ ] 6.2 Sidebar "My Teams" list and the `TeamContextBar` switcher — these render at ~18px; if custom uploads are unreadable at that size, fall back to the crest below a threshold rather than changing the pipeline (design "Risks").
- [ ] 6.3 Game Day panels and Head-to-Head, beside both team names.
- [ ] 6.4 Confirm no existing screen test breaks on the added element; update snapshots/queries that assume a text-only team name.

## 7. Verification

- [ ] 7.1 `make lint && make test` clean. **Typecheck with `npm run build` (`tsc -b`), not `tsc --noEmit -p tsconfig.json`** — the root tsconfig is `"files": []` with project references, so `-p` on it checks nothing and reports success. Six stale fixtures were only caught once `tsc -b` was run.
- [ ] 7.2 Fetch a VECTOR logo and a CUSTOM_UPLOAD logo through the local route against the real account; confirm both return 200 with the right content type, and that the custom upload — which 401s to an unauthenticated client — succeeds through the proxy. That contrast is the whole reason this pipeline exists.
- [ ] 7.3 Confirm the D6 allowlist against real data: every stored `content_type` is either an allowed raster type or `image/svg+xml` from `g.espncdn.com`.
- [ ] 7.4 Open `/team/:id/league` at 375px and confirm no horizontal overflow, matching the Waivers acceptance.
- [ ] 7.5 Acceptance: the standings order matches what ESPN's site shows for a league where `playoffSeed` is populated (THE LEAGUE), and the all-zero-seed league (GAS Lab) renders in a stable order across two reloads.
