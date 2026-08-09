"""`services/quiescence.py` — off-season back-off (task 11.7): the pure decision
function plus the `app_settings`-backed watermark it reads."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import AppSetting, Base
from backend.gridiron.schemas.live_nfl_games import LiveNflGame
from backend.gridiron.services import quiescence

NOW = datetime(2026, 3, 1, 12, 0, 0)  # deep off-season — no NFL games in early March


def _game(game_id: str, kickoff_at: datetime, state: str = "pre") -> LiveNflGame:
    return LiveNflGame(
        nfl_game_id=game_id,
        home_team="KC",
        away_team="BUF",
        home_score=0,
        away_score=0,
        state=state,
        clock=None,
        period=None,
        kickoff_at=kickoff_at,
    )


class TestIsOffSeason:
    def test_never_seen_a_kickoff_is_not_off_season(self) -> None:
        # No positive evidence either way yet -- default to the normal cadence rather
        # than a surprising immediate back-off on a fresh database.
        assert quiescence.is_off_season(NOW, None) is False

    def test_kickoff_eight_days_in_the_past_is_off_season(self) -> None:
        assert quiescence.is_off_season(NOW, NOW - timedelta(days=8)) is True

    def test_kickoff_six_days_in_the_past_is_not_off_season(self) -> None:
        assert quiescence.is_off_season(NOW, NOW - timedelta(days=6)) is False

    def test_kickoff_exactly_at_the_threshold_is_not_off_season(self) -> None:
        assert quiescence.is_off_season(NOW, NOW - quiescence.OFF_SEASON_THRESHOLD) is False

    def test_future_kickoff_is_not_off_season(self) -> None:
        # The normal in-season case: the scoreboard already lists next Sunday's games.
        assert quiescence.is_off_season(NOW, NOW + timedelta(days=3)) is False


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "quiescence.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_newest_kickoff_seen_defaults_to_none(session_factory) -> None:
    async with session_factory() as session:
        assert await quiescence.get_newest_kickoff_seen(session) is None


@pytest.mark.asyncio
async def test_record_kickoffs_seen_persists_the_newest_kickoff(session_factory) -> None:
    async with session_factory() as session:
        await quiescence.record_kickoffs_seen(
            session,
            [_game("1", NOW - timedelta(days=1)), _game("2", NOW + timedelta(days=2))],
        )

    async with session_factory() as session:
        newest = await quiescence.get_newest_kickoff_seen(session)
    assert newest == NOW + timedelta(days=2)


@pytest.mark.asyncio
async def test_record_kickoffs_seen_with_empty_games_is_a_noop(session_factory) -> None:
    async with session_factory() as session:
        await quiescence.record_kickoffs_seen(session, [_game("1", NOW)])

    async with session_factory() as session:
        await quiescence.record_kickoffs_seen(session, [])

    async with session_factory() as session:
        assert await quiescence.get_newest_kickoff_seen(session) == NOW


@pytest.mark.asyncio
async def test_record_kickoffs_seen_never_moves_the_watermark_backwards(session_factory) -> None:
    async with session_factory() as session:
        await quiescence.record_kickoffs_seen(session, [_game("1", NOW + timedelta(days=7))])

    async with session_factory() as session:
        # A later tick sees only older games (e.g. a mid-week fetch before the next
        # week's slate is posted) -- the watermark must not regress.
        await quiescence.record_kickoffs_seen(session, [_game("2", NOW)])

    async with session_factory() as session:
        assert await quiescence.get_newest_kickoff_seen(session) == NOW + timedelta(days=7)


@pytest.mark.asyncio
async def test_record_kickoffs_seen_creates_row_when_none_exists(session_factory) -> None:
    async with session_factory() as session:
        await quiescence.record_kickoffs_seen(session, [_game("1", NOW)])

    async with session_factory() as session:
        row = await session.get(AppSetting, quiescence.NEWEST_KICKOFF_KEY)
    assert row is not None
    assert row.value == NOW.isoformat()
