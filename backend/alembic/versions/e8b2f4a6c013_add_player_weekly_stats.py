"""add player_weekly_stats, player_stat_seasons, players.sleeper_id

Revision ID: e8b2f4a6c013
Revises: d3a7c05b91e4
Create Date: 2026-10-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8b2f4a6c013"
down_revision: Union[str, None] = "d3a7c05b91e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("sleeper_id", sa.String(length=32), nullable=True))
    op.create_table(
        "player_weekly_stats",
        sa.Column("sleeper_id", sa.String(length=32), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("team", sa.String(length=8), nullable=True),
        sa.Column("opponent", sa.String(length=8), nullable=True),
        sa.Column("game_date", sa.String(length=10), nullable=True),
        sa.Column("pts_ppr", sa.Float(), nullable=True),
        sa.Column("pts_half_ppr", sa.Float(), nullable=True),
        sa.Column("pts_std", sa.Float(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        # Leading `sleeper_id` serves the only read: one player's whole history.
        sa.PrimaryKeyConstraint("sleeper_id", "season", "week"),
    )
    op.create_table(
        "player_stat_seasons",
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fetched_through_week", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("season"),
    )


def downgrade() -> None:
    op.drop_table("player_stat_seasons")
    op.drop_table("player_weekly_stats")
    op.drop_column("players", "sleeper_id")
