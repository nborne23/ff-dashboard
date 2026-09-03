"""Third-party point projections for one player, one scope (add-sleeper-projections).

Distinct from `roster_slots.proj_points`, which is whatever ESPN or Yahoo published for
that player in that league. This table holds an INDEPENDENT projection so the two can be
shown side by side — their disagreement is the signal, and a single blended number would
destroy it.

Scope encoding: `week` is the scoring period, and **`week = 0` means season-long totals**.
Sleeper serves those from the same endpoint with the week segment omitted, and they are
not interchangeable with a weekly number — `WaiverCandidate.delta_vs_worst_starter`
compares season totals (364.86) while a roster row shows a weekly one (21.57). A nullable
`week` would have expressed this too, but NULL is not comparable in a composite primary
key on SQLite, so the sentinel is explicit instead.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class PlayerProjection(Base):
    __tablename__ = "player_projections"

    player_id: Mapped[str] = mapped_column(String(255), ForeignKey("players.id"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 0 = season-long totals; 1..18 = that scoring period. See the module docstring.
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Who produced the number, not who served it: Sleeper relays Rotowire's projections
    # and stamps each row `company: "rotowire"`. Kept in the key so a second provider can
    # be added later without colliding.
    source: Mapped[str] = mapped_column(String(32), primary_key=True)

    # All three formats are stored rather than one resolved value: `League.scoring_type`
    # varies per league, and the same player is worth different points in each of the
    # user's leagues. Resolution happens on read.
    pts_ppr: Mapped[float | None] = mapped_column(Float, nullable=True)
    pts_half_ppr: Mapped[float | None] = mapped_column(Float, nullable=True)
    pts_std: Mapped[float | None] = mapped_column(Float, nullable=True)

    # The raw stat line as JSON. The reason a `custom`-scoring league gets `None` rather
    # than a silently-wrong PPR number: everything needed to compute it properly is here
    # for whenever that's built.
    stats_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which of the three matcher tiers produced this row. Persisted because the tiers are
    # not equally trustworthy and a wrong join is invisible once the number is on screen.
    match_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
