# Tasks — add-lineup-optimizer

## 1. Solver
- [x] 1.1 Validate the eligibility predicate against all 300 real starter assignments
- [x] 1.2 `solve()` — exact DP over slot-group capacity, `(filled, points)` lexicographic
- [x] 1.3 `build_candidates()` — IR excluded structurally, unstartable zeroed, missing pinned
- [x] 1.4 Incumbents ordered first so ties resolve to no change

## 2. Advice
- [x] 2.1 `_moves()` — slot-level swaps, incumbents keep their numbered slot
- [x] 2.2 `MIN_MATERIAL_GAIN` — immaterial moves reverted, `gain` recomputed from survivors
- [x] 2.3 `sources_agree` / `consensus` compared after materiality
- [x] 2.4 `advice_available` distinguishes "cannot evaluate" from "already optimal"

## 3. API + UI
- [x] 3.1 `GET /api/teams/{team_id}/lineup?week&source`
- [x] 3.2 `useLineupAdvice` hook, separate query so it never blocks the roster
- [x] 3.3 `LineupAdviceCard` — quiet by default, three distinct states
- [x] 3.4 `.lineup-*` styles

## 4. Injury bridge
- [x] 4.1 `players.espn_athlete_id` + migration `d3a7c05b91e4`
- [x] 4.2 `bridge_espn_athlete_ids()` in the Sleeper refresh
- [x] 4.3 `espn_injuries.espn_athlete_id()` consults it; D/ST stays unsupported
- [x] 4.4 `api/players.py` reports the bridged `detail_supported`

## 5. Tests
- [x] 5.1 Solver: greedy-beating case, empty slots, capacity groups
- [x] 5.2 Candidates: all three honesty rules, incumbent tie-break
- [x] 5.3 Advice: material swap, reverted swap, unstartable, gain invariant, unavailable
- [x] 5.4 Bridge: Yahoo rescued, ESPN untouched, D/ST refused, idempotent
- [x] 5.5 API: envelope, both sources, 422 on a bad source, 404 on unknown team
- [x] 5.6 `LineupAdviceCard`: three states, consensus marker, unevaluated list
