"""An NFL player, normalized across platforms."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class Player(Base):
    """One row per platform player. `id` is `"{platform}:{platform_id}"`.

    `headshot_url` is not persisted here — it's derivable by convention
    (`/api/headshots/{platform}/{platform_id}.png`); the `Headshot` table stores
    the upstream `source_url` only where the platform doesn't have a deterministic
    CDN pattern (Yahoo).
    """

    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(255), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    nfl_team: Mapped[str] = mapped_column(String(8), nullable=False)
    nfl_opponent: Mapped[str | None] = mapped_column(String(8), nullable=True)
    nfl_game_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    bye_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injury_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # ESPN's athlete id, for players whose own platform id isn't one.
    #
    # An ESPN-sourced player already carries it inside `id` (`espn:p-4428209`), so this
    # column exists for YAHOO players: ESPN's public injury API is keyed by athlete id and
    # there is no other way to reach it from a Yahoo roster. Populated by the Sleeper
    # refresh, whose player dump carries `espn_id` and `yahoo_id` side by side.
    #
    # Stays null for D/ST rows on both platforms — a team defense is not an athlete and
    # has no injury report to fetch.
    espn_athlete_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
