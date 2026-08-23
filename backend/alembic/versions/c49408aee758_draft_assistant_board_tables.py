"""draft assistant: board + draft tracking tables

Backs the Draft Assistant board import (phase 1) and live draft tracking: the imported
player board (`board_players`, `board_tiers`, `board_heuristics`), a hand-maintained
ESPN-id override table (`board_id_overrides`), and live draft state (`draft_picks`,
`draft_sessions`).

Revision ID: c49408aee758
Revises: 42de0534b16d
Create Date: 2026-08-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c49408aee758"
down_revision: Union[str, None] = "42de0534b16d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "board_players",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=8), nullable=False),
        sa.Column("nfl_team", sa.String(length=8), nullable=True),
        sa.Column("bye", sa.Integer(), nullable=True),
        sa.Column("adp", sa.Float(), nullable=True),
        sa.Column("adp_rank", sa.Integer(), nullable=True),
        sa.Column("adp_round", sa.Integer(), nullable=True),
        sa.Column("adp_pick", sa.Integer(), nullable=True),
        sa.Column("overall_tier", sa.Integer(), nullable=True),
        sa.Column("positional_tier", sa.Integer(), nullable=True),
        sa.Column("risk", sa.String(length=32), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("rookie", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("out_for_season", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("unpriced_risk", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("take_in_round", sa.String(length=32), nullable=True),
        sa.Column("sleeper_category", sa.String(length=64), nullable=True),
        sa.Column("catalyst", sa.Text(), nullable=True),
        sa.Column("format_fit", sa.Text(), nullable=True),
        sa.Column("flags", sa.Text(), nullable=True),
        sa.Column("injury_tags", sa.Text(), nullable=True),
        sa.Column("analyst_takes", sa.Text(), nullable=True),
        sa.Column("sources", sa.Text(), nullable=True),
        sa.Column("espn_player_id", sa.Integer(), nullable=True),
        sa.Column("match_method", sa.String(length=16), nullable=False, server_default="unmatched"),
        sa.Column("match_confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")),
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
        sa.UniqueConstraint("name", name="uq_board_players_name"),
    )
    op.create_index("ix_board_players_normalized_name", "board_players", ["normalized_name"])
    op.create_index("ix_board_players_espn_player_id", "board_players", ["espn_player_id"])

    op.create_table(
        "board_tiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("position", sa.String(length=8), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.UniqueConstraint("scope", "position", "tier", name="uq_board_tiers_scope_position_tier"),
    )

    op.create_table(
        "board_heuristics",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
    )

    op.create_table(
        "board_id_overrides",
        sa.Column("board_player_name", sa.String(length=255), primary_key=True),
        sa.Column("espn_player_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )

    op.create_table(
        "draft_picks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("overall_pick", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=True),
        sa.Column(
            "board_player_id", sa.Integer(), sa.ForeignKey("board_players.id"), nullable=True
        ),
        sa.Column("espn_player_id", sa.Integer(), nullable=True),
        sa.Column("player_name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=8), nullable=True),
        sa.Column("drafted_by_team", sa.String(length=64), nullable=True),
        sa.Column("is_my_pick", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.UniqueConstraint("overall_pick", name="uq_draft_picks_overall_pick"),
    )

    op.create_table(
        "draft_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("league_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "poll_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("3")
        ),
        sa.Column("armed_at", sa.DateTime(), nullable=True),
        sa.Column("disarmed_at", sa.DateTime(), nullable=True),
        sa.Column("ceiling_at", sa.DateTime(), nullable=True),
        sa.Column("current_overall_pick", sa.Integer(), nullable=True),
        sa.Column("current_round", sa.Integer(), nullable=True),
        sa.Column("on_the_clock_team", sa.String(length=64), nullable=True),
        sa.Column(
            "consecutive_not_in_progress", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_poll_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
    )


def downgrade() -> None:
    op.drop_table("draft_sessions")
    op.drop_table("draft_picks")
    op.drop_table("board_id_overrides")
    op.drop_table("board_heuristics")
    op.drop_table("board_tiers")
    op.drop_index("ix_board_players_espn_player_id", table_name="board_players")
    op.drop_index("ix_board_players_normalized_name", table_name="board_players")
    op.drop_table("board_players")
