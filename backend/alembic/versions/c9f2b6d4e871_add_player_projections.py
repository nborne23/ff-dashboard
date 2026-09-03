"""add player_projections

Revision ID: c9f2b6d4e871
Revises: b7d4a1c9e230
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9f2b6d4e871"
down_revision: Union[str, None] = "b7d4a1c9e230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_projections",
        sa.Column("player_id", sa.String(length=255), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        # 0 = season-long totals; 1..18 = that scoring period.
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("pts_ppr", sa.Float(), nullable=True),
        sa.Column("pts_half_ppr", sa.Float(), nullable=True),
        sa.Column("pts_std", sa.Float(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("match_tier", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("player_id", "season", "week", "source"),
    )
    # The read path always asks "this season, this scope, every player" — the leading
    # player_id of the PK can't serve that, so scope gets its own index.
    op.create_index(
        "ix_player_projections_scope", "player_projections", ["season", "week", "source"]
    )


def downgrade() -> None:
    op.drop_index("ix_player_projections_scope", table_name="player_projections")
    op.drop_table("player_projections")
