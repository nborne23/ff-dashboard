"""Small key/value store for app-wide settings (task 7.4) — currently just the
live-refresh polling tier the Settings screen's PreferencesCard controls.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.gridiron.models.base import Base


class AppSetting(Base):
    """One row per setting. `key` is the primary key; `value` is stored as text."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
