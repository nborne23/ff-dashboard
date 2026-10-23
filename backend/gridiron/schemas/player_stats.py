"""`GET /api/players/{player_id}/stats` payload (add-player-stats)."""

from typing import Literal

from pydantic import BaseModel

PositionGroup = Literal["QB", "RB", "WR", "TE", "K", "DST"]
PointsFormat = Literal["ppr", "half_ppr", "standard"]


class StatColumn(BaseModel):
    key: str
    label: str
    # How a season row totals this column: a long field goal is a max, not a sum.
    agg: Literal["sum", "max"]


class GameLogRow(BaseModel):
    season: int
    week: int
    date: str | None
    team: str | None
    opponent: str | None
    fantasy_points: float | None
    stats: dict[str, float]


class SeasonSummary(BaseModel):
    season: int
    # The team he finished the season with — the last game logged.
    team: str | None
    games: int
    fantasy_points: float | None
    ppg: float | None
    stats: dict[str, float]


class BreakdownLine(BaseModel):
    label: str
    # The stat behind the points (`80` receiving yards). None for tier awards like
    # "7-13 points allowed", whose value is a flag rather than a count.
    stat_value: float | None
    points: float


class ThisWeek(BaseModel):
    season: int
    week: int
    # False while the week is in progress — the stat line can still move, and Sleeper's
    # copy of it can trail the platform's by several minutes.
    final: bool
    opponent: str | None
    is_live: bool
    status_text: str | None
    # The league platform's own numbers from the roster slot, when the player is on a
    # roster in the viewing league. These are the authority; everything else is detail.
    league_points: float | None
    league_proj: float | None
    stats: dict[str, float] | None
    stats_source: Literal["espn", "sleeper"] | None
    breakdown: list[BreakdownLine]
    # `league`: ESPN's own per-stat scoring for this league, exact. `estimated`: the stat
    # line priced with standard rules, with any gap to the league total shown as its own
    # line rather than hidden.
    breakdown_source: Literal["league", "estimated"] | None
    breakdown_total: float | None


class PlayerStatsData(BaseModel):
    player_id: str
    # None when the player couldn't be matched to Sleeper — no history to show.
    sleeper_id: str | None
    position_group: PositionGroup
    points_format: PointsFormat
    # True when the league's scoring is custom and the history is shown in PPR instead.
    points_format_fallback: bool
    columns: list[StatColumn]
    this_week: ThisWeek
    # Newest season first.
    seasons: list[SeasonSummary]
    # Newest season first, weeks ascending within a season.
    game_log: list[GameLogRow]
