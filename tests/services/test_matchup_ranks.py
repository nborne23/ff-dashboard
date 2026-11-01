"""Opponent-vs-position and season position ranks for the player card's game log
(player game log)."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import Base
from backend.gridiron.services import cache, matchup_ranks
from backend.gridiron.services.matchup_ranks import StatLine


def line(sid, week, opp, ppr, half=None, std=None):
    return StatLine(sid, week, opp, ppr, ppr if half is None else half, ppr if std is None else std)


POSITIONS = {"qb1": "QB", "qb2": "QB", "rb1": "RB", "SF": "DST"}


def test_positions_from_dump_maps_def_to_dst_and_drops_idp():
    dump = {
        "qb1": {"position": "QB"},
        "SF": {"position": "DEF"},
        "lb1": {"position": "LB"},
        "bad": "not a dict",
    }
    assert matchup_ranks.positions_from_dump(dump) == {"qb1": "QB", "SF": "DST"}


def test_points_allowed_are_per_game_and_rank_most_allowed_first():
    lines = [
        # LAC faced QBs twice: 30 + 10 = 40 over 2 games = 20/game.
        line("qb1", 1, "LAC", 30.0),
        line("qb2", 2, "LAC", 10.0),
        # DEN faced a QB once, 25 — fewer total, more per game.
        line("qb1", 2, "DEN", 25.0),
        # SEA appears only through an RB line: 0 QB points allowed in its one game.
        line("rb1", 1, "SEA", 12.0),
    ]
    blob = matchup_ranks.compute(lines, POSITIONS, {}, season=2026, through_week=2)
    assert blob["dvp"]["QB"]["ppr"] == {"DEN": 1, "LAC": 2, "SEA": 3}
    assert blob["dvp"]["RB"]["ppr"]["SEA"] == 1
    assert blob["teams"] == 3
    assert blob["through_week"] == 2


def test_in_progress_week_is_left_out_of_opponent_ranks():
    lines = [line("qb1", 1, "LAC", 10.0), line("qb2", 1, "DEN", 20.0), line("qb1", 2, "LAC", 50)]
    blob = matchup_ranks.compute(lines, POSITIONS, {}, season=2026, through_week=1)
    assert blob["dvp"]["QB"]["ppr"] == {"DEN": 1, "LAC": 2}
    # ...but the season rank counts every stored line.
    assert blob["pos_rank"]["ppr"] == {"qb1": 1, "qb2": 2}


def test_ranks_follow_the_points_format():
    lines = [line("qb1", 1, "LAC", ppr=20.0, std=5.0), line("qb2", 1, "DEN", ppr=10.0, std=9.0)]
    blob = matchup_ranks.compute(lines, POSITIONS, {}, season=2026, through_week=1)
    assert blob["dvp"]["QB"]["ppr"]["LAC"] == 1
    assert blob["dvp"]["QB"]["standard"]["DEN"] == 1
    assert blob["pos_rank"]["standard"] == {"qb2": 1, "qb1": 2}


def test_dst_lines_rank_the_offenses_they_faced():
    lines = [line("SF", 1, "ARI", 14.0), line("qb1", 1, "SF", 3.0)]
    blob = matchup_ranks.compute(lines, POSITIONS, {}, season=2026, through_week=1)
    assert blob["dvp"]["DST"]["ppr"]["ARI"] == 1
    assert blob["pos_rank"]["ppr"]["SF"] == 1


def test_no_completed_week_means_no_opponent_ranks():
    blob = matchup_ranks.compute(
        [line("qb1", 1, "LAC", 10)], POSITIONS, {}, season=2026, through_week=0
    )
    assert blob["teams"] == 0
    assert blob["through_week"] == 0
    assert blob["dvp"]["QB"]["ppr"] == {}


def test_numbers_kept_only_for_players_with_lines():
    blob = matchup_ranks.compute(
        [line("qb1", 1, "LAC", 10)], POSITIONS, {"qb1": "7", "x": "1"}, season=2026, through_week=1
    )
    assert blob["numbers"] == {"qb1": "7"}


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "ranks.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_get_cached_reads_the_blob_and_tolerates_garbage(db):
    async with db() as session:
        assert await matchup_ranks.get_cached(session, 2026) is None
        blob = matchup_ranks.compute(
            [line("qb1", 1, "LAC", 10)], POSITIONS, {"qb1": "7"}, season=2026, through_week=1
        )
        await cache.set(
            session,
            "gridiron",
            "matchup_ranks",
            {"season": 2026},
            json.dumps(blob),
            datetime.now(UTC) + matchup_ranks.RANKS_TTL,
        )
        ranks = await matchup_ranks.get_cached(session, 2026)
        assert ranks.opponent_rank("QB", "ppr", "LAC") == 1
        assert ranks.opponent_rank("QB", "ppr", None) is None
        assert ranks.position_rank("ppr", "qb1") == 1
        assert ranks.position_rank("ppr", None) is None
        assert ranks.jersey("qb1") == "7"

        await cache.set(
            session,
            "gridiron",
            "matchup_ranks",
            {"season": 2026},
            "{not json",
            datetime.now(UTC) + matchup_ranks.RANKS_TTL,
        )
        assert await matchup_ranks.get_cached(session, 2026) is None


async def test_refresh_context_survives_a_schedule_outage(db):
    class Down:
        async def get_schedule(self, season):
            raise httpx.ConnectError("down")

    async with db() as session:
        await matchup_ranks.refresh_context(session, Down(), {}, 2026, current_week=3)
        ranks = await matchup_ranks.get_cached(session, 2026)
        assert ranks is not None and ranks.season == 2026 and ranks.through_week == 0
