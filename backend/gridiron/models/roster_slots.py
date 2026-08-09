"""A player's slot assignment on a team's roster for a given week."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class RosterSlot(Base):
    """One row per (team, week, player). Surrogate integer PK; `player_id` is a FK.

    Uniqueness is per player, not per slot label: the internal `Slot` vocabulary has a
    single `BN` (and `IR`) label and real rosters carry several bench players per week,
    so `(team_id, week, slot)` can legitimately repeat.
    """

    __tablename__ = "roster_slots"
    __table_args__ = (
        UniqueConstraint("team_id", "week", "player_id", name="uq_roster_slots_team_week_player"),
        Index("ix_roster_slots_team_week", "team_id", "week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    team_id: Mapped[str] = mapped_column(String(255), ForeignKey("teams.id"), nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[str] = mapped_column(String(8), nullable=False)

    player_id: Mapped[str] = mapped_column(String(255), ForeignKey("players.id"), nullable=False)

    proj_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    game_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status_text: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
