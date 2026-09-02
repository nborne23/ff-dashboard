# add-player-health

## Why

`Player.injury_status` has been carried end-to-end since the data-model phase, but the UI
renders exactly one designation: `RosterTable` prints "OUT" for `O` and nothing else. A
questionable starter, an IR stash and a healthy player are visually identical on MyTeam,
Game Day, Head-to-Head and Waivers.

Two defects surfaced while scoping this:

1. **`NORMAL` is unmapped.** ESPN's fantasy API sends `injuryStatus: "NORMAL"` far more
   often than `"ACTIVE"` (312 vs 219 occurrences across this install's cached payloads).
   `INJURY_STATUS_MAP` has no `NORMAL` key, so those players persist `injury_status = NULL`
   — 200 of the 1030 rows in `players`. "Unknown" and "healthy" are indistinguishable today.
2. **Yahoo asserts health it doesn't have.** `_map_injury_status` falls back to `"ACTIVE"`
   on an unrecognized code, which is the opposite of the ESPN mapper's stated rule
   (unknown -> `None`) and turns a designation we failed to parse into a claim the player
   is fine.

The status code alone is also thin. "Q" doesn't say knee vs hamstring, practice
participation, or whether the guy is trending up. ESPN publishes that detail on a public,
unauthenticated endpoint (verified live, see design below), so a per-player detail panel
is cheap.

## What Changes

- **Status vocabulary** widens from `ACTIVE|Q|D|O|IR|PUP` to add `DTD`, `SUSP`, `NFI`.
  `NORMAL` maps to `ACTIVE`; unrecognized codes stay `None` and are logged at WARNING on
  both platforms so a future gap surfaces instead of silently becoming a wrong answer.
- **New `player_injuries` table + `refresh_injuries` job**, fed by ESPN's public core API
  (`sports.core.api.espn.com/.../seasons/{season}/athletes/{id}/injuries`). Swept only for
  players whose fantasy status is already non-healthy, so it is tens of requests, not
  thousands.
- **`GET /api/players/{player_id}/injury`** — cache-only read (design D7), envelope-wrapped.
- **`InjuryBadge`** on MyTeam roster, Game Day mirrored roster, Head-to-Head and Waivers.
- **`PlayerHealthPanel`** — click a badge to open the detail dialog (injury type, body
  location, side, surgery/rehab detail, projected return date, ESPN's short and long
  comments, and when the report was filed).

## Impact

- Affected specs: `player-health` (new)
- Affected code: `schemas/players.py`, `platforms/espn/mapper.py`, `platforms/yahoo/mapper.py`,
  `platforms/espn_injuries.py` (new), `models/player_injuries.py` (new), one alembic migration,
  `scheduler.py`, `api/players.py` (new), `types/api.ts`, `components/shared/InjuryBadge.tsx`
  (new), `components/shared/PlayerHealthPanel.tsx` (new), `api/players.ts` (new),
  `RosterTable`, `MirroredRoster`, `H2HTable`, `WaiverTable`, `global.css`.
