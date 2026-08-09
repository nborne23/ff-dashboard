"""Audit log of every scheduler job run, surfaced on the Settings screen."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class RefreshRun(Base):
    """One row per scheduler job execution (success or failure)."""

    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    job_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
