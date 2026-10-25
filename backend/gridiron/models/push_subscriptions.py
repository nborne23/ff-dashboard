"""Web Push subscriptions, one per browser that turned notifications on (add-push-notifications).

Written by `POST /api/push/subscriptions` (an upsert by `endpoint`: the app re-posts its
subscription on every open, which repairs a reset database without a second prompt) and
read by `services/push.py` to fan a highlight out. A push service answering 404/410 means
the browser dropped the subscription, and the row is deleted then.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Push-service URLs run long (Apple's carry a ~150-char token); 1024 leaves room.
    endpoint: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    # The browser's keys for payload encryption (RFC 8291), base64url as it sends them.
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
