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
