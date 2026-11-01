"""The `refresh_nfl_weeks` job: every regular-season week's scoreboard and projections
(add-nfl-scores).

`refresh_nfl_state` already keeps the CURRENT week's scoreboard fresh every tick. This job
fills in the rest of the season so the Scores screen can switch weeks, plus Sleeper's
all-player projections for each week so a game's Fantasy tab has both depth charts before
kickoff. Both upstreams are public and unauthenticated.

What a pass fetches:

- A week's scoreboard unless it's already cached AND every game in it is over AND it's
  behind the current week. Finished weeks never change, so the first pass is ~18 calls and
  the rest are only what's still to be played.
- A week's projections unless it's cached and behind the current week. Rotowire revises
  projections on news until kickoff, and a past week's never change again.
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gridiron.platforms.nfl_scoreboard import SCOREBOARD_URL
from backend.gridiron.platforms.sleeper import PROJECTIONS_BASE
from backend.gridiron.platforms.sleeper_stats import POSITIONS
from backend.gridiron.services import nfl_week_cache

logger = logging.getLogger("uvicorn.error")

_FINISHED = ("post", "postponed")


class NflWeeksClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        # Sleeper 403s a bare python UA; ESPN doesn't care. One client serves both.
        self._http = http_client or httpx.AsyncClient(
            timeout=30, headers={"User-Agent": "GridIron/1.0 (self-hosted fantasy dashboard)"}
        )
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_scoreboard(self, season: int | None = None, week: int | None = None) -> dict:
        params = (
            {"dates": season, "seasontype": nfl_week_cache.REGULAR_SEASON, "week": week}
            if season is not None and week is not None
            else None
        )
        response = await self._http.get(SCOREBOARD_URL, params=params)
        response.raise_for_status()
        return response.json()

    async def get_projections(self, season: int, week: int) -> list[dict]:
        response = await self._http.get(
            f"{PROJECTIONS_BASE}/{season}/{week}",
            params=[("season_type", "regular"), *(("position[]", p) for p in POSITIONS)],
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []


def scoreboard_is_settled(cached: dict | None, week: int, current_week: int) -> bool:
    """Whether a cached week can be skipped. Pure, so the policy is testable."""
    if cached is None or week >= current_week:
        return False
    events = cached.get("events") or []
    return bool(events) and all(e.get("state") in _FINISHED for e in events)


async def _current(session: AsyncSession, client: NflWeeksClient) -> tuple[int, int] | None:
    current = await nfl_week_cache.read_current(session)
    if current is not None:
        return current
    # Never seen a `refresh_nfl_state` tick (fresh install, or the scheduler's off):
    # ask ESPN which week it is, and keep the answer.
    trimmed = nfl_week_cache.trim_scoreboard(await client.get_scoreboard())
    if trimmed is None:
        return None
    await nfl_week_cache.store_week(session, trimmed, current=True)
    return trimmed["season"], trimmed["week"]


async def fetch_and_cache(
    session: AsyncSession, client: NflWeeksClient | None = None
) -> str | None:
    owns_client = client is None
    client = client or NflWeeksClient()
    scoreboards = projections = 0
    try:
        current = await _current(session, client)
        if current is None:
            # Off-season or postseason: there's no regular-season week to fill in.
            return None
        season, current_week = current
        for week in range(1, nfl_week_cache.MAX_WEEK + 1):
            cached = await nfl_week_cache.read_week(session, season, week)
            if not scoreboard_is_settled(cached[0] if cached else None, week, current_week):
                trimmed = nfl_week_cache.trim_scoreboard(await client.get_scoreboard(season, week))
                if trimmed is not None:
                    # Never `current=True` here: the pointer belongs to the live tick.
                    await nfl_week_cache.store_week(session, trimmed)
                    scoreboards += 1
            if week >= current_week or not await nfl_week_cache.has_projections(
                session, season, week
            ):
                rows = await client.get_projections(season, week)
                await nfl_week_cache.store_projections(
                    session, season, week, nfl_week_cache.trim_projections(rows)
                )
                projections += 1
    except httpx.HTTPError as exc:
        await session.rollback()
        return f"nfl weeks unavailable: {type(exc).__name__}: {exc}"
    finally:
        if owns_client:
            await client.aclose()

    logger.info(
        "refresh_nfl_weeks season=%d week=%d scoreboards=%d projections=%d",
        season,
        current_week,
        scoreboards,
        projections,
    )
    return None
