"""`League` — design.md D12."""

from typing import Literal

from pydantic import BaseModel

from backend.gridiron.schemas.common import Platform

ScoringType = Literal["standard", "half_ppr", "ppr", "custom"]


class League(BaseModel):
    id: str
    platform: Platform
    platform_id: str
    name: str
    season: int
    team_count: int
    scoring_type: ScoringType
    current_week: int
