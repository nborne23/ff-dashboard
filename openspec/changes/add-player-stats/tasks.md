# Tasks — add-player-stats

## 1. Ingest
- [x] 1.1 `models/player_stats.py` (`PlayerWeeklyStat`, `PlayerStatSeason`), `players.sleeper_id`
- [x] 1.2 Migration `e8b2f4a6c013` (head was `d3a7c05b91e4`)
- [x] 1.3 `sleeper.bridge_sleeper_ids`
- [x] 1.4 `platforms/sleeper_stats.py`: client, `map_row`, bulk upsert, backfill/tail policy, live tick
- [x] 1.5 `refresh_player_stats` scheduler job (2 min tick)

## 2. Read API
- [x] 2.1 `schemas/player_stats.py`
- [x] 2.2 `services/player_stats.py`: columns, format, ESPN breakdown, estimated breakdown, summaries
- [x] 2.3 `GET /api/players/{id}/stats`
- [x] 2.4 `espn/client.roster_matchup_params()` shared with the read path

## 3. UI
- [x] 3.1 Types + `usePlayerStats` (30 s poll while live)
- [x] 3.2 `PlayerStatsPanel`: this week, breakdown, game log, by season
- [x] 3.3 `PlayerName` / `PlayerAvatarButton` wired into My Team, Matchups, Game Day, Waivers, lineup advice

## 4. Tests
- [x] 4.1 `tests/platforms/test_sleeper_stats.py`
- [x] 4.2 `tests/api/test_player_stats.py`
- [x] 4.3 `PlayerStatsPanel.test.tsx`
