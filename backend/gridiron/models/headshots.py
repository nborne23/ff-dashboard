"""Upstream headshot source URLs for platforms without a deterministic CDN pattern.

ESPN headshots are fetched from a deterministic URL
(`https://a.espncdn.com/i/headshots/nfl/players/full/{id}.png`) so no lookup is needed.
Yahoo has no such pattern — its source URL comes from the player payload during
discovery/roster sync and is stashed here so `services/headshots.py` can fetch it.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class Headshot(Base):
    """One row per `(platform, player_id)` — `player_id` is the platform's own id."""

    __tablename__ = "headshots"

    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    player_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
