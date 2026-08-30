"""A player's availability and season projection *within one league*."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class PlayerPoolEntry(Base):
    """One row per (league, player), covering every player in the league — rostered
    or not.

    Keyed per league rather than per player because both facts it carries are
    league-scoped (add-player-pool design D1):

    - `status` obviously so: a player free in one of the user's leagues may be
      rostered in another.
    - `season_proj_points` less obviously, but measurably: `appliedTotal` is a
      *scored* value, so a PPR league and a half-PPR league report different season
      totals for the same pass-catcher (Joshua Palmer 111.2 vs 90.37), while
      quarterbacks match exactly. A column on `Player` would hold whichever league
      synced last, and be wrong for the other four.

    `ONTEAM` rows are ingested deliberately (design D7): the season projection is the
    only scale on which a waiver candidate and an incumbent starter can be compared,
    and `RosterSlot.proj_points` is a *weekly* number roughly an order of magnitude
    smaller. They are stored for comparison, never listed as claimable.
    """

    __tablename__ = "player_pool_entries"
    __table_args__ = (
        # Serves the ranked read in `get_waivers` — league-scoped, ordered by projection.
        Index("ix_player_pool_league_proj", "league_id", "season_proj_points"),
    )

    league_id: Mapped[str] = mapped_column(String(255), ForeignKey("leagues.id"), primary_key=True)
    player_id: Mapped[str] = mapped_column(String(255), ForeignKey("players.id"), primary_key=True)

    # "FREEAGENT" | "WAIVERS" | "ONTEAM"
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # ESPN's numeric team id as text, or None when the player is unrostered.
    on_team_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    percent_owned: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    percent_started: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Nullable on purpose (design D2): "no projection published" and "projected to
    # score nothing" are different states, and 0.0 is a genuine observed value.
    season_proj_points: Mapped[float | None] = mapped_column(Float, nullable=True)

    # JSON-encoded list of ESPN's UNNUMBERED slot names ("RB", "RB/WR", "FLEX", ...),
    # following the `BoardPlayer.flags` convention for list columns.
    #
    # Persisted rather than derived from `position` at read time because eligibility
    # is league-specific: a superflex league admits a QB to `OP`, a TE-premium one
    # admits a TE to `REC_FLEX`. It is what `get_waivers` uses to choose which of the
    # user's starters a candidate is actually competing with.
    eligible_slots: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
