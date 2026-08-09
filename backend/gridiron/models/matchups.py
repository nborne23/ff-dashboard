"""Weekly head-to-head matchups and their per-slot player breakdowns."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class Matchup(Base):
    """One row per (league, week, home/away pair). `id` is `"{platform}:{platform_id}"`."""

    __tablename__ = "matchups"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    league_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("leagues.id"), nullable=False, index=True
    )
    week: Mapped[int] = mapped_column(Integer, nullable=False)

    home_team_id: Mapped[str] = mapped_column(String(255), ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[str] = mapped_column(String(255), ForeignKey("teams.id"), nullable=False)

    home_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    away_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    home_proj: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    away_proj: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MatchupSlot(Base):
    """One row per slot within a matchup, pairing the home/away player in that slot."""

    __tablename__ = "matchup_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    matchup_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("matchups.id"), nullable=False, index=True
    )
    slot: Mapped[str] = mapped_column(String(8), nullable=False)

    home_player_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("players.id"), nullable=False
    )
    away_player_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("players.id"), nullable=False
    )

    home_pts: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    away_pts: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
