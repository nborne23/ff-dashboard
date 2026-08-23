"""Pure snake-draft arithmetic (`backend/gridiron/services/draft_pick_math.py`).
Table-driven, no DB/HTTP/fixtures."""

import pytest

from backend.gridiron.services.draft_pick_math import (
    picks_until_next,
    round_for_pick,
    snake_pick_numbers,
    turn_pairs,
)


def test_snake_pick_numbers_12_team_slot_1() -> None:
    assert snake_pick_numbers(12, 1, 15) == [
        1,
        24,
        25,
        48,
        49,
        72,
        73,
        96,
        97,
        120,
        121,
        144,
        145,
        168,
        169,
    ]


def test_snake_pick_numbers_10_team_slot_7_correct_order_and_no_cross_contamination() -> None:
    picks_10_team = snake_pick_numbers(10, 7, 16)

    # Manually verify snake order for a 10-team, slot-7 draft: odd rounds go slot 7,
    # even rounds go (10 - 7 + 1) = slot 4 within that round.
    expected = []
    for round_num in range(1, 17):
        base = (round_num - 1) * 10
        pick_in_round = 7 if round_num % 2 == 1 else 4
        expected.append(base + pick_in_round)
    assert picks_10_team == expected
    assert picks_10_team == sorted(picks_10_team)  # strictly increasing

    picks_12_team = snake_pick_numbers(12, 1, 15)
    assert set(picks_10_team).isdisjoint(picks_12_team)


def test_picks_until_next_on_the_clock() -> None:
    my_picks = [1, 24, 25, 48, 49]
    assert picks_until_next(24, my_picks) == 0
    assert picks_until_next(1, my_picks) == 0


def test_picks_until_next_counts_forward() -> None:
    my_picks = [1, 24, 25, 48, 49]
    assert picks_until_next(20, my_picks) == 4
    assert picks_until_next(2, my_picks) == 22


def test_picks_until_next_raises_when_no_upcoming_pick() -> None:
    with pytest.raises(ValueError):
        picks_until_next(200, [1, 24, 25])


def test_turn_pairs_finds_consecutive_picks() -> None:
    my_picks = [1, 24, 25, 48, 49, 72, 73]
    assert turn_pairs(my_picks) == [(24, 25), (48, 49), (72, 73)]


def test_turn_pairs_empty_when_no_consecutive_picks() -> None:
    assert turn_pairs([1, 24, 49]) == []


def test_turn_pairs_handles_unsorted_input() -> None:
    assert turn_pairs([25, 1, 24]) == [(24, 25)]


@pytest.mark.parametrize(
    "overall_pick, teams, expected_round",
    [
        (1, 12, 1),
        (12, 12, 1),
        (13, 12, 2),
        (24, 12, 2),
        (25, 12, 3),
        (169, 12, 15),
    ],
)
def test_round_for_pick(overall_pick: int, teams: int, expected_round: int) -> None:
    assert round_for_pick(overall_pick, teams) == expected_round
