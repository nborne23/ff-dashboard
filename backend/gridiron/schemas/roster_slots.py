"""`RosterSlot` — design.md D12."""

from typing import Literal

from pydantic import BaseModel

from backend.gridiron.schemas.common import Slot
from backend.gridiron.schemas.players import Player

GameState = Literal["pre", "in", "post", "bye"]


class RosterSlot(BaseModel):
    team_id: str
    week: int
    slot: Slot
    player: Player
    proj_points: float
    actual_points: float
    is_live: bool
    game_state: GameState | None
    status_text: str
    # An INDEPENDENT weekly projection (Rotowire, via Sleeper) for the same player, in
    # this league's scoring format. Deliberately alongside `proj_points` rather than
    # blended into it: the two disagreeing is the signal a start/sit decision turns on,
    # and one merged number would erase exactly that.
    #
    # None when the player didn't match the feed, when the projection job hasn't run, or
    # when the league scores `custom` — see `_resolve_points`.
    ext_proj_points: float | None = None
