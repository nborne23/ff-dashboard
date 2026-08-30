> **Parallelism.** Group 1 is the gate — it fixes the schema and types both sides code
> against. Once it lands, group 2 (fetch + mapper), group 3 (persistence + job), and
> group 5 (frontend, against group 1's fixture) run as three independent lanes. Group 4
> joins 2 and 3 into the read endpoint; group 6 joins everything.

## 1. Contract (gate — do first, everything forks from here)

- [x] 1.1 Add `backend/gridiron/models/player_pool.py` — `PlayerPoolEntry`, `__tablename__ = "player_pool_entries"`, composite PK `(league_id, player_id)`, both FKs. Columns: `status` (String(16)), `on_team_id` (String(255), nullable), `percent_owned` (Float), `percent_started` (Float), `season_proj_points` (Float, **nullable** per design D2), `updated_at`. Index `(league_id, season_proj_points)` for the ranked read in 4.1. Export from `models/__init__.py`.
- [x] 1.2 Alembic revision creating the table. `uv run alembic revision --autogenerate -m "add player_pool_entries"`, then read the generated file — autogenerate does not always get composite PKs or partial indexes right.
- [x] 1.3 Add `backend/gridiron/schemas/player_pool.py` — `PlayerPoolEntry` (the normalized entity, embedding `Player`) and `WaiverCandidate` (adds `delta_vs_worst_starter: float | None`, `eligible_slots: list[str]`). Per the `fantasy-data-model` delta.
- [x] 1.4 Mirror both in `frontend/src/types/api.ts`, plus `WaiversData`.
- [x] 1.5 Write `frontend/src/screens/Waivers/fixtures.ts` — a typed `WaiversData` fixture spanning at least one player with a null projection and one with a null delta. Unblocks lane 5 before the endpoint exists.

## 2. ESPN fetch + mapper (lane A)

- [x] 2.1 Add `PLAYER_POOL_TTL = timedelta(hours=6)` to `platforms/espn/client.py` and `STAT_SPLIT_SEASON = 0` beside the existing `STAT_SOURCE_*` constants.
- [x] 2.2 Extend `_cached_league_fetch` to accept optional `headers: dict | None` and `store_raw: bool = True`. When `store_raw` is false, call `cache.set` with `raw_json=""` (design D4). Fold `headers` into `cache_params` — **serialized with `sort_keys=True`** (design D5); an unsorted dict produces a fresh `params_hash` per call and refetches every tick.
- [x] 2.3 Add `EspnClient.get_player_pool(league_id, year, scoring_period, *, limit=1500)`. Builds the `x-fantasy-filter` JSON (`filterStatus: ["FREEAGENT","WAIVERS","ONTEAM"]`, `limit`, `offset: 0`, `sortPercOwned` descending), passes `view=kona_player_info`, and calls 2.2 with `store_raw=False` and `PLAYER_POOL_TTL`. **`ONTEAM` is required, not optional** — it is the only source of a season projection for a rostered player, which D7's delta needs on both sides of its subtraction. No `offset` pagination: Q6 confirmed 1030 is a true count, identical at `limit=1500` and `limit=3000`, so 1500 does not truncate.
- [x] 2.4 Add `mapper._season_projection(player, season)` exactly as design D2 specifies — matching on `seasonId` as well as the stat tuple, returning `None` (not `0.0`) when absent. **Do not** reuse `_player_points`; it cannot express this and would match two rows.
- [x] 2.5 Add `mapper.map_player_pool(raw, season) -> tuple[list[schemas.PlayerPoolEntry], int]` returning entries plus a skip count. Reuse `_map_player` for the player half; catch `UnknownSlotError` per entry and count it (design D6). Read availability off the *entry* (`status`, `onTeamId`) and `ownership.percentOwned` / `percentStarted` off the player.
- [x] 2.6 Unit-test 2.4 against a fixture carrying **both** the 2025 and 2026 season-projection rows, asserting the 2026 value is returned. This is the regression that D2 exists to prevent — write it before 2.4 passes.
- [x] 2.7 Unit-test 2.5's skip path: an entry with an unmappable `defaultPositionId` is skipped and counted, and the remaining entries still map.

## 3. Persistence + scheduler job (lane B)

- [ ] 3.1 Add `fantasy_service._upsert_player_pool_entries(session, league_id, entries)` — replace-per-league (delete then insert), matching how `_replace_roster` handles the same "authoritative snapshot" shape. Upsert the players themselves through the existing `_upsert_player`.
- [ ] 3.2 Add `fantasy_service.refresh_player_pool(session) -> str | None`. Resolve target leagues as those with a team where `is_user_team` is true — the column is `is_user_team`, **not** `is_mine`. Loop leagues, fetch, map, persist; return a summary string including total entries and total skips (design D6), or an error string on failure.
- [ ] 3.3 Register `refresh_player_pool` in `scheduler.JOBS` and add an `IntervalTrigger(hours=6)` job in `start_scheduler`. Fixed cadence — do **not** wire it to `reschedule_refresh_fantasy` or live state (design D8).
- [ ] 3.4 Test that `refresh_player_pool` is callable via `POST /api/admin/refresh?job=refresh_player_pool` and records a `refresh_runs` row, matching the existing job tests.
- [ ] 3.5 Test the multi-league case: two leagues with different scoring types produce two distinct `player_pool_entries` rows for one shared `player_id`, with different `season_proj_points`. This is design D1's regression test.

## 4. Read endpoint (joins lanes A + B)

- [ ] 4.1 Add `fantasy_service.get_waivers(session, team_id, week, position=None, limit=50) -> WaiversData | None`. Resolve the team's league, load its **available** pool (`status` in `FREEAGENT`/`WAIVERS` — `ONTEAM` rows are ingested for comparison, never listed as candidates) ranked by `season_proj_points` descending (nulls last), optionally filtered by position.
- [ ] 4.2 **Exclude `BN` and `IR` from `eligible_slots` before matching.** A live pull shows ESPN lists both for essentially every player (`['RB', 'RB/WR', 'FLEX', 'OP', 'BN', 'IR']`), so treating them as startable matches every candidate against every roster spot. Compute `delta_vs_worst_starter` per design D7 — candidate projection minus the lowest season projection among the user's current starters at an eligible slot. Take the starter's identity from `roster_slots` and the starter's projection by joining to that starter's own `player_pool_entries` row. **Never use `roster_slots.proj_points` here** — it is a weekly number (21.57 vs a 364.86 season projection for the same player), and mixing the scales silently ranks every candidate as a huge upgrade. Where the user has no starter at an eligible slot, or either side lacks a projection, the field is `None`, not `0.0`.
- [ ] 4.2a Test the unit-mismatch regression directly: a candidate whose season projection is *below* the weakest starter's must produce a negative delta. Computed against weekly `proj_points` it would come out strongly positive, so this test fails loudly if 4.2 ever regresses to the wrong column.
- [ ] 4.3 Verify 4.1 + 4.2 issue a bounded number of queries — load the roster once and compute deltas in memory rather than querying per candidate.
- [ ] 4.4 Register `GET /api/teams/{team_id}/waivers` in `api/teams.py` alongside the existing `/{team_id}/h2h` and `/{team_id}/season` routes. Set `CACHE_CONTROL`, resolve week via `_resolve_week`, return via `_envelope`, 404 on unknown team.
- [ ] 4.5 API tests: ranked order, position filter, null-projection rows sort last, unknown team 404, and a team whose league has an empty pool returns an empty list rather than erroring.

## 5. Frontend (lane C; builds against 1.5's fixture)

- [ ] 5.1 Add `useWaivers(teamId, week, position)` to `frontend/src/api/teams.ts` — `queryKey: ["waivers", teamId, week, position]`, `staleTime: STALE_TIME_MS`, matching the file's existing hook shape.
- [ ] 5.2 `screens/Waivers/WaiverTable.tsx` — one row per candidate: headshot, name, position pill, NFL team, % owned, season projection, and the delta chip. Reuse `.roster` table classes and the `roster-col-*` width vocabulary rather than inventing a parallel set; they already carry the mobile column-hiding rules.
- [ ] 5.3 Render a null `delta_vs_worst_starter` as an em dash, and a null `season_proj_points` as an em dash — never as `0.0`. D2/D7 both depend on the distinction surviving to the UI.
- [ ] 5.4 `screens/Waivers/index.tsx` — position filter control, the table, and `EmptyState` / `ErrorCard` wired via `usePlatformsDisconnected`, matching Head-to-Head and Season.
- [ ] 5.5 `screens/Waivers/WaiversSkeleton.tsx` matching loaded geometry, following the `SeasonSkeleton` approach in `screens/Season/index.tsx:24`.
- [ ] 5.6 Add `/team/:teamId/waivers` to `frontend/src/routes.tsx` and a sidebar entry in the team group in `components/shell/Sidebar.tsx`, following the team-scoped pattern Matchups and Season already use.
- [ ] 5.7 Component tests: ranked render, position filter, empty pool, error state, and the two null-rendering cases from 5.3.

## 6. Verification

- [ ] 6.1 `make lint && make test` clean.
- [ ] 6.2 Run `POST /api/admin/refresh?job=refresh_player_pool` against the real account and confirm all five leagues populate, with the skip count reported and plausible (a handful of IDP/unknown positions, not hundreds).
- [ ] 6.3 Confirm the D4 cost decision held: `http_cache` growth after a full pool refresh is negligible, and `player_pool_entries` holds roughly 1000 rows **per league** — expect ~1030 for an undrafted league and ~970 for a drafted one, not a uniform count. Each drafted league should show a nonzero `ONTEAM` share (~150 for a 12-team league); zero `ONTEAM` rows in a drafted league means the filter lost `ONTEAM` and D7's delta is silently broken.
- [ ] 6.4 Spot-check D1 end to end against the live data — pick one pass-catcher rostered in neither THE LEAGUE nor GAS Lab and confirm the two leagues show different `season_proj_points`, matching the probe's ppr/half_ppr split.
- [ ] 6.5 Acceptance: open `/team/:id/waivers` on a phone over Tailscale, confirm the table fits without horizontal scroll at 375px, and confirm the top-ranked candidate is one you'd actually consider claiming — if the ranking is obviously wrong, D7's comparison is the thing to revisit.
