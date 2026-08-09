"""Shared SQLAlchemy declarative base for all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base. Alembic's `env.py` targets `Base.metadata` for autogenerate."""
