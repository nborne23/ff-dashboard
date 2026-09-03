"""The most recent ESPN injury report for one player (add-player-health D1/D2).

One row per player, not per report: the panel shows "what is wrong with him now", and
ESPN's per-season `injuries` collection is ordered newest-first, so only the head is kept.
Rows are written exclusively by the `refresh_injuries` scheduler job — `GET /api/players/
{id}/injury` reads them and never fetches (design.md D7).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class PlayerInjury(Base):
    __tablename__ = "player_injuries"

    player_id: Mapped[str] = mapped_column(String(255), ForeignKey("players.id"), primary_key=True)

    # ESPN's own report id, kept so a refresh can tell "same report, re-fetched" from "a
    # new report was filed" without diffing prose.
    report_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ESPN's human-readable status ("Injured Reserve", "Questionable"). Deliberately NOT
    # the normalized `InjuryStatus` code — that already lives on `players.injury_status`
    # and comes from the fantasy API, which is the authority the badge renders from. This
    # is the detail feed's own wording, shown as prose in the panel.
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # `details.type` ("Knee - PCL"), `.location` ("Leg"), `.detail` ("Surgery"),
    # `.side` ("Right"), `.returnDate` ("2027-02-15", a plain date string upstream).
    injury_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(128), nullable=True)
    side: Mapped[str | None] = mapped_column(String(32), nullable=True)
    return_date: Mapped[str | None] = mapped_column(String(32), nullable=True)

    short_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    long_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When ESPN filed the report (naive UTC, matching the rest of the codebase).
    reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # When this app last successfully fetched it — distinct from `reported_at`, and what
    # the panel shows as "checked".
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
