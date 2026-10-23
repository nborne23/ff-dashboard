# add-player-stats

## Why

A roster row shows one number per player per week. There is no way to see what produced it
(the stat line, how the league priced each stat) or whether it is typical for that player
(his game log this season, his previous seasons). Both questions come up most during live
games, when the number is moving.

## What Changes

- **Clickable players.** The name and the headshot on My Team, Matchups (both sides),
  Game Day, Waivers and the lineup advice card (Game Day: name only) open a player stats card.
- **This week.** The card shows the league's own points and projection, live status, the
  stat line, and a line-by-line **points breakdown**:
  - ESPN leagues: ESPN's own `appliedStats` for that league, read from the roster payload
    `refresh_fantasy` already caches. Exact, and as live as the roster.
  - Yahoo leagues and unrostered players: the Sleeper stat line priced with standard rules
    for the league's format. Once the week is final, a reconciling line brings the total to
    the league's own score. While the week is in progress it is labelled an estimate and is
    not reconciled, because the two numbers refresh on different clocks.
- **History.** A per-season game log with a season picker, totals, and a by-season career
  table. The current season plus the nine before it, regular season.
- **New ingest.** The `refresh_player_stats` job pulls Sleeper's bulk weekly stats feed
  (Sportradar data) into `player_weekly_stats`. `players.sleeper_id` is the bridge from our
  per-platform ids.

## Impact

- New: `player_weekly_stats`, `player_stat_seasons`, `players.sleeper_id` (migration
  `e8b2f4a6c013`), `GET /api/players/{id}/stats`, `refresh_player_stats` job.
- One-time backfill of ~180 upstream calls (~45 s, ~74k rows, measured on this install).
  After that: one call per tick while games are live, two every 30 minutes otherwise.
- No upstream request on read (design.md D7 holds).
