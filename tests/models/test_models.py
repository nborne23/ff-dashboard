"""ORM round-trip + Alembic migration coverage for the fantasy data model tables."""

import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import (
    Base,
    Headshot,
    HttpCache,
    League,
    LiveNflGame,
    Matchup,
    MatchupSlot,
    Player,
    RefreshRun,
    RosterSlot,
    SeasonWeek,
    Team,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "connections",
    "leagues",
    "teams",
    "players",
    "roster_slots",
    "matchups",
    "matchup_slots",
    "season_weeks",
    "live_nfl_games",
    "http_cache",
    "refresh_runs",
    "headshots",
}


def test_metadata_registers_all_expected_tables() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables.keys())


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "roundtrip.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_orm_round_trip_across_all_entities(session_factory) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_factory() as session:
        league = League(
            id="yahoo:nfl.l.123456",
            platform="yahoo",
            platform_id="nfl.l.123456",
            name="Highland Bombers League",
            season=2026,
            team_count=10,
            scoring_type="half_ppr",
            current_week=14,
        )
        team_a = Team(
            id="yahoo:nfl.l.123456.t.4",
            league_id=league.id,
            platform="yahoo",
            platform_id="nfl.l.123456.t.4",
            name="Highland Bombers",
            manager_name="Nick",
            record_w=8,
            record_l=5,
            record_t=0,
            rank_current=3,
            rank_total=10,
            points_for=1234.5,
            points_against=1100.2,
            is_user_team=True,
        )
        team_b = Team(
            id="yahoo:nfl.l.123456.t.7",
            league_id=league.id,
            platform="yahoo",
            platform_id="nfl.l.123456.t.7",
            name="Rival Squad",
            manager_name="Rival",
            record_w=5,
            record_l=8,
            record_t=0,
            rank_current=8,
            rank_total=10,
            points_for=1000.0,
            points_against=1200.0,
            is_user_team=False,
        )
        player = Player(
            id="yahoo:1234",
            platform="yahoo",
            platform_id="1234",
            name="Test Player",
            position="RB",
            nfl_team="SF",
            nfl_opponent="SEA",
            nfl_game_id="401547500",
            bye_week=9,
            injury_status="Q",
        )
        opp_player = Player(
            id="yahoo:5678",
            platform="yahoo",
            platform_id="5678",
            name="Opponent Player",
            position="WR",
            nfl_team="SEA",
            nfl_opponent="SF",
            nfl_game_id="401547500",
            bye_week=9,
            injury_status=None,
        )
        session.add_all([league, team_a, team_b, player, opp_player])
        await session.commit()

        roster_slot = RosterSlot(
            team_id=team_a.id,
            week=14,
            slot="RB1",
            player_id=player.id,
            proj_points=15.2,
            actual_points=18.4,
            is_live=True,
            game_state="in",
            status_text="Q3 8:14",
        )
        matchup = Matchup(
            id="yahoo:nfl.l.123456.w.14.m.2",
            league_id=league.id,
            week=14,
            home_team_id=team_a.id,
            away_team_id=team_b.id,
            home_score=101.2,
            away_score=98.4,
            home_proj=110.0,
            away_proj=105.0,
            is_complete=False,
        )
        season_week = SeasonWeek(
            team_id=team_a.id,
            week=13,
            score=120.4,
            opp_score=98.1,
            opp_team_name="Some Other Team",
            is_win=True,
            is_current=False,
        )
        live_game = LiveNflGame(
            nfl_game_id="401547500",
            home_team="SF",
            away_team="SEA",
            home_score=17,
            away_score=14,
            state="in",
            clock="8:14",
            period=3,
            kickoff_at=now,
        )
        http_cache_row = HttpCache(
            platform="yahoo",
            endpoint="/team/roster",
            params_hash="a" * 64,
            raw_json='{"ok": true}',
            fetched_at=now,
            expires_at=now,
        )
        refresh_run = RefreshRun(
            job_name="refresh_fantasy",
            run_at=now,
            ok=True,
            error=None,
            duration_ms=842,
        )
        headshot = Headshot(
            platform="yahoo",
            player_id="1234",
            source_url="https://s.yimg.com/players/1234.png",
            fetched_at=now,
        )
        session.add_all(
            [roster_slot, matchup, season_week, live_game, http_cache_row, refresh_run, headshot]
        )
        await session.commit()

        matchup_slot = MatchupSlot(
            matchup_id=matchup.id,
            slot="RB1",
            home_player_id=player.id,
            away_player_id=opp_player.id,
            home_pts=18.4,
            away_pts=9.2,
        )
        session.add(matchup_slot)
        await session.commit()

    async with session_factory() as session:
        fetched_team = await session.get(Team, team_a.id)
        assert fetched_team is not None
        assert fetched_team.name == "Highland Bombers"
        assert fetched_team.rank_current == 3

        fetched_slot = await session.get(RosterSlot, roster_slot.id)
        assert fetched_slot is not None
        assert fetched_slot.player_id == player.id
        assert fetched_slot.slot == "RB1"

        fetched_matchup_slot = await session.get(MatchupSlot, matchup_slot.id)
        assert fetched_matchup_slot is not None
        assert fetched_matchup_slot.home_pts == 18.4

        fetched_cache = await session.get(HttpCache, ("yahoo", "/team/roster", "a" * 64))
        assert fetched_cache is not None
        assert fetched_cache.raw_json == '{"ok": true}'

        fetched_headshot = await session.get(Headshot, ("yahoo", "1234"))
        assert fetched_headshot is not None
        assert fetched_headshot.source_url.endswith("1234.png")


@pytest.mark.asyncio
async def test_roster_slot_unique_constraint_rejects_duplicate_team_week_slot(
    session_factory,
) -> None:
    async with session_factory() as session:
        league = League(
            id="espn:1",
            platform="espn",
            platform_id="1",
            name="ESPN League",
            season=2026,
            team_count=8,
            scoring_type="ppr",
            current_week=14,
        )
        team = Team(
            id="espn:1:t:1",
            league_id=league.id,
            platform="espn",
            platform_id="1",
            name="ESPN Team",
            manager_name="Manager",
            rank_current=1,
            rank_total=8,
            is_user_team=True,
        )
        player = Player(
            id="espn:99",
            platform="espn",
            platform_id="99",
            name="Some Player",
            position="QB",
            nfl_team="KC",
        )
        session.add_all([league, team, player])
        await session.commit()

        session.add(
            RosterSlot(team_id=team.id, week=14, slot="QB", player_id=player.id, status_text="")
        )
        await session.commit()

        session.add(
            RosterSlot(team_id=team.id, week=14, slot="QB", player_id=player.id, status_text="")
        )
        with pytest.raises(IntegrityError):
            await session.commit()


def _run_alembic(args: list[str], db_path: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "GRIDIRON_DB_PATH": str(db_path)}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("select name from sqlite_master where type='table'")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def test_alembic_upgrade_head_from_scratch(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"

    result = _run_alembic(["upgrade", "head"], db_path)

    assert result.returncode == 0, result.stderr
    assert db_path.exists()
    assert EXPECTED_TABLES <= _table_names(db_path)


def test_alembic_upgrade_head_from_existing_connections_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "existing.db"

    first = _run_alembic(["upgrade", "88514573fd22"], db_path)
    assert first.returncode == 0, first.stderr
    assert _table_names(db_path) == {"alembic_version", "connections"}

    second = _run_alembic(["upgrade", "head"], db_path)
    assert second.returncode == 0, second.stderr
    assert EXPECTED_TABLES <= _table_names(db_path)
