"""Per-team, per-week season history row (used for the Season screen)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class SeasonWeek(Base):
    """One row per (team, week). Surrogate integer PK."""

    __tablename__ = "season_weeks"
    __table_args__ = (Index("ix_season_weeks_team_week", "team_id", "week", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    team_id: Mapped[str] = mapped_column(String(255), ForeignKey("teams.id"), nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)

    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opp_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    opp_team_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    is_win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
