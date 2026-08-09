"""`LiveNflGame` — design.md D12."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

GameState = Literal["pre", "in", "post", "postponed"]


class LiveNflGame(BaseModel):
    nfl_game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    state: GameState
    clock: str | None
    period: int | None
    kickoff_at: datetime
