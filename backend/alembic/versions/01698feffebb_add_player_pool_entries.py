"""add player_pool_entries — league-scoped availability and season projections

One row per (league, player), covering every player in the league rather than only
the unrostered ones. The composite primary key is the point: `appliedTotal` is a
scored value, so the same player's season projection differs between a PPR and a
half-PPR league, and availability differs too — free in one of the user's leagues,
rostered in another. Neither fact can live on `players`.

`season_proj_points` is nullable so "no projection published" stays distinguishable
from a genuine 0.0.

Revision ID: 01698feffebb
Revises: c49408aee758
Create Date: 2026-08-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "01698feffebb"
down_revision: Union[str, None] = "c49408aee758"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_pool_entries",
        sa.Column("league_id", sa.String(length=255), nullable=False),
        sa.Column("player_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("on_team_id", sa.String(length=255), nullable=True),
        sa.Column("percent_owned", sa.Float(), nullable=False),
        sa.Column("percent_started", sa.Float(), nullable=False),
        sa.Column("season_proj_points", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("league_id", "player_id"),
    )
    # Serves the ranked waiver read: league-scoped, ordered by projection.
    op.create_index(
        "ix_player_pool_league_proj",
        "player_pool_entries",
        ["league_id", "season_proj_points"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_pool_league_proj", table_name="player_pool_entries")
    op.drop_table("player_pool_entries")
