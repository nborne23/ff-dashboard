"""The NFL regular-season schedule, from Sleeper's public feed (player game log).

    https://api.sleeper.com/schedule/nfl/regular/{season}

One call returns the whole season — 272 games of `{week, home, away, date, status,
game_id}` — in the team codes the rosters use ("WAS", not the scoreboard's "WSH"). That
is what the player card's game log needs and nothing else here has: who a player faces
in a week that hasn't happened yet, and which week is his bye. ESPN's scoreboard
(`platforms/nfl_scoreboard.py`) stays the source for live scores; this carries pairings
and dates only.

Stored in `http_cache` like the player dump next door, so there is no table to migrate.
The `refresh_player_stats` full pass refreshes it (re-fetching only once the TTL lapses);
reads go through `get_cached` and never fetch (design.md D7).
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.services import cache

logger = logging.getLogger("uvicorn.error")

SCHEDULE_BASE = "https://api.sleeper.com/schedule/nfl/regular"
CACHE_PLATFORM = "sleeper"
CACHE_ENDPOINT = "schedule"

# Flexed kickoffs move a game's date, never its pairing or week, and nothing here reads
# a kickoff time — twice a day is plenty.
SCHEDULE_TTL = timedelta(hours=12)


@dataclass(frozen=True)
class ScheduleGame:
    week: int
    home: str
    away: str
    # `YYYY-MM-DD`, the local (Eastern) calendar date of the game.
    date: str | None
    status: str | None
    game_id: str | None


def _params(season: int) -> dict:
    return {"season": season}


def parse(payload: object) -> list[ScheduleGame]:
    """Upstream rows -> games, dropping anything without a week and both teams."""
    games: list[ScheduleGame] = []
    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            week = int(row["week"])
            home, away = str(row["home"]), str(row["away"])
        except (KeyError, TypeError, ValueError):
            continue
        games.append(
            ScheduleGame(
                week=week,
                home=home,
                away=away,
                date=row.get("date"),
                status=row.get("status"),
                game_id=str(row["game_id"]) if row.get("game_id") is not None else None,
            )
        )
    return games


async def get_cached(session: AsyncSession, season: int) -> list[ScheduleGame]:
    """The stored schedule for `season`, stale or not; `[]` when it was never fetched."""
    entry = await cache.get(session, CACHE_PLATFORM, CACHE_ENDPOINT, _params(season))
    if entry is None or not entry.raw_json:
        return []
    try:
        return parse(json.loads(entry.raw_json))
    except json.JSONDecodeError:
        return []


class ScheduleSource(Protocol):
    """Anything that can fetch a season's raw schedule JSON — `SleeperStatsClient` in
    production (same host, same User-Agent), a fake in tests."""

    async def get_schedule(self, season: int) -> str: ...


async def fetch_raw(http: httpx.AsyncClient, season: int) -> str:
    response = await http.get(f"{SCHEDULE_BASE}/{season}")
    response.raise_for_status()
    return response.text


async def refresh(session: AsyncSession, source: ScheduleSource, season: int) -> bool:
    """Fetch and store `season`'s schedule unless the cached copy is still fresh.

    Returns whether a fetch happened. Raises `httpx.HTTPError` for the caller to log — a
    missing schedule only costs the game log its future rows, so callers fail soft.
    """
    entry = await cache.get(session, CACHE_PLATFORM, CACHE_ENDPOINT, _params(season))
    if entry is not None and not entry.is_expired:
        return False
    raw = await source.get_schedule(season)
    if not parse(json.loads(raw)):
        # An empty or reshaped payload must not overwrite a good copy.
        logger.warning("nfl schedule %d: upstream returned no games; keeping cache", season)
        return False
    expires_at = datetime.now(UTC).replace(tzinfo=None) + SCHEDULE_TTL
    await cache.set(session, CACHE_PLATFORM, CACHE_ENDPOINT, _params(season), raw, expires_at)
    return True


def game_for(games: list[ScheduleGame], team: str | None, week: int) -> ScheduleGame | None:
    if not team:
        return None
    return next((g for g in games if g.week == week and team in (g.home, g.away)), None)


def bye_week(games: list[ScheduleGame], team: str | None) -> int | None:
    """The first regular-season week `team` has no game, or None when unknown."""
    if not team or not games:
        return None
    played = {g.week for g in games if team in (g.home, g.away)}
    if not played:
        return None  # not a team on this schedule ("FA", a typo)
    last = max(g.week for g in games)
    return next((w for w in range(1, last + 1) if w not in played), None)
