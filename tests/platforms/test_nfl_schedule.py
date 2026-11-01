"""Sleeper's season schedule: parsing, the cache-only read path, and the refresh policy
(player game log)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base
from backend.gridiron.platforms import nfl_schedule
from backend.gridiron.services import cache

SCHEDULE = [
    {"week": 1, "home": "NE", "away": "BUF", "date": "2026-09-13", "status": "complete"},
    {"week": 2, "home": "MIA", "away": "NE", "date": "2026-09-20", "game_id": 202620},
    {"week": 2, "home": "BUF", "away": "NYJ", "date": "2026-09-20"},
    # Week 3: NE is off.
    {"week": 3, "home": "MIA", "away": "BUF", "date": "2026-09-27"},
    {"week": 4, "home": "NE", "away": "NYJ", "date": "2026-10-04"},
]


class FakeSource:
    def __init__(self, payload: object = SCHEDULE):
        self.payload = payload
        self.calls: list[int] = []

    async def get_schedule(self, season: int) -> str:
        self.calls.append(season)
        return json.dumps(self.payload)


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "schedule.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def test_parse_drops_rows_without_week_or_teams():
    games = nfl_schedule.parse([*SCHEDULE, {"week": "x", "home": "A"}, {"home": "A"}, "junk"])
    assert len(games) == len(SCHEDULE)
    assert games[1] == nfl_schedule.ScheduleGame(
        week=2, home="MIA", away="NE", date="2026-09-20", status=None, game_id="202620"
    )
    assert nfl_schedule.parse({"not": "a list"}) == []


def test_game_for_and_bye_week():
    games = nfl_schedule.parse(SCHEDULE)
    assert nfl_schedule.game_for(games, "NE", 2).home == "MIA"
    assert nfl_schedule.game_for(games, "NE", 3) is None
    assert nfl_schedule.game_for(games, None, 1) is None
    assert nfl_schedule.bye_week(games, "NE") == 3
    assert nfl_schedule.bye_week(games, "FA") is None
    assert nfl_schedule.bye_week([], "NE") is None


async def test_refresh_stores_then_skips_while_fresh(db):
    source = FakeSource()
    async with db() as session:
        assert await nfl_schedule.get_cached(session, 2026) == []
        assert await nfl_schedule.refresh(session, source, 2026) is True
        assert await nfl_schedule.refresh(session, source, 2026) is False
        assert source.calls == [2026]
        games = await nfl_schedule.get_cached(session, 2026)
        assert [g.week for g in games] == [1, 2, 2, 3, 4]


async def test_refresh_refetches_once_expired(db):
    source = FakeSource()
    async with db() as session:
        await cache.set(
            session,
            nfl_schedule.CACHE_PLATFORM,
            nfl_schedule.CACHE_ENDPOINT,
            {"season": 2026},
            json.dumps(SCHEDULE[:1]),
            datetime.now(UTC) - timedelta(minutes=1),
        )
        assert await nfl_schedule.refresh(session, source, 2026) is True
        assert len(await nfl_schedule.get_cached(session, 2026)) == len(SCHEDULE)


async def test_empty_upstream_keeps_the_good_copy(db):
    async with db() as session:
        await nfl_schedule.refresh(session, FakeSource(), 2026)
        entry = await cache.get(session, "sleeper", "schedule", {"season": 2026})
        await cache.set(
            session,
            "sleeper",
            "schedule",
            {"season": 2026},
            entry.raw_json,
            datetime.now(UTC) - timedelta(minutes=1),
        )
        assert await nfl_schedule.refresh(session, FakeSource(payload=[]), 2026) is False
        assert len(await nfl_schedule.get_cached(session, 2026)) == len(SCHEDULE)
