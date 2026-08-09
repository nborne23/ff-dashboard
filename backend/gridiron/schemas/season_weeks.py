"""`SeasonWeek` — design.md D12."""

from pydantic import BaseModel


class SeasonWeek(BaseModel):
    team_id: str
    week: int
    score: float
    opp_score: float
    opp_team_name: str
    is_win: bool
    is_current: bool
