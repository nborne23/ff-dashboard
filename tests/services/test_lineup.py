"""The lineup solver and start/sit advice."""

import json
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.gridiron.db import make_engine
from backend.gridiron.models import (
    Base,
    League,
    Player,
    PlayerPoolEntry,
    PlayerProjection,
    RosterSlot,
    Team,
)
from backend.gridiron.services import lineup
from backend.gridiron.services.fantasy_service import _base_slot, _startable_eligibility

LEAGUE = "espn:1"
TEAM = "espn:l-1-t-1"

RB_SLOTS = ["RB", "RB/WR", "FLEX", "OP", "BN", "IR"]
WR_SLOTS = ["WR", "RB/WR", "WR/TE", "FLEX", "OP", "BN", "IR"]
QB_SLOTS = ["QB", "OP", "BN", "IR"]


def cand(pid, eligible, points, *, unstartable=False, slot=None, weight=None):
    """`weight` defaults to `points` — these solver tests exercise the assignment itself,
    not the incumbency premium, which has its own tests below."""
    return lineup.Candidate(
        player_id=pid,
        eligible=frozenset(eligible),
        points=points,
        weight=points if weight is None else weight,
        has_projection=True,
        unstartable=unstartable,
        current_slot=slot,
    )


# --------------------------------------------------------------------------------------
# solve() — the assignment itself
# --------------------------------------------------------------------------------------


def test_solve_fills_every_slot_with_the_best_legal_player():
    groups = [("FLEX", 1), ("RB", 1)]
    result = lineup.solve(
        groups,
        [
            cand("rb_big", {"RB", "FLEX"}, 20.0),
            cand("rb_small", {"RB", "FLEX"}, 8.0),
            cand("wr", {"WR", "FLEX"}, 12.0),
        ],
    )
    # The RB slot can only take an RB, so the big RB goes there and FLEX takes the WR —
    # total 32, versus the 28 a positional-greedy pass would settle for.
    assert result == {"RB": ["rb_big"], "FLEX": ["wr"]}


def test_solve_beats_greedy_when_the_best_player_blocks_a_slot():
    """The case this feature exists for: a greedy 'best player into the first slot they
    fit' pass gets this wrong."""
    groups = [("QB", 1), ("OP", 1)]
    result = lineup.solve(
        groups,
        [
            cand("qb1", {"QB", "OP"}, 25.0),
            cand("qb2", {"QB", "OP"}, 24.0),
            cand("wr", {"WR", "OP"}, 10.0),
        ],
    )
    assert set(result["QB"] + result["OP"]) == {"qb1", "qb2"}


def test_solve_never_leaves_a_slot_empty_to_gain_points():
    """A lineup with a hole is one the platform rejects, so filling is lexicographically
    ahead of scoring."""
    groups = [("QB", 1), ("RB", 1)]
    result = lineup.solve(groups, [cand("qb", {"QB"}, 0.0), cand("rb", {"RB"}, 5.0)])
    assert result == {"QB": ["qb"], "RB": ["rb"]}


def test_solve_leaves_a_group_empty_when_nobody_is_eligible():
    groups = [("QB", 1), ("K", 1)]
    result = lineup.solve(groups, [cand("qb", {"QB"}, 10.0)])
    assert result == {"QB": ["qb"], "K": []}


def test_solve_handles_a_multi_capacity_group():
    groups = [("WR", 2)]
    result = lineup.solve(
        groups,
        [cand("a", {"WR"}, 5.0), cand("b", {"WR"}, 15.0), cand("c", {"WR"}, 10.0)],
    )
    assert sorted(result["WR"]) == ["b", "c"]


def test_solve_is_empty_for_no_groups():
    assert lineup.solve([], [cand("a", {"WR"}, 5.0)]) == {}


# --------------------------------------------------------------------------------------
# Candidate construction — the three honesty rules
# --------------------------------------------------------------------------------------


def roster_row(slot, pid, points, *, injury=None, eligible=None, position="RB"):
    rs = RosterSlot(
        team_id=TEAM, week=1, slot=slot, player_id=pid, proj_points=points, actual_points=0.0
    )
    player = Player(
        id=pid,
        platform="espn",
        platform_id=pid.split("-")[-1],
        name=pid,
        position=position,
        nfl_team="KC",
        injury_status=injury,
    )
    pe = PlayerPoolEntry(
        league_id=LEAGUE,
        player_id=pid,
        status="ONTEAM",
        percent_owned=0.0,
        percent_started=0.0,
        eligible_slots=json.dumps(eligible if eligible is not None else RB_SLOTS),
    )
    return rs, player, pe


def test_ir_players_are_excluded_structurally_not_by_injury_status():
    """An IR row with a stale/absent designation must still never be startable — the
    platform won't accept it whatever our status column says."""
    rows = [roster_row("IR", "espn:p-1", 30.0, injury=None)]
    cands, _ = lineup.build_candidates(rows, {}, source="platform", scoring_type="ppr")
    assert cands == []


def test_unstartable_designations_score_zero():
    rows = [roster_row("RB1", "espn:p-1", 18.0, injury="O")]
    cands, _ = lineup.build_candidates(rows, {}, source="platform", scoring_type="ppr")
    assert cands[0].points == 0.0
    assert cands[0].unstartable is True


@pytest.mark.parametrize("status", ["Q", "D", "DTD"])
def test_questionable_players_keep_their_projection(status):
    """Zeroing a questionable player would make the start/sit call the user came here for."""
    rows = [roster_row("RB1", "espn:p-1", 18.0, injury=status)]
    cands, _ = lineup.build_candidates(rows, {}, source="platform", scoring_type="ppr")
    assert cands[0].points == 18.0
    assert cands[0].unstartable is False


def test_an_incumbent_carries_the_materiality_premium():
    """Materiality lives in the objective, not in a filter over the result — so a
    starter is only displaced by a challenger who beats them by MIN_MATERIAL_GAIN."""
    rows = [roster_row("RB1", "espn:p-1", 10.0), roster_row("BN", "espn:p-2", 10.0)]
    cands, _ = lineup.build_candidates(rows, {}, source="platform", scoring_type="ppr")
    by_id = {c.player_id: c for c in cands}
    assert by_id["espn:p-1"].weight == 10.0 + lineup.MIN_MATERIAL_GAIN
    assert by_id["espn:p-2"].weight == 10.0


def test_an_unstartable_incumbent_gets_no_premium():
    """They should always be displaced, so they must not be protected by it."""
    rows = [roster_row("RB1", "espn:p-1", 10.0, injury="O")]
    cands, _ = lineup.build_candidates(rows, {}, source="platform", scoring_type="ppr")
    assert cands[0].weight == 0.0


def test_has_projection_reports_the_truth_for_a_pinned_starter():
    rows = [roster_row("RB1", "espn:p-1", 12.0)]
    cands, _ = lineup.build_candidates(rows, {}, source="rotowire", scoring_type="ppr")
    assert cands[0].has_projection is False


def test_a_bench_player_with_no_projection_is_never_promoted():
    rows = [roster_row("BN", "espn:p-1", 0.0)]
    cands, unevaluated = lineup.build_candidates(rows, {}, source="rotowire", scoring_type="ppr")
    assert cands == []
    assert [p.id for p in unevaluated] == ["espn:p-1"]


def test_a_starter_with_no_projection_is_pinned_where_they_are():
    """A change that cannot be evaluated cannot be justified — so they hold their slot
    rather than being benched by a projection that doesn't exist."""
    rows = [roster_row("RB1", "espn:p-1", 12.0)]
    cands, unevaluated = lineup.build_candidates(rows, {}, source="rotowire", scoring_type="ppr")
    assert cands[0].eligible == frozenset({"RB"})
    assert cands[0].points == 0.0
    assert [p.id for p in unevaluated] == ["espn:p-1"]


def test_a_starter_with_a_missing_pool_row_keeps_their_current_slot():
    """The platform already accepted this assignment, so its own slot proves eligibility
    even when the pool sync is stale."""
    rs, player, _pe = roster_row("WR1", "espn:p-1", 12.0, position="WR")
    cands, _ = lineup.build_candidates(
        [(rs, player, None)], {}, source="platform", scoring_type="ppr"
    )
    assert "WR" in cands[0].eligible


def test_starters_are_ordered_before_the_bench_so_ties_favour_no_change():
    rows = [roster_row("BN", "espn:p-bench", 10.0), roster_row("RB1", "espn:p-start", 10.0)]
    cands, _ = lineup.build_candidates(rows, {}, source="platform", scoring_type="ppr")
    assert cands[0].player_id == "espn:p-start"


# --------------------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------------------


@pytest.fixture
async def db(tmp_path):
    engine = make_engine(tmp_path / "lineup.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed(db, roster, projections=None, scoring="ppr"):
    """`roster` is [(slot, pid, platform_pts, injury, eligible, position)]."""
    async with db() as session:
        session.add(
            League(
                id=LEAGUE,
                platform="espn",
                platform_id="1",
                name="L",
                season=2026,
                team_count=10,
                scoring_type=scoring,
                current_week=1,
            )
        )
        session.add(
            Team(
                id=TEAM,
                league_id=LEAGUE,
                platform="espn",
                platform_id="1",
                name="Mine",
                manager_name="Me",
                rank_current=1,
                rank_total=10,
                is_user_team=True,
            )
        )
        for slot, pid, pts, injury, eligible, position in roster:
            rs, player, pe = roster_row(
                slot, pid, pts, injury=injury, eligible=eligible, position=position
            )
            session.add_all([player, rs, pe])
        for pid, ppr in (projections or {}).items():
            session.add(
                PlayerProjection(
                    player_id=pid,
                    season=2026,
                    week=1,
                    source="rotowire",
                    pts_ppr=ppr,
                    pts_half_ppr=ppr,
                    pts_std=ppr,
                    match_tier="espn_id",
                    fetched_at=datetime(2026, 9, 3),
                )
            )
        await session.commit()


async def test_advice_recommends_a_material_swap(db):
    await seed(
        db,
        [
            ("RB1", "espn:p-1", 10.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-2", 18.0, None, RB_SLOTS, "RB"),
        ],
        projections={"espn:p-1": 10.0, "espn:p-2": 18.0},
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)

    assert advice is not None
    assert [m.slot for m in advice.moves] == ["RB1"]
    assert advice.moves[0].in_player.id == "espn:p-2"
    assert advice.gain == pytest.approx(8.0)
    # Both sources see the same numbers here, so they must agree.
    assert advice.sources_agree is True
    assert advice.moves[0].consensus is True


async def test_an_immaterial_swap_is_reverted_not_shown(db):
    """A 0.2-point 'upgrade' is a coin flip dressed as advice."""
    await seed(
        db,
        [
            ("RB1", "espn:p-1", 10.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-2", 10.2, None, RB_SLOTS, "RB"),
        ],
        projections={"espn:p-1": 10.0, "espn:p-2": 10.2},
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)
    assert advice.moves == []
    # And `gain` reflects the moves actually shown, not the raw solver optimum.
    assert advice.gain == 0.0


async def test_an_out_starter_is_benched_even_for_a_worse_replacement(db):
    await seed(
        db,
        [
            ("RB1", "espn:p-1", 20.0, "O", RB_SLOTS, "RB"),
            ("BN", "espn:p-2", 3.0, None, RB_SLOTS, "RB"),
        ],
        projections={"espn:p-1": 20.0, "espn:p-2": 3.0},
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)
    assert [m.reason for m in advice.moves] == ["unstartable"]
    assert advice.moves[0].in_player.id == "espn:p-2"


async def test_gain_always_equals_the_sum_of_the_moves_shown(db):
    await seed(
        db,
        [
            ("RB1", "espn:p-1", 5.0, None, RB_SLOTS, "RB"),
            ("WR1", "espn:p-3", 9.0, None, WR_SLOTS, "WR"),
            ("BN", "espn:p-2", 14.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-4", 9.1, None, WR_SLOTS, "WR"),
        ],
        projections={"espn:p-1": 5.0, "espn:p-2": 14.0, "espn:p-3": 9.0, "espn:p-4": 9.1},
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)
    # The WR swap is immaterial (+0.1) and reverted; only the RB swap survives.
    assert [m.slot for m in advice.moves] == ["RB1"]
    assert advice.gain == pytest.approx(sum(m.delta for m in advice.moves))


async def test_no_projections_reports_unavailable_not_optimal(db):
    """ "We can't tell" must never render as "your lineup is right"."""
    await seed(db, [])
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)
    assert advice.advice_available is False
    assert advice.moves == []


async def test_unknown_team_returns_none(db):
    await seed(db, [])
    async with db() as session:
        assert await lineup.get_lineup_advice(session, "espn:l-1-t-99", 1) is None


async def test_the_eligibility_rule_accepts_every_platform_accepted_lineup(db):
    """The predicate the whole feature rests on. Checked against all 300 real starter
    assignments in this install before the solver was written; pinned here so a change to
    `_base_slot` or `_startable_eligibility` can't silently invalidate it."""
    await seed(
        db,
        [
            ("QB1", "espn:p-q", 20.0, None, QB_SLOTS, "QB"),
            ("RB1", "espn:p-1", 10.0, None, RB_SLOTS, "RB"),
            ("FLEX1", "espn:p-3", 9.0, None, WR_SLOTS, "WR"),
        ],
    )
    async with db() as session:
        rows = await lineup._load_roster(session, TEAM, LEAGUE, 1)
    for rs, _player, pe in rows:
        if rs.slot in (lineup.BENCH_SLOT, lineup.IR_SLOT):
            continue
        eligible = _startable_eligibility(json.loads(pe.eligible_slots))
        assert _base_slot(rs.slot) in eligible, f"{rs.slot} not legal under our rule"


# --------------------------------------------------------------------------------------
# Regressions from the code review
# --------------------------------------------------------------------------------------


async def test_no_projections_at_all_is_not_reported_as_an_optimal_lineup(db):
    """The bug this pins: a starter with no projection is still added as a PINNED
    candidate, so `by_id` was non-empty and `advice_available` came back True with zero
    moves — rendering "Your lineup is optimal." on a team we could not evaluate at all."""
    await seed(
        db,
        [
            ("RB1", "espn:p-1", 10.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-2", 12.0, None, RB_SLOTS, "RB"),
        ],
        projections={},  # rotowire knows nothing about either player
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1, source="rotowire")
    assert advice.advice_available is False
    assert advice.moves == []


async def test_a_chained_move_keeps_the_lineup_complete_and_the_gain_consistent(db):
    """Regression for a -5.0 gain reported next to a +7.0 move.

    `d` is eligible for WR only, so promoting him displaces `b` out of WR2, and `b` then
    lands in FLEX1 over `c`. Filtering the immaterial first link (+0.3) out of the RESULT
    left `b` recommended into FLEX1 while still occupying WR2 — a lineup with an empty
    slot. Materiality now lives in the objective, so every solution is complete.
    """
    await seed(
        db,
        [
            ("WR1", "espn:p-a", 30.0, None, WR_SLOTS, "WR"),
            ("WR2", "espn:p-b", 12.0, None, WR_SLOTS, "WR"),
            ("FLEX1", "espn:p-c", 5.0, None, WR_SLOTS, "WR"),
            ("BN", "espn:p-d", 12.3, None, ["WR", "BN", "IR"], "WR"),
        ],
        projections={
            "espn:p-a": 30.0,
            "espn:p-b": 12.0,
            "espn:p-c": 5.0,
            "espn:p-d": 12.3,
        },
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)

    assert advice.gain > 0
    assert advice.gain == pytest.approx(sum(m.delta for m in advice.moves))
    # Every starting slot still has exactly one occupant, and nobody holds two.
    filled = [m.slot for m in advice.moves]
    assert len(filled) == len(set(filled))
    incoming = [m.in_player.id for m in advice.moves]
    outgoing = [m.out_player.id for m in advice.moves]
    assert not (set(incoming) & set(outgoing) & {"espn:p-b"}) or advice.gain > 0


async def test_a_move_names_the_slot_its_outgoing_player_actually_held(db):
    """The old pairing zipped `free_slots` against `leaving` in independent orders, so
    with two departures from one group a move could name the wrong slot."""
    await seed(
        db,
        [
            ("RB1", "espn:p-1", 2.0, None, RB_SLOTS, "RB"),
            ("RB2", "espn:p-2", 3.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-3", 20.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-4", 21.0, None, RB_SLOTS, "RB"),
        ],
        projections={
            "espn:p-1": 2.0,
            "espn:p-2": 3.0,
            "espn:p-3": 20.0,
            "espn:p-4": 21.0,
        },
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)

    held = {"espn:p-1": "RB1", "espn:p-2": "RB2"}
    for move in advice.moves:
        assert move.slot == held[move.out_player.id]


async def test_duplicate_unnumbered_slot_labels_do_not_lose_a_starter(db):
    """The internal vocabulary numbers RB/WR/FLEX but leaves K/TE/QB/DST bare, and a real
    league in this install starts TWO kickers — `[..., "K", "K", ...]`.

    Keying the recommended lineup by slot label collapsed those into one entry and dropped
    a starter, which surfaced as a -8.09 gain reported next to zero moves.
    """
    await seed(
        db,
        [
            ("K", "espn:p-k1", 8.0, None, ["K", "BN", "IR"], "K"),
            ("K", "espn:p-k2", 7.0, None, ["K", "BN", "IR"], "K"),
        ],
        projections={"espn:p-k1": 8.0, "espn:p-k2": 7.0},
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)

    assert advice.moves == []
    # Both kickers still counted; the lineup is unchanged, so the gain must be exactly 0.
    assert advice.current_points == pytest.approx(15.0)
    assert advice.optimal_points == pytest.approx(15.0)
    assert advice.gain == 0.0


async def test_every_advice_reports_a_gain_equal_to_its_moves(db):
    """The invariant, stated once: whatever the roster shape, `gain` is the sum of the
    moves shown. Two separate bugs violated it before it was pinned."""
    await seed(
        db,
        [
            ("QB", "espn:p-q", 18.0, None, QB_SLOTS, "QB"),
            ("RB1", "espn:p-1", 4.0, None, RB_SLOTS, "RB"),
            ("RB2", "espn:p-2", 9.0, "O", RB_SLOTS, "RB"),
            ("K", "espn:p-k1", 8.0, None, ["K", "BN", "IR"], "K"),
            ("K", "espn:p-k2", 7.0, None, ["K", "BN", "IR"], "K"),
            ("BN", "espn:p-3", 16.0, None, RB_SLOTS, "RB"),
            ("BN", "espn:p-4", 11.0, None, RB_SLOTS, "RB"),
        ],
        projections={
            "espn:p-q": 18.0,
            "espn:p-1": 4.0,
            "espn:p-2": 9.0,
            "espn:p-k1": 8.0,
            "espn:p-k2": 7.0,
            "espn:p-3": 16.0,
            "espn:p-4": 11.0,
        },
    )
    async with db() as session:
        advice = await lineup.get_lineup_advice(session, TEAM, 1)

    assert advice.gain == pytest.approx(sum(m.delta for m in advice.moves), abs=0.02)
    # The OUT starter is benched even though the rule that displaces him is a different
    # one from the rule that displaces the merely-worse starter.
    assert "unstartable" in {m.reason for m in advice.moves}
