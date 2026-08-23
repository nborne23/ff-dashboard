"""Draft recommendation engine (`backend/gridiron/services/draft_recommender.py`).
Table-driven, plain dataclasses, no DB/HTTP/fixtures."""

import pytest

from backend.gridiron.services.draft_recommender import (
    DEFAULT_WEIGHTS,
    Candidate,
    LeagueShape,
    TierAlarm,
    Weights,
    _draft_the_tier_fires,
    _flags_component,
    _need_component,
    _pair_is_redundant_single_starter,
    _risk_component,
    _tier_counts,
    _tier_urgency_component,
    _value_component,
    bye_collisions,
    elite_te_window_advisories,
    handcuff_advisories,
    no_kicker_advisory,
    positional_runs,
    recommend,
    recommend_pair,
    replacement_rank,
    tier_break_alarms,
)

LEAGUE = LeagueShape(
    teams=12,
    starters={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "DST": 1, "K": 0},
    flex_eligible=("RB", "WR", "TE"),
    rounds=15,
    slot=1,
)


def _cand(
    name,
    position="WR",
    adp_rank=None,
    positional_tier=None,
    risk_score=None,
    unpriced_risk=False,
    flags=(),
    bye=None,
    off_board=False,
    overall_tier=None,
    nfl_team=None,
):
    return Candidate(
        name=name,
        position=position,
        nfl_team=nfl_team,
        bye=bye,
        adp_rank=adp_rank,
        overall_tier=overall_tier,
        positional_tier=positional_tier,
        risk_score=risk_score,
        unpriced_risk=unpriced_risk,
        flags=tuple(flags),
        off_board=off_board,
    )


# ---------------------------------------------------------------------------
# 2.3 value component
# ---------------------------------------------------------------------------


def test_value_component_null_adp_rank_is_zero() -> None:
    c = _cand("No ADP", adp_rank=None)
    assert _value_component(c, current_pick=10, teams=12) == 0.0


def test_value_component_clamped_high_and_low() -> None:
    # Surplus, not lateness: a consensus 1.01 still on the board at pick 100 is the
    # bargain (clamped high); taking the 100th-ranked player at 1.01 is the reach.
    fallen = _cand("Fell far", adp_rank=1)
    assert _value_component(fallen, current_pick=100, teams=12) == pytest.approx(3.0)

    reached = _cand("Reached for", adp_rank=100)
    assert _value_component(reached, current_pick=1, teams=12) == pytest.approx(-2.0)


def test_value_component_unclamped_midrange() -> None:
    c = _cand("Mid", adp_rank=1)
    assert _value_component(c, current_pick=13, teams=12) == pytest.approx(1.0)


def test_value_component_does_not_saturate_across_an_early_board() -> None:
    """The regression that made the shortlist meaningless.

    With the old `(adp_rank - current_pick)` sign, every candidate ranked >= 3 rounds
    below the current pick pinned to the +3.0 clamp -- at pick 1 that was nearly the
    whole board, so the term stopped discriminating and the shortlist fell through to
    pool order. Correct behavior at pick 1: the consensus 1.01 leads and later-ranked
    players score strictly worse.
    """
    scores = [
        _value_component(_cand(str(r), adp_rank=r), current_pick=1, teams=12) for r in (1, 40, 74)
    ]
    assert scores == sorted(scores, reverse=True)
    # The 1.01 leads outright; the late-board pair bottoms out at the low clamp
    # instead of all three sharing the high clamp, which made the shortlist arbitrary.
    assert scores[0] > scores[1]
    assert scores[0] != max(scores[1:])


# ---------------------------------------------------------------------------
# 2.4 tier urgency + alarm + draft_the_tier citation
# ---------------------------------------------------------------------------


def test_tier_urgency_zero_when_no_positional_tier() -> None:
    c = _cand("No tier", positional_tier=None)
    assert _tier_urgency_component(c, {}, picks_until_next=5) == 0.0


def test_tier_urgency_on_the_clock_scales_by_scarcity() -> None:
    """On the clock the term must still discriminate, not flatten to a constant.

    The original guard returned `_TIER_URGENCY_MAX` for every candidate when
    `picks_until_next == 0` -- which is precisely when recommendations are requested --
    making the highest-weighted component identical for the whole pool. It now scales by
    how much of the tier is left, so the last man in a tier is now-or-never and one of
    five is not. Still no ZeroDivisionError.
    """
    c = _cand("On clock", positional_tier=2)
    sole = _tier_urgency_component(c, {("WR", 2): 1}, picks_until_next=0)
    several = _tier_urgency_component(c, {("WR", 2): 5}, picks_until_next=0)
    assert sole == pytest.approx(10.0)
    assert several == pytest.approx(2.0)
    assert sole > several

    empty = _tier_urgency_component(c, {}, picks_until_next=0)
    assert empty == pytest.approx(10.0)


def test_tier_urgency_rises_as_remaining_falls() -> None:
    c = _cand("Thin tier", positional_tier=2)
    thin = _tier_urgency_component(c, {("WR", 2): 1}, picks_until_next=5)
    deep = _tier_urgency_component(c, {("WR", 2): 10}, picks_until_next=5)
    assert thin > deep


def test_tier_urgency_rises_as_picks_until_next_rises() -> None:
    c = _cand("Watched tier", positional_tier=2)
    counts = {("WR", 2): 4}
    soon = _tier_urgency_component(c, counts, picks_until_next=2)
    later = _tier_urgency_component(c, counts, picks_until_next=8)
    assert later > soon


def test_tier_break_alarms_fires_only_under_two_and_over_eight() -> None:
    pool = [
        _cand("A", position="RB", positional_tier=3),
        _cand("B", position="RB", positional_tier=3),
        _cand("C", position="WR", positional_tier=1),
        _cand("D", position="WR", positional_tier=1),
        _cand("E", position="WR", positional_tier=1),
    ]
    alarms = tier_break_alarms(pool, picks_until_next=9)
    assert alarms == [
        _alarm(position="RB", tier=3, remaining=2, picks_until_next=9),
    ]


def _alarm(**kwargs):
    return TierAlarm(**kwargs)


def test_tier_break_alarms_clears_at_or_below_eight_picks_out() -> None:
    pool = [
        _cand("A", position="RB", positional_tier=3),
        _cand("B", position="RB", positional_tier=3),
    ]
    assert tier_break_alarms(pool, picks_until_next=8) == []


def test_tier_break_alarms_clears_on_the_clock() -> None:
    pool = [
        _cand("A", position="RB", positional_tier=3),
        _cand("B", position="RB", positional_tier=3),
    ]
    assert tier_break_alarms(pool, picks_until_next=0) == []


def test_tier_break_alarms_ignores_off_board_and_untiered() -> None:
    pool = [
        _cand("A", position="RB", positional_tier=3, off_board=True),
        _cand("B", position="RB", positional_tier=3),
        _cand("C", position="RB", positional_tier=None),
    ]
    assert tier_break_alarms(pool, picks_until_next=9) == [
        _alarm(position="RB", tier=3, remaining=1, picks_until_next=9)
    ]


def test_draft_the_tier_fires_condition() -> None:
    counts = {("WR", 2): 1}
    c = _cand("Last one", position="WR", positional_tier=2)
    assert _draft_the_tier_fires(c, counts, picks_until_next=5) is True
    assert _draft_the_tier_fires(c, {("WR", 2): 10}, picks_until_next=5) is False
    assert _draft_the_tier_fires(c, {}, picks_until_next=5) is False


# ---------------------------------------------------------------------------
# 2.5 replacement rank / need
# ---------------------------------------------------------------------------


def test_replacement_rank_rb_wr_materially_above_naive_24() -> None:
    rb = replacement_rank("RB", LEAGUE)
    wr = replacement_rank("WR", LEAGUE)
    te = replacement_rank("TE", LEAGUE)
    assert rb == 35
    assert wr == 35
    assert te == 14
    assert rb > 24 and wr > 24


def test_need_component_falls_as_position_fills() -> None:
    empty_roster: list[Candidate] = []
    one_rb = [_cand("RB1", position="RB")]
    two_rb = [_cand("RB1", position="RB"), _cand("RB2", position="RB")]

    c = _cand("Candidate RB", position="RB")
    need_empty = _need_component(c, empty_roster, LEAGUE)
    need_one = _need_component(c, one_rb, LEAGUE)
    need_two = _need_component(c, two_rb, LEAGUE)
    assert need_empty > need_one > need_two >= 0


def test_need_component_shifts_to_flex_eligible_positions_once_starters_filled() -> None:
    # RB starters (2) filled; flex-eligible RB need should still be > 0 thanks to FLEX share.
    roster = [_cand("RB1", position="RB"), _cand("RB2", position="RB")]
    c = _cand("Third RB", position="RB")
    need = _need_component(c, roster, LEAGUE)
    assert need > 0  # FLEX still has room for RB overflow

    # Once FLEX is also fully consumed by RB overflow, RB need should bottom out at 0.
    heavy_rb_roster = [_cand(f"RB{i}", position="RB") for i in range(6)]
    need_saturated = _need_component(c, heavy_rb_roster, LEAGUE)
    assert need_saturated == 0.0


def test_need_component_zero_for_k_league_never_needs_kicker() -> None:
    c = _cand("Some Kicker", position="K")
    assert _need_component(c, [], LEAGUE) == 0.0


# ---------------------------------------------------------------------------
# 2.6 risk component -- gated on unpriced_risk ONLY
# ---------------------------------------------------------------------------


def test_risk_component_zero_when_not_unpriced() -> None:
    c = _cand("Priced risk", risk_score=5, unpriced_risk=False)
    assert _risk_component(c) == 0.0


def test_risk_component_penalizes_unpriced_high_risk() -> None:
    love = _cand("Jeremiyah Love", risk_score=5, unpriced_risk=True)
    pierce = _cand("Alec Pierce", risk_score=5, unpriced_risk=True)
    assert _risk_component(love) == pytest.approx(-5.0)
    assert _risk_component(pierce) == pytest.approx(-5.0)


def test_risk_component_zero_below_threshold_even_if_unpriced() -> None:
    c = _cand("Low risk", risk_score=3, unpriced_risk=True)
    assert _risk_component(c) == 0.0


def test_risk_component_zero_when_risk_score_missing() -> None:
    c = _cand("No risk data", risk_score=None, unpriced_risk=True)
    assert _risk_component(c) == 0.0


# ---------------------------------------------------------------------------
# 2.7 flags + composite + non-empty fired_rule_ids/reason
# ---------------------------------------------------------------------------


def test_default_weights_tier_urgency_is_largest() -> None:
    # Tier structure, not raw ranking, is the board's stated edge -- weights.tier_urgency
    # must dominate the other four components.
    w = DEFAULT_WEIGHTS
    assert w.tier_urgency > max(w.value, w.need, w.risk, w.flags)


def test_custom_weights_change_ranking() -> None:
    pool = [
        # Deep tier (remaining=10 incl. fillers) but the best raw ADP value in the pool.
        _cand("Best Value", position="RB", adp_rank=1, positional_tier=3),
        *[_cand(f"Filler{i}", position="RB", adp_rank=60 + i, positional_tier=3) for i in range(9)],
        # Sole member of his tier (remaining=1) -- huge tier_urgency, modest value.
        _cand("Thin Tier", position="RB", adp_rank=30, positional_tier=7),
    ]
    default_results = recommend(
        pool, [], LEAGUE, current_pick=50, picks_until_next=5, recent_picks=[]
    )
    zero_urgency = Weights(value=1.0, tier_urgency=0.0, need=0.0, risk=0.0, flags=0.0)
    reweighted_results = recommend(
        pool, [], LEAGUE, current_pick=50, picks_until_next=5, recent_picks=[], weights=zero_urgency
    )
    # Under default weights, tier_urgency's huge pull for the sole member of a thin tier
    # wins the top spot; zeroing that weight out flips it to pure ADP value.
    assert default_results[0].candidate.name == "Thin Tier"
    assert reweighted_results[0].candidate.name == "Best Value"


def test_tier_counts_ignores_off_board_and_untiered() -> None:
    pool = [
        _cand("A", position="RB", positional_tier=2),
        _cand("B", position="RB", positional_tier=2, off_board=True),
        _cand("C", position="RB", positional_tier=None),
        _cand("D", position="WR", positional_tier=2),
    ]
    counts = _tier_counts(pool)
    assert counts == {("RB", 2): 1, ("WR", 2): 1}


def test_flags_component_values() -> None:
    assert _flags_component(_cand("T", flags=("TARGET",))) == 1.0
    assert _flags_component(_cand("F", flags=("FADE",))) == -1.0
    assert _flags_component(_cand("N", flags=("NEUTRAL",))) == 0.0
    assert _flags_component(_cand("S", flags=("SLEEPER",))) == 0.0
    assert _flags_component(_cand("Plain", flags=())) == 0.0


def test_recommend_every_result_has_nonempty_reason_and_fired_rule_ids() -> None:
    pool = [
        _cand("A", position="RB", adp_rank=20, positional_tier=3),
        _cand("B", position="WR", adp_rank=25, positional_tier=2),
        _cand("C", position="TE", adp_rank=30, positional_tier=1),
        _cand("D", position="RB", adp_rank=40, positional_tier=4),
        _cand("E", position="WR", adp_rank=45, positional_tier=3),
        _cand("F", position="RB", adp_rank=50, positional_tier=4),
    ]
    results = recommend(pool, [], LEAGUE, current_pick=20, picks_until_next=3, recent_picks=[])
    assert len(results) >= 3
    for rec in results:
        assert rec.fired_rule_ids  # non-empty tuple
        assert rec.reason.strip()  # non-empty string
        assert sum(rec.components.values()) == pytest.approx(rec.score)


def test_recommend_returns_all_when_pool_smaller_than_three() -> None:
    pool = [
        _cand("Only one", position="RB", adp_rank=5, positional_tier=1),
        _cand("Only two", position="WR", adp_rank=6, positional_tier=1),
    ]
    results = recommend(pool, [], LEAGUE, current_pick=5, picks_until_next=1, recent_picks=[])
    assert len(results) == 2
    for rec in results:
        assert rec.fired_rule_ids


def test_recommend_shortlist_between_three_and_five() -> None:
    pool = [
        _cand(f"P{i}", position="RB", adp_rank=i, positional_tier=(i % 4) + 1) for i in range(1, 20)
    ]
    results = recommend(
        pool, [], LEAGUE, current_pick=10, picks_until_next=3, recent_picks=[], limit=5
    )
    assert 3 <= len(results) <= 5


# ---------------------------------------------------------------------------
# 2.9 draft_the_tier outranks a higher-ranked player from a surviving tier
# ---------------------------------------------------------------------------


def test_draft_the_tier_outranks_higher_ranked_survivor() -> None:
    # Every candidate shares the SAME adp_rank, so the `value` component is identical
    # across the whole pool and cannot be what decides the ranking -- only tier depth
    # differs, isolating draft_the_tier / tier_urgency as the actual mechanism under
    # test. (If tier_urgency were deleted entirely, all 5 scores here would tie and a
    # stable sort would keep "Last In Tier" -- last in the input list -- LAST, not
    # first, so this test would correctly fail.)
    SAME_ADP_RANK = 20
    pool = [
        # Safe tier: remaining=4 (> picks_until_next=3) -- survives, doesn't fire.
        *[
            _cand(f"TierMate{i}", position="WR", positional_tier=1, adp_rank=SAME_ADP_RANK)
            for i in range(1, 4)
        ],
        _cand("Safe Star", position="WR", adp_rank=SAME_ADP_RANK, positional_tier=1),
        # Thin tier: remaining=1 (<= picks_until_next=3) -- the LAST player, fires.
        _cand("Last In Tier", position="WR", adp_rank=SAME_ADP_RANK, positional_tier=6),
    ]
    results = recommend(
        pool, [], LEAGUE, current_pick=1, picks_until_next=3, recent_picks=[], limit=5
    )

    names_in_order = [r.candidate.name for r in results]
    assert "Last In Tier" in names_in_order
    assert "Safe Star" in names_in_order
    assert names_in_order.index("Last In Tier") < names_in_order.index("Safe Star")
    assert results[0].candidate.name == "Last In Tier"

    last_in_tier_rec = next(r for r in results if r.candidate.name == "Last In Tier")
    safe_star_rec = next(r for r in results if r.candidate.name == "Safe Star")
    assert "draft_the_tier" in last_in_tier_rec.fired_rule_ids
    assert "draft_the_tier" not in safe_star_rec.fired_rule_ids


# ---------------------------------------------------------------------------
# 2.8 categorical filters
# ---------------------------------------------------------------------------


def test_no_kicker_never_recommended() -> None:
    pool = [
        _cand("Great Kicker", position="K", adp_rank=1, positional_tier=1),
        _cand("Mediocre RB", position="RB", adp_rank=80, positional_tier=5),
        _cand("Mediocre WR", position="WR", adp_rank=90, positional_tier=5),
    ]
    results = recommend(pool, [], LEAGUE, current_pick=80, picks_until_next=2, recent_picks=[])
    assert all(r.candidate.position != "K" for r in results)


def test_no_kicker_advisory_present_when_league_has_zero_k_starters() -> None:
    advisory = no_kicker_advisory(LEAGUE)
    assert advisory is not None
    assert "kicker" in advisory.lower()


def test_no_kicker_advisory_absent_when_league_has_k_starter() -> None:
    league_with_k = LeagueShape(
        teams=12,
        starters={**LEAGUE.starters, "K": 1},
        flex_eligible=LEAGUE.flex_eligible,
        rounds=15,
        slot=1,
    )
    assert no_kicker_advisory(league_with_k) is None


def test_qb_wait_blocks_early_non_elite_qb() -> None:
    pool = [
        _cand("Mid QB", position="QB", adp_rank=45, positional_tier=2),
        _cand("Filler WR", position="WR", adp_rank=46, positional_tier=3),
        _cand("Filler RB", position="RB", adp_rank=47, positional_tier=3),
    ]
    results = recommend(pool, [], LEAGUE, current_pick=45, picks_until_next=1, recent_picks=[])
    assert all(r.candidate.name != "Mid QB" for r in results)


def test_qb_wait_allows_elite_qb_fallen_far_enough() -> None:
    pool = [
        _cand("Elite QB", position="QB", adp_rank=10, positional_tier=1),
        _cand("Filler WR", position="WR", adp_rank=30, positional_tier=3),
    ]
    # current_pick - adp_rank = 30 - 10 = 20 >= 8
    results = recommend(pool, [], LEAGUE, current_pick=30, picks_until_next=1, recent_picks=[])
    assert any(r.candidate.name == "Elite QB" for r in results)
    rec = next(r for r in results if r.candidate.name == "Elite QB")
    assert "qb_wait" in rec.fired_rule_ids


def test_qb_wait_allows_any_qb_after_pick_fifty() -> None:
    pool = [
        _cand("Late QB", position="QB", adp_rank=55, positional_tier=3),
        _cand("Filler WR", position="WR", adp_rank=56, positional_tier=3),
    ]
    results = recommend(pool, [], LEAGUE, current_pick=51, picks_until_next=1, recent_picks=[])
    assert any(r.candidate.name == "Late QB" for r in results)


def test_dst_last_blocks_dst_before_final_two_rounds() -> None:
    # Round for pick 100 in a 12-team league: (100-1)//12+1 = 9, well before round 14/15.
    pool = [
        _cand("Early DST", position="DST", adp_rank=100, positional_tier=None),
        _cand("Filler RB", position="RB", adp_rank=101, positional_tier=3),
    ]
    results = recommend(pool, [], LEAGUE, current_pick=100, picks_until_next=1, recent_picks=[])
    assert all(r.candidate.name != "Early DST" for r in results)


def test_dst_last_allows_exactly_one_dst_in_final_two_rounds() -> None:
    # Round 14 starts at pick 157 in a 12-team league; use pick 160 (round 14).
    pool = [
        _cand("DST A", position="DST", adp_rank=160, positional_tier=None),
        _cand("DST B", position="DST", adp_rank=165, positional_tier=None),
        _cand("DST C", position="DST", adp_rank=168, positional_tier=None),
        _cand("Filler RB", position="RB", adp_rank=161, positional_tier=6),
    ]
    results = recommend(
        pool, [], LEAGUE, current_pick=160, picks_until_next=1, recent_picks=[], limit=5
    )
    dst_recs = [r for r in results if r.candidate.position == "DST"]
    assert len(dst_recs) == 1
    assert "dst_last" in dst_recs[0].fired_rule_ids


# ---------------------------------------------------------------------------
# elite_te_window
# ---------------------------------------------------------------------------


def test_elite_te_window_advisory_only_after_pick_thirty() -> None:
    pool = [_cand("Trey McBride", position="TE", adp_rank=39, positional_tier=1)]
    assert elite_te_window_advisories(pool, current_pick=30) == []
    advisories = elite_te_window_advisories(pool, current_pick=31)
    assert len(advisories) == 1
    assert "Trey McBride" in advisories[0]


def test_elite_te_window_forces_inclusion_regardless_of_weighted_rank() -> None:
    # McBride buried with a mediocre ADP rank amid many better-scoring candidates.
    pool = [_cand("Trey McBride", position="TE", adp_rank=39, positional_tier=1)]
    pool += [
        _cand(f"Better{i}", position="RB", adp_rank=32 + i, positional_tier=1) for i in range(8)
    ]

    results = recommend(
        pool, [], LEAGUE, current_pick=32, picks_until_next=1, recent_picks=[], limit=3
    )
    names = [r.candidate.name for r in results]
    assert "Trey McBride" in names
    mcbride_rec = next(r for r in results if r.candidate.name == "Trey McBride")
    assert "elite_te_window" in mcbride_rec.fired_rule_ids


def test_elite_te_window_forces_inclusion_of_both_named_tes_simultaneously() -> None:
    # Both McBride AND Bowers buried behind many better-scoring candidates -- regression
    # test for a forced-inclusion bug where processing the two TEs one at a time let the
    # second overwrite the slot the first had just been bumped into.
    pool = [
        _cand("Trey McBride", position="TE", adp_rank=39, positional_tier=1),
        _cand("Brock Bowers", position="TE", adp_rank=44, positional_tier=1),
    ]
    pool += [
        _cand(f"Better{i}", position="RB", adp_rank=32 + i, positional_tier=1) for i in range(8)
    ]

    results = recommend(
        pool, [], LEAGUE, current_pick=32, picks_until_next=1, recent_picks=[], limit=3
    )
    names = [r.candidate.name for r in results]
    assert "Trey McBride" in names
    assert "Brock Bowers" in names
    for rec in results:
        if rec.candidate.name in ("Trey McBride", "Brock Bowers"):
            assert "elite_te_window" in rec.fired_rule_ids


# ---------------------------------------------------------------------------
# handcuff_own_studs -- risk_score only, never injury_tags
# ---------------------------------------------------------------------------


def test_handcuff_advisories_keyed_on_risk_score_only() -> None:
    roster = [
        _cand("At Risk RB", position="RB", risk_score=4),
        _cand("Safe RB", position="RB", risk_score=1),
        _cand("At Risk WR", position="WR", risk_score=5),  # not RB -- no handcuff advisory
    ]
    advisories = handcuff_advisories(roster)
    assert len(advisories) == 1
    assert "At Risk RB" in advisories[0]


def test_handcuff_advisories_empty_when_no_risky_rbs() -> None:
    roster = [_cand("Safe RB", position="RB", risk_score=2)]
    assert handcuff_advisories(roster) == []


# Structural note: Candidate carries no injury_tags field at all, so handcuff_advisories
# cannot key off it even by accident -- risk_score is the only signal available.
def test_candidate_has_no_injury_tags_field() -> None:
    assert not hasattr(_cand("X"), "injury_tags")


# ---------------------------------------------------------------------------
# bye_stacking
# ---------------------------------------------------------------------------


def test_bye_collisions_fires_at_three_or_more() -> None:
    roster = [
        _cand("A", bye=11),
        _cand("B", bye=11),
        _cand("C", bye=11),
        _cand("D", bye=7),
    ]
    collisions = bye_collisions(roster)
    assert len(collisions) == 1
    assert collisions[0].bye == 11
    assert collisions[0].count == 3
    assert set(collisions[0].players) == {"A", "B", "C"}


def test_bye_collisions_silent_below_three() -> None:
    roster = [_cand("A", bye=11), _cand("B", bye=11)]
    assert bye_collisions(roster) == []


# ---------------------------------------------------------------------------
# 2.10 turn-pair reasoning
# ---------------------------------------------------------------------------


def test_pair_is_redundant_single_starter_flags_double_qb_not_double_rb() -> None:
    qb_a = _cand("QB1", position="QB")
    qb_b = _cand("QB2", position="QB")
    rb_a = _cand("RB1", position="RB")
    rb_b = _cand("RB2", position="RB")
    assert _pair_is_redundant_single_starter(qb_a, qb_b, LEAGUE) is True  # QB starters == 1
    assert _pair_is_redundant_single_starter(rb_a, rb_b, LEAGUE) is False  # RB is flex-eligible
    assert _pair_is_redundant_single_starter(qb_a, rb_a, LEAGUE) is False  # different positions


def test_recommend_pair_prefers_distinct_positions_over_redundant_single_starter() -> None:
    # pick_a/pick_b must be >= 50 (qb_wait's threshold) so QB candidates actually reach
    # scoring instead of being filtered out of the pool before the pairing logic runs.
    pool = [
        _cand("QB1", position="QB", adp_rank=52, positional_tier=1),
        _cand("QB2", position="QB", adp_rank=53, positional_tier=2),
        _cand("RB1", position="RB", adp_rank=52, positional_tier=2),
        _cand("WR1", position="WR", adp_rank=53, positional_tier=2),
    ]
    pairs = recommend_pair(pool, [], LEAGUE, pick_a=52, pick_b=53, recent_picks=[], limit=20)
    assert len(pairs) > 0

    positions_by_pair = [{a.candidate.position, b.candidate.position} for a, b in pairs]
    qb_qb_indices = [i for i, positions in enumerate(positions_by_pair) if positions == {"QB"}]
    distinct_indices = [i for i, positions in enumerate(positions_by_pair) if positions != {"QB"}]
    assert (
        qb_qb_indices  # the redundant QB/QB combo really was generated (not just filtered out)...
    )
    assert distinct_indices
    # ...but every distinct-position pair outranks every redundant QB/QB pair.
    assert max(distinct_indices) < min(qb_qb_indices)


def test_recommend_pair_returns_pure_recommendation_pairs_with_reasons() -> None:
    pool = [
        _cand("RB1", position="RB", adp_rank=24, positional_tier=2),
        _cand("WR1", position="WR", adp_rank=25, positional_tier=2),
        _cand("TE1", position="TE", adp_rank=26, positional_tier=1),
    ]
    pairs = recommend_pair(pool, [], LEAGUE, pick_a=24, pick_b=25, recent_picks=[], limit=5)
    assert len(pairs) > 0
    for rec_a, rec_b in pairs:
        assert rec_a.candidate.name != rec_b.candidate.name
        assert rec_a.fired_rule_ids and rec_b.fired_rule_ids


# ---------------------------------------------------------------------------
# 6.1 positional run detection
# ---------------------------------------------------------------------------


def test_positional_runs_fires_at_exactly_four_of_eight() -> None:
    recent = [_cand(f"RB{i}", position="RB") for i in range(4)] + [
        _cand("WR1", position="WR"),
        _cand("TE1", position="TE"),
        _cand("QB1", position="QB"),
        _cand("DST1", position="DST"),
    ]
    runs = positional_runs(recent)
    assert runs == {"RB": 4}


def test_positional_runs_does_not_fire_at_three_of_eight() -> None:
    recent = [
        _cand("RB1", position="RB"),
        _cand("RB2", position="RB"),
        _cand("RB3", position="RB"),
        _cand("WR1", position="WR"),
        _cand("TE1", position="TE"),
        _cand("QB1", position="QB"),
        _cand("DST1", position="DST"),
        _cand("K1", position="K"),
    ]
    assert positional_runs(recent) == {}


def test_positional_runs_clears_as_the_window_moves() -> None:
    # The RB run's members sit at the tail of the trailing-8 window (oldest 4 of 8).
    before = [
        _cand("WR1", position="WR"),
        _cand("WR2", position="WR"),
        _cand("WR3", position="WR"),
        _cand("TE1", position="TE"),
        _cand("RB1", position="RB"),
        _cand("RB2", position="RB"),
        _cand("RB3", position="RB"),
        _cand("RB4", position="RB"),
    ]
    assert "RB" in positional_runs(before)

    # One more pick happens (a new most-recent WR); the window advances and the oldest
    # RB (position 8) falls out of the trailing-8 -- the RB flag must clear.
    after = [_cand("WR_new", position="WR")] + before[:-1]
    assert "RB" not in positional_runs(after)


def test_positional_runs_ignores_picks_past_the_trailing_eight() -> None:
    recent = (
        [_cand(f"RB{i}", position="RB") for i in range(4)]
        + [
            _cand("WR1", position="WR"),
            _cand("TE1", position="TE"),
            _cand("QB1", position="QB"),
            _cand("DST1", position="DST"),
        ]
        + [_cand(f"X{i}", position="WR") for i in range(20)]
    )
    # Only the first 8 (most-recent-first) count -- the RB run stays visible regardless
    # of how much older history is appended after it.
    assert positional_runs(recent) == {"RB": 4}


def test_tier_urgency_component_run_boost_raises_but_still_caps() -> None:
    counts = {("RB", 2): 3}
    candidate = _cand("Target", position="RB", positional_tier=2)
    base = _tier_urgency_component(candidate, counts, picks_until_next=3, run_boost=False)
    boosted = _tier_urgency_component(candidate, counts, picks_until_next=3, run_boost=True)
    assert boosted > base
    assert boosted <= 10.0  # _TIER_URGENCY_MAX


def test_recommend_scores_running_position_strictly_higher() -> None:
    pool = [
        _cand("Target", position="RB", adp_rank=10, positional_tier=2),
        _cand("Peer1", position="RB", positional_tier=2),
        _cand("Peer2", position="RB", positional_tier=2),
    ]
    no_run_recent: list = []
    run_recent = [_cand(f"RB{i}", position="RB") for i in range(4)] + [
        _cand(f"WR{i}", position="WR") for i in range(4)
    ]

    no_run_results = recommend(
        pool, [], LEAGUE, current_pick=20, picks_until_next=3, recent_picks=no_run_recent
    )
    run_results = recommend(
        pool, [], LEAGUE, current_pick=20, picks_until_next=3, recent_picks=run_recent
    )

    no_run_score = next(r.score for r in no_run_results if r.candidate.name == "Target")
    run_rec = next(r for r in run_results if r.candidate.name == "Target")

    assert run_rec.score > no_run_score
    assert "_positional_run" in run_rec.fired_rule_ids
    assert "RB run in progress" in run_rec.reason


def test_positional_run_not_cited_when_it_could_not_have_changed_the_score() -> None:
    """The citation must track the arithmetic, not merely the run being live.

    A run is a no-op on the score only when tier urgency is already pinned at
    `_TIER_URGENCY_MAX` -- which, now that the on-the-clock case scales by scarcity,
    means the candidate is the last man in his tier. A boost cannot raise a capped
    value, so it must not be cited. (Before the scarcity fix, urgency was flat-max for
    *every* on-the-clock candidate, so this held vacuously for the whole pool.)
    """
    sole = [_cand("Target", position="RB", adp_rank=10, positional_tier=2)]
    run_recent = [_cand(f"RB{i}", position="RB") for i in range(4)] + [
        _cand(f"WR{i}", position="WR") for i in range(4)
    ]
    results = recommend(
        sole, [], LEAGUE, current_pick=20, picks_until_next=0, recent_picks=run_recent
    )
    target = next(r for r in results if r.candidate.name == "Target")
    # `components` holds the *weighted* contribution: _TIER_URGENCY_MAX * weight 1.6.
    assert target.components["tier_urgency"] == pytest.approx(16.0)
    assert "_positional_run" not in target.fired_rule_ids
    assert "run in progress" not in target.reason


def test_positional_run_is_cited_on_the_clock_when_the_tier_is_not_pinned() -> None:
    """Counterpart: with room below the cap, an on-the-clock run does move the score."""
    pool = [_cand(f"RB{i}", position="RB", positional_tier=2) for i in range(4)]
    run_recent = [_cand(f"P{i}", position="RB") for i in range(4)]
    results = recommend(
        pool, [], LEAGUE, current_pick=20, picks_until_next=0, recent_picks=run_recent
    )
    assert any("_positional_run" in r.fired_rule_ids for r in results)
