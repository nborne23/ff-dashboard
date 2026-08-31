"""`Team` — design.md D12, including the nested `record` and `rank` objects."""

from pydantic import BaseModel


class Record(BaseModel):
    w: int
    l: int  # noqa: E741 — field name mirrors design.md D12's `record.l` exactly.
    t: int


class Rank(BaseModel):
    current: int
    total: int


class Team(BaseModel):
    id: str
    league_id: str
    name: str
    manager_name: str
    record: Record
    rank: Rank
    points_for: float
    points_against: float
    is_user_team: bool
    current_score: float
    current_opp_score: float
    current_opponent_name: str
    is_live: bool
    spark_last_6: list[float]
    accent_color: str
    # A LOCAL url pointing at this app's own logo route, or None when the team has no
    # logo. Deliberately not the upstream URL: ESPN's uploaded-logo host returns 401 to
    # an unauthenticated client, so a browser given that URL renders a broken image.
    # Derived by convention like `headshot_url`, never persisted.
    logo_url: str | None = None
