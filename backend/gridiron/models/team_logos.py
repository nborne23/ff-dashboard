"""Cached fantasy-team logos — a sibling of `headshots.py`, not an extension of it.

The headshot cache bakes PNG into three places: the route's `.png` suffix, the
on-disk filename, and the silhouette fallback. Team logos are neither reliably PNG
nor reliably raster — ESPN serves its stock logos as `image/svg+xml` and uploaded
ones as `image/jpg` from an extensionless URL — so the format has to be a property
of the stored record instead of the path.

The other difference is auth: player headshots come from a public CDN, while an
uploaded team logo returns **401 without ESPN session cookies**. That is why the
bytes are cached and served locally at all — a browser cannot fetch them directly.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class TeamLogo(Base):
    """One row per `(platform, team_id)` — `team_id` is the platform's own id."""

    __tablename__ = "team_logos"

    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    # The upstream URL these cached bytes were fetched FROM. Compared against the
    # team's current `logo_source_url` to decide whether the cache is stale: an
    # uploaded logo's URL carries a generated id that changes when the image does,
    # so a mismatch detects a logo change exactly, with no TTL to guess at.
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Recorded from the response at fetch time and echoed back on serve. Not
    # inferable: the upload URL has no extension, and ESPN reports the nonstandard
    # `image/jpg` rather than `image/jpeg`.
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
