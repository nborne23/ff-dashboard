"""Raw upstream response cache, keyed by `(platform, endpoint, params_hash)`.

Read endpoints ALWAYS serve whatever is here (design.md D7) — they never fetch
upstream on a cache miss. Only the scheduler writes.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class HttpCache(Base):
    """Composite PK `(platform, endpoint, params_hash)` doubles as the uniqueness constraint."""

    __tablename__ = "http_cache"

    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(255), primary_key=True)
    params_hash: Mapped[str] = mapped_column(String(64), primary_key=True)

    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
