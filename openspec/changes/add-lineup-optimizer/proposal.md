# add-lineup-optimizer

## Why

The gap analysis listed start/sit and a weekly lineup optimizer as the most-used
in-season feature in both competing products, and identified the blocker precisely: not
the mechanics, but the absence of a projection worth optimising against. GridIron already
had weekly per-player projections, slot eligibility, the numbered-slot vocabulary and the
delta arithmetic. `add-sleeper-projections` supplied the missing input.

## What Changes

- **`services/lineup.py`** — an exact max-points legal-assignment solver over the roster,
  plus the start/sit advice built on it.
- **`GET /api/teams/{team_id}/lineup`** — optimal lineup, the moves that reach it, and
  whether the second projection source independently agrees.
- **`LineupAdviceCard`** on MyTeam, above the score.
- **`players.espn_athlete_id`** — the cross-platform bridge that closes
  `detail_supported: false` in the injury panel. Sleeper's dump is the only place in this
  codebase carrying `espn_id` and `yahoo_id` on one record, so a Yahoo-sourced player can
  now reach ESPN's public injury API.

## What deliberately does NOT change

Nothing is written back to the platform. The advice says what to do; you still change the
lineup in ESPN or Yahoo. Write-back is a separate, larger change with an unverified
payload shape (see `add-player-health`'s notes on `scripts/probe-espn-writes.py`).

## Impact

- Affected specs: `lineup-advice` (new)
- Affected code: `services/lineup.py` (new), `schemas/lineup.py` (new), `api/teams.py`,
  `models/players.py` + one migration, `platforms/sleeper.py`, `platforms/espn_injuries.py`,
  `api/players.py`, `types/api.ts`, `api/teams.ts`, `screens/MyTeam/LineupAdviceCard.tsx`
  (new), `screens/MyTeam/index.tsx`, `global.css`.
