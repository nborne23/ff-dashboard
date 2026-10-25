"""add player_highlights

Revision ID: f4c19d2e7a55
Revises: e8b2f4a6c013
Create Date: 2026-10-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4c19d2e7a55"
down_revision: Union[str, None] = "e8b2f4a6c013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_highlights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sleeper_id", sa.String(length=32), nullable=False),
        sa.Column("player_id", sa.String(length=255), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("stat_key", sa.String(length=32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("yards", sa.Integer(), nullable=True),
        sa.Column("stat_line", sa.String(length=128), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sleeper_id", "season", "week", "stat_key", "ordinal"),
    )


def downgrade() -> None:
    op.drop_table("player_highlights")
