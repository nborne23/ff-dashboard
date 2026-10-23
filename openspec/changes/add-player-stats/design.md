# Design — add-player-stats

## D1. Ingest ahead of time, never on click
"Whoever was clicked" suggests fetching on demand, which would break D7. Sleeper's bulk
endpoint `stats/nfl/{season}/{week}?position[]=…` returns every fantasy-relevant player's
line for a week in one call (~450 rows, ~250 KB gzipped). A whole season is 18 calls no
matter who gets clicked, so ingesting everything ahead of time is cheap. The per-player
endpoint was rejected: it costs one call per player per season, and it disagreed with the
bulk feed mid-game.

## D2. Keyed by Sleeper id
The same NFL player is two `players` rows when he is on ESPN and Yahoo rosters, and his
2019 log is one fact. `player_weekly_stats` is keyed `(sleeper_id, season, week)`.
`bridge_sleeper_ids` fills `players.sleeper_id` from the Sleeper player dump, trying these
in order:
1. ESPN id or Yahoo id.
2. Normalized name plus NFL team, with ambiguous keys dropped.
3. Team abbreviation for a D/ST, since Sleeper keys DEF that way, relocations included.

Measured coverage: 394 of 394 rostered players, 1270 of 1547 known players.

## D3. Backfill and cadence
`player_stat_seasons` marks a past season `complete` after one full pull, and it is never
fetched again. The current season fetches any weeks it hasn't pulled, and always re-pulls
the current week and the previous one (stat corrections). The job ticks every 2 minutes:
- **Live:** fetches only the current week.
- **Otherwise:** a full pass (bridge, backfill, tail) once 30 minutes have passed.

## D4. Points breakdown sources
ESPN's roster payload carries `appliedStats`, the league's own points per stat id, on the
actual-stats entry. The read path rebuilds the `http_cache` key with
`roster_matchup_params()` and reads the payload; it never fetches. Its lines sum to ESPN's
`appliedTotal` exactly.

Yahoo returns raw stat values but not the league's modifiers, so its breakdown is
estimated. The reconciling line ("Bonuses & league-specific scoring") appears only when the
week is final. Mid-week, the gap between Sleeper's line and the platform score is
refresh lag, not scoring rules, and presenting it as rules would be wrong.

## D5. Points format
The game log is shown in the viewing league's format (`ppr`/`half_ppr`/`standard`, from
Sleeper's three precomputed columns). For `custom`, unlike the projection column (which
shows nothing), history falls back to PPR and the card labels it. A game log without a
points column would be useless.

## D6. UI
`PlayerName` and `PlayerAvatarButton` each own their open state, following the
`PlayerHealth` pattern. The headshot button is `aria-hidden` and out of the tab order,
because the name is the accessible target. The card reuses the `.draft-detail-*` dialog
(portal, Escape, scroll lock), widened to 760 px. Tables scroll sideways on phones. The
query polls every 30 s while the player's game is live.

Game Day names are clickable too. There is no `:teamId` route there, so each panel passes
its own `team_id` down. Its injury badge stays static, as before.
