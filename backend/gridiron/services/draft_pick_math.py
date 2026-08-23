"""Pure snake-draft pick arithmetic. No DB, no HTTP, no wall-clock reads -- every
time-varying input is a parameter, per the Draft Assistant recommender's design
constraint (see `draft_recommender.py`)."""

from __future__ import annotations


def snake_pick_numbers(teams: int, slot: int, rounds: int) -> list[int]:
    """Overall pick numbers for `slot` (1-indexed draft position) across `rounds` of a
    standard snake draft. Odd rounds go 1..teams; even rounds reverse (teams..1)."""
    picks = []
    for round_num in range(1, rounds + 1):
        if round_num % 2 == 1:
            pick_in_round = slot
        else:
            pick_in_round = teams - slot + 1
        picks.append((round_num - 1) * teams + pick_in_round)
    return picks


def picks_until_next(current_pick: int, my_picks: list[int]) -> int:
    """Picks remaining before the user is next on the clock. `0` when `current_pick`
    itself is one of the user's picks (on the clock right now)."""
    upcoming = [p for p in my_picks if p >= current_pick]
    if not upcoming:
        raise ValueError("no upcoming picks: current_pick is past the user's last pick")
    return min(upcoming) - current_pick


def turn_pairs(my_picks: list[int]) -> list[tuple[int, int]]:
    """Consecutive picks in `my_picks` that differ by exactly 1 (a snake draft's
    round-turn, e.g. picks 24 and 25)."""
    ordered = sorted(my_picks)
    return [(a, b) for a, b in zip(ordered, ordered[1:]) if b - a == 1]


def round_for_pick(overall_pick: int, teams: int) -> int:
    """1-indexed round containing `overall_pick` in a `teams`-team draft."""
    return (overall_pick - 1) // teams + 1
