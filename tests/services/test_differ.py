"""`services/differ.py` — snapshot-diff fingerprints -> `data.changed` scopes (task 8.4)."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, LiveNflGame, Matchup, SeasonWeek, Team
from backend.gridiron.schemas.events import DataChangedEvent
from backend.gridiron.services import differ, events

WEEK = 14
LEAGUE_ID = "yahoo:l1"
USER_TEAM = "yahoo:l1.t1"
OPP_TEAM = "yahoo:l1.t2"


@pytest.fixture(autouse=True)
def _reset_module_state():
    differ.reset_state()
    events.reset()
    yield
    differ.reset_state()
    events.reset()


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "differ.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _team(team_id: str, is_user_team: bool) -> Team:
    return Team(
        id=team_id,
        league_id=LEAGUE_ID,
        platform="yahoo",
        platform_id=team_id.split(".", 1)[1],
        name=team_id,
        manager_name="Nick",
        record_w=0,
        record_l=0,
        record_t=0,
        rank_current=1,
        rank_total=10,
        points_for=0,
        points_against=0,
        is_user_team=is_user_team,
    )


async def seed_basic(
    session_factory, *, home_score: float = 100.0, away_score: float = 90.0
) -> None:
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE_ID,
                platform="yahoo",
                platform_id="l1",
                name="Test League",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=WEEK,
            )
        )
        session.add(_team(USER_TEAM, True))
        session.add(_team(OPP_TEAM, False))
        session.add(
            Matchup(
                id="yahoo:m1",
                league_id=LEAGUE_ID,
                week=WEEK,
                home_team_id=USER_TEAM,
                away_team_id=OPP_TEAM,
                home_score=home_score,
                away_score=away_score,
                home_proj=0,
                away_proj=0,
                is_complete=False,
            )
        )
        session.add(
            SeasonWeek(
                team_id=USER_TEAM,
                week=WEEK,
                score=home_score,
                opp_score=away_score,
                opp_team_name="Opp",
                is_win=home_score > away_score,
                is_current=True,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_fantasy_fingerprints_empty_db_returns_empty_dict(session_factory) -> None:
    async with session_factory() as session:
        fingerprints = await differ.fantasy_fingerprints(session, WEEK)
    assert fingerprints == {}


@pytest.mark.asyncio
async def test_fantasy_fingerprints_includes_expected_scopes(session_factory) -> None:
    await seed_basic(session_factory)

    async with session_factory() as session:
        fingerprints = await differ.fantasy_fingerprints(session, WEEK)

    assert set(fingerprints) == {
        "teams",
        f"team:{USER_TEAM}",
        f"h2h:{USER_TEAM}",
        f"season:{USER_TEAM}",
    }


@pytest.mark.asyncio
async def test_fantasy_fingerprints_stable_when_nothing_changes(session_factory) -> None:
    await seed_basic(session_factory)

    async with session_factory() as session:
        first = await differ.fantasy_fingerprints(session, WEEK)
    async with session_factory() as session:
        second = await differ.fantasy_fingerprints(session, WEEK)

    assert first == second


@pytest.mark.asyncio
async def test_fantasy_fingerprints_changes_when_matchup_score_changes(session_factory) -> None:
    await seed_basic(session_factory, home_score=100.0)

    async with session_factory() as session:
        before = await differ.fantasy_fingerprints(session, WEEK)

    async with session_factory() as session:
        matchup = await session.get(Matchup, "yahoo:m1")
        matchup.home_score = 110.0
        await session.commit()

    async with session_factory() as session:
        after = await differ.fantasy_fingerprints(session, WEEK)

    assert before["teams"] != after["teams"]
    assert before[f"h2h:{USER_TEAM}"] != after[f"h2h:{USER_TEAM}"]
    # An unrelated scope (season, untouched) stays the same.
    assert before[f"season:{USER_TEAM}"] == after[f"season:{USER_TEAM}"]


@pytest.mark.asyncio
async def test_fantasy_fingerprints_ignores_disabled_leagues(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            League(
                id=LEAGUE_ID,
                platform="yahoo",
                platform_id="l1",
                name="Disabled League",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=WEEK,
                is_enabled=False,
            )
        )
        session.add(_team(USER_TEAM, True))
        await session.commit()

    async with session_factory() as session:
        fingerprints = await differ.fantasy_fingerprints(session, WEEK)

    assert fingerprints == {}


@pytest.mark.asyncio
async def test_live_nfl_games_fingerprints_changes_with_score(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            LiveNflGame(
                nfl_game_id="401",
                home_team="KC",
                away_team="BUF",
                home_score=10,
                away_score=7,
                state="in",
                clock="10:00",
                period=2,
                kickoff_at=datetime(2025, 12, 7, 18, 0, 0),
            )
        )
        await session.commit()

    async with session_factory() as session:
        before = await differ.live_nfl_games_fingerprints(session)

    async with session_factory() as session:
        game = await session.get(LiveNflGame, "401")
        game.home_score = 17
        await session.commit()

    async with session_factory() as session:
        after = await differ.live_nfl_games_fingerprints(session)

    assert before != after
    assert set(before) == {"live_nfl_games"}


# --- diff_and_publish ------------------------------------------------------------


def test_diff_and_publish_publishes_only_changed_scopes_and_returns_them() -> None:
    queue = events.subscribe()

    changed = differ.diff_and_publish({"teams": "hash-a", "team:t1": "hash-b"})
    assert changed == ["team:t1", "teams"]

    event = queue.get_nowait()
    assert isinstance(event, DataChangedEvent)
    assert set(event.scopes) == {"teams", "team:t1"}


def test_diff_and_publish_is_a_no_op_when_fingerprints_are_unchanged() -> None:
    queue = events.subscribe()

    differ.diff_and_publish({"teams": "hash-a"})
    queue.get_nowait()  # drain the first publish

    changed = differ.diff_and_publish({"teams": "hash-a"})

    assert changed == []
    assert queue.empty()


def test_diff_and_publish_only_reports_the_scopes_that_actually_changed() -> None:
    differ.diff_and_publish({"teams": "hash-a", "team:t1": "hash-b"})

    changed = differ.diff_and_publish({"teams": "hash-a", "team:t1": "hash-c"})

    assert changed == ["team:t1"]


def test_reset_state_clears_remembered_fingerprints() -> None:
    differ.diff_and_publish({"teams": "hash-a"})
    differ.reset_state()

    # After reset, the same fingerprint looks "new" again and republishes.
    changed = differ.diff_and_publish({"teams": "hash-a"})
    assert changed == ["teams"]
