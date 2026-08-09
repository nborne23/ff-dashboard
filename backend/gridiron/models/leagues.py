"""A fantasy league on a platform (Yahoo or ESPN)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class League(Base):
    """One row per platform league. `id` is `"{platform}:{platform_id}"`."""

    __tablename__ = "leagues"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(255), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    team_count: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_type: Mapped[str] = mapped_column(String(32), nullable=False)
    current_week: Mapped[int] = mapped_column(Integer, nullable=False)

    # Settings' "ESPN Leagues" card (task 7.3): disabling a league excludes its teams
    # from GET /api/teams aggregation without dropping the discovered league/team rows.
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
