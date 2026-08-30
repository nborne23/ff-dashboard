"""Pydantic v2 response models matching design.md D12's TypeScript interfaces exactly.

These are the envelope contract's payload types — FastAPI response models for the read
API layer built in later tasks (3.9/3.10).
"""

from backend.gridiron.schemas.common import (
    Envelope,
    LiveState,
    Meta,
    Platform,
    PlatformStatus,
    Slot,
)
from backend.gridiron.schemas.connections import Connection, ConnectionError
from backend.gridiron.schemas.draft import (
    BoardData,
    BoardPlayerOut,
    ByeCollisionOut,
    CandidateOut,
    CurrentPickData,
    CurrentPickIn,
    DraftPickOut,
    DraftStateData,
    PoolData,
    RecommendationOut,
    RecommendationsData,
    RecordPickIn,
    RosterData,
    RosterSlotOut,
    SettingsConflictOut,
    TierAlarmOut,
    TurnPairOut,
    UndoResultData,
)
from backend.gridiron.schemas.events import (
    DataChangedEvent,
    HeartbeatEvent,
    LiveStateChangedEvent,
    SseEvent,
    TierChangeEvent,
)
from backend.gridiron.schemas.leagues import League, ScoringType
from backend.gridiron.schemas.live_nfl_games import LiveNflGame
from backend.gridiron.schemas.matchups import Matchup, MatchupSlot
from backend.gridiron.schemas.player_pool import (
    PlayerPoolEntry,
    PoolStatus,
    WaiverCandidate,
    WaiversData,
)
from backend.gridiron.schemas.players import InjuryStatus, Player, Position
from backend.gridiron.schemas.roster_slots import RosterSlot
from backend.gridiron.schemas.season_weeks import SeasonWeek
from backend.gridiron.schemas.teams import Rank, Record, Team

__all__ = [
    "BoardData",
    "BoardPlayerOut",
    "ByeCollisionOut",
    "CandidateOut",
    "Connection",
    "ConnectionError",
    "CurrentPickData",
    "CurrentPickIn",
    "DataChangedEvent",
    "DraftPickOut",
    "DraftStateData",
    "Envelope",
    "HeartbeatEvent",
    "InjuryStatus",
    "League",
    "LiveNflGame",
    "LiveState",
    "LiveStateChangedEvent",
    "Matchup",
    "MatchupSlot",
    "Meta",
    "Platform",
    "PlatformStatus",
    "Player",
    "PlayerPoolEntry",
    "PoolData",
    "PoolStatus",
    "Position",
    "Rank",
    "Record",
    "RecommendationOut",
    "RecommendationsData",
    "RecordPickIn",
    "RosterData",
    "RosterSlot",
    "RosterSlotOut",
    "ScoringType",
    "SeasonWeek",
    "SettingsConflictOut",
    "Slot",
    "SseEvent",
    "Team",
    "TierAlarmOut",
    "TierChangeEvent",
    "TurnPairOut",
    "UndoResultData",
    "WaiverCandidate",
    "WaiversData",
]
