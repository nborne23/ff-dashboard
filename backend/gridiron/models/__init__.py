"""ORM models. Import this package to register all tables on `Base.metadata`."""

from backend.gridiron.models.app_settings import AppSetting
from backend.gridiron.models.base import Base
from backend.gridiron.models.connections import Connection
from backend.gridiron.models.draft import (
    BoardHeuristic,
    BoardIdOverride,
    BoardPlayer,
    BoardTier,
    DraftPick,
    DraftSession,
)
from backend.gridiron.models.headshots import Headshot
from backend.gridiron.models.http_cache import HttpCache
from backend.gridiron.models.leagues import League
from backend.gridiron.models.live_nfl_games import LiveNflGame
from backend.gridiron.models.matchups import Matchup, MatchupSlot
from backend.gridiron.models.player_pool import PlayerPoolEntry
from backend.gridiron.models.players import Player
from backend.gridiron.models.refresh_runs import RefreshRun
from backend.gridiron.models.roster_slots import RosterSlot
from backend.gridiron.models.season_weeks import SeasonWeek
from backend.gridiron.models.team_logos import TeamLogo
from backend.gridiron.models.teams import Team

__all__ = [
    "AppSetting",
    "Base",
    "BoardHeuristic",
    "BoardIdOverride",
    "BoardPlayer",
    "BoardTier",
    "Connection",
    "DraftPick",
    "DraftSession",
    "Headshot",
    "HttpCache",
    "League",
    "LiveNflGame",
    "Matchup",
    "MatchupSlot",
    "Player",
    "PlayerPoolEntry",
    "RefreshRun",
    "RosterSlot",
    "SeasonWeek",
    "Team",
    "TeamLogo",
]
