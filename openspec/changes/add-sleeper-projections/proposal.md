# add-sleeper-projections

## Why

Every number GridIron reasons with is the one ESPN or Yahoo published. Those are the
weakest projections in the market, and they are the exact numbers a competitor product
exists to replace — the gap analysis called this a missing *foundation*, not a missing
feature, because start/sit, waiver and trade quality are all capped by it.

Sleeper serves Rotowire's projections through a public, unauthenticated endpoint: weekly
and season-long, with `pts_ppr` / `pts_half_ppr` / `pts_std` pre-computed and the full
stat line underneath. Verified live on 2026-09-03 — 9,419 rows for week 1.

## What Changes

- **`player_projections` table + `refresh_projections` job**, fed by Sleeper's public
  feed. Two upstream calls per run regardless of roster size; the feed is served whole.
- **A three-tier matcher.** Sleeper's `espn_id` reaches only 32% of a real roster —
  coverage is patchy for recently-drafted players — so id matching is backed by
  normalized name + NFL team, then D/ST by team abbreviation. Measured at **100% of 194
  rostered players** on this install.
- **Both scopes stored.** Weekly for the roster, season-long for waivers. `week = 0`
  encodes season.
- **All three scoring formats stored**, resolved per league on read. A `custom`-scoring
  league gets `null`, never a silently-wrong PPR number.
- **`ext_proj_points` / `ext_season_proj_points`** on the roster and waiver payloads, and
  an `RW` column on both tables that colours only a material disagreement.

## What deliberately does NOT change

`WaiverCandidate.delta_vs_worst_starter` keeps computing from the platform's own season
projection. Swapping the inputs of the comparison the Waivers screen exists to make is a
judgement call for the user, not a side effect of adding a data source.

This also does **not** close the expert-rankings gap. Rotowire is one provider's
projection — a better single number, not a consensus of 130 analysts.

## Impact

- Affected specs: `player-projections` (new)
- Affected code: `platforms/sleeper.py` (new), `models/player_projections.py` (new), one
  alembic migration, `schemas/{roster_slots,player_pool}.py`, `services/fantasy_service.py`,
  `scheduler.py`, `types/api.ts`, `components/shared/ProjectionCompare.tsx` (new),
  `RosterTable`, `WaiverTable`, `global.css`.
