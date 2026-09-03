# Tasks — add-sleeper-projections

## 1. Ingest
- [x] 1.1 `platforms/sleeper.py` — client for the player dump (24 h `http_cache`) and projections
- [x] 1.2 `PlayerIndex` — three matcher tiers, ambiguity dropped, teamless rows excluded
- [x] 1.3 `models/player_projections.py` + alembic migration `c9f2b6d4e871`
- [x] 1.4 `refresh_projections` scheduler job, fixed 3 h cadence
- [x] 1.5 Escalate a total match failure onto the refresh-runs row

## 2. Read path
- [x] 2.1 `_resolve_points` — league scoring format, `custom` -> None
- [x] 2.2 `_projections_by_player` — one bulk query, not one per player
- [x] 2.3 `ext_proj_points` on `RosterSlot` (weekly scope)
- [x] 2.4 `ext_season_proj_points` on `WaiverCandidate` (season scope)
- [x] 2.5 Leave `delta_vs_worst_starter` computing from the platform projection

## 3. UI
- [x] 3.1 `ProjectionCompare` — quiet by default, colour only on divergence
- [x] 3.2 `RW` column on `RosterTable` and `WaiverTable`; hidden on mobile
- [x] 3.3 `.proj-ext` styles reusing the existing pos/neg vocabulary

## 4. Tests
- [x] 4.1 Matcher: all three tiers, ambiguity, FA/teamless, id-beats-name precedence
- [x] 4.2 Upsert: both scopes written, total-miss reported
- [x] 4.3 `_resolve_points` across every scoring type including `custom`
- [x] 4.4 `ProjectionCompare` incl. 0.0-is-not-missing
- [x] 4.5 Re-point Waivers' positional cell assertions at named columns
