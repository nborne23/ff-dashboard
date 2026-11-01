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


class GameLogColumn(StatColumn):
    # Interceptions, fumbles, points allowed: a big number is a bad game, so the
    # above/below-average shading flips.
    lower_is_better: bool = False


WeekState = Literal["final", "live", "upcoming", "bye", "dnp"]


class SeasonLogWeek(BaseModel):
    """One row of the season game log — every regular-season week, played or not."""

    week: int
    # `final`: played and over. `live`: his game is on (or the week is mid-flight and his
    # line may still move). `upcoming`: not yet kicked off. `bye`: his team is off.
    # `dnp`: his team played and he has no line (inactive, injured, a healthy scratch).
    state: WeekState
    opponent: str | None
    # None when there's no schedule to say (and on a bye).
    home: bool | None
    # The opponent's rank by fantasy points allowed to this position per game, 1st being
    # the most allowed. None before any week is complete, or with no schedule.
    opponent_rank: int | None
    # Rotowire, via Sleeper, in the same points format as `fantasy_points`.
    proj_points: float | None
    fantasy_points: float | None
    stats: dict[str, float] | None


class SeasonLog(BaseModel):
    """The current season, week by week, with the matchup context the Yahoo-style game
    log prints: opponent ranks, projections, the bye, and the season's headline numbers."""

    season: int
    columns: list[GameLogColumn]
    weeks: list[SeasonLogWeek]
    # Season total in `points_format`, every stored line including an in-progress week.
    fantasy_points: float | None
    # Where that total ranks among players at the position. None when unranked.
    position_rank: int | None
    bye_week: int | None
    # What the opponent ranks are out of (normally 32), and the last week they cover.
    ranked_teams: int
    ranks_through_week: int


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
    # The current season as the Game Log tab shows it. Optional so older callers and
    # fixtures that build this model by hand keep working.
    season_log: SeasonLog | None = None
    jersey_number: str | None = None
