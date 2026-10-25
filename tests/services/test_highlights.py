"""`services/highlights.py` — the pure `detect`/`stat_line` rules plus the
snapshot -> record_new round trip against a real SQLite file (add-play-highlights)."""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import (
    Base,
    League,
    Player,
    PlayerHighlight,
    PlayerWeeklyStat,
    RosterSlot,
    Team,
)
from backend.gridiron.platforms import sleeper_stats
from backend.gridiron.services import events, fantasy_service, highlights

SEASON, WEEK = 2026, 8
T0 = datetime(2026, 10, 25, 18, 0)
T1 = T0 + timedelta(minutes=2)


@pytest.fixture(autouse=True)
def _reset_module_state():
    events.reset()
    fantasy_service.reset_state()
    yield
    events.reset()
    fantasy_service.reset_state()


class TestDetect:
    def test_touchdown_increase_fires_with_new_ordinal(self) -> None:
        found = highlights.detect({"rush_td": 1}, {"rush_td": 2, "rush_td_lng": 34})
        assert found == [highlights.Detection("touchdown", "rush_td", 2, 34)]

    def test_first_touchdown_from_a_missing_key(self) -> None:
        # Sleeper omits zero-valued keys, so "absent" before is zero.
        assert highlights.detect({}, {"rec_td": 1}) == [
            highlights.Detection("touchdown", "rec_td", 1, None)
        ]

    def test_unchanged_or_decreased_fires_nothing(self) -> None:
        assert highlights.detect({"rec_td": 1}, {"rec_td": 1}) == []
        assert highlights.detect({"rec_td": 2}, {"rec_td": 1}) == []

    def test_big_play_from_40p_counter(self) -> None:
        found = highlights.detect({"rec_40p": 0, "rec_lng": 22}, {"rec_40p": 1, "rec_lng": 57})
        assert found == [highlights.Detection("big_play", "rec_40p", 1, 57)]

    def test_big_play_yards_omitted_when_not_the_new_longest(self) -> None:
        found = highlights.detect({"rec_40p": 1, "rec_lng": 57}, {"rec_40p": 2, "rec_lng": 57})
        assert found == [highlights.Detection("big_play", "rec_40p", 2, None)]

    def test_touchdown_swallows_big_play_in_the_same_tick(self) -> None:
        found = highlights.detect({}, {"rec_40p": 1, "rec_td": 1})
        assert [d.kind for d in found] == ["touchdown"]

    def test_qb_passing_and_rushing_td_in_one_tick_are_both_reported(self) -> None:
        found = highlights.detect({}, {"pass_td": 1, "rush_td": 1})
        assert {d.stat_key for d in found} == {"pass_td", "rush_td"}

    def test_big_yardage_without_a_40_yard_play_is_not_a_big_play(self) -> None:
        assert highlights.detect({"rec_yd": 10}, {"rec_yd": 60}) == []


class TestStatLine:
    def test_receiver(self) -> None:
        assert highlights.stat_line("WR", {"rec": 6, "rec_yd": 112, "rec_td": 2}) == (
            "6 rec · 112 yds · 2 TD"
        )

    def test_running_back_with_catches(self) -> None:
        line = highlights.stat_line("RB", {"rush_att": 14, "rush_yd": 71, "rec": 2, "rush_td": 1})
        assert line == "14 car · 71 yds · 2 rec · 1 TD"

    def test_quarterback(self) -> None:
        line = highlights.stat_line(
            "QB", {"pass_cmp": 18, "pass_att": 27, "pass_yd": 245.0, "pass_td": 2, "rush_td": 1}
        )
        assert line == "18/27 · 245 yds · 2 TD · 1 rush TD"


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "highlights.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _league(league_id: str) -> League:
    return League(
        id=league_id,
        platform="yahoo",
        platform_id=league_id.split(":")[1],
        name=league_id,
        season=SEASON,
        team_count=10,
        scoring_type="ppr",
        current_week=WEEK,
        is_enabled=True,
    )


def _team(team_id: str, league_id: str, *, is_user_team: bool = True) -> Team:
    return Team(
        id=team_id,
        league_id=league_id,
        platform="yahoo",
        platform_id=team_id.split(":")[1],
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


def _player(player_id: str, sleeper_id: str | None, position: str = "WR") -> Player:
    return Player(
        id=player_id,
        platform="yahoo",
        platform_id=player_id.split(":")[1],
        name=f"Player {player_id}",
        position=position,
        nfl_team="KC",
        nfl_opponent=None,
        nfl_game_id=None,
        bye_week=None,
        injury_status=None,
        sleeper_id=sleeper_id,
    )


def _slot(team_id: str, player_id: str, slot: str = "WR1") -> RosterSlot:
    return RosterSlot(
        team_id=team_id,
        week=WEEK,
        slot=slot,
        player_id=player_id,
        proj_points=10.0,
        actual_points=0.0,
        is_live=True,
        game_state="in",
        status_text="",
    )


def _stat(sleeper_id: str, fetched_at: datetime, **stats: float) -> PlayerWeeklyStat:
    return PlayerWeeklyStat(
        sleeper_id=sleeper_id,
        season=SEASON,
        week=WEEK,
        stats_json=json.dumps({"gp": 1, **stats}),
        fetched_at=fetched_at,
    )


async def _seed(session_factory, *rows) -> None:
    async with session_factory() as session:
        session.add(_league("yahoo:l1"))
        session.add(_team("yahoo:t1", "yahoo:l1"))
        for row in rows:
            session.add(row)
        await session.commit()


async def _tick(session_factory, sleeper_id: str, fetched_at: datetime, now: datetime, **stats):
    """One `refresh_player_stats` run: snapshot, overwrite the line, record."""
    async with session_factory() as session:
        before = await highlights.snapshot(session, now=now)
        assert before is not None
        # Written the way `fetch_and_upsert` writes: a Core upsert in the SAME session,
        # which never refreshes ORM objects the snapshot may have loaded.
        row = sleeper_stats.map_row(
            {"player_id": sleeper_id, "stats": {"gp": 1, **stats}},
            season=SEASON,
            week=WEEK,
            fetched_at=fetched_at,
        )
        await sleeper_stats._upsert_week(session, [row])
        await session.commit()
        return await highlights.record_new(session, before, now=now)


async def _all_highlights(session_factory) -> list[PlayerHighlight]:
    async with session_factory() as session:
        return list((await session.execute(select(PlayerHighlight))).scalars())


@pytest.mark.asyncio
async def test_touchdown_is_recorded_once_and_signalled(session_factory) -> None:
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("100", T0, rec=3, rec_yd=40),
    )
    queue = events.subscribe()

    inserted = await _tick(session_factory, "100", T1, T1, rec=4, rec_yd=62, rec_td=1)

    assert [(h.kind, h.stat_key, h.ordinal) for h in inserted] == [("touchdown", "rec_td", 1)]
    assert inserted[0].stat_line == "4 rec · 62 yds · 1 TD"
    assert queue.get_nowait().scopes == [highlights.SCOPE]


@pytest.mark.asyncio
async def test_rereading_the_same_line_inserts_nothing(session_factory) -> None:
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("100", T0),
    )
    await _tick(session_factory, "100", T1, T1, rec_td=1)

    # The next tick re-reads the TD with a fresh `fetched_at`; and to be sure the unique
    # key (not just the diff) is what holds, also replay the 0 -> 1 jump outright.
    later = T1 + timedelta(minutes=2)
    assert await _tick(session_factory, "100", later, later, rec_td=1) == []
    async with session_factory() as session:
        await sleeper_stats._upsert_week(
            session,
            [
                sleeper_stats.map_row(
                    {"player_id": "100", "stats": {"gp": 1}},
                    season=SEASON,
                    week=WEEK,
                    fetched_at=later,
                )
            ],
        )
        await session.commit()
    again = later + timedelta(minutes=2)
    assert await _tick(session_factory, "100", again, again, rec_td=1) == []
    assert len(await _all_highlights(session_factory)) == 1


@pytest.mark.asyncio
async def test_first_reading_of_the_week_seeds_silently(session_factory) -> None:
    await _seed(session_factory, _player("yahoo:p1", "100"), _slot("yahoo:t1", "yahoo:p1"))

    assert await _tick(session_factory, "100", T1, T1, rec_td=1) == []


@pytest.mark.asyncio
async def test_first_line_mid_week_fires_when_the_feed_was_read_recently(session_factory) -> None:
    # Someone else's row from the last tick proves the feed was read and he had nothing.
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("999", T0, rec=2),
    )

    inserted = await _tick(session_factory, "100", T1, T1, rec_td=1)

    assert [(h.stat_key, h.ordinal) for h in inserted] == [("rec_td", 1)]


@pytest.mark.asyncio
async def test_first_line_after_a_stale_read_seeds_silently(session_factory) -> None:
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("999", T0),
    )
    late = T0 + highlights.STALE_BASELINE + timedelta(minutes=1)

    assert await _tick(session_factory, "100", late, late, rec_td=1) == []


@pytest.mark.asyncio
async def test_rows_loaded_before_the_upsert_do_not_mask_it(session_factory) -> None:
    """The production session keeps objects across commits; the diff must still see the
    upsert even when the old row is sitting in the identity map."""
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("100", T0),
    )
    async with session_factory() as session:
        held = list((await session.execute(select(PlayerWeeklyStat))).scalars())
        before = await highlights.snapshot(session, now=T1)
        row = sleeper_stats.map_row(
            {"player_id": "100", "stats": {"gp": 1, "rec_td": 1}},
            season=SEASON,
            week=WEEK,
            fetched_at=T1,
        )
        await sleeper_stats._upsert_week(session, [row])
        await session.commit()
        inserted = await highlights.record_new(session, before, now=T1)

    assert held  # kept alive on purpose
    assert len(inserted) == 1


@pytest.mark.asyncio
async def test_stale_baseline_seeds_silently(session_factory) -> None:
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("100", T0),
    )
    late = T0 + highlights.STALE_BASELINE + timedelta(minutes=1)

    assert await _tick(session_factory, "100", late, late, rec_td=2) == []


@pytest.mark.asyncio
async def test_correction_downward_fires_nothing(session_factory) -> None:
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _slot("yahoo:t1", "yahoo:p1"),
        _stat("100", T0, rec_td=2),
    )

    assert await _tick(session_factory, "100", T1, T1, rec_td=1) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", ["BN", "IR"])
async def test_bench_and_ir_are_not_watched(session_factory, slot) -> None:
    await _seed(
        session_factory,
        _player("yahoo:p1", "100"),
        _player("yahoo:p2", "200"),
        _slot("yahoo:t1", "yahoo:p1", slot=slot),
        _slot("yahoo:t1", "yahoo:p2"),  # someone, so the snapshot isn't empty
        _stat("100", T0),
    )

    assert await _tick(session_factory, "100", T1, T1, rec_td=1) == []


@pytest.mark.asyncio
async def test_opponents_players_are_not_watched(session_factory) -> None:
    await _seed(
        session_factory,
        _team("yahoo:t2", "yahoo:l1", is_user_team=False),
        _player("yahoo:p1", "100"),
        _player("yahoo:p2", "200"),
        _slot("yahoo:t2", "yahoo:p1"),
        _slot("yahoo:t1", "yahoo:p2"),
        _stat("100", T0),
    )

    assert await _tick(session_factory, "100", T1, T1, rec_td=1) == []


@pytest.mark.asyncio
async def test_same_player_on_two_user_teams_is_one_highlight(session_factory) -> None:
    await _seed(
        session_factory,
        _league("yahoo:l2"),
        _team("yahoo:t2", "yahoo:l2"),
        _player("yahoo:p1", "100"),
        _player("yahoo:p9", "100"),  # same man, other league's player row
        _slot("yahoo:t1", "yahoo:p1"),
        _slot("yahoo:t2", "yahoo:p9"),
        _stat("100", T0),
    )

    inserted = await _tick(session_factory, "100", T1, T1, rec_td=1)

    assert len(inserted) == 1
    assert inserted[0].player_id == "yahoo:p1"


@pytest.mark.asyncio
async def test_no_starters_means_no_snapshot(session_factory) -> None:
    await _seed(session_factory, _player("yahoo:p1", None), _slot("yahoo:t1", "yahoo:p1"))

    async with session_factory() as session:
        assert await highlights.snapshot(session) is None
