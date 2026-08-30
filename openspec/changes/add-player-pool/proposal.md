## Why

Every screen in this app describes players the user already owns. Nothing describes the ones they don't — and across five leagues, the waiver wire is the largest in-season lever left after setting a lineup. Answering "who should I claim?" today means opening ESPN's own site five times and eyeballing it.

Three features want this same missing data: free-agent/waiver visibility, trade evaluation, and matchup context. All three fail for one reason — there is no free-agent, waiver, or transaction data anywhere in the schema, and `players` has no projection column. This change builds the ingestion path once and lands the first consumer on top of it; trade evaluation and matchup context become follow-ups that need no new pipeline.

The design here is grounded in a probe run against the live account (`scripts/probe-espn-player-pool.py`), not on assumption. Its four findings drive every decision in `design.md`.

## What Changes

**New ingestion**

- `EspnClient.get_player_pool(league_id, year, scoring_period)` — a `view=kona_player_info` fetch driven by an `x-fantasy-filter` header. The filter *is* the query: `filterStatus: ["FREEAGENT", "WAIVERS", "ONTEAM"]` is what selects the pool, and `limit` bounds it. `ONTEAM` is included deliberately — it is the only source of a season projection for a player already on a roster, which the waiver comparison needs (design D7).
- New scheduler job `refresh_player_pool`, on its own slow cadence (6h), for every league where the user owns a team. It is deliberately **not** folded into `refresh_fantasy`, which reschedules itself down to 30s during live games.
- New mapper functions `map_player_pool()` and `_season_projection()`.

**New persistence**

- New table `player_pool_entries`, keyed `(league_id, player_id)`, carrying availability (`status`, `on_team_id`, `percent_owned`, `percent_started`) and `season_proj_points`. One Alembic migration. It holds every player in the league — rostered or not — because a season projection is needed on both sides of the waiver comparison.
- **Per-league, not per-player.** The probe proved `appliedTotal` is league-scoped: for the same `playerId`, Joshua Palmer projects 111.2 in a ppr league and 90.37 in a half_ppr one, while Kyler Murray is byte-identical in both. The players who differ are pass-catchers; the ones who match are QBs. Projections therefore cannot hang off `players`, and neither can availability — a player free in one of the five leagues may be rostered in another.
- Pool players reuse the existing `players` table via `_upsert_player`; only the league-scoped facts live in the new table.

**New read surface**

- `GET /api/teams/{team_id}/waivers?position=&limit=` — the pool for that team's league, ranked, each row carrying the projection delta against the weakest starter the user currently has at that position. "Is this player better than what I'd drop" is the actual question; a raw projection leaderboard is not.
- New screen at `/team/:teamId/waivers` with a sidebar entry under the team group, following the team-scoped navigation the app already uses.

## Non-Goals

- **Trade evaluation.** Needs roster-context modeling this change does not build — positional scarcity, starter displacement, and two-sided value. It consumes this pipeline unchanged; deferred to `add-trade-evaluator`.
- **Matchup context** (defense-vs-position, snap share, target share). None of it is in `kona_player_info`; it is a separate ingestion problem against a different source. Deferred to `add-matchup-context`.
- **Executing waiver claims.** `scripts/probe-espn-writes.py` established that stored cookies are accepted for writes, but a claim is an irreversible roster transaction and belongs behind its own change with its own confirmation model. This change is read-only.
- **True rest-of-season projections.** ESPN returns a **full-season** projection, not a remaining-season one. See design D3: at week 1 with zero actuals the two coincide, and the honest partial (season total minus actuals to date) lands here rather than a modeled ROS number.
- **Yahoo.** No Yahoo league is connected (`leagues` holds five ESPN rows and nothing else). The service layer stays platform-agnostic so a Yahoo path can be added, but no Yahoo code ships here.

## Capabilities

### Modified Capabilities

- `platform-integrations`: gains "ESPN player pool fetching" and a pool row in the cache-TTL table, plus an explicit carve-out from raw-response retention.
- `fantasy-data-model`: "Normalized internal entities" gains `PlayerPoolEntry`; "Read API for the frontend" gains `GET /api/teams/{team_id}/waivers`.
- `gridiron-ui`: the screen shell gains a team-scoped Waivers screen.
- `live-updates`: the scheduler job set gains `refresh_player_pool`.

> **Archive-order dependency — this change archives LAST, after `scaffold-gridiron` and `add-game-day-view`.**
>
> Two links in the chain, not one:
>
> 1. All four capabilities above still live in `openspec/changes/scaffold-gridiron/specs/` and only reach `openspec/specs/` when that change archives — `openspec/specs/` currently holds only the four `draft-*` capabilities. Archiving this change first aborts with *"target spec does not exist; only ADDED requirements are allowed for new specs."* This is the constraint `add-game-day-view` already documents.
> 2. The `gridiron-ui` delta here renames **Six-screen application shell → Seven-screen**, and "Six-screen" is itself the product of `add-game-day-view`'s own rename from "Five-screen". Archiving this change before that one leaves the rename with no target.
>
> Required order: `scaffold-gridiron` → `add-game-day-view` → `add-player-pool`. `add-team-scoped-navigation` is independent of this change (its `gridiron-ui` delta is purely ADDED requirements) and may archive anywhere after `scaffold-gridiron`.
>
> Verified on a throwaway copy of `openspec/`, following the precedent `add-game-day-view` set. Archiving this change first **fails loudly and changes no files** — *"fantasy-data-model: target spec does not exist… Aborted. No files were changed."* The in-order chain applies cleanly: the shell requirement lands as **Seven-screen application shell**, `gridiron-ui` ends with 10 requirements including the new Waivers screen, and no pre-existing requirement is dropped from any of the four capabilities.

## Impact

**Backend** — `platforms/espn/client.py` (new fetch + a filter-aware cache key), `platforms/espn/mapper.py` (new pool mapper + season-projection accessor), new `models/player_pool.py`, new `schemas/player_pool.py`, `services/fantasy_service.py` (new `get_waivers()` + `refresh_player_pool()`), `scheduler.py` (one job), `api/teams.py` (one route), one Alembic migration.

**Frontend** — new `screens/Waivers/`, touches `types/api.ts`, `api/teams.ts`, `routes.tsx`, `components/shell/Sidebar.tsx`.

**New dependencies** — none.

**Breaking changes** — none. Every addition is additive; no existing endpoint, table, or schema changes shape.

**Notable cost** — a full pool pull is ~3.5–3.7 MB per league (~970–1030 players), giving a ~18.5 MB upper bound across all five. This is roughly two orders of magnitude larger than a roster payload and is why design D4 exempts it from design.md D7's raw-response retention.
