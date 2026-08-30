"""`Matchup` and `MatchupSlot` — design.md D12."""

from pydantic import BaseModel

from backend.gridiron.schemas.common import Slot
from backend.gridiron.schemas.players import Player
from backend.gridiron.schemas.roster_slots import GameState


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

    # Per-side live state, mirrored from the `roster_slots` rows for the same players
    # (fantasy-data-model spec, "Per-side live state on matchup slots"). Read-path
    # fields with no column of their own, so they default: the write paths
    # (`espn.mapper.map_matchup`) construct MatchupSlots before live state is resolved,
    # and `matchup_slots` persists only the points. Carrying per-side `game_state` is
    # what lets a consumer tell "0.0, hasn't played" (`pre`) from "0.0, shut out"
    # (`post`) — it does NOT drive panel-level live/settled state (design D4).
    home_state: GameState | None = None
    away_state: GameState | None = None
    home_is_live: bool = False
    away_is_live: bool = False
