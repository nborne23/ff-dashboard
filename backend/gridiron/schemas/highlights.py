"""`GET /api/highlights` payload (add-play-highlights)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PlayerHighlightOut(BaseModel):
    id: int
    kind: Literal["touchdown", "big_play"]
    stat_key: str
    yards: int | None
    stat_line: str
    player_id: str
    player_name: str
    position: str
    nfl_team: str
    headshot_url: str
    created_at: datetime


class HighlightsData(BaseModel):
    highlights: list[PlayerHighlightOut]
    # The newest id on file, whether or not it's in `highlights` — the client's cursor.
    latest_id: int | None
