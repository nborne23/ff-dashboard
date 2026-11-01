"""`GET /api/scores` and `GET /api/scores/games/{game_id}` payloads (add-nfl-scores)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from backend.gridiron.schemas.live_nfl_games import GameState
from backend.gridiron.schemas.player_stats import PointsFormat
from backend.gridiron.schemas.players import Player

FantasyPosition = Literal["QB", "RB", "WR", "TE", "K", "DEF"]


class ScoreTeam(BaseModel):
    abbr: str
    name: str
    location: str
    record: str | None
    # None before kickoff — a 0 there would read as a score.
    score: int | None
    logo: str | None
    # ESPN's hex, no leading `#`.
    color: str | None
    linescores: list[int]
    winner: bool


class GameLeader(BaseModel):
    category: Literal["passing", "rushing", "receiving"]
    name: str
    short_name: str
    position: str | None
    team: str
    headshot_url: str | None
    stat_line: str


class ScoreGame(BaseModel):
    game_id: str
    kickoff_at: datetime
    state: GameState
    # "Final", "Final/OT", "Q3 4:12", "Half", "End Q1", "Postponed" — or ESPN's own
    # kickoff text before the game (the client formats its local time instead).
    status_text: str
    period: int | None
    clock: str | None
    broadcast: str | None
    possession: str | None
    down_distance: str | None
    away: ScoreTeam
    home: ScoreTeam
    top_performer: GameLeader | None


class ScoresWeek(BaseModel):
    season: int | None
    week: int
    current_week: int | None
    weeks: list[int]
    byes: list[str]
    # When the week was last fetched; None when it never has been.
    fetched_at: datetime | None
    games: list[ScoreGame]


class StatToken(BaseModel):
    """One piece of a Sleeper-style stat line: `24/31` + `CMP`."""

    value: str
    label: str


class FantasyPlayer(BaseModel):
    sleeper_id: str
    name: str
    short_name: str
    position: FantasyPosition
    team: str
    points: float | None
    projection: float | None
    # "league": the selected league's own number (the player is rostered there this
    # week). "estimated": Sleeper's line in the league's format — standard rules, so a
    # league with custom bonuses can differ.
    source: Literal["league", "estimated"]
    stats: dict[str, float]
    stat_line: list[StatToken]
    # Our `players` row when there is one — what opens the stats card. Most of a depth
    # chart has none.
    player: Player | None
    fantasy_team: str | None
    is_mine: bool


class FantasyGroup(BaseModel):
    position: FantasyPosition
    away: list[FantasyPlayer]
    home: list[FantasyPlayer]


class ScoringLeague(BaseModel):
    league_id: str
    name: str
    platform: str
    scoring_type: str
    # The user's team in it — the stats card's league context.
    team_id: str | None


class GameDetail(BaseModel):
    season: int
    week: int
    game: ScoreGame
    leagues: list[ScoringLeague]
    league_id: str | None
    points_format: PointsFormat
    # True when the league scores `custom` and the estimate fell back to PPR.
    points_format_fallback: bool
    groups: list[FantasyGroup]
    # Newest Sleeper stat line behind the points; None before anyone has one.
    stats_as_of: datetime | None
