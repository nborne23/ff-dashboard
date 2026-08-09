"""`services/cache.py` — get/set/expiry/invalidate + stable `params_hash`."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, HttpCache
from backend.gridiron.services import cache

# --- select_ttl (task 9.5) ---------------------------------------------------------------


def test_select_ttl_returns_default_when_week_is_current() -> None:
    default = timedelta(hours=1)
    assert cache.select_ttl(week=14, current_week=14, default_ttl=default) == default


def test_select_ttl_returns_default_for_the_just_finished_week() -> None:
    """`current_week == week + 1` is still "just finished" — late stat corrections are
    still expected, so it keeps the short default rather than the 24h past-week TTL."""
    default = timedelta(hours=1)
    assert cache.select_ttl(week=13, current_week=14, default_ttl=default) == default


def test_select_ttl_returns_24h_once_a_full_week_has_elapsed() -> None:
    default = timedelta(hours=1)
    assert cache.select_ttl(week=12, current_week=14, default_ttl=default) == cache.PAST_WEEK_TTL
    assert cache.PAST_WEEK_TTL == timedelta(hours=24)


def test_select_ttl_returns_default_when_current_week_is_unknown() -> None:
    """`current_week=None` (the caller doesn't know) always preserves the default —
    every call site that predates task 9.5 keeps its old behavior unchanged."""
    default = timedelta(hours=1)
    assert cache.select_ttl(week=1, current_week=None, default_ttl=default) == default


def test_params_hash_is_stable_regardless_of_key_order() -> None:
    a = cache.params_hash({"week": 14, "team": "yahoo:1"})
    b = cache.params_hash({"team": "yahoo:1", "week": 14})
    assert a == b
    assert len(a) == 64  # sha256 hex digest


def test_params_hash_none_and_empty_dict_are_equivalent() -> None:
    assert cache.params_hash(None) == cache.params_hash({})


def test_params_hash_differs_for_different_params() -> None:
    assert cache.params_hash({"week": 14}) != cache.params_hash({"week": 15})


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "cache.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_returns_none_when_never_cached(session_factory) -> None:
    async with session_factory() as session:
        entry = await cache.get(session, "yahoo", "/teams", {"week": 14})
        assert entry is None


@pytest.mark.asyncio
async def test_set_then_get_round_trips_and_is_not_expired(session_factory) -> None:
    future = datetime.now(UTC) + timedelta(minutes=30)
    async with session_factory() as session:
        await cache.set(
            session, "yahoo", "/teams", {"week": 14}, '{"teams": []}', expires_at=future
        )

    async with session_factory() as session:
        entry = await cache.get(session, "yahoo", "/teams", {"week": 14})
        assert entry is not None
        assert entry.raw_json == '{"teams": []}'
        assert entry.is_expired is False


@pytest.mark.asyncio
async def test_get_marks_expired_rows_but_still_returns_them(session_factory) -> None:
    past = datetime.now(UTC) - timedelta(minutes=5)
    async with session_factory() as session:
        await cache.set(session, "espn", "/roster", None, '{"stale": true}', expires_at=past)

    async with session_factory() as session:
        entry = await cache.get(session, "espn", "/roster", None)
        assert entry is not None
        assert entry.raw_json == '{"stale": true}'
        assert entry.is_expired is True


@pytest.mark.asyncio
async def test_set_upserts_existing_row(session_factory) -> None:
    future = datetime.now(UTC) + timedelta(minutes=30)
    async with session_factory() as session:
        await cache.set(session, "yahoo", "/teams", {"week": 14}, '{"v": 1}', expires_at=future)
        await cache.set(session, "yahoo", "/teams", {"week": 14}, '{"v": 2}', expires_at=future)

    async with session_factory() as session:
        entry = await cache.get(session, "yahoo", "/teams", {"week": 14})
        assert entry is not None
        assert entry.raw_json == '{"v": 2}'

    async with session_factory() as session:
        result = await session.execute(HttpCache.__table__.select())
        rows = result.fetchall()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_invalidate_by_exact_key_expires_row_without_deleting_it(session_factory) -> None:
    """Invalidation marks `expires_at = now()` rather than deleting — design.md D7 requires
    reads to always serve whatever's cached, even a just-invalidated (stale) row."""
    future = datetime.now(UTC) + timedelta(minutes=30)
    async with session_factory() as session:
        await cache.set(session, "yahoo", "/teams", {"week": 14}, "{}", expires_at=future)
        await cache.set(session, "yahoo", "/teams", {"week": 15}, "{}", expires_at=future)

    async with session_factory() as session:
        await cache.invalidate(session, platform="yahoo", endpoint="/teams", params={"week": 14})

    async with session_factory() as session:
        invalidated = await cache.get(session, "yahoo", "/teams", {"week": 14})
        assert invalidated is not None
        assert invalidated.is_expired is True

        untouched = await cache.get(session, "yahoo", "/teams", {"week": 15})
        assert untouched is not None
        assert untouched.is_expired is False


@pytest.mark.asyncio
async def test_invalidate_by_platform(session_factory) -> None:
    future = datetime.now(UTC) + timedelta(minutes=30)
    async with session_factory() as session:
        await cache.set(session, "yahoo", "/teams", None, "{}", expires_at=future)
        await cache.set(session, "yahoo", "/roster", None, "{}", expires_at=future)
        await cache.set(session, "espn", "/teams", None, "{}", expires_at=future)

    async with session_factory() as session:
        await cache.invalidate(session, platform="yahoo")

    async with session_factory() as session:
        teams_entry = await cache.get(session, "yahoo", "/teams", None)
        roster_entry = await cache.get(session, "yahoo", "/roster", None)
        espn_entry = await cache.get(session, "espn", "/teams", None)

        assert teams_entry is not None and teams_entry.is_expired is True
        assert roster_entry is not None and roster_entry.is_expired is True
        assert espn_entry is not None and espn_entry.is_expired is False


@pytest.mark.asyncio
async def test_invalidate_all(session_factory) -> None:
    future = datetime.now(UTC) + timedelta(minutes=30)
    async with session_factory() as session:
        await cache.set(session, "yahoo", "/teams", None, "{}", expires_at=future)
        await cache.set(session, "espn", "/teams", None, "{}", expires_at=future)

    async with session_factory() as session:
        await cache.invalidate(session)

    async with session_factory() as session:
        yahoo_entry = await cache.get(session, "yahoo", "/teams", None)
        espn_entry = await cache.get(session, "espn", "/teams", None)

        assert yahoo_entry is not None and yahoo_entry.is_expired is True
        assert espn_entry is not None and espn_entry.is_expired is True


@pytest.mark.asyncio
async def test_invalidate_rejects_endpoint_without_platform(session_factory) -> None:
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await cache.invalidate(session, endpoint="/teams")


@pytest.mark.asyncio
async def test_invalidate_rejects_params_without_endpoint(session_factory) -> None:
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await cache.invalidate(session, platform="yahoo", params={"week": 14})
