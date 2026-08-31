"""A fantasy team within a league."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class Team(Base):
    """One row per platform team. `id` is `"{platform}:{platform_id}"`."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    league_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("leagues.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(255), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manager_name: Mapped[str] = mapped_column(String(255), nullable=False)

    record_w: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_l: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_t: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    rank_current: Mapped[int] = mapped_column(Integer, nullable=False)
    rank_total: Mapped[int] = mapped_column(Integer, nullable=False)

    points_for: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    points_against: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    is_user_team: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Straight off the platform payload. Nullable rather than defaulted to "" so
    # "this team has no logo" stays distinguishable from "the URL is blank" — the
    # cache-invalidation comparison keys on this value and would otherwise treat
    # both as the same state.
    logo_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    logo_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
