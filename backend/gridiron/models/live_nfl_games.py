"""Live NFL game state, polled from ESPN's public scoreboard (not the fantasy APIs)."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class LiveNflGame(Base):
    """One row per NFL game, upserted every `refresh_nfl_state` tick."""

    __tablename__ = "live_nfl_games"

    nfl_game_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    home_team: Mapped[str] = mapped_column(String(8), nullable=False)
    away_team: Mapped[str] = mapped_column(String(8), nullable=False)
    home_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    state: Mapped[str] = mapped_column(String(16), nullable=False)
    clock: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
