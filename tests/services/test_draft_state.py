"""`services/draft_state.py` — pick record/undo, pool/roster reads, D13's explicit
current-pick tracking, and league-shape resolution (tasks 3.1/3.2)."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.errors import DraftPickConflictError
from backend.gridiron.models import Base, BoardPlayer, DraftSession, League
from backend.gridiron.platforms.espn.slot_table import UnknownSlotError
from backend.gridiron.services import differ, draft_state, events

# Read the static config rather than hardcoding its values. These tests assert the
# resolution *behavior* (platform preferred, static fallback, conflict reporting), not
# the league's particular shape -- which is real user data and changed once ESPN
# confirmed 10 teams and 3 FLEX against the board's assumed 12 and 2.
_STATIC_CONFIG = json.loads(
    (
        Path(__file__).resolve().parents[2] / "backend/gridiron/draft_board/league_config.json"
    ).read_text()
)
STATIC_TEAMS: int = _STATIC_CONFIG["teams"]
STATIC_FLEX_SLOTS: list[str] = [
    f"FLEX{i + 1}" for i in range(_STATIC_CONFIG["roster"]["starters"]["FLEX"])
]


@pytest.fixture(autouse=True)
def _reset_module_state():
    differ.reset_state()
    events.reset()
    yield
    differ.reset_state()
    events.reset()


@pytest.fixture
async def session_factory(tmp_path):
    engine = make_engine(tmp_path / "draft-state.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _player(
    name: str,
    position: str = "RB",
    *,
    adp_rank: int | None = None,
    out_for_season: bool = False,
    bye: int | None = None,
    flags: str | None = None,
) -> BoardPlayer:
    return BoardPlayer(
        name=name,
        normalized_name=name.lower(),
        position=position,
        adp_rank=adp_rank,
        out_for_season=out_for_season,
        bye=bye,
        flags=flags,
    )


async def seed_players(session_factory, players: list[BoardPlayer]) -> None:
    async with session_factory() as session:
        for p in players:
            session.add(p)
        await session.commit()


# ---------------------------------------------------------------------------
# record_pick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_pick_by_board_player_id_copies_position_and_round(session_factory) -> None:
    await seed_players(session_factory, [_player("Bijan Robinson", "RB", adp_rank=1)])

    async with session_factory() as session:
        bp = (await session.execute(select(BoardPlayer))).scalars().one()
        pick = await draft_state.record_pick(
            session, board_player_id=bp.id, overall_pick=1, is_my_pick=True
        )

    assert pick.overall_pick == 1
    assert pick.round == 1
    assert pick.position == "RB"
    assert pick.player_name == "Bijan Robinson"
    assert pick.is_my_pick is True


@pytest.mark.asyncio
async def test_record_pick_off_board_name_has_no_position(session_factory) -> None:
    async with session_factory() as session:
        pick = await draft_state.record_pick(session, player_name="Some Rookie", overall_pick=200)

    assert pick.position is None
    assert pick.board_player_id is None
    assert pick.player_name == "Some Rookie"


@pytest.mark.asyncio
async def test_record_pick_without_overall_pick_uses_next_unused(session_factory) -> None:
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1)
        await draft_state.record_pick(session, player_name="B", overall_pick=2)
        pick = await draft_state.record_pick(session, player_name="C")

    assert pick.overall_pick == 3


@pytest.mark.asyncio
async def test_record_pick_without_overall_pick_uses_current_pick_not_earliest_gap(
    session_factory,
) -> None:
    # The frontend's MarkDrafted control never sends `overall_pick`. If a gap exists
    # from an earlier explicit far-ahead pick (5), an omitted-number pick must still land
    # on `current_overall_pick` (4 here) -- NOT backfill the earliest historical hole
    # (which an old, buggy implementation would have placed at 3, misattributing this
    # brand-new pick to an already-passed round).
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1)
        await draft_state.record_pick(session, player_name="B", overall_pick=2)
        await draft_state.record_pick(session, player_name="E", overall_pick=5)
        assert await draft_state.get_current_overall_pick(session) == 4

        pick = await draft_state.record_pick(session, player_name="D")

    assert pick.overall_pick == 4


@pytest.mark.asyncio
async def test_record_pick_advances_current_overall_pick_by_exactly_one(session_factory) -> None:
    async with session_factory() as session:
        assert await draft_state.get_current_overall_pick(session) == 1
        await draft_state.record_pick(session, player_name="A", overall_pick=1)
        assert await draft_state.get_current_overall_pick(session) == 2
        # A far-ahead explicit overall_pick does NOT jump the counter to pick+1.
        await draft_state.record_pick(session, player_name="Z", overall_pick=150)
        assert await draft_state.get_current_overall_pick(session) == 3


@pytest.mark.asyncio
async def test_record_pick_manual_duplicate_different_player_raises(session_factory) -> None:
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1, source="manual")
        with pytest.raises(DraftPickConflictError):
            await draft_state.record_pick(session, player_name="B", overall_pick=1, source="manual")


@pytest.mark.asyncio
async def test_record_pick_espn_source_overwrites_existing_slot(session_factory) -> None:
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1, source="manual")
        pick = await draft_state.record_pick(
            session, player_name="B", overall_pick=1, source="espn"
        )

    assert pick.player_name == "B"
    assert pick.source == "espn"

    async with session_factory() as session:
        picks = await draft_state.list_picks(session)
    assert len(picks) == 1
    assert picks[0].player_name == "B"


@pytest.mark.asyncio
async def test_record_pick_same_player_reconfirm_does_not_raise(session_factory) -> None:
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1, source="manual")
        pick = await draft_state.record_pick(
            session, player_name="A", overall_pick=1, source="manual"
        )
    assert pick.player_name == "A"


@pytest.mark.asyncio
async def test_record_pick_publishes_draft_scope_sse_event(session_factory) -> None:
    queue = events.subscribe()
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1)

    event = queue.get_nowait()
    assert event.type == "data.changed"
    assert event.scopes == ["draft"]


# ---------------------------------------------------------------------------
# undo_last_pick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_last_pick_removes_highest_overall_pick_regardless_of_source(
    session_factory,
) -> None:
    async with session_factory() as session:
        await draft_state.record_pick(session, player_name="A", overall_pick=1, source="manual")
        await draft_state.record_pick(session, player_name="B", overall_pick=2, source="espn")
        undone = await draft_state.undo_last_pick(session)

    assert undone is not None
    assert undone.player_name == "B"

    async with session_factory() as session:
        picks = await draft_state.list_picks(session)
    assert [p.player_name for p in picks] == ["A"]


@pytest.mark.asyncio
async def test_undo_last_pick_returns_none_when_no_picks(session_factory) -> None:
    async with session_factory() as session:
        undone = await draft_state.undo_last_pick(session)
    assert undone is None


@pytest.mark.asyncio
async def test_undo_last_pick_restores_current_overall_pick_exactly(session_factory) -> None:
    async with session_factory() as session:
        assert await draft_state.get_current_overall_pick(session) == 1
        await draft_state.record_pick(session, player_name="A", overall_pick=1)
        assert await draft_state.get_current_overall_pick(session) == 2
        await draft_state.undo_last_pick(session)
        assert await draft_state.get_current_overall_pick(session) == 1


@pytest.mark.asyncio
async def test_undo_last_pick_floors_current_overall_pick_at_one(session_factory) -> None:
    async with session_factory() as session:
        await draft_state.set_current_overall_pick(session, 1)
        await draft_state.record_pick(session, player_name="A", overall_pick=1)
        await draft_state.undo_last_pick(session)
        await draft_state.undo_last_pick(session)  # no-op: nothing left to undo
        assert await draft_state.get_current_overall_pick(session) == 1


@pytest.mark.asyncio
async def test_record_then_undo_restores_state_exactly(session_factory) -> None:
    await seed_players(session_factory, [_player("Bijan Robinson", "RB", adp_rank=1)])

    async with session_factory() as session:
        bp = (await session.execute(select(BoardPlayer))).scalars().one()

    async with session_factory() as session:
        pool_before = await draft_state.undrafted_pool(session)
        assert any(c.name == "Bijan Robinson" for c in pool_before)

    async with session_factory() as session:
        await draft_state.record_pick(
            session, board_player_id=bp.id, overall_pick=1, is_my_pick=True
        )

    async with session_factory() as session:
        pool_during = await draft_state.undrafted_pool(session)
        roster_during = await draft_state.my_roster(session)
    assert all(c.name != "Bijan Robinson" for c in pool_during)
    assert [c.name for c in roster_during] == ["Bijan Robinson"]

    async with session_factory() as session:
        await draft_state.undo_last_pick(session)

    async with session_factory() as session:
        pool_after = await draft_state.undrafted_pool(session)
        roster_after = await draft_state.my_roster(session)
        current_pick_after = await draft_state.get_current_overall_pick(session)

    assert [c.name for c in pool_after] == [c.name for c in pool_before]
    assert roster_after == []
    assert current_pick_after == 1


# ---------------------------------------------------------------------------
# undrafted_pool / my_roster
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undrafted_pool_excludes_out_for_season(session_factory) -> None:
    await seed_players(
        session_factory,
        [
            _player("Active Guy", "RB", adp_rank=1),
            _player("Hurt Guy", "RB", adp_rank=2, out_for_season=True),
        ],
    )
    async with session_factory() as session:
        pool = await draft_state.undrafted_pool(session)
    assert [c.name for c in pool] == ["Active Guy"]


@pytest.mark.asyncio
async def test_undrafted_pool_excludes_drafted_players_any_source(session_factory) -> None:
    await seed_players(
        session_factory,
        [_player("Drafted By Espn", "RB", adp_rank=1), _player("Still Free", "RB", adp_rank=2)],
    )
    async with session_factory() as session:
        drafted = (await session.execute(select(BoardPlayer))).scalars().all()
        target = next(bp for bp in drafted if bp.name == "Drafted By Espn")
        await draft_state.record_pick(
            session, board_player_id=target.id, overall_pick=1, source="espn"
        )

    async with session_factory() as session:
        pool = await draft_state.undrafted_pool(session)
    assert [c.name for c in pool] == ["Still Free"]


@pytest.mark.asyncio
async def test_undrafted_pool_orders_by_adp_rank_with_nulls_last(session_factory) -> None:
    await seed_players(
        session_factory,
        [
            _player("No ADP", "WR", adp_rank=None),
            _player("Rank Two", "WR", adp_rank=2),
            _player("Rank One", "WR", adp_rank=1),
        ],
    )
    async with session_factory() as session:
        pool = await draft_state.undrafted_pool(session)
    assert [c.name for c in pool] == ["Rank One", "Rank Two", "No ADP"]


@pytest.mark.asyncio
async def test_my_roster_only_includes_is_my_pick_true(session_factory) -> None:
    await seed_players(
        session_factory, [_player("Mine", "RB", adp_rank=1), _player("Theirs", "RB", adp_rank=2)]
    )
    async with session_factory() as session:
        rows = (await session.execute(select(BoardPlayer))).scalars().all()
        mine = next(bp for bp in rows if bp.name == "Mine")
        theirs = next(bp for bp in rows if bp.name == "Theirs")
        await draft_state.record_pick(
            session, board_player_id=mine.id, overall_pick=1, is_my_pick=True
        )
        await draft_state.record_pick(
            session, board_player_id=theirs.id, overall_pick=2, is_my_pick=False
        )

    async with session_factory() as session:
        roster = await draft_state.my_roster(session)
    assert [c.name for c in roster] == ["Mine"]


@pytest.mark.asyncio
async def test_to_candidate_decodes_flags_json(session_factory) -> None:
    await seed_players(
        session_factory, [_player("Flagged", "WR", adp_rank=1, flags='["TARGET","SLEEPER"]')]
    )
    async with session_factory() as session:
        pool = await draft_state.undrafted_pool(session)
    assert pool[0].flags == ("TARGET", "SLEEPER")


# ---------------------------------------------------------------------------
# D13: explicit current-pick tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_overall_pick_defaults_to_one_lazily(session_factory) -> None:
    async with session_factory() as session:
        assert await draft_state.get_current_overall_pick(session) == 1
        rows = (await session.execute(select(DraftSession))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "manual"


@pytest.mark.asyncio
async def test_set_current_overall_pick_is_explicit_and_user_correctable(session_factory) -> None:
    async with session_factory() as session:
        await draft_state.set_current_overall_pick(session, 25)
        assert await draft_state.get_current_overall_pick(session) == 25


@pytest.mark.asyncio
async def test_set_current_overall_pick_rejects_less_than_one(session_factory) -> None:
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await draft_state.set_current_overall_pick(session, 0)


def test_picks_until_next_returns_none_past_last_pick() -> None:
    my_picks = [1, 24, 25]
    assert draft_state.picks_until_next(26, my_picks) is None


def test_picks_until_next_returns_value_normally() -> None:
    my_picks = [1, 24, 25]
    assert draft_state.picks_until_next(5, my_picks) == 19


# ---------------------------------------------------------------------------
# resolve_league_shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_league_shape_falls_back_to_static_config_when_no_espn(
    session_factory,
) -> None:
    async with session_factory() as session:
        shape, conflicts = await draft_state.resolve_league_shape(session)

    assert shape.teams == STATIC_TEAMS
    assert shape.starters["RB"] == 2
    assert shape.starters["K"] == 0
    assert shape.rounds == 15  # 9 static starters + default bench of 6
    assert shape.slot == 1

    by_field = {c.field: c for c in conflicts}
    assert by_field["teams"].confirmed_by_espn is False
    assert by_field["teams"].espn_value is None
    assert by_field["teams"].resolved_value == STATIC_TEAMS
    assert by_field["_espn_connectivity"].confirmed_by_espn is False


@pytest.mark.asyncio
async def test_resolve_league_shape_prefers_espn_team_count_when_a_league_row_exists(
    session_factory,
) -> None:
    async with session_factory() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="ESPN League",
                season=2026,
                team_count=10,
                scoring_type="half_ppr",
                current_week=1,
                is_enabled=True,
            )
        )
        await session.commit()

    async with session_factory() as session:
        shape, conflicts = await draft_state.resolve_league_shape(session)

    assert shape.teams == 10
    by_field = {c.field: c for c in conflicts}
    assert by_field["teams"].confirmed_by_espn is True
    assert by_field["teams"].espn_value == 10
    assert by_field["teams"].static_value == STATIC_TEAMS
    assert by_field["_espn_connectivity"].confirmed_by_espn is True


@pytest.mark.asyncio
async def test_resolve_league_shape_ignores_disabled_espn_league(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            League(
                id="espn:1",
                platform="espn",
                platform_id="1",
                name="ESPN League",
                season=2026,
                team_count=10,
                scoring_type="half_ppr",
                current_week=1,
                is_enabled=False,
            )
        )
        await session.commit()

    async with session_factory() as session:
        shape, _conflicts = await draft_state.resolve_league_shape(session)
    assert shape.teams == STATIC_TEAMS  # static fallback -- the disabled row doesn't count


def test_starters_from_lineup_slot_counts_translates_via_slot_table() -> None:
    counts = {0: 1, 2: 2, 4: 2, 6: 1, 23: 2, 16: 1, 17: 0, 20: 6, 21: 1}
    starters, bench = draft_state._starters_from_lineup_slot_counts(counts)
    assert starters == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "DST": 1, "K": 0}
    assert bench == 6


def test_starters_from_lineup_slot_counts_raises_on_unsupported_slot() -> None:
    with pytest.raises(UnknownSlotError):
        draft_state._starters_from_lineup_slot_counts({8: 1})  # 8 == "DT", unsupported
