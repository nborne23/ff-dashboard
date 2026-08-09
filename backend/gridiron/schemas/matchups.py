"""`Matchup` and `MatchupSlot` — design.md D12."""

from pydantic import BaseModel

from backend.gridiron.schemas.common import Slot
from backend.gridiron.schemas.players import Player


class Matchup(BaseModel):
    id: str
    league_id: str
    week: int
    home_team_id: str
    away_team_id: str
    home_score: float
    away_score: float
    home_proj: float
    away_proj: float
    is_complete: bool


class MatchupSlot(BaseModel):
    matchup_id: str
    slot: Slot
    home_player: Player
    away_player: Player
    home_pts: float
    away_pts: float
