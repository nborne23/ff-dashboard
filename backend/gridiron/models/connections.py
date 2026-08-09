"""Single-row-per-platform table storing encrypted OAuth/cookie credentials."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class Connection(Base):
    """One row per platform ("yahoo" | "espn"). Token/cookie columns are Fernet-encrypted."""

    __tablename__ = "connections"

    platform: Mapped[str] = mapped_column(String(16), primary_key=True)

    # Yahoo OAuth
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ESPN cookies
    swid_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    espn_s2_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
