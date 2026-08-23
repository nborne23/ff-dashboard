"""Draft Assistant board data: imported player board, tiers, heuristics, and live draft
tracking (picks + polling session state). See `backend/gridiron/draft_board/` for the
source data and `backend/gridiron/services/draft_board.py` for the import parsers.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class BoardPlayer(Base):
    """One row per drafted-board player (149 skill players + 12 DST rows = 161).

    `name` is the upsert conflict target for re-imports (verified unique in the source
    JSON). `espn_player_id` / `match_method` / `match_confidence` are populated by a later
    matching phase and are deliberately NOT touched by the board import beyond first
    insert, so re-running the import never clobbers a live ESPN match.
    """

    __tablename__ = "board_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    nfl_team: Mapped[str | None] = mapped_column(String(8), nullable=True)
    bye: Mapped[int | None] = mapped_column(Integer, nullable=True)

    adp: Mapped[float | None] = mapped_column(Float, nullable=True)
    adp_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adp_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adp_pick: Mapped[int | None] = mapped_column(Integer, nullable=True)

    overall_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    positional_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)

    risk: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rookie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    out_for_season: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unpriced_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    take_in_round: Mapped[str | None] = mapped_column(String(32), nullable=True)

    sleeper_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalyst: Mapped[str | None] = mapped_column(Text, nullable=True)
    format_fit: Mapped[str | None] = mapped_column(Text, nullable=True)

    flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    injury_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst_takes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[str | None] = mapped_column(Text, nullable=True)

    espn_player_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    match_method: Mapped[str] = mapped_column(String(16), nullable=False, default="unmatched")
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BoardTier(Base):
    """Deduped tier-label lookup, one row per (scope, position, tier). `position` is NULL
    for `scope="overall"`."""

    __tablename__ = "board_tiers"
    __table_args__ = (
        UniqueConstraint("scope", "position", "tier", name="uq_board_tiers_scope_position_tier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class BoardHeuristic(Base):
    """One row per strategy-rules entry: the 9 named heuristics, plus synthetic keys
    (`_positional_cliffs`, `_value_calc`, `_draft_slot_1_plan`) for the remaining
    top-level blocks in `strategy_rules.json`. `payload` is the full source object."""

    __tablename__ = "board_heuristics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)


class BoardIdOverride(Base):
    """Hand-maintained override mapping a board player's name to an ESPN player id,
    applied by the import in preference to any auto-matching result."""

    __tablename__ = "board_id_overrides"

    board_player_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    espn_player_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class DraftPick(Base):
    """One row per pick made in the live draft, manual or ESPN-observed."""

    __tablename__ = "draft_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    round: Mapped[int | None] = mapped_column(Integer, nullable=True)

    board_player_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("board_players.id"), nullable=True
    )
    espn_player_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(8), nullable=True)

    drafted_by_team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_my_pick: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class DraftSession(Base):
    """Polling-session state for a live draft watch (armed -> polling -> completed/disarmed
    /failed). One row is expected to be active at a time."""

    __tablename__ = "draft_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    league_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    armed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disarmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ceiling_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    current_overall_pick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    on_the_clock_team: Mapped[str | None] = mapped_column(String(64), nullable=True)

    consecutive_not_in_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
