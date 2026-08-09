"""`services/live_state.py` — the pure `classify` matrix (task 8.1) plus the
`user_nfl_teams` DB helper and the module-level current-state store."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base, League, Player, RosterSlot, Team
from backend.gridiron.schemas.live_nfl_games import LiveNflGame
from backend.gridiron.services import live_state

NOW = datetime(2025, 12, 7, 18, 0, 0)  # a Sunday afternoon


@pytest.fixture(autouse=True)
def _reset_module_state():
    live_state.reset_state()
    yield
    live_state.reset_state()


def make_game(
    game_id: str = "401",
    home: str = "KC",
    away: str = "BUF",
    state: str = "pre",
    kickoff_at: datetime = NOW,
) -> LiveNflGame:
    return LiveNflGame(
        nfl_game_id=game_id,
        home_team=home,
        away_team=away,
        home_score=0,
        away_score=0,
        state=state,
        clock=None,
        period=None,
        kickoff_at=kickoff_at,
    )


class TestClassify:
    def test_no_games_is_off_day(self) -> None:
        assert live_state.classify([], set(), NOW) == "off_day"

    def test_all_games_finished_and_not_today_is_off_day(self) -> None:
        games = [make_game(state="post", kickoff_at=NOW - timedelta(days=3))]
        assert live_state.classify(games, {"KC"}, NOW) == "off_day"

    def test_in_progress_game_with_rostered_team_is_live(self) -> None:
        games = [make_game(home="KC", away="BUF", state="in", kickoff_at=NOW - timedelta(hours=1))]
        assert live_state.classify(games, {"KC"}, NOW) == "live"

    def test_in_progress_game_with_rostered_away_team_is_live(self) -> None:
        games = [make_game(home="KC", away="BUF", state="in", kickoff_at=NOW - timedelta(hours=1))]
        assert live_state.classify(games, {"BUF"}, NOW) == "live"

    def test_in_progress_game_without_a_rostered_team_is_game_day_not_live(self) -> None:
        games = [make_game(home="KC", away="BUF", state="in", kickoff_at=NOW - timedelta(hours=1))]
        assert live_state.classify(games, {"DAL"}, NOW) == "game_day"

    def test_pregame_kickoff_today_is_game_day(self) -> None:
        games = [make_game(state="pre", kickoff_at=NOW.replace(hour=20))]
        assert live_state.classify(games, set(), NOW) == "game_day"

    def test_kickoff_within_pre_game_window_but_different_date_is_game_day(self) -> None:
        # "now" is just before midnight; kickoff is an hour later, on the next calendar
        # date, but still well within PRE_GAME_WINDOW (2h).
        now_near_midnight = NOW.replace(hour=23, minute=30)
        kickoff = now_near_midnight + timedelta(hours=1)
        assert kickoff.date() != now_near_midnight.date()
        games = [make_game(state="pre", kickoff_at=kickoff)]
        assert live_state.classify(games, set(), now_near_midnight) == "game_day"

    def test_kickoff_far_beyond_pre_game_window_and_not_today_is_off_day(self) -> None:
        games = [make_game(state="pre", kickoff_at=NOW + timedelta(days=1))]
        assert live_state.classify(games, set(), NOW) == "off_day"

    def test_live_takes_priority_over_other_pregame_games(self) -> None:
        games = [
            make_game(game_id="1", home="KC", away="BUF", state="in", kickoff_at=NOW),
            make_game(game_id="2", home="DAL", away="PHI", state="pre", kickoff_at=NOW),
        ]
        assert live_state.classify(games, {"KC"}, NOW) == "live"

    def test_finished_game_today_with_another_pregame_is_still_game_day(self) -> None:
        games = [
            make_game(game_id="1", state="post", kickoff_at=NOW - timedelta(hours=5)),
            make_game(game_id="2", state="pre", kickoff_at=NOW + timedelta(hours=3)),
        ]
        assert live_state.classify(games, set(), NOW) == "game_day"


class TestCurrentStateStore:
    def test_defaults_to_off_day(self) -> None:
        assert live_state.get_current_live_state() == "off_day"

    def test_set_then_get_round_trips(self) -> None:
        live_state.set_current_live_state("live")
        assert live_state.get_current_live_state() == "live"

    def test_reset_state_restores_default(self) -> None:
        live_state.set_current_live_state("live")
        live_state.reset_state()
        assert live_state.get_current_live_state() == "off_day"


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "live-state.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_roster(
    session_factory, *, league_enabled: bool, is_user_team: bool, slot: str
) -> None:
    async with session_factory() as session:
        session.add(
            League(
                id="yahoo:l1",
                platform="yahoo",
                platform_id="l1",
                name="Test League",
                season=2025,
                team_count=10,
                scoring_type="standard",
                current_week=14,
                is_enabled=league_enabled,
            )
        )
        session.add(
            Team(
                id="yahoo:l1.t1",
                league_id="yahoo:l1",
                platform="yahoo",
                platform_id="l1.t1",
                name="My Team",
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
        )
        session.add(
            Player(
                id="yahoo:p1",
                platform="yahoo",
                platform_id="p1",
                name="Test Player",
                position="QB",
                nfl_team="KC",
                nfl_opponent=None,
                nfl_game_id=None,
                bye_week=None,
                injury_status=None,
            )
        )
        session.add(
            RosterSlot(
                team_id="yahoo:l1.t1",
                week=14,
                slot=slot,
                player_id="yahoo:p1",
                proj_points=10.0,
                actual_points=8.0,
                is_live=False,
                game_state=None,
                status_text="",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_user_nfl_teams_includes_starter_on_enabled_league_user_team(session_factory) -> None:
    await _seed_roster(session_factory, league_enabled=True, is_user_team=True, slot="QB")

    async with session_factory() as session:
        teams = await live_state.user_nfl_teams(session)

    assert teams == {"KC"}


@pytest.mark.asyncio
async def test_user_nfl_teams_excludes_bench_slot(session_factory) -> None:
    await _seed_roster(session_factory, league_enabled=True, is_user_team=True, slot="BN")

    async with session_factory() as session:
        teams = await live_state.user_nfl_teams(session)

    assert teams == set()


@pytest.mark.asyncio
async def test_user_nfl_teams_excludes_disabled_league(session_factory) -> None:
    await _seed_roster(session_factory, league_enabled=False, is_user_team=True, slot="QB")

    async with session_factory() as session:
        teams = await live_state.user_nfl_teams(session)

    assert teams == set()


@pytest.mark.asyncio
async def test_user_nfl_teams_excludes_non_user_team(session_factory) -> None:
    await _seed_roster(session_factory, league_enabled=True, is_user_team=False, slot="QB")

    async with session_factory() as session:
        teams = await live_state.user_nfl_teams(session)

    assert teams == set()
