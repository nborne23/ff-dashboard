"""`Player` — design.md D12."""

from typing import Literal

from pydantic import BaseModel

Position = Literal["QB", "RB", "WR", "TE", "K", "DST"]
# Normalized injury designations. `DTD` (day-to-day), `SUSP` (suspended) and `NFI`
# (non-football injury/illness) are real NFL designations both platforms emit and that
# the original six-value set silently dropped to `None`.
#
# `PROBABLE` is deliberately absent: the NFL removed it from the injury report in 2016,
# so a value for it would only ever match historical data we don't ingest.
InjuryStatus = Literal["ACTIVE", "Q", "D", "O", "IR", "PUP", "DTD", "SUSP", "NFI"]


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
