"""`Player` — design.md D12."""

from typing import Literal

from pydantic import BaseModel

Position = Literal["QB", "RB", "WR", "TE", "K", "DST"]
InjuryStatus = Literal["ACTIVE", "Q", "D", "O", "IR", "PUP"]


class Player(BaseModel):
    id: str
    name: str
    position: Position
    nfl_team: str
    nfl_opponent: str | None
    nfl_game_id: str | None
    headshot_url: str
    bye_week: int | None
    injury_status: InjuryStatus | None
