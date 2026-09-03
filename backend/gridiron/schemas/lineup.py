"""`LineupAdvice` — the optimal legal lineup and the moves that reach it."""

from typing import Literal

from pydantic import BaseModel

from backend.gridiron.schemas.common import Slot
from backend.gridiron.schemas.players import Player

# Which projection the advice was computed from. Never a blend: the two sources are on
# different scales with different biases, and averaging them produces a number that is
# no source's opinion.
ProjectionSource = Literal["platform", "rotowire"]

# Why a player is being benched.
#
# `unstartable` and `higher_projection` are genuinely different recommendations — "your
# starter is OUT" needs no further justification, while "this guy projects 1.2 more" is a
# judgement the user may well decline — so the reason travels with the move.
MoveReason = Literal["unstartable", "higher_projection"]


class LineupMove(BaseModel):
    """One starting slot whose occupant should change."""

    slot: Slot
    out_player: Player
    in_player: Player
    out_points: float
    in_points: float
    # `in_points - out_points`. Always > 0 for a `higher_projection` move; can be 0 for an
    # `unstartable` one, where the gain is avoiding a certain zero rather than adding points.
    delta: float
    reason: MoveReason
    # True when the OTHER projection source independently also starts `in_player` and
    # benches `out_player`. A confidence marker, never an input to the recommendation.
    consensus: bool


class LineupAdvice(BaseModel):
    """Payload of `GET /api/teams/{team_id}/lineup`."""

    team_id: str
    week: int
    source: ProjectionSource
    current_points: float
    optimal_points: float
    # `optimal_points - current_points`, 0.0 when the lineup is already optimal. Both
    # operands are scored by the SAME rules — including the zeroing of unstartable
    # players — so the number is a real comparison rather than an artifact.
    gain: float
    moves: list[LineupMove]

    # True when both sources independently pick the same set of starters. The strongest
    # signal this endpoint produces: two unrelated projections agreeing on a lineup is
    # worth more than either one's margin.
    sources_agree: bool
    # False when the second source had too little coverage to compare (a fresh database,
    # or the projections job has not run). `sources_agree` is then meaningless.
    comparison_available: bool
    # False when the CHOSEN source could evaluate nothing — an empty roster, or a
    # projections job that has never run. Without it a total absence of data is
    # indistinguishable from "your lineup is already optimal", which is a lie the user
    # would act on.
    advice_available: bool

    # Players the chosen source has no number for. They are never promoted off the bench
    # on the strength of a projection that doesn't exist, and if they are already starting
    # they are left alone — listed here so the silence is visible rather than implied.
    unevaluated: list[Player]
