"""add player_injuries

Revision ID: b7d4a1c9e230
Revises: 380dfc2ab9bc
Create Date: 2026-09-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4a1c9e230"
down_revision: Union[str, None] = "380dfc2ab9bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_injuries",
        sa.Column("player_id", sa.String(length=255), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("injury_type", sa.String(length=128), nullable=True),
        sa.Column("location", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.String(length=128), nullable=True),
        sa.Column("side", sa.String(length=32), nullable=True),
        sa.Column("return_date", sa.String(length=32), nullable=True),
        sa.Column("short_comment", sa.Text(), nullable=True),
        sa.Column("long_comment", sa.Text(), nullable=True),
        sa.Column("reported_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("player_id"),
    )


def downgrade() -> None:
    op.drop_table("player_injuries")
