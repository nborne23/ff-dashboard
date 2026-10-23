"""Historical weekly stat lines, one row per (Sleeper player, season, week) (add-player-stats).

Keyed by **Sleeper's** player id rather than our `players.id`: the same NFL player is two
rows in `players` when he is on an ESPN roster and a Yahoo one, and his 2019 game log is
the same fact for both. `players.sleeper_id` is the bridge; a team defense's Sleeper id is
its team abbreviation (`SF`).

Written only by the `refresh_player_stats` scheduler job — `GET /api/players/{id}/stats`
reads and never fetches (design.md D7).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class PlayerWeeklyStat(Base):
    __tablename__ = "player_weekly_stats"

    sleeper_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The team he played FOR that week, not his current one — a traded player's log
    # should say which uniform each line was earned in.
    team: Mapped[str | None] = mapped_column(String(8), nullable=True)
    opponent: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # `YYYY-MM-DD` as Sleeper sends it; a calendar date with no kickoff time behind it.
    game_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # All three formats, resolved on read against the viewing league's `scoring_type` —
    # the same reasoning as `player_projections`.
    pts_ppr: Mapped[float | None] = mapped_column(Float, nullable=True)
    pts_half_ppr: Mapped[float | None] = mapped_column(Float, nullable=True)
    pts_std: Mapped[float | None] = mapped_column(Float, nullable=True)

    # A TRIMMED stat line: only the keys `platforms/sleeper_stats.KEPT_STATS` names. The
    # raw rows carry ~60 keys (snap splits, IDP, positional ranks) that nothing renders,
    # and over ten seasons that is most of the table's size.
    stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlayerStatSeason(Base):
    """Ingest bookkeeping: whether a season's weeks have all been fetched.

    A finished season never changes, so once `complete` is set the job never asks for it
    again. Without this marker every run would either re-pull ten seasons (~180 calls) or
    have to infer completeness from row counts, which a bye-heavy week can't distinguish
    from a failed fetch.
    """

    __tablename__ = "player_stat_seasons"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Highest week fetched so far. For the current season the job re-fetches only the
    # tail (the live week and the one before it, for stat corrections) above this.
    fetched_through_week: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
