"""Historical weekly stat lines from Sleeper's public stats feed (add-player-stats).

    https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular&position[]=QB...

One call returns every player's line for that week (~450 fantasy-relevant rows,
~250 KB gzipped), so a whole season is 18 calls regardless of how many players the user
cares about. That is what makes it possible to keep the no-fetch-on-read rule (design.md
D7) for a feature whose natural shape is "look up whoever was clicked": everything is
ingested ahead of time, and the read path only ever touches the table.

Undocumented, like the projections host next door — same handling: fail soft, keep the
last good rows.

Backfill shape:

- Past seasons (back to `HISTORY_SEASONS - 1` years before the current one) are pulled
  once and marked `complete` in `player_stat_seasons`. They never change again.
- The current season fetches any weeks not yet pulled, and ALWAYS re-pulls the current
  week and the one before it: the current week is in progress, and the previous one is
  still taking stat corrections.

Cadence: the job ticks every `LIVE_INTERVAL` but only does work on a tick when games are
live (then just the current week — one call) or when `FULL_INTERVAL` has passed since the
last full pass. That keeps a Yahoo player's in-game stat line about two minutes behind
without hitting a free endpoint every two minutes on a Tuesday.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.models import Player, PlayerStatSeason, PlayerWeeklyStat
from backend.gridiron.platforms import sleeper

logger = logging.getLogger("uvicorn.error")

STATS_BASE = "https://api.sleeper.com/stats/nfl"

# The current season plus nine before it. Ten years covers every active player's career
# but a handful of veterans, and the first backfill stays under ~200 calls.
HISTORY_SEASONS = 10

# Regular season only. 2016-2020 had 17 weeks; asking for an 18th just returns `[]`.
MAX_WEEK = 18

LIVE_INTERVAL = timedelta(minutes=2)
FULL_INTERVAL = timedelta(minutes=30)

# Sleeper's position vocabulary. Server-side filtering cuts each payload from ~2,000 rows
# (IDP, OL, long snappers) to the ~450 a fantasy roster can hold.
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

# Everything the stats panel's columns read, plus `gp`. See `services/player_stats.py`
# for which position shows which. The rest of each raw line is dropped at ingest.
KEPT_STATS = frozenset(
    {
        "gp",
        "off_snp",
        "tm_off_snp",
        "pass_cmp",
        "pass_att",
        "pass_yd",
        "pass_td",
        "pass_int",
        "rush_att",
        "rush_yd",
        "rush_td",
        "rec_tgt",
        "rec",
        "rec_yd",
        "rec_td",
        "fum_lost",
        "pass_2pt",
        "rush_2pt",
        "rec_2pt",
        "fgm",
        "fgm_0_19",
        "fgm_20_29",
        "fgm_30_39",
        "fgm_40_49",
        "fgm_50p",
        "fgmiss",
        "xpmiss",
        "fga",
        "fgm_lng",
        "xpm",
        "xpa",
        "sack",
        "int",
        "fum_rec",
        "td",
        "safe",
        "blk_kick",
        "pts_allow",
        "yds_allow",
    }
)


class SleeperStatsClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        # Same explicit UA as `SleeperClient` — a bare python UA gets a 403 here.
        self._http = http_client or httpx.AsyncClient(
            timeout=60, headers={"User-Agent": "GridIron/1.0 (self-hosted fantasy dashboard)"}
        )
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_week(self, season: int, week: int) -> list[dict]:
        response = await self._http.get(
            f"{STATS_BASE}/{season}/{week}",
            params=[("season_type", "regular"), *(("position[]", p) for p in POSITIONS)],
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []


def map_row(row: dict, *, season: int, week: int, fetched_at: datetime) -> dict | None:
    """One upstream row -> `player_weekly_stats` values, or None when it isn't a game played.

    Sleeper also emits rows for players who were active but never touched the field
    (`gp` 0, or a stats dict of nothing but snap counts). Those are not games in a game
    log, and keeping them would make "games played" a lie.
    """
    stats = row.get("stats") or {}
    if not row.get("player_id") or not stats.get("gp"):
        return None
    return {
        "sleeper_id": str(row["player_id"]),
        "season": season,
        "week": week,
        "team": row.get("team"),
        "opponent": row.get("opponent"),
        "game_date": row.get("date"),
        "pts_ppr": stats.get("pts_ppr"),
        "pts_half_ppr": stats.get("pts_half_ppr"),
        "pts_std": stats.get("pts_std"),
        "stats_json": json.dumps(
            {k: v for k, v in stats.items() if k in KEPT_STATS}, sort_keys=True
        ),
        "fetched_at": fetched_at,
    }


async def _upsert_week(session: AsyncSession, values: list[dict]) -> None:
    """Bulk upsert. `session.merge` would issue a SELECT per row — ~90k on first backfill."""
    if not values:
        return
    stmt = insert(PlayerWeeklyStat)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sleeper_id", "season", "week"],
        set_={
            col: stmt.excluded[col]
            for col in (
                "team",
                "opponent",
                "game_date",
                "pts_ppr",
                "pts_half_ppr",
                "pts_std",
                "stats_json",
                "fetched_at",
            )
        },
    )
    # SQLite caps bound parameters per statement; 12 columns x 400 rows stays well under.
    for start in range(0, len(values), 400):
        await session.execute(stmt, values[start : start + 400])


def weeks_to_fetch(
    season: int, current_season: int, current_week: int, state: PlayerStatSeason | None
) -> list[int]:
    """Which weeks of `season` this run should pull. Pure, so the policy is testable."""
    if season < current_season:
        return [] if state is not None and state.complete else list(range(1, MAX_WEEK + 1))
    through = state.fetched_through_week if state is not None else 0
    # Never-fetched weeks, plus the in-progress week and the one taking corrections.
    pending = set(range(through + 1, current_week + 1))
    pending |= {w for w in (current_week - 1, current_week) if w >= 1}
    return sorted(pending)


def is_full_pass_due(state: PlayerStatSeason | None, now: datetime) -> bool:
    """Whether this tick does the full pass (bridge + backfill + tail) or only the live week."""
    return state is None or state.fetched_at is None or now - state.fetched_at >= FULL_INTERVAL


async def _fetch_weeks(
    session: AsyncSession,
    client: SleeperStatsClient,
    season: int,
    weeks: list[int],
    fetched_at: datetime,
) -> int:
    rows = 0
    for week in weeks:
        upstream = await client.get_week(season, week)
        values = [
            v
            for v in (map_row(r, season=season, week=week, fetched_at=fetched_at) for r in upstream)
            if v is not None
        ]
        await _upsert_week(session, values)
        # Per week, not per season: holding SQLite's write lock across 18 HTTP calls
        # (~5 s) would stall `refresh_fantasy` on a game day. Re-pulling a half-done
        # season is an idempotent upsert, so nothing depends on the season commit.
        await session.commit()
        rows += len(values)
    return rows


async def fetch_and_upsert(
    session: AsyncSession,
    client: SleeperStatsClient | None = None,
    players_client: sleeper.SleeperClient | None = None,
    *,
    live: bool = False,
) -> str | None:
    owns_client = client is None
    client = client or SleeperStatsClient()
    owns_players_client = players_client is None
    players_client = players_client or sleeper.SleeperClient()
    now = datetime.now(UTC).replace(tzinfo=None)
    calls = rows = bridged = 0
    try:
        current_season, current_week = await sleeper._season_and_week(session)
        states = {s.season: s for s in (await session.execute(select(PlayerStatSeason))).scalars()}
        current_state = states.get(current_season)
        if not is_full_pass_due(current_state, now):
            if not live:
                return None
            # Live tick: the in-progress week only. `fetched_at` is deliberately left
            # alone so the full pass (stat corrections, the bridge) still comes due.
            rows = await _fetch_weeks(session, client, current_season, [current_week], now)
            await session.commit()
            logger.info("refresh_player_stats live week=%d rows=%d", current_week, rows)
            return None

        # Bridge first: a player with no `sleeper_id` has stats on file that nothing can
        # reach. The dump comes from `http_cache` (24 h), so this is a parse, not a fetch.
        dump = await players_client.get_players(session)
        players = list((await session.execute(select(Player))).scalars().all())
        bridged = sleeper.bridge_sleeper_ids(dump, players)
        await session.commit()

        for season in range(current_season - HISTORY_SEASONS + 1, current_season + 1):
            weeks = weeks_to_fetch(season, current_season, current_week, states.get(season))
            if not weeks:
                continue
            rows += await _fetch_weeks(session, client, season, weeks, now)
            calls += len(weeks)

            state = states.get(season) or PlayerStatSeason(season=season, fetched_through_week=0)
            state.complete = season < current_season
            state.fetched_through_week = max(state.fetched_through_week or 0, max(weeks))
            state.fetched_at = now
            session.add(state)
            # Per season, so an interrupted backfill keeps what it finished.
            await session.commit()
    except httpx.HTTPError as exc:
        await session.rollback()
        return f"sleeper stats unavailable: {type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            await client.aclose()
        if owns_players_client:
            await players_client.aclose()

    logger.info(
        "refresh_player_stats season=%d week=%d calls=%d rows=%d bridged=%d",
        current_season,
        current_week,
        calls,
        rows,
        bridged,
    )
    return None
