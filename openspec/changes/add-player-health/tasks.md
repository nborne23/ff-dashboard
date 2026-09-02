# Tasks — add-player-health

## 1. Status vocabulary
- [x] 1.1 Widen `InjuryStatus` to add `DTD`, `SUSP`, `NFI` (`backend/gridiron/schemas/players.py`)
- [x] 1.2 ESPN mapper: `NORMAL`->`ACTIVE`, new codes, WARNING on unrecognized
- [x] 1.3 Yahoo mapper: unknown -> `None` (was `"ACTIVE"`), new codes, WARNING on unrecognized
- [x] 1.4 Mirror the literal in `frontend/src/types/api.ts`
- [x] 1.5 ESPN roster path: read the designation from `teams[].roster.entries[]` — it is
      NOT on the player object there, so every rostered player mapped to `None` regardless
      of the `NORMAL` fix (`injury_status_by_player_id`, threaded into
      `map_roster`/`map_matchup`)

## 2. Injury detail pipeline
- [x] 2.1 `models/player_injuries.py` + register on `models/__init__`
- [x] 2.2 Alembic migration (head `380dfc2ab9bc`)
- [x] 2.3 `schemas/player_injuries.py` — `PlayerInjuryReport`, `PlayerInjuryData`
- [x] 2.4 `platforms/espn_injuries.py` — client, mapper, `fetch_and_upsert`
- [x] 2.5 `refresh_injuries` scheduler job, fixed 30-min cadence

## 3. Read API
- [x] 3.1 `api/players.py` — `GET /api/players/{player_id}/injury`, cache-only, envelope-wrapped
- [x] 3.2 Register the router in `backend/main.py`

## 4. UI
- [x] 4.1 `.pill.inj-*` variants in `global.css`
- [x] 4.2 `components/shared/InjuryBadge.tsx`
- [x] 4.3 `components/shared/PlayerHealthPanel.tsx` + `api/players.ts`
- [x] 4.4 Wire into `RosterTable`, `MirroredRoster`, `H2HTable`, `WaiverTable`

## 5. Tests
- [x] 5.1 Mapper tests for `NORMAL`, the new codes, and unknown -> `None`
- [x] 5.2 `espn_injuries` mapper/upsert tests incl. `count: 0` and skipped id classes
- [x] 5.3 `GET /api/players/{id}/injury` API test
- [x] 5.4 `InjuryBadge` / `PlayerHealthPanel` component tests
